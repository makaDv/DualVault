"""High-level operations: backup, list, prune, verify, restore."""

from __future__ import annotations

import logging
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dualvault import crypto, destinations, paths, rotation
from dualvault.config import Config
from dualvault.destinations import BaseDestination, DestinationUnavailable
from dualvault.restore import extract_archive
from dualvault.snapshot import SnapshotName, create_archive, verify_archive

log = logging.getLogger(__name__)
STALE_LOCK_SECONDS = 24 * 60 * 60


class LockedError(RuntimeError):
    """Another DualVault run is in progress."""


@contextmanager
def run_lock(lock_dir: Path | None = None):
    lock_dir = lock_dir or paths.state_dir()
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock = lock_dir / "dualvault.lock"
    if lock.exists() and time.time() - lock.stat().st_mtime > STALE_LOCK_SECONDS:
        log.warning("Removing stale lock file %s", lock)
        lock.unlink(missing_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise LockedError(f"Another backup is running (lock file: {lock})") from None
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


@dataclass
class RunReport:
    created: list[str] = field(default_factory=list)
    uploaded: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def exit_code(self) -> int:
        if self.errors:
            return 1
        return 2 if self.skipped else 0


def _select(items, names: list[str] | None, getter):
    if not names:
        return list(items)
    return [getter(n) for n in names]


def list_snapshots(dest: BaseDestination, source: str) -> list[SnapshotName]:
    found = []
    for fname in dest.list(source):
        snap = SnapshotName.parse(fname)
        if snap and snap.source == source:
            found.append(snap)
    return sorted(found, key=lambda s: s.created, reverse=True)


def prune(config: Config, dest: BaseDestination, source: str, dry_run: bool = False) -> list[str]:
    snaps = list_snapshots(dest, source)
    _keep, delete = rotation.split(snaps, lambda s: s.created, config.retention)
    removed = []
    for snap in delete:
        if dry_run:
            log.info("[dry-run] would delete %s from %s", snap.filename, dest.name)
        else:
            dest.delete(source, snap.filename)
            log.info("Deleted old snapshot %s from %s", snap.filename, dest.name)
        removed.append(snap.filename)
    return removed


def run_backup(
    config: Config,
    password: str | None = None,
    source_names: list[str] | None = None,
    dest_names: list[str] | None = None,
    now: datetime | None = None,
    do_prune: bool = True,
) -> RunReport:
    report = RunReport()
    if config.settings.encrypt and not password:
        raise ValueError("Encryption is enabled but no password was provided")
    sources = _select(config.sources, source_names, config.source)
    dests_cfg = _select(config.destinations, dest_names, config.destination)
    if not sources:
        raise ValueError("No sources configured (use 'dualvault add-source')")
    if not dests_cfg:
        raise ValueError("No destinations configured (use 'dualvault add-dest')")

    available: list[BaseDestination] = []
    for dcfg in dests_cfg:
        dest = destinations.build(dcfg, config.settings)
        try:
            dest.check()
            available.append(dest)
        except DestinationUnavailable as exc:
            log.warning("Destination %s skipped: %s", dest.describe(), exc)
            report.skipped.append(f"{dest.name}: {exc}")
    if not available:
        report.errors.append("No destination is available")
        log.error("No destination is available; nothing was backed up")
        return report

    with run_lock(), tempfile.TemporaryDirectory(prefix="dualvault-") as tmp:
        staging = Path(tmp)
        for src in sources:
            encrypted = config.settings.encrypt
            snap = SnapshotName.new(src.name, encrypted, now)
            plain = staging / (snap.filename.removesuffix(crypto.SUFFIX) + ".tmp")
            final = staging / snap.filename
            log.info("Backing up %s (%s)", src.name, src.path)
            try:
                stats = create_archive(
                    Path(src.path).expanduser(),
                    plain,
                    src.name,
                    src.exclude,
                    config.settings.compression_level,
                    config.settings.follow_symlinks,
                )
                if encrypted:
                    crypto.encrypt_file(plain, final, password or "")
                    plain.unlink()
                else:
                    os.replace(plain, final)
            except Exception as exc:
                log.error("Could not create snapshot of %s: %s", src.name, exc)
                report.errors.append(f"{src.name}: {exc}")
                continue
            log.info(
                "Created %s: %d files, %.1f MB read, %d skipped, archive %.1f MB",
                snap.filename,
                stats.files,
                stats.bytes / 1e6,
                stats.skipped,
                final.stat().st_size / 1e6,
            )
            report.created.append(snap.filename)
            if stats.skipped:
                report.skipped.append(f"{src.name}: {stats.skipped} unreadable file(s)")
            for dest in available:
                try:
                    dest.put(final, src.name, snap.filename)
                    log.info("Stored %s on %s", snap.filename, dest.describe())
                    report.uploaded.append(f"{dest.name}/{src.name}/{snap.filename}")
                except Exception as exc:
                    log.error("Upload of %s to %s failed: %s", snap.filename, dest.name, exc)
                    report.errors.append(f"{dest.name}/{src.name}: {exc}")
                    continue
                if do_prune:
                    try:
                        report.deleted += prune(config, dest, src.name)
                    except Exception as exc:
                        log.error("Pruning %s on %s failed: %s", src.name, dest.name, exc)
                        report.errors.append(f"prune {dest.name}/{src.name}: {exc}")
            final.unlink(missing_ok=True)
    log.info(
        "Run finished: %d snapshot(s), %d upload(s), %d deleted, %d warning(s), %d error(s)",
        len(report.created),
        len(report.uploaded),
        len(report.deleted),
        len(report.skipped),
        len(report.errors),
    )
    return report


def _resolve_snapshot(dest: BaseDestination, source: str, snapshot: str) -> SnapshotName:
    snaps = list_snapshots(dest, source)
    if not snaps:
        raise FileNotFoundError(f"No snapshots of {source!r} on {dest.name}")
    if snapshot in ("", "latest"):
        return snaps[0]
    for s in snaps:
        if s.filename == snapshot:
            return s
    raise FileNotFoundError(f"Snapshot {snapshot!r} not found on {dest.name}")


@contextmanager
def fetch_archive(dest: BaseDestination, source: str, snapshot: str, password: str | None):
    """Download (and decrypt) a snapshot into a temp folder; yields the plain ZIP path."""
    snap = _resolve_snapshot(dest, source, snapshot)
    with tempfile.TemporaryDirectory(prefix="dualvault-") as tmp:
        downloaded = Path(tmp) / snap.filename
        dest.get(source, snap.filename, downloaded)
        if snap.encrypted:
            if not password:
                raise ValueError("This snapshot is encrypted: a password is required")
            plain = Path(tmp) / "snapshot.zip"
            crypto.decrypt_file(downloaded, plain, password)
            downloaded.unlink()
            yield snap, plain
        else:
            yield snap, downloaded


def verify(dest: BaseDestination, source: str, snapshot: str, password: str | None) -> list[str]:
    with fetch_archive(dest, source, snapshot, password) as (snap, archive):
        problems = verify_archive(archive)
        log.info("Verified %s: %s", snap.filename, problems or "OK")
        return problems


def restore(
    dest: BaseDestination,
    source: str,
    snapshot: str,
    target: Path,
    password: str | None,
    overwrite: bool = False,
) -> int:
    with fetch_archive(dest, source, snapshot, password) as (snap, archive):
        problems = verify_archive(archive)
        if problems:
            raise ValueError(f"Snapshot {snap.filename} is damaged: {problems[:5]}")
        count = extract_archive(archive, target, overwrite=overwrite)
        log.info("Restored %d files from %s to %s", count, snap.filename, target)
        return count
