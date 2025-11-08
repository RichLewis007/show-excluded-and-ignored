"""Filesystem tree data structures and Qt model."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Literal

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel

from .rules_model import Rule

NodeType = Literal["file", "dir"]


@dataclass(slots=True)
class PathNode:
    abs_path: Path
    rel_path: str
    type: NodeType
    size: int | None = None
    mtime: float | None = None
    rule_index: int | None = None
    rule_ids: list[int] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    children: list[PathNode] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.abs_path.name or self.rel_path


class PathTreeModel(QStandardItemModel):
    """Qt model representing a tree of `PathNode` objects."""

    HEADERS: ClassVar[list[str]] = ["Name", "Type", "Size", "Modified", "Rule", "Full Path"]

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.setHorizontalHeaderLabels(self.HEADERS)
        self._rules: Sequence[Rule] = []

    def load_nodes(self, nodes: Sequence[PathNode], rules: Sequence[Rule]) -> None:
        self._rules = rules
        self.clear()
        self.setHorizontalHeaderLabels(self.HEADERS)
        for node in nodes:
            items = self._node_to_items(node)
            self.appendRow(items)

    def _node_to_items(self, node: PathNode) -> list[QStandardItem]:
        name_item = QStandardItem(node.name)
        name_item.setData(node, Qt.ItemDataRole.UserRole)

        type_item = QStandardItem(node.type)
        size_item = QStandardItem(self._format_size(node.size))
        mtime_item = QStandardItem(self._format_mtime(node.mtime))
        rule_item = QStandardItem(self._rule_label(node.rule_index))
        path_item = QStandardItem(str(node.abs_path))

        row = [name_item, type_item, size_item, mtime_item, rule_item, path_item]

        for child in node.children:
            child_items = self._node_to_items(child)
            name_item.appendRow(child_items)

        return row

    def _rule_label(self, index: int | None) -> str:
        if index is None or index < 0 or index >= len(self._rules):
            return ""
        rule = self._rules[index]
        return rule.label or rule.pattern

    @staticmethod
    def _format_size(size: int | None) -> str:
        if size is None:
            return ""
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        if size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        return f"{size / (1024 * 1024 * 1024):.1f} GB"

    @staticmethod
    def _format_mtime(mtime: float | None) -> str:
        if mtime is None:
            return ""
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
