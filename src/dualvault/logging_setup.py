"""Logging to console and to a rotating file in the per-user log folder."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dualvault import paths

LOG_FILE = "dualvault.log"


def setup(level: str = "INFO", verbose: bool = False, log_dir: Path | None = None) -> Path:
    log_dir = log_dir or paths.log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILE
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root.addHandler(file_handler)
    if sys.stderr is not None:  # None under pythonw / scheduled tasks without a console
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG if verbose else logging.INFO)
        console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        root.addHandler(console)
    return log_file
