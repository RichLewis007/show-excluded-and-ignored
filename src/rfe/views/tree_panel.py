# Filename: tree_panel.py
# Author: Rich Lewis @RichLewis007
# Description: Tree view panel displaying filesystem matches. Manages the results tree view,
#              sorting, filtering, search functionality, and selection handling.

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
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from rfe.models.fs_model import PathNode, PathTreeModel
from rfe.models.match_engine import MatchEngine
from rfe.models.rules_model import Rule
from rfe.views.search_bar import SearchMode


class TreeFilterProxyModel(QSortFilterProxyModel):
    # Proxy model applying search text and rule filters.

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._search_regex: QRegularExpression | None = None
        self._rule_filter: set[int] | None = None
        self.setRecursiveFilteringEnabled(True)
        self.setSortRole(Qt.ItemDataRole.DisplayRole)
        # Enable dynamic sorting to ensure lessThan is called when sorting changes
        self.setDynamicSortFilter(True)
        # Set case-insensitive sorting as default for text columns
        # This ensures Name and Full Path columns sort case-insensitively
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_search_regex(self, regex: QRegularExpression | None) -> None:
        # Update the active search regex and re-filter the view.
        self._search_regex = regex
        self.invalidateFilter()

    def set_rule_filter(self, rule_indices: Sequence[int] | None) -> None:
        # Limit matches to the supplied rule indices.
        if rule_indices is None:
            self._rule_filter = None
        else:
            self._rule_filter = set(rule_indices)
        self.invalidateFilter()

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:  # type: ignore[override]
        # Custom comparison for numeric sorting of Size and Modified columns.
        # For text columns (Name, Full Path, etc.), the parent's lessThan is used
        # which respects setSortCaseSensitivity(Qt.CaseInsensitive) set in __init__.
        source_model = self.sourceModel()
        if source_model is None:
            return super().lessThan(left, right)

        if not isinstance(source_model, QStandardItemModel):
            return super().lessThan(left, right)

        # Validate indices before mapping
        if not left.isValid() or not right.isValid():
            return super().lessThan(left, right)

        # Verify indices belong to this proxy model
        if left.model() != self or right.model() != self:
            return super().lessThan(left, right)

        try:
            left_source = self.mapToSource(left)
            right_source = self.mapToSource(right)
        except (RuntimeError, ValueError):
            return super().lessThan(left, right)

        if not left_source.isValid() or not right_source.isValid():
            return super().lessThan(left, right)

        column = left.column()

        # Get the PathNode for raw value access (stored in column 0's UserRole)
        left_name_index = source_model.index(left_source.row(), 0, left_source.parent())
        right_name_index = source_model.index(right_source.row(), 0, right_source.parent())
        if not left_name_index.isValid() or not right_name_index.isValid():
            return super().lessThan(left, right)

        left_name_item = source_model.itemFromIndex(left_name_index)
        right_name_item = source_model.itemFromIndex(right_name_index)

        if left_name_item is None or right_name_item is None:
            return super().lessThan(left, right)

        node_left = left_name_item.data(Qt.ItemDataRole.UserRole)
        node_right = right_name_item.data(Qt.ItemDataRole.UserRole)

        # Size column (index 2): sort by raw byte size (numeric)
        if column == 2 and isinstance(node_left, PathNode) and isinstance(node_right, PathNode):
            size_left = node_left.size if node_left.size is not None else 0
            size_right = node_right.size if node_right.size is not None else 0
            return size_left < size_right

        # Modified column (index 3): sort by raw timestamp (numeric)
        if column == 3 and isinstance(node_left, PathNode) and isinstance(node_right, PathNode):
            mtime_left = node_left.mtime if node_left.mtime is not None else 0.0
            mtime_right = node_right.mtime if node_right.mtime is not None else 0.0
            return mtime_left < mtime_right

        # For all other columns (Name=0, Type=1, First Rule=4, All Rules=5, Full Path=6),
        # use the parent's lessThan which respects setSortCaseSensitivity(Qt.CaseInsensitive)
        # This ensures case-insensitive sorting for Name and Full Path columns
        return super().lessThan(left, right)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # type: ignore[override]
        # Decide whether a source-model row passes the current filters.
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
        # Return True when the node represented by ``index`` matches filters.
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
    # Wrapper around QTreeView for displaying root paths.

    deleteRequested = Signal()
    selectionChanged = Signal()
    soundToggled = Signal(bool)

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
        self._root_path: Path | None = None
        self._guard_item_change = False
        self._highlight_color_hex: str | None = None

        self._tree = QTreeView(self)
        self._tree.setModel(self._proxy)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setUniformRowHeights(True)
        self._tree.setSortingEnabled(True)
        self._tree.setAnimated(True)
        self._tree.setHeaderHidden(False)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)

        selection_model = self._tree.selectionModel()
        selection_model.selectionChanged.connect(self._on_selection_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)
        self._expand_all_button = QPushButton("Expand all", self)
        self._expand_all_button.clicked.connect(self.expand_all)
        self._collapse_all_button = QPushButton("Collapse all", self)
        self._collapse_all_button.clicked.connect(self.collapse_all)
        controls.addWidget(self._expand_all_button)
        controls.addWidget(self._collapse_all_button)
        controls.addStretch(1)
        layout.addLayout(controls)
        layout.addWidget(self._tree)
        self._summary_label = QLabel(self)
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._summary_label.setText("Files: 0   Folders: 0   Total: 0")

        summary_row = QHBoxLayout()
        summary_row.setContentsMargins(0, 0, 0, 0)
        summary_row.addWidget(self._summary_label, 1)
        summary_row.addStretch(1)

        self._sounds_toggle = QCheckBox("UI Sounds", self)
        self._sounds_toggle.setChecked(True)
        self._sounds_toggle.toggled.connect(self._on_sound_toggled)
        summary_row.addWidget(self._sounds_toggle, 0, Qt.AlignmentFlag.AlignRight)

        layout.addLayout(summary_row)
        self.setLayout(layout)

        self._model.itemChanged.connect(self._on_item_changed)

    def load_nodes(self, nodes: Sequence[PathNode], rules: Sequence[Rule]) -> None:
        # Load a fresh tree of nodes into the view.
        import logging

        logger = logging.getLogger(__name__)

        logger.debug("Starting load_nodes: %d nodes", len(nodes))
        self._model.load_nodes(nodes, rules)
        logger.debug("Model loaded, updating tree view")

        self._current_nodes = list(nodes)
        self._rules = list(rules)
        self._tree.expandToDepth(0)
        logger.debug("Tree expanded")

        header = self._tree.header()
        header.setStretchLastSection(True)

        # resizeColumnToContents is very slow with large datasets - only resize visible columns
        # or use a reasonable default width instead
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()  # Allow UI to update before expensive operation

        # Only resize first few columns, let the rest use stretch
        # This avoids measuring every cell which can freeze the UI
        column_count = self._model.columnCount()
        if len(nodes) < 1000:  # Only auto-resize for smaller datasets
            for column in range(min(3, column_count)):  # Only resize first 3 columns
                self._tree.resizeColumnToContents(column)
                QApplication.processEvents()  # Keep UI responsive
        else:
            # For large datasets, set reasonable default widths
            if column_count > 0:
                self._tree.setColumnWidth(0, 300)  # Name column
            if column_count > 1:
                self._tree.setColumnWidth(1, 80)  # Type column
            if column_count > 2:
                self._tree.setColumnWidth(2, 100)  # Size column

        logger.debug("Columns resized")
        QApplication.processEvents()

        logger.debug("Emitting selectionChanged and updating summary")
        self.selectionChanged.emit()
        QApplication.processEvents()

        self._update_summary()
        QApplication.processEvents()

        self._highlight_rule_index = None
        self._highlight_paths = set()
        self._model.highlight_rule(set(), None)
        logger.debug("load_nodes completed")

    def set_root_path(self, path: Path) -> None:
        # Record the root path in the widget's accessible metadata.
        self._root_path = path
        self._tree.setWhatsThis(f"Root path: {path}")

    def on_search_requested(self, text: str, mode: SearchMode, case_sensitive: bool) -> None:
        # Update the filter proxy based on a search request.
        regex = self._build_regex(text, mode, case_sensitive)
        self._proxy.set_search_regex(regex)
        self._update_summary()

    def on_rules_selection_changed(self, rule_indices: list[int] | None) -> None:
        # React to rule selection changes from the rules panel.
        if rule_indices is None:
            self._proxy.set_rule_filter(None)
        elif len(rule_indices) == 0:
            self._proxy.set_rule_filter([])
        else:
            self._proxy.set_rule_filter(rule_indices)
        self._update_summary()

    def on_rule_highlighted(self, payload: object) -> None:
        # Highlight rows that match the selected rule.
        if payload is None:
            self._highlight_rule_index = None
            self._highlight_color_hex = None
        else:
            index, color_hex = payload if isinstance(payload, tuple) else (None, None)
            if isinstance(index, int) and 0 <= index < len(self._rules):
                self._highlight_rule_index = index
                self._highlight_color_hex = color_hex if isinstance(color_hex, str) else None
            else:
                self._highlight_rule_index = None
                self._highlight_color_hex = None

        self._apply_highlight()
        self._update_summary()

    def selected_paths(self) -> list[Path]:
        # Return absolute paths for the current selection.
        return [node.abs_path for node in self.selected_nodes()]

    def selected_nodes(self) -> list[PathNode]:
        # Return ``PathNode`` objects for the current selection.
        nodes: list[PathNode] = []
        for index in self._tree.selectionModel().selectedRows():
            node = index.data(Qt.ItemDataRole.UserRole)
            if isinstance(node, PathNode):
                nodes.append(node)
        return nodes

    def expand_all(self) -> None:
        self._tree.expandAll()

    def collapse_all(self) -> None:
        self._tree.collapseAll()

    def _show_context_menu(self, point: QPoint) -> None:
        # Display a context menu with destructive actions.
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
        # Forward selection changes to listeners.
        _ = selected, deselected
        self.selectionChanged.emit()
        self._update_summary()

    def collect_nodes(self, *, visible_only: bool) -> list[PathNode]:
        # Collect nodes from the model, optionally limited to visible rows.
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
        import logging

        logger = logging.getLogger(__name__)
        logger.debug("_update_summary: collecting visible nodes")
        nodes = self.collect_nodes(visible_only=True)
        logger.debug("_update_summary: collected %d visible nodes", len(nodes))
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

    def _on_item_changed(self, item: QStandardItem) -> None:
        if self._guard_item_change:
            return
        if item.column() != 0:
            return

        node = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(node, PathNode) or node.type != "file":
            return

        new_name = item.text().strip()
        old_path = node.abs_path
        if not new_name or new_name == old_path.name:
            item.setText(old_path.name)
            return
        if "/" in new_name:
            QMessageBox.warning(self, "Rename failed", "File names cannot contain '/'.")
            self._reset_item_text(item, old_path.name)
            return

        parent_dir = old_path.parent
        new_path = parent_dir / new_name
        if new_path.exists():
            QMessageBox.warning(
                self,
                "Rename failed",
                f"A file named '{new_name}' already exists in {parent_dir}.",
            )
            self._reset_item_text(item, old_path.name)
            return

        try:
            old_path.rename(new_path)
        except OSError as exc:
            QMessageBox.warning(self, "Rename failed", f"Could not rename file:\n{exc}")
            self._reset_item_text(item, old_path.name)
            return

        node.abs_path = new_path
        if self._root_path and new_path.is_relative_to(self._root_path):
            node.rel_path = new_path.relative_to(self._root_path).as_posix()
        else:
            node.rel_path = new_path.name

        parent_item = item.parent() or self._model.invisibleRootItem()
        row = item.row()
        path_column = self._model.HEADERS.index("Full Path")
        path_item = parent_item.child(row, path_column)
        if path_item is not None:
            path_item.setText(str(new_path))

        if self._highlight_rule_index is not None:
            self._apply_highlight()
        self._update_summary()

    def _reset_item_text(self, item: QStandardItem, text: str) -> None:
        self._guard_item_change = True
        item.setText(text)
        self._guard_item_change = False

    def _apply_highlight(self) -> None:
        if self._highlight_rule_index is None or not (
            0 <= self._highlight_rule_index < len(self._rules)
        ):
            self._highlight_paths = set()
            self._model.highlight_rule(set(), None)
            return

        rule = self._rules[self._highlight_rule_index]
        engine = MatchEngine([rule], case_sensitive=True)
        paths = {
            node.rel_path
            for node in self.collect_nodes(visible_only=False)
            if engine.matching_rule_indexes(node.rel_path)
        }
        self._highlight_paths = paths

        color_hex = self._highlight_color_hex or rule.color or "#FFF59D"
        color = QColor(color_hex)
        if not color.isValid():
            color = QColor("#FFF59D")
        self._model.highlight_rule(paths, color)

    def _on_sound_toggled(self, checked: bool) -> None:
        self.soundToggled.emit(checked)

    def ui_sounds_enabled(self) -> bool:
        return self._sounds_toggle.isChecked()

    def _build_regex(
        self,
        text: str,
        mode: SearchMode,
        case_sensitive: bool,
    ) -> QRegularExpression | None:
        # Build a regular expression reflecting the search request.
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
