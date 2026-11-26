"""Safe extraction of snapshot archives."""

from __future__ import annotations

import logging
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from dualvault.snapshot import MANIFEST, read_manifest

log = logging.getLogger(__name__)


class UnsafeArchiveError(Exception):
    """The archive contains a path that would escape the target folder."""


def _check_member(name: str, target_root: Path) -> Path:
    if "\0" in name:
        raise UnsafeArchiveError(f"Invalid entry name {name!r}")
    posix = PurePosixPath(name)
    win = PureWindowsPath(name)
    if posix.is_absolute() or win.is_absolute() or win.drive or name.startswith(("/", "\\")):
        raise UnsafeArchiveError(f"Absolute path in archive: {name!r}")
    if ".." in posix.parts or ".." in win.parts:
        raise UnsafeArchiveError(f"Path traversal in archive: {name!r}")
    dest = (target_root / name).resolve()
    if dest != target_root and target_root not in dest.parents:
        raise UnsafeArchiveError(f"Entry escapes target folder: {name!r}")
    return dest


def extract_archive(archive_path: Path, target: Path, *, overwrite: bool = False) -> int:
    """Extract a snapshot into ``target``. Returns the number of files written."""
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    if not overwrite and any(root.iterdir()):
        raise FileExistsError(f"{root} is not empty (use --force to restore into it anyway)")
    count = 0
    with zipfile.ZipFile(archive_path) as zf:
        read_manifest(zf)  # make sure this is a DualVault archive
        members = [m for m in zf.infolist() if m.filename != MANIFEST]
        # Validate everything before writing anything.
        plan = [(m, _check_member(m.filename, root)) for m in members]
        for member, dest in plan:
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                log.warning("Skipping symlink entry %s", member.filename)
                continue
            if member.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out, 1024 * 1024)
            count += 1
    return count
