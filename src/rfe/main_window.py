"""Main window implementation."""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .models.fs_model import PathNode
from .services.config import SettingsStore
from .views.rules_panel import RulesPanel
from .views.search_bar import SearchBar
from .views.status_bar import AppStatusBar
from .views.tree_panel import TreePanel
from .workers.delete_worker import DeleteResult, DeleteWorker
from .workers.scan_worker import ScanPayload, ScanWorker

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Primary UI window."""

    def __init__(
        self,
        *,
        root_path: Path,
        filter_file: Path,
        settings_store: SettingsStore,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the main window and restore user preferences."""
        super().__init__(parent)
        last_root, last_filter = settings_store.load_last_paths()
        self._root_path = last_root if last_root and last_root.exists() else root_path
        self._filter_file = last_filter if last_filter and last_filter.exists() else filter_file
        self._settings_store = settings_store

        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._delete_thread: QThread | None = None
        self._delete_worker: DeleteWorker | None = None
        self._delete_errors: list[str] = []
        self._controls_enabled = True
        self._last_scan_nodes: list[PathNode] = []
        self._last_export_format = self._settings_store.load_export_format()

        self.setWindowTitle("Show Excluded and Ignored")
        self.resize(1200, 800)
        logger.debug("MainWindow initialized: root=%s filter=%s", root_path, filter_file)

        self._init_ui()
        self._restore_state()
        self._load_initial_data()

    def _init_ui(self) -> None:
        """Create child widgets and compose the layout."""
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        self.rules_panel = RulesPanel(self)
        rules_dock = QDockWidget("Rules", self)
        rules_dock.setWidget(self.rules_panel)
        rules_dock.setMinimumWidth(260)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, rules_dock)

        self.tree_panel = TreePanel(self)
        splitter.addWidget(self.tree_panel)

        central = QWidget(self)
        layout = self._create_central_layout(splitter)
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.search_bar = SearchBar(self)
        layout.insertWidget(0, self.search_bar)

        self.status_bar = AppStatusBar(self)
        self.setStatusBar(self.status_bar)

        self._create_actions()
        self._make_connections()

    def _create_actions(self) -> None:
        """Build the window toolbar and key QAction objects."""
        toolbar = QToolBar("Main actions", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.delete_action = QAction("Delete…", self)
        self.delete_action.setEnabled(False)
        self.delete_action.triggered.connect(self._prompt_delete_selection)
        toolbar.addAction(self.delete_action)

        self.export_action = QAction("Export…", self)
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self._prompt_export)
        toolbar.addAction(self.export_action)

    def _create_central_layout(self, splitter: QSplitter) -> QVBoxLayout:
        """Return the central layout containing the tree view and search."""
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(splitter)
        return layout

    def _make_connections(self) -> None:
        """Connect cross-widget signals and slots."""
        self.search_bar.searchRequested.connect(self.tree_panel.on_search_requested)
        self.rules_panel.selectionChanged.connect(self.tree_panel.on_rules_selection_changed)
        self.tree_panel.selectionChanged.connect(self._update_action_states)
        self.tree_panel.deleteRequested.connect(self._prompt_delete_selection)

    def _restore_state(self) -> None:
        """Restore geometry and other persisted UI state."""
        geometry = self._settings_store.load_window_geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            logger.debug("No previous window geometry stored.")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Persist state and ensure background work stops before closing."""
        self._cancel_active_scan(wait=True)
        self._cancel_active_delete(wait=True)
        self._settings_store.save_window_geometry(self.saveGeometry())
        super().closeEvent(event)

    def _load_initial_data(self) -> None:
        """Kick off the initial rule load and directory scan."""
        if not self._filter_file.exists():
            QMessageBox.warning(
                self,
                "Missing filter file",
                f"The default filter file was not found:\n{self._filter_file}",
            )
        else:
            self.rules_panel.load_rules_from_path(self._filter_file)

        self.tree_panel.set_root_path(self._root_path)
        self._start_scan()

    # ------------------------------------------------------------------
    # Scanning lifecycle

    def _start_scan(self) -> None:
        """Begin a background scan using the current rules and root path."""
        self._cancel_active_scan(wait=True)
        self._last_scan_nodes = []

        if not self.rules_panel.rules:
            self.status_bar.set_message("No rules loaded.")
            self.tree_panel.load_nodes([], [])
            self._set_controls_enabled(True)
            return

        self.status_bar.set_message("Starting scan…")
        self.status_bar.set_progress(None)
        self._set_controls_enabled(False)

        worker = ScanWorker(root_path=self._root_path, rules=self.rules_panel.rules)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.start)
        worker.progress.connect(self._on_scan_progress)
        worker.finished.connect(self._on_scan_finished)
        worker.error.connect(self._on_scan_error)
        worker.cancelled.connect(self._on_scan_cancelled)

        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        worker.cancelled.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_scan_thread_finished)

        self._scan_worker = worker
        self._scan_thread = thread
        thread.start()

    def _cancel_active_scan(self, *, wait: bool) -> None:
        """Request cancellation of the running scan thread."""
        if self._scan_worker is not None:
            self._scan_worker.request_cancel()
        if self._scan_thread is not None:
            self._scan_thread.quit()
            if wait:
                self._scan_thread.wait(3000)
            self._scan_thread = None
            self._scan_worker = None

    def _on_scan_progress(self, scanned: int, matched: int, current_path: str) -> None:
        """Update progress feedback while scanning."""
        parts = [f"Scanning… {matched} matches / {scanned} items"]
        if current_path and current_path not in {"", "done"}:
            parts.append(current_path)
        self.status_bar.set_message(" — ".join(parts))

    def _on_scan_finished(self, payload: ScanPayload) -> None:
        """Handle completion of a scan by updating the tree and status."""
        self.tree_panel.load_nodes(payload.nodes, self.rules_panel.rules)
        duration = payload.stats.duration
        duration_text = f"{duration:.2f}s" if duration is not None else "n/a"
        self.status_bar.set_message(
            f"Scan complete: {payload.stats.matched} matches across "
            f"{payload.stats.scanned} items in {duration_text}",
        )
        self.status_bar.set_progress(None)
        self._set_controls_enabled(True)
        self._last_scan_nodes = self.tree_panel.collect_nodes(visible_only=False)
        self._settings_store.save_last_paths(self._root_path, self._filter_file)
        self._update_action_states()

    def _on_scan_error(self, message: str) -> None:
        """Surface scan failures to the user."""
        self.status_bar.set_message("Scan failed.")
        self._set_controls_enabled(True)
        QMessageBox.critical(self, "Scan failed", message)

    def _on_scan_cancelled(self) -> None:
        """Reset UI after a cancelled scan."""
        self.status_bar.set_message("Scan cancelled.")
        self.status_bar.set_progress(None)
        self._set_controls_enabled(True)

    def _on_scan_thread_finished(self) -> None:
        """Clear references once the scan thread exits."""
        self._scan_thread = None
        self._scan_worker = None

    # ------------------------------------------------------------------
    # Delete workflow

    def _prompt_delete_selection(self) -> None:
        """Ask the user to confirm deleting the current selection."""
        if not self._controls_enabled:
            return

        nodes = self.tree_panel.selected_nodes()
        if not nodes:
            QMessageBox.information(
                self,
                "Delete",
                "Select one or more files to delete.",
            )
            return

        count = len(nodes)
        total_size = sum(node.size or 0 for node in nodes if node.size)
        preview_lines = [str(node.abs_path) for node in nodes[:10]]
        if count > 10:
            preview_lines.append(f"… and {count - 10} more")

        size_text = self._format_size(total_size) if total_size else "unknown"
        message = (
            f"Move {count} item(s) to Trash?\n\n"
            f"Size (files only): {size_text}\n\n"
            f"Items:\n" + "\n".join(preview_lines)
        )

        response = QMessageBox.question(
            self,
            "Confirm delete",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return

        self._start_delete(nodes)

    def _start_delete(self, nodes: list[PathNode]) -> None:
        """Start the background delete worker for the given nodes."""
        self._cancel_active_delete(wait=True)
        paths = [node.abs_path for node in nodes if node.type == "file"]
        if not paths:
            self.status_bar.set_message("No files selected for deletion.")
            return
        self.status_bar.set_message("Deleting selected items…")
        self._set_controls_enabled(False)
        self._delete_errors = []

        worker = DeleteWorker(paths)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.start)
        worker.progress.connect(self._on_delete_progress)
        worker.finished.connect(self._on_delete_finished)
        worker.error.connect(self._on_delete_error)

        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_delete_thread_finished)

        self._delete_worker = worker
        self._delete_thread = thread
        thread.start()

    def _cancel_active_delete(self, *, wait: bool) -> None:
        """Stop the delete worker if it is running."""
        if self._delete_thread is not None:
            self._delete_thread.quit()
            if wait:
                self._delete_thread.wait(3000)
            self._delete_thread = None
            self._delete_worker = None

    def _on_delete_progress(self, current: int, total: int, path: str) -> None:
        """Update the status bar as items are deleted."""
        self.status_bar.set_message(f"Deleting {current}/{total}: {path}")

    def _on_delete_error(self, message: str) -> None:
        """Collect delete errors for later display."""
        self._delete_errors.append(message)

    def _on_delete_finished(self, result: DeleteResult) -> None:
        """Handle completion of the delete worker."""
        if self._delete_errors:
            QMessageBox.warning(self, "Delete issues", "\n".join(self._delete_errors))

        summary = f"Deleted {len(result.removed)} item(s). {len(result.failed)} failed."
        self.status_bar.set_message(summary)
        self._set_controls_enabled(True)
        self._start_scan()

    def _on_delete_thread_finished(self) -> None:
        """Clean up delete worker state once the thread exits."""
        self._delete_thread = None
        self._delete_worker = None
        self._delete_errors = []

    # ------------------------------------------------------------------
    # Export workflow

    def _prompt_export(self) -> None:
        """Display the export dialog and write out the selected format."""
        if not self._last_scan_nodes:
            QMessageBox.information(self, "Export", "Nothing to export yet.")
            return

        filters = "Text files (*.txt);;CSV files (*.csv);;JSON files (*.json);;JSON Lines (*.jsonl)"
        initial_filter = {
            "lines": "Text files (*.txt)",
            "csv": "CSV files (*.csv)",
            "json": "JSON files (*.json)",
            "jsonl": "JSON Lines (*.jsonl)",
        }.get(self._last_export_format, "Text files (*.txt)")

        filename, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export matches",
            str(self._root_path),
            filters,
            initial_filter,
        )
        if not filename:
            return

        fmt = self._determine_export_format(filename, selected_filter)
        if fmt is None:
            QMessageBox.warning(self, "Export", "Unable to determine export format.")
            return

        choice = QMessageBox.question(
            self,
            "Export scope",
            "Export only visible rows?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return
        visible_only = choice == QMessageBox.StandardButton.Yes

        nodes = self.tree_panel.collect_nodes(visible_only=visible_only)
        if not nodes:
            QMessageBox.information(self, "Export", "Nothing to export with current view.")
            return

        try:
            self._write_export_file(Path(filename), fmt, nodes)
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return

        self._last_export_format = fmt
        self._settings_store.save_export_format(fmt)
        scope_text = "visible rows" if visible_only else "all matches"
        self.status_bar.set_message(f"Exported {len(nodes)} item(s) ({scope_text}).")

    def _determine_export_format(self, filename: str, selected_filter: str) -> str | None:
        """Infer an export format from the filename and dialog selection."""
        ext = Path(filename).suffix.lower()
        mapping = {
            ".txt": "lines",
            ".log": "lines",
            ".csv": "csv",
            ".json": "json",
            ".jsonl": "jsonl",
        }
        fmt = mapping.get(ext)
        if fmt:
            return fmt
        if "jsonl" in selected_filter.lower():
            return "jsonl"
        if "json" in selected_filter.lower():
            return "json"
        if "csv" in selected_filter.lower():
            return "csv"
        if "text" in selected_filter.lower():
            return "lines"
        return None

    def _write_export_file(self, filepath: Path, fmt: str, nodes: Iterable[PathNode]) -> None:
        """Write the export file in the requested format."""
        if fmt == "lines":
            text = "\n".join(str(node.abs_path) for node in nodes) + "\n"
            filepath.write_text(text, encoding="utf-8")
            return

        if fmt == "csv":
            with filepath.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["path", "type", "size", "mtime", "first_rule", "all_rules"])
                for node in nodes:
                    first_rule, all_rules = self._rule_labels(node)
                    writer.writerow(
                        [
                            str(node.abs_path),
                            node.type,
                            node.size if node.size is not None else "",
                            self._format_mtime(node.mtime),
                            first_rule or "",
                            "; ".join(all_rules),
                        ]
                    )
            return

        if fmt == "json":
            data = [self._node_payload(node) for node in nodes]
            filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return

        if fmt == "jsonl":
            with filepath.open("w", encoding="utf-8") as handle:
                for node in nodes:
                    handle.write(json.dumps(self._node_payload(node)) + "\n")
            return

        raise ValueError(f"Unsupported export format: {fmt}")

    def _node_payload(self, node: PathNode) -> dict[str, object]:
        """Return a JSON-serialisable representation of a node."""
        first_rule, all_rules = self._rule_labels(node)
        return {
            "abs_path": str(node.abs_path),
            "rel_path": node.rel_path,
            "type": node.type,
            "size": node.size,
            "mtime": self._format_mtime(node.mtime),
            "first_rule": first_rule,
            "all_rules": all_rules,
            "tags": list(node.tags),
        }

    def _rule_labels(self, node: PathNode) -> tuple[str | None, list[str]]:
        """Return the primary and secondary rule labels for ``node``."""
        first: str | None = None
        labels: list[str] = []
        rules = self.rules_panel.rules

        def rule_label(rule_index: int) -> str | None:
            if 0 <= rule_index < len(rules):
                rule = rules[rule_index]
                return rule.label or rule.pattern
            return None

        if node.rule_index is not None:
            first = rule_label(node.rule_index)
        for idx in node.rule_ids:
            label = rule_label(idx)
            if label and label not in labels:
                labels.append(label)
        if first and first not in labels:
            labels.insert(0, first)
        return first, labels

    # ------------------------------------------------------------------
    # Shared helpers

    def _set_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable interactive controls and refresh state."""
        self._controls_enabled = enabled
        self.rules_panel.setEnabled(enabled)
        self.search_bar.setEnabled(enabled)
        self.tree_panel.setEnabled(enabled)
        self._update_action_states()

    def _update_action_states(self) -> None:
        """Ensure toolbar actions reflect current selection and data."""
        has_selection = bool(self.tree_panel.selected_nodes())
        self.delete_action.setEnabled(self._controls_enabled and has_selection)
        has_data = bool(self._last_scan_nodes)
        self.export_action.setEnabled(self._controls_enabled and has_data)

    @staticmethod
    def _format_size(num_bytes: int) -> str:
        """Return a human-readable string for ``num_bytes``."""
        value = float(num_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if value < 1024:
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} PB"

    @staticmethod
    def _format_mtime(timestamp: float | None) -> str | None:
        """Format a timestamp for presentation or return ``None``."""
        if timestamp is None:
            return None
        return datetime.fromtimestamp(timestamp).isoformat(timespec="seconds")
