"""Utilities for safely moving files to system trash."""

from __future__ import annotations

from pathlib import Path

from send2trash import send2trash


def send_path_to_trash(path: Path) -> None:
    """Move a file or directory to the system Trash."""
    send2trash(str(path))
