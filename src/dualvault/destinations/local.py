"""Local folder destination: external drives, NAS shares, synced cloud folders."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from dualvault.destinations.base import BaseDestination, DestinationUnavailable
from dualvault.snapshot import sha256_file


def _safe_component(value: str) -> str:
    if not value or value in {".", ".."} or any(c in value for c in "/\\:") or "\0" in value:
        raise ValueError(f"Unsafe path component: {value!r}")
    return value


class LocalDestination(BaseDestination):
    def __init__(self, name: str, path: str) -> None:
        super().__init__(name)
        self.root = Path(path).expanduser()

    def describe(self) -> str:
        return f"{self.name} ({self.root})"

    def check(self) -> None:
        anchor = Path(self.root.anchor) if self.root.anchor else None
        if anchor and not anchor.exists():
            raise DestinationUnavailable(f"Drive {anchor} is not connected")
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DestinationUnavailable(f"Cannot use {self.root}: {exc}") from exc
        if not os.access(self.root, os.W_OK):
            raise DestinationUnavailable(f"{self.root} is not writable")

    def _path(self, folder: str, filename: str | None = None) -> Path:
        p = self.root / _safe_component(folder)
        return p / _safe_component(filename) if filename else p

    def put(self, local_file: Path, folder: str, filename: str) -> None:
        target = self._path(folder, filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f"{target} already exists")
        needed = local_file.stat().st_size
        free = shutil.disk_usage(target.parent).free
        if free < needed:
            raise OSError(f"Not enough free space on {self.root}: need {needed}, have {free}")
        partial = target.with_name(target.name + ".partial")
        try:
            shutil.copyfile(local_file, partial)
            if sha256_file(partial) != sha256_file(local_file):
                raise OSError(f"Checksum mismatch after copying to {partial}")
            os.replace(partial, target)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise

    def list(self, folder: str) -> list[str]:
        p = self._path(folder)
        if not p.is_dir():
            return []
        return sorted(f.name for f in p.iterdir() if f.is_file())

    def get(self, folder: str, filename: str, local_file: Path) -> None:
        shutil.copyfile(self._path(folder, filename), local_file)

    def delete(self, folder: str, filename: str) -> None:
        self._path(folder, filename).unlink()
