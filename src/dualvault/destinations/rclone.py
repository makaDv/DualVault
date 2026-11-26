"""Cloud destination through the user's own rclone installation.

DualVault never handles cloud credentials: they stay in the user's
``rclone.conf`` (set up with ``rclone config``). Commands are always run
with an argument list, never through a shell.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from dualvault.destinations.base import BaseDestination, DestinationUnavailable
from dualvault.destinations.local import _safe_component

log = logging.getLogger(__name__)
TIMEOUT = 6 * 60 * 60


class RcloneDestination(BaseDestination):
    def __init__(self, name: str, remote: str, binary: str = "rclone") -> None:
        super().__init__(name)
        if remote.startswith("-"):
            raise ValueError("rclone remote must not start with '-'")
        self.remote = remote.rstrip("/")
        self.binary = binary

    def describe(self) -> str:
        return f"{self.name} ({self.remote})"

    def _remote_path(self, folder: str, filename: str | None = None) -> str:
        path = f"{self.remote}/{_safe_component(folder)}"
        return f"{path}/{_safe_component(filename)}" if filename else path

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        exe = shutil.which(self.binary)
        if not exe:
            raise DestinationUnavailable(
                f"rclone not found ('{self.binary}'). Install it from https://rclone.org"
            )
        cmd = [exe, *args]
        log.debug("Running %s", cmd)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, check=False)
        except subprocess.TimeoutExpired as exc:
            raise OSError(f"rclone timed out: {' '.join(args[:1])}") from exc
        if check and proc.returncode != 0:
            raise OSError(f"rclone {args[0]} failed ({proc.returncode}): {proc.stderr.strip()}")
        return proc

    def check(self) -> None:
        remote_name = self.remote.split(":", 1)[0] + ":"
        proc = self._run("listremotes", check=False)
        if proc.returncode != 0:
            raise DestinationUnavailable(f"rclone error: {proc.stderr.strip()}")
        if remote_name not in proc.stdout.split():
            raise DestinationUnavailable(
                f"rclone remote '{remote_name}' is not configured (run 'rclone config')"
            )

    def put(self, local_file: Path, folder: str, filename: str) -> None:
        target = self._remote_path(folder, filename)
        # --checksum verifies the upload against the source hash where the backend supports it.
        self._run("copyto", "--checksum", "--", str(local_file), target)
        proc = self._run(
            "check",
            "--one-way",
            "--include",
            "/" + local_file.name,
            "--",
            str(local_file.parent),
            self._remote_path(folder),
            check=False,
        )
        if proc.returncode != 0:
            log.warning("rclone could not verify %s: %s", target, proc.stderr.strip())

    def list(self, folder: str) -> list[str]:
        proc = self._run("lsf", "--files-only", "--", self._remote_path(folder), check=False)
        if proc.returncode != 0:
            if "not found" in proc.stderr.lower():
                return []
            raise OSError(f"rclone lsf failed: {proc.stderr.strip()}")
        return sorted(line.strip() for line in proc.stdout.splitlines() if line.strip())

    def get(self, folder: str, filename: str, local_file: Path) -> None:
        self._run("copyto", "--", self._remote_path(folder, filename), str(local_file))

    def delete(self, folder: str, filename: str) -> None:
        self._run("deletefile", "--", self._remote_path(folder, filename))
