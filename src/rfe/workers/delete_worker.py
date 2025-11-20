# Filename: delete_worker.py
# Author: Rich Lewis @RichLewis007
# Description: Background worker for deleting paths via system trash. Performs safe file
#              deletion operations in a separate thread to avoid blocking the UI.

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from rfe.services.trash import send_path_to_trash


@dataclass(slots=True)
class DeleteResult:
    # Summary of a delete request, split into successes and failures.

    removed: list[Path]
    failed: list[Path]


class DeleteWorker(QObject):
    # Moves files and folders to the Trash in a worker thread.

    progress = Signal(int, int, str)
    finished = Signal(object)  # DeleteResult
    error = Signal(str)

    def __init__(self, paths: Iterable[Path]) -> None:
        super().__init__()
        self._paths = [path for path in paths if path.is_file()]

    def start(self) -> None:
        # Delete each requested path, emitting progress and errors.
        removed: list[Path] = []
        failed: list[Path] = []
        total = len(self._paths)

        for index, path in enumerate(self._paths, start=1):
            self.progress.emit(index, total, str(path))
            try:
                send_path_to_trash(path)
                removed.append(path)
            except OSError as exc:  # pragma: no cover - surfaced in UI
                failed.append(path)
                self.error.emit(f"Failed to delete {path}: {exc}")

        self.finished.emit(DeleteResult(removed=removed, failed=failed))
