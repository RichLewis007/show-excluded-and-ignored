# Filename: fs_model.py
# Author: Rich Lewis @RichLewis007
# Description: Filesystem tree data structures and Qt model implementation. Defines PathNode
#              data structure and PathTreeModel for displaying file system trees in the Qt tree view.

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Literal

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication

from rfe.services.formatting import format_bytes

from .rules_model import Rule

logger = logging.getLogger(__name__)

NodeType = Literal["file", "dir"]


@dataclass(slots=True)
class PathNode:
    # Representation of a file-system item participating in the tree view.

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
        # Return the display name for the node.
        return self.abs_path.name or self.rel_path


class PathTreeModel(QStandardItemModel):
    # Qt model representing a tree of `PathNode` objects.

    HEADERS: ClassVar[list[str]] = [
        "Name",
        "Type",
        "Size",
        "Modified",
        "First Rule",
        "All Rules",
        "Full Path",
    ]

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.setHorizontalHeaderLabels(self.HEADERS)
        self._rules: Sequence[Rule] = []

    def load_nodes(self, nodes: Sequence[PathNode], rules: Sequence[Rule]) -> None:
        # Populate the model with a fresh tree.
        # Process nodes in chunks to keep UI responsive with large datasets.
        self._rules = rules
        self.clear()
        self.setHorizontalHeaderLabels(self.HEADERS)

        total_nodes = len(nodes)
        logger.info("Loading %d nodes into tree model", total_nodes)

        # Process in chunks to keep UI responsive
        chunk_size = 50  # Process 50 nodes at a time (reduced for better responsiveness)
        processed = 0
        total_children_processed = 0

        for i, node in enumerate(nodes):
            logger.debug("Processing node %d/%d: %s", i + 1, total_nodes, node.name)
            child_counter = [0]  # Track children for this node
            self._append_node(parent_item=None, node=node, prefix="", child_counter=child_counter)
            total_children_processed += child_counter[0]
            processed += 1

            # Periodically process events to keep UI responsive
            if processed % chunk_size == 0:
                QApplication.processEvents()
                logger.debug(
                    "Processed %d/%d top-level nodes, %d total items",
                    processed,
                    total_nodes,
                    total_children_processed,
                )
            elif processed % 10 == 0:
                # Process events more frequently for better responsiveness
                QApplication.processEvents()

        logger.info(
            "Finished loading %d top-level nodes (%d total items)",
            processed,
            total_children_processed,
        )

    def _append_node(
        self,
        *,
        parent_item: QStandardItem | None,
        node: PathNode,
        prefix: str,
        child_counter: list[int] | None = None,
    ) -> None:
        # Append a node to the model.
        # child_counter is a mutable list to track total children processed across recursion
        if child_counter is None:
            child_counter = [0]

        segment = node.name
        display_name = f"{prefix}/{segment}" if prefix else segment

        row = self._create_row(node, display_name)
        if parent_item is None:
            self.appendRow(row)
        else:
            parent_item.appendRow(row)

        name_item = row[0]
        child_count = len(node.children)
        if child_count > 0:
            # Log if a node has many children (potential performance issue)
            if child_count > 500:
                logger.debug(
                    "Node %s has %d children - processing in chunks", display_name, child_count
                )

            # Process children in chunks to keep UI responsive
            # Use smaller chunks for better responsiveness with large lists
            chunk_size = 25 if child_count > 500 else (50 if child_count > 200 else 200)
            for i, child in enumerate(node.children):
                # Log if this child itself has many children (nested large structure)
                if len(child.children) > 500:
                    logger.debug(
                        "  Child %d/%d (%s) has %d children - will process incrementally",
                        i + 1,
                        child_count,
                        child.name,
                        len(child.children),
                    )

                self._append_node(
                    parent_item=name_item, node=child, prefix="", child_counter=child_counter
                )
                child_counter[0] += 1

                # Process events more frequently for large child lists
                # This is critical to prevent UI freezing with deeply nested structures
                if child_count > 500:
                    # Process events every chunk_size children
                    if i > 0 and i % chunk_size == 0:
                        QApplication.processEvents()
                        logger.debug(
                            "  Processed %d/%d children of %s", i, child_count, display_name
                        )
                    # Also process events after each child that has many children itself
                    elif len(child.children) > 200:
                        QApplication.processEvents()
                elif child_count > 200:
                    if i > 0 and i % 50 == 0:
                        QApplication.processEvents()
                elif i > 0 and i % 200 == 0:
                    # Process events for smaller lists too, but less frequently
                    QApplication.processEvents()

    def _create_row(self, node: PathNode, display_name: str) -> list[QStandardItem]:
        # Create a standard-item row for ``node``.
        name_item = QStandardItem(display_name)
        name_item.setData(node, Qt.ItemDataRole.UserRole)
        if node.type == "dir":
            font = name_item.font()
            font.setBold(True)
            name_item.setFont(font)
            name_item.setEditable(False)

        type_item = QStandardItem(node.type)
        size_item = QStandardItem(self._format_size(node.size))
        mtime_item = QStandardItem(self._format_mtime(node.mtime))
        rule_item = QStandardItem(self._rule_label(node.rule_index))
        all_rules_item = QStandardItem(self._all_rule_labels(node.rule_ids))
        path_str = str(node.abs_path)
        if node.type == "dir" and not path_str.endswith("/"):
            path_str += "/"
        path_item = QStandardItem(path_str)

        return [name_item, type_item, size_item, mtime_item, rule_item, all_rules_item, path_item]

    def _rule_label(self, index: int | None) -> str:
        # Resolve a rule index into a user-facing label.
        if index is None or index < 0 or index >= len(self._rules):
            return ""
        rule = self._rules[index]
        return rule.label or rule.pattern

    def _all_rule_labels(self, indexes: list[int]) -> str:
        labels: list[str] = []
        seen: set[str] = set()
        for index in indexes:
            label = self._rule_label(index)
            if label and label not in seen:
                labels.append(label)
                seen.add(label)
        return ", ".join(labels)

    @staticmethod
    def _format_size(size: int | None) -> str:
        # Return a human-readable size string.
        return format_bytes(size, empty="")

    @staticmethod
    def _format_mtime(mtime: float | None) -> str:
        # Format a modified timestamp for presentation.
        if mtime is None:
            return ""
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")

    def highlight_rule(self, rel_paths: set[str], color: QColor | None) -> None:
        # Apply background highlighting to rows whose relative paths match ``rel_paths``.
        brush = QBrush(color) if color is not None else QBrush()
        column_count = len(self.HEADERS)

        def walk(parent: QStandardItem) -> None:
            for row in range(parent.rowCount()):
                name_item = parent.child(row, 0)
                if name_item is None:
                    continue
                node = name_item.data(Qt.ItemDataRole.UserRole)
                matches = isinstance(node, PathNode) and node.rel_path in rel_paths

                for column in range(column_count):
                    item = parent.child(row, column)
                    if item is None:
                        continue
                    if matches and color is not None:
                        item.setBackground(brush)
                    else:
                        item.setBackground(QBrush())

                walk(name_item)

        walk(self.invisibleRootItem())
