# Filename: status_bar.py
# Author: Rich Lewis @RichLewis007
# Description: Status bar widget displaying scan progress and statistics. Shows progress
#              indicators, match counts, and status messages at the bottom of the main window.

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QProgressBar, QStatusBar, QWidget


class AppStatusBar(QStatusBar):
    # Status bar showing scan progress and stats.

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)  # Indeterminate by default.
        self._progress.setVisible(False)

        self._stats = QLabel("Ready", self)

        self.addWidget(self._stats, 1)
        self.addPermanentWidget(self._progress, 0)

    def set_message(self, message: str) -> None:
        # Display a textual status update.
        self._stats.setText(message)

    def set_progress(self, fraction: float | None) -> None:
        # Show progress in the range [0, 1] or hide when ``None``.
        if fraction is None:
            self._progress.setRange(0, 0)
            self._progress.setVisible(False)
        else:
            self._progress.setRange(0, 1000)
            self._progress.setValue(int(fraction * 1000))
            self._progress.setVisible(True)
