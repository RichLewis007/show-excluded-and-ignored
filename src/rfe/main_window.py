"""Main window implementation."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
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
            self.tree_panel.load_demo_data(self.rules_panel.rules, self._root_path)

        self.tree_panel.set_root_path(self._root_path)
