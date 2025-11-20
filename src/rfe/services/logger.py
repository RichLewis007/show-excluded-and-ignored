# Filename: logger.py
# Author: Rich Lewis @RichLewis007
# Description: Logging configuration utilities. Sets up rotating file and console handlers
#              for application-wide logging with configurable log levels.

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from platformdirs import PlatformDirs

from .config import APP_NAME, ORG_NAME


def _get_log_path() -> Path:
    # Return the path to the rotating log file, creating folders as needed.
    dirs = PlatformDirs(appname=APP_NAME, appauthor=ORG_NAME)
    path = Path(dirs.user_log_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path / "ghost-files-finder.log"


def configure(*, log_level: str = "INFO") -> None:
    # Configure root logger with rotating file and console handlers.
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    log_path = _get_log_path()
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Avoid duplicate handlers when reconfiguring.
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)
