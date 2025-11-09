"""Tree view displaying filesystem matches."""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import (
    QItemSelection,
    QModelIndex,
    QPoint,
    QRegularExpression,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTreeView, QVBoxLayout, QWidget

from rfe.models.fs_model import PathNode, PathTreeModel
from rfe.models.rules_model import Rule
from rfe.views.search_bar import SearchMode


class TreeFilterProxyModel(QSortFilterProxyModel):
    """Proxy model applying search text and rule filters."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._search_regex: QRegularExpression | None = None
        self._rule_filter: set[int] | None = None
        self.setRecursiveFilteringEnabled(True)

    def set_search_regex(self, regex: QRegularExpression | None) -> None:
        self._search_regex = regex
        self.invalidateFilter()

    def set_rule_filter(self, rule_indices: Sequence[int]) -> None:
        self._rule_filter = set(rule_indices) if rule_indices else None
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # type: ignore[override]
        source_model = self.sourceModel()
        if source_model is None:
            return False

        index = source_model.index(source_row, 0, source_parent)
        if not index.isValid():
            return False

        if self._matches(index):
            return True

        for row in range(source_model.rowCount(index)):
            if self.filterAcceptsRow(row, index):
                return True
        return False

    def _matches(self, index: QModelIndex) -> bool:
        node = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(node, PathNode):
            return True

        if self._rule_filter is not None:
            candidate_rules = set(node.rule_ids)
            if node.rule_index is not None:
                candidate_rules.add(node.rule_index)
            if not candidate_rules.intersection(self._rule_filter):
                return False

        if self._search_regex is None or not self._search_regex.pattern():
            return True

        haystack = f"{node.rel_path} {node.abs_path}"
        return self._search_regex.match(haystack).hasMatch()


class TreePanel(QWidget):
    """Wrapper around QTreeView for displaying root paths."""

    deleteRequested = Signal()
    selectionChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = PathTreeModel(self)
        self._proxy = TreeFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._current_nodes: list[PathNode] = []

        self._tree = QTreeView(self)
        self._tree.setModel(self._proxy)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setUniformRowHeights(True)
        self._tree.setSortingEnabled(False)
        self._tree.setAnimated(True)
        self._tree.setHeaderHidden(False)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)

        selection_model = self._tree.selectionModel()
        selection_model.selectionChanged.connect(self._on_selection_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tree)
        self.setLayout(layout)

    def load_nodes(self, nodes: Sequence[PathNode], rules: Sequence[Rule]) -> None:
        self._model.load_nodes(nodes, rules)
        self._current_nodes = list(nodes)
        self._tree.expandToDepth(0)
        header = self._tree.header()
        header.setStretchLastSection(True)
        for column in range(self._model.columnCount()):
            self._tree.resizeColumnToContents(column)
        self.selectionChanged.emit()

    def set_root_path(self, path: Path) -> None:
        self._tree.setWhatsThis(f"Root path: {path}")

    def on_search_requested(self, text: str, mode: SearchMode, case_sensitive: bool) -> None:
        regex = self._build_regex(text, mode, case_sensitive)
        self._proxy.set_search_regex(regex)

    def on_rules_selection_changed(self, rule_indices: list[int]) -> None:
        self._proxy.set_rule_filter(rule_indices)

    def selected_paths(self) -> list[Path]:
        return [node.abs_path for node in self.selected_nodes()]

    def selected_nodes(self) -> list[PathNode]:
        nodes: list[PathNode] = []
        for index in self._tree.selectionModel().selectedRows():
            node = index.data(Qt.ItemDataRole.UserRole)
            if isinstance(node, PathNode):
                nodes.append(node)
        return nodes

    def _show_context_menu(self, point: QPoint) -> None:
        if not self.selected_nodes():
            return
        menu = QMenu(self)
        delete_action = menu.addAction("Delete…")
        delete_action.triggered.connect(lambda _checked=False: self.deleteRequested.emit())
        menu.exec(self._tree.viewport().mapToGlobal(point))

    def _on_selection_changed(
        self,
        selected: QItemSelection,
        deselected: QItemSelection,
    ) -> None:
        _ = selected, deselected
        self.selectionChanged.emit()

    def collect_nodes(self, *, visible_only: bool) -> list[PathNode]:
        if visible_only:
            collected: list[PathNode] = []

            def walk(parent: QModelIndex) -> None:
                proxy = self._proxy
                for row in range(proxy.rowCount(parent)):
                    index = proxy.index(row, 0, parent)
                    node = index.data(Qt.ItemDataRole.UserRole)
                    if isinstance(node, PathNode):
                        collected.append(node)
                    walk(index)

            walk(QModelIndex())
            return collected

        flattened: list[PathNode] = []

        def flatten(nodes: Sequence[PathNode]) -> None:
            for node in nodes:
                flattened.append(node)
                if node.children:
                    flatten(node.children)

        flatten(self._current_nodes)
        return flattened

    def _build_regex(
        self,
        text: str,
        mode: SearchMode,
        case_sensitive: bool,
    ) -> QRegularExpression | None:
        if not text:
            return None

        if mode == "text":
            pattern = re.escape(text)
        elif mode == "glob":
            pattern = fnmatch.translate(text)
            if pattern.endswith(r"\Z(?ms)"):
                pattern = pattern[:-6]
        else:
            pattern = text

        options = QRegularExpression.PatternOption.NoPatternOption
        if not case_sensitive:
            options |= QRegularExpression.PatternOption.CaseInsensitiveOption

        regex = QRegularExpression(pattern, options)
        if not regex.isValid():
            return QRegularExpression()
        return regex
