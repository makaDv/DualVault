"""Destination interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class DestinationUnavailable(RuntimeError):
    """The destination cannot be reached right now (drive unplugged, rclone missing...)."""


class BaseDestination(ABC):
    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def check(self) -> None:
        """Raise DestinationUnavailable if the destination cannot be used."""

    @abstractmethod
    def put(self, local_file: Path, folder: str, filename: str) -> None:
        """Upload ``local_file`` to ``<folder>/<filename>`` and verify it."""

    @abstractmethod
    def list(self, folder: str) -> list[str]:
        """Return filenames stored in ``folder`` (empty list if it does not exist)."""

    @abstractmethod
    def get(self, folder: str, filename: str, local_file: Path) -> None:
        """Download ``<folder>/<filename>`` to ``local_file``."""

    @abstractmethod
    def delete(self, folder: str, filename: str) -> None:
        """Delete ``<folder>/<filename>``."""

    def describe(self) -> str:
        return self.name
