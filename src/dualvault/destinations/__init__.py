"""Backup destinations (external/local folders and rclone remotes)."""

from __future__ import annotations

from dualvault.config import Destination, Settings
from dualvault.destinations.base import BaseDestination, DestinationUnavailable
from dualvault.destinations.local import LocalDestination
from dualvault.destinations.rclone import RcloneDestination

__all__ = [
    "BaseDestination",
    "DestinationUnavailable",
    "LocalDestination",
    "RcloneDestination",
    "build",
]


def build(dest: Destination, settings: Settings) -> BaseDestination:
    if dest.type == "local":
        return LocalDestination(dest.name, dest.path)
    if dest.type == "rclone":
        return RcloneDestination(dest.name, dest.remote, settings.rclone_binary)
    raise ValueError(f"Unsupported destination type {dest.type!r}")
