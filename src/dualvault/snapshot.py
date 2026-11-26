"""Create and inspect snapshot archives (ZIP + embedded manifest)."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from dualvault import __version__

log = logging.getLogger(__name__)

MANIFEST = ".dualvault-manifest.json"
PREFIX = "dualvault"
NAME_RE = re.compile(
    r"^dualvault-(?P<source>[A-Za-z0-9][A-Za-z0-9_-]*)-(?P<ts>\d{8}T\d{6}Z)\.zip(?P<enc>\.dvenc)?$"
)
TS_FORMAT = "%Y%m%dT%H%M%SZ"
BUF = 1024 * 1024


@dataclass(frozen=True)
class SnapshotName:
    filename: str
    source: str
    created: datetime
    encrypted: bool

    @classmethod
    def parse(cls, filename: str) -> SnapshotName | None:
        m = NAME_RE.match(filename)
        if not m:
            return None
        created = datetime.strptime(m["ts"], TS_FORMAT).replace(tzinfo=timezone.utc)
        return cls(filename, m["source"], created, bool(m["enc"]))

    @classmethod
    def new(cls, source: str, encrypted: bool, now: datetime | None = None) -> SnapshotName:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
        name = f"{PREFIX}-{source}-{now.strftime(TS_FORMAT)}.zip" + (".dvenc" if encrypted else "")
        return cls(name, source, now, encrypted)


@dataclass
class SnapshotStats:
    files: int = 0
    bytes: int = 0
    skipped: int = 0


def _excluded(rel: PurePosixPath, patterns: list[str]) -> bool:
    text = rel.as_posix()
    for pat in patterns:
        if fnmatch.fnmatch(text, pat) or any(fnmatch.fnmatch(part, pat) for part in rel.parts):
            return True
    return False


def iter_files(root: Path, exclude: list[str], follow_symlinks: bool = False):
    """Yield ``(absolute_path, relative_posix_path)`` for files under ``root``."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        base = Path(dirpath)
        rel_base = PurePosixPath(base.relative_to(root).as_posix())
        dirnames[:] = sorted(
            d
            for d in dirnames
            if not _excluded(rel_base / d, exclude)
            and (follow_symlinks or not (base / d).is_symlink())
        )
        for fname in sorted(filenames):
            full = base / fname
            rel = rel_base / fname
            if _excluded(rel, exclude):
                continue
            if full.is_symlink() and not follow_symlinks:
                log.info("Skipping symlink %s", full)
                continue
            yield full, rel


def create_archive(
    source_dir: Path,
    archive_path: Path,
    source_name: str,
    exclude: list[str] | None = None,
    compression_level: int = 6,
    follow_symlinks: bool = False,
) -> SnapshotStats:
    """Write a ZIP of ``source_dir`` with a SHA-256 manifest. Unreadable files are skipped."""
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source folder not found: {source_dir}")
    stats = SnapshotStats()
    manifest_files: dict[str, dict] = {}
    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=compression_level
    ) as zf:
        for full, rel in iter_files(source_dir, exclude or [], follow_symlinks):
            name = rel.as_posix()
            if name == MANIFEST:
                log.warning("Skipping %s: reserved file name", full)
                stats.skipped += 1
                continue
            try:
                info = zipfile.ZipInfo.from_file(full, arcname=name, strict_timestamps=False)
                info.compress_type = zipfile.ZIP_DEFLATED
                digest = hashlib.sha256()
                size = 0
                with full.open("rb") as fin, zf.open(info, "w", force_zip64=True) as fout:
                    while block := fin.read(BUF):
                        digest.update(block)
                        fout.write(block)
                        size += len(block)
            except (OSError, ValueError) as exc:
                log.warning("Skipping unreadable file %s: %s", full, exc)
                stats.skipped += 1
                continue
            manifest_files[name] = {"size": size, "sha256": digest.hexdigest()}
            stats.files += 1
            stats.bytes += size
        manifest = {
            "format": 1,
            "tool": f"dualvault {__version__}",
            "source": source_name,
            "created": datetime.now(timezone.utc).isoformat(),
            "files": manifest_files,
        }
        zf.writestr(MANIFEST, json.dumps(manifest, indent=1, sort_keys=True))
    return stats


def read_manifest(zf: zipfile.ZipFile) -> dict:
    try:
        return json.loads(zf.read(MANIFEST))
    except KeyError:
        raise ValueError("Archive has no DualVault manifest") from None


def verify_archive(archive_path: Path) -> list[str]:
    """Return a list of problems (empty list means the archive is intact)."""
    problems: list[str] = []
    with zipfile.ZipFile(archive_path) as zf:
        manifest = read_manifest(zf)
        names = {n for n in zf.namelist() if n != MANIFEST}
        expected = manifest.get("files", {})
        for name in sorted(set(expected) - names):
            problems.append(f"missing: {name}")
        for name in sorted(names - set(expected)):
            problems.append(f"unexpected: {name}")
        for name in sorted(names & set(expected)):
            digest = hashlib.sha256()
            with zf.open(name) as fh:
                while block := fh.read(BUF):
                    digest.update(block)
            if digest.hexdigest() != expected[name]["sha256"]:
                problems.append(f"checksum mismatch: {name}")
    return problems


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(BUF):
            digest.update(block)
    return digest.hexdigest()
