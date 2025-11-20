# Filename: search_bar.py
# Author: Rich Lewis @RichLewis007
# Description: Search bar widget for filtering results. Provides text, glob, and regex
#              search modes with case-sensitivity toggle.

from __future__ import annotations

from pathlib import Path
from typing import Literal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

SearchMode = Literal["text", "glob", "regex"]

_ASSET_IMAGE = Path(__file__).resolve().parents[3] / "assets" / "in-app-ghost-pic.png"


class SearchBar(QWidget):
    # Search controls with mode selection.

    searchRequested = Signal(str, str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._input = QLineEdit(self)
        self._input.setPlaceholderText("Search current results…")
        self._mode = QComboBox(self)
        self._mode.addItems(["text", "glob", "regex"])
        self._case_toggle = QPushButton("Aa")
        self._case_toggle.setCheckable(True)
        self._case_toggle.setToolTip("Toggle case-sensitive search")
        self._submit = QPushButton("Search")
        self._submit.setDefault(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(QLabel("Search:", self))
        layout.addWidget(self._input, 1)
        layout.addWidget(QLabel("Mode:", self))
        layout.addWidget(self._mode)
        layout.addWidget(self._case_toggle)
        layout.addWidget(self._submit)

        self._badge_label = QLabel(self)
        self._badge_label.setVisible(False)
        if _ASSET_IMAGE.exists():
            pixmap = QPixmap(str(_ASSET_IMAGE))
            if not pixmap.isNull():
                scaled = pixmap.scaledToHeight(64, Qt.TransformationMode.SmoothTransformation)
                self._badge_label.setPixmap(scaled)
                self._badge_label.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self._badge_label.setVisible(True)
        layout.addWidget(self._badge_label)

        self.setLayout(layout)

        self._input.returnPressed.connect(self._emit_search)
        self._submit.clicked.connect(self._emit_search)
        self._input.textChanged.connect(self._on_text_changed)

    def _emit_search(self) -> None:
        # Emit a search request using the current widget state.
        text = self._input.text()
        mode = self._mode.currentText()
        case_sensitive = self._case_toggle.isChecked()
        self.searchRequested.emit(text, mode, case_sensitive)

    def set_search_text(self, value: str) -> None:
        # Programmatically update the search field text.
        self._input.setText(value)

    def _on_text_changed(self, value: str) -> None:
        # Trigger a fresh search when the field is cleared.
        if value == "":
            self._emit_search()
