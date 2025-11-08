"""Search bar widget."""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

SearchMode = Literal["text", "glob", "regex"]


class SearchBar(QWidget):
    """Search controls with mode selection."""

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
        self.setLayout(layout)

        self._input.returnPressed.connect(self._emit_search)
        self._submit.clicked.connect(self._emit_search)

    def _emit_search(self) -> None:
        text = self._input.text()
        mode = self._mode.currentText()
        case_sensitive = self._case_toggle.isChecked()
        self.searchRequested.emit(text, mode, case_sensitive)

    def set_search_text(self, value: str) -> None:
        self._input.setText(value)
