# Filename: rules_panel.py
# Author: Rich Lewis @RichLewis007
# Description: Sidebar panel for rule management. Displays filter rules with checkboxes,
#              allows rule selection for filtering results, and highlights selected rules.

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
    # Widget listing filter rules with checkboxes.

    selectionChanged = Signal(object)
    ruleHighlighted = Signal(object)

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
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.itemChanged.connect(self._emit_selection)
        self._list.itemSelectionChanged.connect(self._on_item_selection_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._select_all)
        layout.addWidget(self._list)
        self.setLayout(layout)

        self._rules: list[Rule] = []
        self._rule_colors: dict[int, str] = {}

    def load_rules_from_path(self, path: Path) -> None:
        # Populate the panel with rules parsed from ``path``.
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
        # Refresh the list widget with the current rule set.
        self._list.clear()
        color_cycle = itertools.cycle(self._fallback_colors)

        self._rule_colors.clear()
        self._list.blockSignals(True)
        for index, rule in enumerate(self._rules):
            item = QListWidgetItem(rule.display_label())
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, index)
            tooltip = f"Line {rule.lineno}: {rule.action} {rule.pattern}"
            item.setToolTip(tooltip)

            color_hex = rule.color or next(color_cycle)
            self._rule_colors[index] = color_hex
            color = QColor(color_hex)
            if color.isValid():
                brush = QBrush(color)
                item.setForeground(brush)

            pattern = rule.pattern.strip()
            if pattern.endswith("/**"):
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self._list.addItem(item)
        self._list.blockSignals(False)

        self._select_all.setEnabled(bool(self._rules))
        self._update_select_all_state()
        self._emit_selection()
        self._list.clearSelection()
        self.ruleHighlighted.emit(None)

    def _emit_selection(self) -> None:
        # Emit the currently selected rule indices.
        selected_indices: list[int] = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                index = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(index, int):
                    selected_indices.append(index)
        self._update_select_all_state()
        self.selectionChanged.emit(selected_indices or None)

    def _on_item_selection_changed(self) -> None:
        # Emit the highlighted rule index and color when rows are selected.
        selected_items = self._list.selectedItems()
        if not selected_items:
            self.ruleHighlighted.emit(None)
            return

        item = selected_items[0]
        index = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(index, int):
            self.ruleHighlighted.emit(None)
            return
        color_hex = self._rule_colors.get(index)
        self.ruleHighlighted.emit((index, color_hex))

    def _on_select_all_state_changed(self, state: int) -> None:
        # Handle changes to the tri-state “select all” checkbox.
        if self._updating_checkbox_state:
            return

        check_state = Qt.CheckState(state)
        if check_state == Qt.CheckState.PartiallyChecked:
            check_state = Qt.CheckState.Checked

        self._set_all_items(check_state)

    def _set_all_items(self, state: Qt.CheckState, *, emit_clear: bool = False) -> None:
        # Apply the same check state to every list item.
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setCheckState(state)
        self._list.blockSignals(False)
        self._emit_selection()

    def _update_select_all_state(self) -> None:
        # Synchronise the tri-state checkbox with individual item states.
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
        # Update the select-all checkbox without triggering loops.
        self._updating_checkbox_state = True
        try:
            self._select_all.setCheckState(state)
        finally:
            self._updating_checkbox_state = False

    @property
    def rules(self) -> list[Rule]:
        # Return the current list of rules.
        return self._rules
