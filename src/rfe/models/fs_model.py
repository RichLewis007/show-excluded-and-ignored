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
    """Representation of a file-system item participating in the tree view."""

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
        """Return the display name for the node."""
        return self.abs_path.name or self.rel_path


class PathTreeModel(QStandardItemModel):
    """Qt model representing a tree of `PathNode` objects."""

    HEADERS: ClassVar[list[str]] = ["Name", "Type", "Size", "Modified", "Rule", "Full Path"]

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.setHorizontalHeaderLabels(self.HEADERS)
        self._rules: Sequence[Rule] = []

    def load_nodes(self, nodes: Sequence[PathNode], rules: Sequence[Rule]) -> None:
        """Populate the model with a fresh tree, hiding unmatched filesystem nodes."""
        self._rules = rules
        self.clear()
        self.setHorizontalHeaderLabels(self.HEADERS)
        for node in nodes:
            self._append_node(parent_item=None, node=node, prefix="")

    def _append_node(
        self,
        *,
        parent_item: QStandardItem | None,
        node: PathNode,
        prefix: str,
    ) -> None:
        """Append a node to the model, skipping ones that lack matches."""
        is_match = (bool(node.rule_ids) or node.rule_index is not None) and node.type == "file"
        segment = node.name
        display_name = f"{prefix}/{segment}" if prefix else segment

        if not is_match:
            next_prefix = display_name if segment else prefix
            for child in node.children:
                self._append_node(parent_item=parent_item, node=child, prefix=next_prefix)
            return

        row = self._create_row(node, display_name)
        if parent_item is None:
            self.appendRow(row)
        else:
            parent_item.appendRow(row)

        name_item = row[0]
        for child in node.children:
            self._append_node(parent_item=name_item, node=child, prefix="")

    def _create_row(self, node: PathNode, display_name: str) -> list[QStandardItem]:
        """Create a standard-item row for ``node``."""
        name_item = QStandardItem(display_name)
        name_item.setData(node, Qt.ItemDataRole.UserRole)

        type_item = QStandardItem(node.type)
        size_item = QStandardItem(self._format_size(node.size))
        mtime_item = QStandardItem(self._format_mtime(node.mtime))
        rule_item = QStandardItem(self._rule_label(node.rule_index))
        path_item = QStandardItem(str(node.abs_path))

        return [name_item, type_item, size_item, mtime_item, rule_item, path_item]

    def _rule_label(self, index: int | None) -> str:
        """Resolve a rule index into a user-facing label."""
        if index is None or index < 0 or index >= len(self._rules):
            return ""
        rule = self._rules[index]
        return rule.label or rule.pattern

    @staticmethod
    def _format_size(size: int | None) -> str:
        """Return a human-readable size string."""
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
        """Format a modified timestamp for presentation."""
        if mtime is None:
            return ""
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
