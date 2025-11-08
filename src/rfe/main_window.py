"""Main window implementation."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .services.config import SettingsStore
from .views.rules_panel import RulesPanel
from .views.search_bar import SearchBar
from .views.status_bar import AppStatusBar
from .views.tree_panel import TreePanel
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
        super().__init__(parent)
        self._root_path = root_path
        self._filter_file = filter_file
        self._settings_store = settings_store

        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None

        self.setWindowTitle("Show Excluded and Ignored")
        self.resize(1200, 800)
        logger.debug("MainWindow initialized: root=%s filter=%s", root_path, filter_file)

        self._init_ui()
        self._restore_state()
        self._load_initial_data()

    def _init_ui(self) -> None:
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

        self._make_connections()

    def _create_central_layout(self, splitter: QSplitter) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(splitter)
        return layout

    def _make_connections(self) -> None:
        self.search_bar.searchRequested.connect(self.tree_panel.on_search_requested)
        self.rules_panel.selectionChanged.connect(self.tree_panel.on_rules_selection_changed)

    def _restore_state(self) -> None:
        geometry = self._settings_store.load_window_geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            logger.debug("No previous window geometry stored.")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._cancel_active_scan(wait=True)
        self._settings_store.save_window_geometry(self.saveGeometry())
        super().closeEvent(event)

    def _load_initial_data(self) -> None:
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
        self._cancel_active_scan(wait=True)

        if not self.rules_panel.rules:
            self.status_bar.set_message("No rules loaded.")
            self.tree_panel.load_nodes([], [])
            self._set_scan_ui_enabled(True)
            return

        self.status_bar.set_message("Starting scan…")
        self.status_bar.set_progress(None)
        self._set_scan_ui_enabled(False)

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
        if self._scan_worker is not None:
            self._scan_worker.request_cancel()
        if self._scan_thread is not None:
            self._scan_thread.quit()
            if wait:
                self._scan_thread.wait(3000)

    def _on_scan_progress(self, scanned: int, matched: int, current_path: str) -> None:
        parts = [f"Scanning… {matched} matches / {scanned} items"]
        if current_path and current_path not in {"", "done"}:
            parts.append(current_path)
        self.status_bar.set_message(" — ".join(parts))

    def _on_scan_finished(self, payload: ScanPayload) -> None:
        self.tree_panel.load_nodes(payload.nodes, self.rules_panel.rules)
        duration = payload.stats.duration
        duration_text = f"{duration:.2f}s" if duration is not None else "n/a"
        self.status_bar.set_message(
            f"Scan complete: {payload.stats.matched} matches across "
            f"{payload.stats.scanned} items in {duration_text}",
        )
        self.status_bar.set_progress(None)
        self._set_scan_ui_enabled(True)

    def _on_scan_error(self, message: str) -> None:
        self.status_bar.set_message("Scan failed.")
        self._set_scan_ui_enabled(True)
        QMessageBox.critical(self, "Scan failed", message)

    def _on_scan_cancelled(self) -> None:
        self.status_bar.set_message("Scan cancelled.")
        self.status_bar.set_progress(None)
        self._set_scan_ui_enabled(True)

    def _on_scan_thread_finished(self) -> None:
        self._scan_thread = None
        self._scan_worker = None

    def _set_scan_ui_enabled(self, enabled: bool) -> None:
        self.rules_panel.setEnabled(enabled)
        self.search_bar.setEnabled(enabled)
