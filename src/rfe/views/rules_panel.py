"""Sidebar for rule management."""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import ClassVar

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from rfe.models.rules_model import Rule, parse_filter_file


class RulesPanel(QWidget):
    """Widget listing filter rules with checkboxes."""

    selectionChanged = Signal(list)

    _fallback_colors: ClassVar[list[str]] = [
        "#1abc9c",
        "#3498db",
        "#9b59b6",
        "#e67e22",
        "#e74c3c",
        "#16a085",
        "#2980b9",
        "#8e44ad",
        "#2ecc71",
        "#f1c40f",
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._updating_checkbox_state = False

        self._select_all = QCheckBox("Select all", self)
        self._select_all.setTristate(True)
        self._select_all.stateChanged.connect(self._on_select_all_state_changed)

        self._list = QListWidget(self)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self._list.itemChanged.connect(self._emit_selection)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._select_all)
        layout.addWidget(self._list)
        self.setLayout(layout)

        self._rules: list[Rule] = []

    def load_rules_from_path(self, path: Path) -> None:
        try:
            self._rules = parse_filter_file(path)
        except OSError as exc:  # pragma: no cover - UI feedback
            QMessageBox.warning(
                self,
                "Failed to load rules",
                f"Could not read filter file:\n{path}\n\n{exc}",
            )
            self._rules = []
        self._populate_list()

    def _populate_list(self) -> None:
        self._list.clear()
        color_cycle = itertools.cycle(self._fallback_colors)

        self._list.blockSignals(True)
        for index, rule in enumerate(self._rules):
            item = QListWidgetItem(rule.display_label())
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, index)
            tooltip = f"Line {rule.lineno}: {rule.action} {rule.pattern}"
            item.setToolTip(tooltip)

            color_hex = rule.color or next(color_cycle)
            color = QColor(color_hex)
            if color.isValid():
                brush = QBrush(color)
                item.setForeground(brush)

            self._list.addItem(item)
        self._list.blockSignals(False)

        self._select_all.setEnabled(bool(self._rules))
        self._update_select_all_state()
        self._emit_selection()

    def _emit_selection(self) -> None:
        selected_indices: list[int] = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                index = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(index, int):
                    selected_indices.append(index)
        self._update_select_all_state()
        self.selectionChanged.emit(selected_indices)

    def _on_select_all_state_changed(self, state: int) -> None:
        if self._updating_checkbox_state:
            return

        check_state = Qt.CheckState(state)
        if check_state == Qt.CheckState.PartiallyChecked:
            check_state = Qt.CheckState.Checked

        self._set_all_items(check_state)

    def _set_all_items(self, state: Qt.CheckState) -> None:
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setCheckState(state)
        self._list.blockSignals(False)
        self._emit_selection()

    def _update_select_all_state(self) -> None:
        if not self._rules:
            self._set_select_all_state(Qt.CheckState.Unchecked)
            return

        total = self._list.count()
        checked = sum(
            1 for i in range(total) if self._list.item(i).checkState() == Qt.CheckState.Checked
        )

        if checked == 0:
            self._set_select_all_state(Qt.CheckState.Unchecked)
        elif checked == total:
            self._set_select_all_state(Qt.CheckState.Checked)
        else:
            self._set_select_all_state(Qt.CheckState.PartiallyChecked)

    def _set_select_all_state(self, state: Qt.CheckState) -> None:
        self._updating_checkbox_state = True
        try:
            self._select_all.setCheckState(state)
        finally:
            self._updating_checkbox_state = False

    @property
    def rules(self) -> list[Rule]:
        return self._rules
