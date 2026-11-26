"""Per-user directories for configuration, logs and state.

Nothing is ever written inside the installation or the source tree.
Set ``DUALVAULT_HOME`` to put everything under one directory (useful for
portable installs and tests).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP = "DualVault"


def _home_override() -> Path | None:
    value = os.environ.get("DUALVAULT_HOME")
    return Path(value).expanduser() if value else None


def config_dir() -> Path:
    override = _home_override()
    if override:
        return override
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / APP.lower()


def state_dir() -> Path:
    override = _home_override()
    if override:
        return override / "state"
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        return Path(base) / APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP / "state"
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base) / APP.lower()


def log_dir() -> Path:
    return state_dir() / "logs"


def default_config_path() -> Path:
    env = os.environ.get("DUALVAULT_CONFIG")
    if env:
        return Path(env).expanduser()
    return config_dir() / "config.toml"
