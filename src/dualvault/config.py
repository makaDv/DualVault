"""Configuration model, validation and TOML persistence."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import tomli_w

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
DEST_TYPES = ("local", "rclone")


class ConfigError(ValueError):
    """Raised when the configuration is invalid."""


def validate_name(name: str, what: str) -> str:
    if not NAME_RE.match(name or ""):
        raise ConfigError(
            f"Invalid {what} name {name!r}: use 1-64 letters, digits, '-' or '_' "
            "(must start with a letter or digit)."
        )
    return name


@dataclass
class Source:
    name: str
    path: str
    exclude: list[str] = field(default_factory=list)


@dataclass
class Destination:
    name: str
    type: str = "local"
    path: str = ""  # for type "local"
    remote: str = ""  # for type "rclone", e.g. "gdrive:Backups/DualVault"


@dataclass
class Retention:
    keep_last: int = 7
    keep_daily: int = 7
    keep_weekly: int = 4
    keep_monthly: int = 12


@dataclass
class Settings:
    encrypt: bool = False
    # Optional file whose first line is the encryption password (for unattended runs).
    # Protect it with filesystem permissions. Leave empty to be prompted or to use
    # the DUALVAULT_PASSWORD environment variable.
    password_file: str = ""
    compression_level: int = 6
    rclone_binary: str = "rclone"
    log_level: str = "INFO"
    follow_symlinks: bool = False


@dataclass
class Config:
    settings: Settings = field(default_factory=Settings)
    retention: Retention = field(default_factory=Retention)
    sources: list[Source] = field(default_factory=list)
    destinations: list[Destination] = field(default_factory=list)

    # ---- lookup helpers -------------------------------------------------
    def source(self, name: str) -> Source:
        for s in self.sources:
            if s.name == name:
                return s
        raise ConfigError(f"Unknown source {name!r}")

    def destination(self, name: str) -> Destination:
        for d in self.destinations:
            if d.name == name:
                return d
        raise ConfigError(f"Unknown destination {name!r}")

    # ---- validation -----------------------------------------------------
    def validate(self) -> Config:
        seen: set[str] = set()
        for s in self.sources:
            validate_name(s.name, "source")
            if s.name in seen:
                raise ConfigError(f"Duplicate source name {s.name!r}")
            seen.add(s.name)
            if not s.path:
                raise ConfigError(f"Source {s.name!r} has no path")
            if not all(isinstance(p, str) for p in s.exclude):
                raise ConfigError(f"Source {s.name!r}: exclude must be a list of strings")
        seen = set()
        for d in self.destinations:
            validate_name(d.name, "destination")
            if d.name in seen:
                raise ConfigError(f"Duplicate destination name {d.name!r}")
            seen.add(d.name)
            if d.type not in DEST_TYPES:
                raise ConfigError(f"Destination {d.name!r}: type must be one of {DEST_TYPES}")
            if d.type == "local" and not d.path:
                raise ConfigError(f"Destination {d.name!r}: 'path' is required for type local")
            if d.type == "rclone" and ":" not in d.remote:
                raise ConfigError(
                    f"Destination {d.name!r}: 'remote' must look like 'myremote:folder'"
                )
        r = self.retention
        for key, value in asdict(r).items():
            if not isinstance(value, int) or value < 0:
                raise ConfigError(f"retention.{key} must be a non-negative integer")
        if r.keep_last + r.keep_daily + r.keep_weekly + r.keep_monthly == 0:
            raise ConfigError("Retention would delete every snapshot; keep at least one.")
        if not 0 <= self.settings.compression_level <= 9:
            raise ConfigError("settings.compression_level must be between 0 and 9")
        return self

    # ---- (de)serialisation ---------------------------------------------
    @classmethod
    def from_dict(cls, data: dict) -> Config:
        try:
            return cls(
                settings=Settings(**data.get("settings", {})),
                retention=Retention(**data.get("retention", {})),
                sources=[Source(**s) for s in data.get("sources", [])],
                destinations=[Destination(**d) for d in data.get("destinations", [])],
            ).validate()
        except TypeError as exc:  # unknown keys
            raise ConfigError(f"Invalid configuration: {exc}") from exc

    def to_dict(self) -> dict:
        return {
            "settings": asdict(self.settings),
            "retention": asdict(self.retention),
            "sources": [asdict(s) for s in self.sources],
            "destinations": [asdict(d) for d in self.destinations],
        }


def load(path: Path) -> Config:
    if not path.exists():
        raise ConfigError(f"Configuration not found at {path}. Run 'dualvault init' first.")
    with path.open("rb") as fh:
        try:
            data = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{path}: {exc}") from exc
    return Config.from_dict(data)


def save(config: Config, path: Path) -> None:
    config.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as fh:
        tomli_w.dump(config.to_dict(), fh)
    os.replace(tmp, path)
    if os.name == "posix":
        os.chmod(path, 0o600)
