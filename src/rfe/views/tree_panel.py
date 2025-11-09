"""Tree view displaying filesystem matches."""

from __future__ import annotations

import fnmatch
import os
import platform
import re
from collections.abc import Sequence
from pathlib import Path
from shutil import which

from PySide6.QtCore import (
    QItemSelection,
    QModelIndex,
    QPoint,
    QProcess,
    QRegularExpression,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QMenu,
    QMessageBox,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from rfe.models.fs_model import PathNode, PathTreeModel
from rfe.models.match_engine import MatchEngine
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
        """Update the active search regex and re-filter the view."""
        self._search_regex = regex
        self.invalidateFilter()

    def set_rule_filter(self, rule_indices: Sequence[int] | None) -> None:
        """Limit matches to the supplied rule indices."""
        if rule_indices is None:
            self._rule_filter = None
        else:
            self._rule_filter = set(rule_indices)
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # type: ignore[override]
        """Decide whether a source-model row passes the current filters."""
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
        """Return True when the node represented by ``index`` matches filters."""
        node = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(node, PathNode):
            return True

        if self._rule_filter is not None:
            if self._rule_filter:
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
        self._open_action_label = (
            "Open in Finder" if platform.system() == "Darwin" else "Open in File Explorer"
        )
        self._highlight_rule_index: int | None = None
        self._highlight_paths: set[str] = set()
        self._rules: list[Rule] = []

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
        self._summary_label = QLabel(self)
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._summary_label.setText("Files: 0   Folders: 0   Total: 0")
        layout.addWidget(self._summary_label)
        self.setLayout(layout)

    def load_nodes(self, nodes: Sequence[PathNode], rules: Sequence[Rule]) -> None:
        """Load a fresh tree of nodes into the view."""
        self._model.load_nodes(nodes, rules)
        self._current_nodes = list(nodes)
        self._rules = list(rules)
        self._tree.expandToDepth(0)
        header = self._tree.header()
        header.setStretchLastSection(True)
        for column in range(self._model.columnCount()):
            self._tree.resizeColumnToContents(column)
        self.selectionChanged.emit()
        self._update_summary()
        self._highlight_rule_index = None
        self._highlight_paths = set()
        self._model.highlight_rule(set(), None)

    def set_root_path(self, path: Path) -> None:
        """Record the root path in the widget's accessible metadata."""
        self._tree.setWhatsThis(f"Root path: {path}")

    def on_search_requested(self, text: str, mode: SearchMode, case_sensitive: bool) -> None:
        """Update the filter proxy based on a search request."""
        regex = self._build_regex(text, mode, case_sensitive)
        self._proxy.set_search_regex(regex)
        self._update_summary()

    def on_rules_selection_changed(self, rule_indices: list[int] | None) -> None:
        """React to rule selection changes from the rules panel."""
        if rule_indices is None:
            self._proxy.set_rule_filter(None)
        elif len(rule_indices) == 0:
            self._proxy.set_rule_filter([])
        else:
            self._proxy.set_rule_filter(rule_indices)
        self._update_summary()

    def on_rule_highlighted(self, payload: object) -> None:
        """Highlight rows that match the selected rule."""
        if payload is None:
            self._highlight_rule_index = None
            self._highlight_paths = set()
            self._model.highlight_rule(set(), None)
            self._update_summary()
            return

        index, color_hex = payload if isinstance(payload, tuple) else (None, None)
        if not isinstance(index, int) or index < 0 or index >= len(self._rules):
            self._highlight_rule_index = None
            self._highlight_paths = set()
            self._model.highlight_rule(set(), None)
            self._update_summary()
            return

        color = QColor(color_hex) if isinstance(color_hex, str) else QColor()
        if not color.isValid():
            color = QColor("#FFF59D")  # soft highlight fallback
        self._highlight_rule_index = index
        rule = self._rules[index]
        engine = MatchEngine([rule], case_sensitive=True)
        paths = {
            node.rel_path
            for node in self.collect_nodes(visible_only=False)
            if engine.matching_rule_indexes(node.rel_path)
        }
        self._highlight_paths = paths
        self._model.highlight_rule(paths, color)
        self._update_summary()

    def selected_paths(self) -> list[Path]:
        """Return absolute paths for the current selection."""
        return [node.abs_path for node in self.selected_nodes()]

    def selected_nodes(self) -> list[PathNode]:
        """Return ``PathNode`` objects for the current selection."""
        nodes: list[PathNode] = []
        for index in self._tree.selectionModel().selectedRows():
            node = index.data(Qt.ItemDataRole.UserRole)
            if isinstance(node, PathNode):
                nodes.append(node)
        return nodes

    def _show_context_menu(self, point: QPoint) -> None:
        """Display a context menu with destructive actions."""
        nodes = self.selected_nodes()
        if not nodes:
            return
        menu = QMenu(self)
        open_action = menu.addAction(self._open_action_label)
        open_action.triggered.connect(lambda _checked=False: self._open_selected_in_file_manager())

        if any(node.type == "dir" for node in nodes):
            placeholder = menu.addAction("Can't delete folders")
            placeholder.setEnabled(False)

        if nodes and all(node.type == "file" for node in nodes):
            delete_action = menu.addAction("Delete..")
            delete_action.triggered.connect(lambda _checked=False: self.deleteRequested.emit())

        menu.exec(self._tree.viewport().mapToGlobal(point))

    def _on_selection_changed(
        self,
        selected: QItemSelection,
        deselected: QItemSelection,
    ) -> None:
        """Forward selection changes to listeners."""
        _ = selected, deselected
        self.selectionChanged.emit()
        self._update_summary()

    def collect_nodes(self, *, visible_only: bool) -> list[PathNode]:
        """Collect nodes from the model, optionally limited to visible rows."""
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

    def _update_summary(self) -> None:
        nodes = self.collect_nodes(visible_only=True)
        files = sum(1 for node in nodes if node.type == "file")
        dirs = sum(1 for node in nodes if node.type == "dir")
        total = len(nodes)
        parts = [f"Files: {files}", f"Folders: {dirs}", f"Total: {total}"]

        if self._highlight_rule_index is not None:
            highlight_files = 0
            highlight_dirs = 0
            if self._highlight_paths:
                for node in nodes:
                    if node.rel_path in self._highlight_paths:
                        if node.type == "file":
                            highlight_files += 1
                        else:
                            highlight_dirs += 1
            highlight_total = highlight_files + highlight_dirs
            parts.append(
                f"Highlighted: {highlight_total} ({highlight_files} files, {highlight_dirs} folders)"
            )

        self._summary_label.setText("   ".join(parts))

    def _build_regex(
        self,
        text: str,
        mode: SearchMode,
        case_sensitive: bool,
    ) -> QRegularExpression | None:
        """Build a regular expression reflecting the search request."""
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

    def _open_selected_in_file_manager(self) -> None:
        nodes = self.selected_nodes()
        if not nodes:
            QMessageBox.information(self, "Open", "Select at least one item to open.")
            return

        for node in nodes:
            self._open_path_in_file_manager(node.abs_path, node.type)

    def _open_path_in_file_manager(self, path: Path, node_type: str) -> None:
        system = platform.system()
        try:
            if system == "Darwin":
                command = "/usr/bin/open"
                if not Path(command).exists():
                    raise OSError("Could not locate the 'open' command.")
                if node_type == "file":
                    args = ["-R", str(path)]
                else:
                    args = [str(path)]
                QProcess.startDetached(command, args)
            elif system == "Windows":
                windows_dir = os.environ.get("WINDIR", r"C:\Windows")
                command_path = Path(windows_dir) / "explorer.exe"
                if not command_path.exists():
                    raise OSError("Could not locate the 'explorer.exe' command.")
                resolved = str(path.resolve())
                if node_type == "file":
                    args = ["/select,", resolved]
                else:
                    args = [resolved]
                QProcess.startDetached(str(command_path), args)
            else:
                xdg_command = which("xdg-open")
                if xdg_command is None:
                    raise OSError("Could not locate the 'xdg-open' command.")
                QProcess.startDetached(xdg_command, [str(path)])
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Open failed",
                f"Could not open {path} in the file manager.\n\n{exc}",
            )
