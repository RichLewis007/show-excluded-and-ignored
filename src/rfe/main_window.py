# Filename: main_window.py
# Author: Rich Lewis @RichLewis007
# Description: Main window implementation for Ghost Files Finder. Manages the primary application
#              window, toolbar, menu bar, scan workflow, and coordinates all UI components.

from __future__ import annotations

import csv
import json
import logging
import re
import sys
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QGroupBox,
    QMainWindow,
    QMessageBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .models.fs_model import PathNode
from .models.rules_model import parse_filter_file
from .services.config import SettingsStore
from .services.formatting import format_bytes, format_match_bytes
from .services.sounds import SoundManager, build_default_sound_manager
from .views.about_dialog import AboutDialog
from .views.rules_panel import RulesPanel
from .views.scan_progress_dialog import ScanProgressDialog
from .views.search_bar import SearchBar
from .views.status_bar import AppStatusBar
from .views.tree_panel import TreePanel
from .workers.delete_worker import DeleteResult, DeleteWorker
from .workers.scan_worker import ScanPayload, ScanWorker

logger = logging.getLogger(__name__)

ICON_ROOT = Path(__file__).resolve().parent / "resources" / "icons" / "feather"


# Enable developer shortcuts when true (e.g., auto-preload scan inputs).
DEBUG_MODE = True


def _icon(name: str) -> QIcon:
    # Load a Feather icon from the bundled resources, logging a warning if missing.
    path = ICON_ROOT / f"{name}.svg"
    if not path.exists():
        logger.warning("Toolbar icon missing: %s", path)
        return QIcon()
    return QIcon(str(path))


class MainWindow(QMainWindow):
    # Primary UI window.

    def __init__(
        self,
        *,
        root_path: Path,
        filter_file: Path,
        settings_store: SettingsStore,
        parent: QWidget | None = None,
    ) -> None:
        # Initialise the main window and restore user preferences.
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
        self._sound_manager: SoundManager = build_default_sound_manager(self)
        self._controls_enabled = True
        self._last_scan_nodes: list[PathNode] = []
        self._last_export_format = self._settings_store.load_export_format()
        self._export_visible_only = self._settings_store.load_export_visible_only()
        self._scan_running = False
        self._scan_paused = False
        self._progress_dialog: ScanProgressDialog | None = None
        self._current_match_bytes = 0
        self._root_selected = DEBUG_MODE and self._root_path.exists()
        self._rules_selected = DEBUG_MODE and self._filter_file.exists()
        self._about_shown = False

        self.setWindowTitle("Ghost Files Finder")
        self.resize(1200, 800)
        logger.debug("MainWindow initialized: root=%s filter=%s", root_path, filter_file)

        self._init_ui()
        self._restore_state()
        self._load_initial_data()

    def _init_ui(self) -> None:
        # Create child widgets and compose the layout.
        self.rules_panel = RulesPanel(self)
        rules_dock = QDockWidget("Rules", self)
        rules_dock.setWidget(self.rules_panel)
        rules_dock.setMinimumWidth(260)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, rules_dock)

        self.tree_panel = TreePanel(self)

        central = QWidget(self)
        layout = self._create_central_layout()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.search_bar = SearchBar(self)
        layout.insertWidget(0, self.search_bar)
        layout.setStretch(0, 0)
        layout.setStretch(1, 1)

        self.status_bar = AppStatusBar(self)
        self.setStatusBar(self.status_bar)

        self._create_actions()
        self._make_connections()
        self._sound_manager.set_enabled(self.tree_panel.ui_sounds_enabled())

    def _create_actions(self) -> None:
        # Build the window toolbar and key QAction objects.
        toolbar = QToolBar("Main actions", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        toolbar.setIconSize(QSize(28, 28))
        self.addToolBar(toolbar)

        self.select_root_action = QAction("Source folder..", self)
        self.select_root_action.triggered.connect(
            self._wrap_with_click_sound(self._prompt_select_root)
        )
        self.select_root_action.setIcon(_icon("folder"))
        self.select_root_action.setToolTip("Choose source folder")
        toolbar.addAction(self.select_root_action)

        self.open_action = QAction("Rules file..", self)
        self.open_action.triggered.connect(
            self._wrap_with_click_sound(self._prompt_open_filter_file)
        )
        self.open_action.setIcon(_icon("file-text"))
        self.open_action.setToolTip("Open rules file")
        toolbar.addAction(self.open_action)

        self.scan_action = QAction("Scan", self)
        self.scan_action.triggered.connect(self._wrap_with_click_sound(self._start_scan))
        self.scan_action.setIcon(_icon("play"))
        self.scan_action.setToolTip("Start scanning")
        toolbar.addAction(self.scan_action)

        # self.delete_action = QAction("Delete..", self)
        # self.delete_action.setEnabled(False)
        # self.delete_action.triggered.connect(self._prompt_delete_selection)
        # self.delete_action.setIcon(_icon("trash-2"))
        # self.delete_action.setToolTip("Delete selected files")
        # toolbar.addAction(self.delete_action)

        self.export_action = QAction("Export results..", self)
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self._wrap_with_click_sound(self._prompt_export))
        self.export_action.setIcon(_icon("download"))
        self.export_action.setToolTip("Export visible results")
        toolbar.addAction(self.export_action)

        toolbar.addSeparator()

        self.quit_action = QAction("Quit", self)
        self.quit_action.triggered.connect(
            self._wrap_with_click_sound(self._prompt_exit, sound="secondary")
        )
        self.quit_action.setIcon(_icon("log-out"))
        self.quit_action.setToolTip("Quit Ghost Files Finder")
        toolbar.addAction(self.quit_action)

        # macOS system menu (appears in menu bar under app name)
        if sys.platform == "darwin":
            # Enable native menu bar so macOS handles app menu automatically
            # This integrates the menu bar with the macOS system menu bar
            self.menuBar().setNativeMenuBar(True)

            # On macOS, Qt automatically moves actions with AboutRole and QuitRole
            # to the Application menu (the first menu in the system menu bar).
            # We create the first menu which becomes the Application menu on macOS.
            # The menu title will be replaced by the app icon/name on macOS.
            app_menu = self.menuBar().addMenu("")  # First menu becomes Application menu on macOS

            # Add "About Ghost Files Finder" with AboutRole
            # Qt automatically moves this to the Application menu
            about_action = QAction("About Ghost Files Finder", self)
            about_action.setMenuRole(QAction.MenuRole.AboutRole)
            about_action.triggered.connect(self._show_about_dialog)
            app_menu.addAction(about_action)

            # Add separator - appears after About in the Application menu
            app_menu.addSeparator()

            # Add "Quit Ghost Files Finder" with QuitRole
            # Qt automatically moves this to the Application menu (with Cmd+Q shortcut)
            quit_macos_action = QAction("Quit Ghost Files Finder", self)
            quit_macos_action.setMenuRole(QAction.MenuRole.QuitRole)
            quit_macos_action.setShortcut(QKeySequence.StandardKey.Quit)  # Cmd+Q
            quit_macos_action.triggered.connect(
                self._wrap_with_click_sound(self._prompt_exit, sound="secondary")
            )
            app_menu.addAction(quit_macos_action)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.scan_action)
        file_menu.addAction(self.select_root_action)
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addAction(self.quit_action)

        self._set_scan_running(False)

    def _create_central_layout(self) -> QVBoxLayout:
        # Return the central layout containing the results tree and search.
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.results_group = QGroupBox("Results", self)
        results_layout = QVBoxLayout()
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(0)
        results_layout.addWidget(self.tree_panel)
        self.results_group.setLayout(results_layout)
        layout.addWidget(self.results_group, 1)
        return layout

    def _make_connections(self) -> None:
        # Connect cross-widget signals and slots.
        self.search_bar.searchRequested.connect(self.tree_panel.on_search_requested)
        self.rules_panel.selectionChanged.connect(self.tree_panel.on_rules_selection_changed)
        self.rules_panel.ruleHighlighted.connect(self.tree_panel.on_rule_highlighted)
        self.tree_panel.selectionChanged.connect(self._update_action_states)
        self.tree_panel.deleteRequested.connect(self._prompt_delete_selection)
        self.tree_panel.soundToggled.connect(self._on_sound_toggled)

    def _restore_state(self) -> None:
        # Restore geometry and other persisted UI state.
        geometry = self._settings_store.load_window_geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)
            # Ensure the window is on a visible screen after restoration
            self._ensure_window_on_screen()
        else:
            logger.debug("No previous window geometry stored.")

    def _ensure_window_on_screen(self) -> None:
        # Ensure the window frame geometry is visible on at least one screen.
        # Qt's restoreGeometry() should restore the window to the correct monitor,
        # but if that monitor is disconnected, we need to move it to a valid screen.
        screens = QGuiApplication.screens()

        if not screens:
            return

        # Wait a moment for geometry to be fully restored
        # Then check if window is visible on any screen
        QTimer.singleShot(10, lambda: self._check_and_fix_window_position())

    def _check_and_fix_window_position(self) -> None:
        # Check if the window is visible on any screen and fix if needed.
        frame_rect = self.frameGeometry()
        screens = QGuiApplication.screens()

        if not screens:
            return

        # Check if any part of the window is visible on any screen
        visible_on_screen = False
        target_screen = None

        for screen in screens:
            available = screen.availableGeometry()
            # Check if the window's top-left corner is on this screen
            window_top_left = frame_rect.topLeft()
            if available.contains(window_top_left):
                visible_on_screen = True
                target_screen = screen
                break
            # Also check if any part of the window intersects this screen
            if available.intersects(frame_rect):
                visible_on_screen = True
                if target_screen is None:
                    target_screen = screen

        if not visible_on_screen or target_screen is None:
            # Window is off-screen, try to find the screen that was used last time
            # or fall back to the primary screen
            primary_screen = QGuiApplication.primaryScreen()
            target_screen = primary_screen if primary_screen is not None else screens[0]

        if target_screen is not None:
            available = target_screen.availableGeometry()
            # Move window to the target screen, keeping it centered if possible
            current_size = frame_rect.size()
            x = available.x() + (available.width() - current_size.width()) // 2
            y = available.y() + (available.height() - current_size.height()) // 2
            # Ensure window fits on screen
            x = max(available.x(), min(x, available.right() - current_size.width()))
            y = max(available.y(), min(y, available.bottom() - current_size.height()))
            self.move(x, y)
            if not visible_on_screen:
                logger.debug(
                    "Window was off-screen, moved to screen '%s' at (%d, %d)",
                    target_screen.name(),
                    x,
                    y,
                )

    def showEvent(self, event: QShowEvent) -> None:
        # Show About dialog on first launch, after main window is fully visible and positioned.
        super().showEvent(event)
        if not self._about_shown:
            self._about_shown = True
            # Ensure the window is fully visible and positioned before showing the dialog
            self.raise_()
            self.activateWindow()
            # Use QTimer to delay showing the dialog until window is fully rendered
            # This ensures geometry is restored and window is on the correct screen
            QTimer.singleShot(100, self._show_about_dialog)

    def closeEvent(self, event: QCloseEvent) -> None:
        # Persist state and ensure background work stops before closing.
        if not (self._root_selected and self._rules_selected):
            self.status_bar.set_message("Select a source folder and rules file before scanning.")
            self._set_scan_running(False)
            return

        self._cancel_active_scan(wait=True)
        self._cancel_active_delete(wait=True)
        self._settings_store.save_window_geometry(self.saveGeometry())
        super().closeEvent(event)

    def _load_initial_data(self) -> None:
        # Kick off the initial rule load and directory scan.
        if not self._filter_file.exists():
            QMessageBox.warning(
                self,
                "Missing filter file",
                f"The default filter file was not found:\n{self._filter_file}",
            )
        else:
            self.rules_panel.load_rules_from_path(self._filter_file)

        self.tree_panel.set_root_path(self._root_path)
        self.status_bar.set_message("Ready to scan.")

    def _get_progress_dialog(self) -> ScanProgressDialog:
        # Lazily create the scan progress dialog.
        if self._progress_dialog is None:
            dialog = ScanProgressDialog(self, play_sound=self._sound_manager.play)
            dialog.scanRequested.connect(self._on_dialog_scan_requested)
            dialog.pauseRequested.connect(self._pause_scan)
            dialog.resumeRequested.connect(self._resume_scan)
            dialog.cancelRequested.connect(self._cancel_scan)
            self._progress_dialog = dialog
        return self._progress_dialog

    def _show_progress_dialog(self) -> ScanProgressDialog:
        # Display the modal scan progress dialog.
        dialog = self._get_progress_dialog()
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        if not dialog.isVisible():
            dialog.open()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    # ------------------------------------------------------------------
    # Scanning lifecycle

    def _start_scan(self) -> None:
        # Begin a background scan using the current rules and root path.
        self._cancel_active_scan(wait=True)
        self._last_scan_nodes = []

        if not self.rules_panel.rules:
            self.status_bar.set_message("No rules loaded.")
            self.tree_panel.load_nodes([], [])
            self._set_controls_enabled(True)
            self._set_scan_running(False)
            return

        self.status_bar.set_message("Starting scan…")
        self.status_bar.set_progress(None)
        self._set_controls_enabled(False)
        self._set_scan_running(True)
        self._scan_paused = False
        self._current_match_bytes = 0

        progress_dialog = self._show_progress_dialog()
        progress_dialog.prepare_for_scan(self._root_path, self._filter_file)

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
        # Request cancellation of the running scan thread.
        if self._scan_worker is not None:
            self._scan_worker.request_resume()
            self._scan_worker.request_cancel()
        if self._scan_thread is not None:
            self._scan_thread.quit()
            if wait:
                self._scan_thread.wait(3000)
            self._scan_thread = None
            self._scan_worker = None
            self._set_scan_running(False)
        self._scan_paused = False
        if self._progress_dialog is not None and not self._scan_running:
            self._progress_dialog.set_running(False)
            self._progress_dialog.set_paused(False)

    def _on_scan_progress(
        self,
        files: int,
        folders: int,
        matches: int,
        matched_bytes: int,
        elapsed: float,
        current_path: str,
    ) -> None:
        # Update progress feedback while scanning.
        self._current_match_bytes = matched_bytes
        parts = [
            "Scanning…",
            f"Files: {files:,}",
            f"Folders: {folders:,}",
            f"Matches: {matches:,}",
            f"Size of matches: {format_match_bytes(matched_bytes)}",
            f"Elapsed: {self._format_elapsed(elapsed)}",
        ]
        if current_path and current_path not in {"", "done"}:
            parts.append(current_path)
        self.status_bar.set_message(" — ".join(parts))
        if self._progress_dialog is not None:
            self._progress_dialog.update_progress(
                files,
                folders,
                matches,
                matched_bytes,
                elapsed,
                current_path,
            )

    def _on_scan_finished(self, payload: ScanPayload) -> None:
        # Handle completion of a scan by updating the tree and status.
        # Show processing state in dialog before the potentially long-running load_nodes call
        if self._progress_dialog is not None:
            self._progress_dialog.show_processing()
            # Force Qt to process events and repaint the dialog immediately
            QApplication.processEvents()

        # This call can take a while with many files, but user now knows what's happening
        self.tree_panel.load_nodes(payload.nodes, self.rules_panel.rules)

        duration = payload.stats.duration
        duration_text = self._format_elapsed(duration) if duration is not None else "n/a"
        size_text = format_match_bytes(payload.stats.matched_bytes)
        self.status_bar.set_message(
            f"Scan complete: {payload.stats.matched:,} matches across "
            f"{payload.stats.scanned:,} items in {duration_text} — Size of matches: {size_text}",
        )
        self.status_bar.set_progress(None)
        self._set_controls_enabled(True)
        self._last_scan_nodes = self.tree_panel.collect_nodes(visible_only=False)
        self._settings_store.save_last_paths(self._root_path, self._filter_file)
        self._update_action_states()
        self._set_scan_running(False)
        self._scan_paused = False
        self._sound_manager.play("complete")
        if self._progress_dialog is not None:
            self._progress_dialog.set_paused(False)
            self._progress_dialog.show_finished()

    def _on_scan_error(self, message: str) -> None:
        # Surface scan failures to the user.
        self.status_bar.set_message("Scan failed.")
        self._set_controls_enabled(True)
        QMessageBox.critical(self, "Scan failed", message)
        self._set_scan_running(False)
        self._scan_paused = False
        if self._progress_dialog is not None:
            self._progress_dialog.set_paused(False)
            self._progress_dialog.show_error("Scan failed.")

    def _on_scan_cancelled(self) -> None:
        # Reset UI after a cancelled scan.
        self.status_bar.set_message("Scan cancelled")
        self.status_bar.set_progress(None)
        self._set_controls_enabled(True)
        self._set_scan_running(False)
        self._scan_paused = False
        if self._progress_dialog is not None:
            self._progress_dialog.set_paused(False)
            self._progress_dialog.show_cancelled()

    def _on_scan_thread_finished(self) -> None:
        # Clear references once the scan thread exits.
        self._scan_thread = None
        self._scan_worker = None
        self._set_scan_running(False)
        self._scan_paused = False

    def _on_dialog_scan_requested(self) -> None:
        # Start a scan when requested via the progress dialog.
        if self._scan_running:
            if self._scan_paused:
                self._resume_scan()
            return
        self._start_scan()

    # ------------------------------------------------------------------
    # Filter file management

    def _prompt_open_filter_file(self) -> None:
        # Allow the user to choose a new rclone filter file.
        start_dir = (
            str(self._filter_file.parent) if self._filter_file.exists() else str(Path.home())
        )
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open filter file",
            start_dir,
            "Filter files (*.txt *.filter *.conf);;All files (*)",
        )
        if not filename:
            return

        path = Path(filename)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            QMessageBox.warning(
                self,
                "Invalid filter file",
                "The selected file is not valid UTF-8 text.",
            )
            return
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Open failed",
                f"Unable to read the selected file:\n{exc}",
            )
            return

        if "\x00" in text:
            QMessageBox.warning(
                self,
                "Invalid filter file",
                "The selected file appears to be binary data.",
            )
            return

        rule_line_pattern = re.compile(r"^\s*[!+-]\s*\S")
        if not any(rule_line_pattern.match(line) for line in text.splitlines()):
            QMessageBox.warning(
                self,
                "Invalid filter file",
                "The selected file does not contain any rclone-style filter rules.",
            )
            return

        rules = parse_filter_file(path)
        if not rules:
            QMessageBox.warning(
                self,
                "Unsupported rules",
                "No supported exclude rules (- or !) were found in the selected file.",
            )
            return

        self._filter_file = path
        self.rules_panel.load_rules_from_path(path)
        self.status_bar.set_message(f"Loaded filter rules from {path}")
        self._rules_selected = True
        self._update_action_states()

    def _prompt_select_root(self) -> None:
        # Allow the user to choose a new root directory to scan.
        start_dir = str(self._root_path) if self._root_path.exists() else str(Path.home())
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select root directory",
            start_dir,
        )
        if not directory:
            return

        path = Path(directory)
        if not path.exists():
            QMessageBox.warning(
                self,
                "Invalid root",
                "The selected directory does not exist.",
            )
            return

        self._root_path = path
        self.tree_panel.set_root_path(path)
        self.status_bar.set_message(f"Root path set to {path}")
        self._root_selected = True
        self._update_action_states()

    def _prompt_exit(self) -> None:
        # Confirm with the user before quitting the application.
        if DEBUG_MODE:
            self.close()
            return

        response = QMessageBox.question(
            self,
            "Quit Ghost Files Finder",
            "Quit the application and discard the currently collected results?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response == QMessageBox.StandardButton.Yes:
            self.close()

    # ------------------------------------------------------------------
    # Delete workflow

    def _prompt_delete_selection(self) -> None:
        # Ask the user to confirm deleting the current selection.
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

        file_nodes = [node for node in nodes if node.type == "file"]
        if not file_nodes:
            QMessageBox.information(
                self,
                "Delete",
                "Only files can be deleted. Select file entries and try again.",
            )
            return

        count = len(file_nodes)
        total_size = sum(node.size or 0 for node in file_nodes if node.size)
        preview_lines = [str(node.abs_path) for node in file_nodes[:10]]
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

        self._start_delete(file_nodes)

    def _start_delete(self, nodes: list[PathNode]) -> None:
        # Start the background delete worker for the given nodes.
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
        # Stop the delete worker if it is running.
        if self._delete_thread is not None:
            self._delete_thread.quit()
            if wait:
                self._delete_thread.wait(3000)
            self._delete_thread = None
            self._delete_worker = None

    def _on_delete_progress(self, current: int, total: int, path: str) -> None:
        # Update the status bar as items are deleted.
        self.status_bar.set_message(f"Deleting {current}/{total}: {path}")

    def _on_delete_error(self, message: str) -> None:
        # Collect delete errors for later display.
        self._delete_errors.append(message)

    def _on_delete_finished(self, result: DeleteResult) -> None:
        # Handle completion of the delete worker.
        if self._delete_errors:
            QMessageBox.warning(self, "Delete issues", "\n".join(self._delete_errors))

        summary = f"Deleted {len(result.removed)} item(s). {len(result.failed)} failed."
        self.status_bar.set_message(summary)
        self._set_controls_enabled(True)
        self._start_scan()

    def _on_delete_thread_finished(self) -> None:
        # Clean up delete worker state once the thread exits.
        self._delete_thread = None
        self._delete_worker = None
        self._delete_errors = []

    # ------------------------------------------------------------------
    # Export workflow

    def _prompt_export(self) -> None:
        # Display the export dialog and write out the selected format.
        if not self._last_scan_nodes:
            QMessageBox.information(self, "Export", "Nothing to export yet.")
            return

        scope_box = QMessageBox(self)
        scope_box.setWindowTitle("Export scope")
        scope_box.setText("Choose which rows to include in the export.")
        scope_box.setInformativeText(
            "Use the checkbox to restrict the export to the rows currently visible in the tree."
        )
        scope_box.setIcon(QMessageBox.Icon.Question)
        scope_box.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        visible_toggle = QCheckBox("Export only visible rows", scope_box)
        visible_toggle.setChecked(self._export_visible_only)
        scope_box.setCheckBox(visible_toggle)
        if scope_box.exec() != QMessageBox.StandardButton.Ok:
            return
        visible_only = visible_toggle.isChecked()
        self._export_visible_only = visible_only
        self._settings_store.save_export_visible_only(visible_only)

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
        # Infer an export format from the filename and dialog selection.
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
        # Write the export file in the requested format.
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
        # Return a JSON-serialisable representation of a node.
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
        # Return the primary and secondary rule labels for ``node``.
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
        # Enable or disable interactive controls and refresh state.
        self._controls_enabled = enabled
        self.rules_panel.setEnabled(enabled)
        self.search_bar.setEnabled(enabled)
        self.tree_panel.setEnabled(enabled)
        self._update_action_states()

    def _set_scan_running(self, running: bool) -> None:
        self._scan_running = running
        if hasattr(self, "scan_action"):
            ready = self._root_selected and self._rules_selected and self._controls_enabled
            self.scan_action.setEnabled(ready and not running)

    def _show_about_dialog(self) -> None:
        # Show the About dialog with version and copyright information.
        # Late import to avoid circular dependency
        from . import app as app_module

        about_dialog = AboutDialog(
            self,
            version=app_module.APP_VERSION,
            copyright_year=app_module.COPYRIGHT_YEAR,
        )
        about_dialog.exec()

    def _wrap_with_click_sound(
        self,
        handler: Callable[[], None],
        *,
        sound: str = "primary",
    ) -> Callable[[bool], None]:
        def wrapped(checked: bool = False) -> None:
            del checked
            self._sound_manager.play(sound)
            handler()

        return wrapped

    def _pause_scan(self) -> None:
        if not self._scan_running or self._scan_worker is None or self._scan_paused:
            return
        self._scan_paused = True
        self.status_bar.set_message("Scan Paused.")
        self.status_bar.set_progress(None)
        self._set_controls_enabled(True)
        self._scan_worker.request_pause()
        if self._progress_dialog is not None:
            self._progress_dialog.set_paused(True)

    def _cancel_scan(self) -> None:
        if not self._scan_running:
            if self._progress_dialog is not None:
                self._progress_dialog.hide()
            return
        self.status_bar.set_message("Scan cancelled.")
        self.status_bar.set_progress(None)
        self._scan_paused = False
        self._cancel_active_scan(wait=True)
        self._set_controls_enabled(True)

    def _resume_scan(self) -> None:
        if not self._scan_running or not self._scan_paused or self._scan_worker is None:
            return
        self._scan_paused = False
        self.status_bar.set_message("Resuming scan…")
        self._set_controls_enabled(False)
        self._scan_worker.request_resume()
        if self._progress_dialog is not None:
            self._progress_dialog.set_paused(False)

    def _on_sound_toggled(self, enabled: bool) -> None:
        self._sound_manager.set_enabled(enabled)

    def _update_action_states(self) -> None:
        # Ensure toolbar actions reflect current selection and data.
        has_selection = bool(self.tree_panel.selected_nodes())
        if hasattr(self, "delete_action"):
            self.delete_action.setEnabled(self._controls_enabled and has_selection)
        has_data = bool(self._last_scan_nodes)
        self.export_action.setEnabled(self._controls_enabled and has_data)
        self._set_scan_running(self._scan_running)

    @staticmethod
    def _format_size(num_bytes: int) -> str:
        # Return a human-readable string for ``num_bytes``.
        return format_bytes(num_bytes)

    @staticmethod
    def _format_elapsed(elapsed: float) -> str:
        # Return elapsed time formatted as seconds or minutes/seconds.
        total_seconds = max(round(elapsed), 0)
        if total_seconds < 60:
            return f"{total_seconds:,}s"
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:,}m {seconds:02d}s"

    @staticmethod
    def _format_mtime(timestamp: float | None) -> str | None:
        # Format a timestamp for presentation or return ``None``.
        if timestamp is None:
            return None
        return datetime.fromtimestamp(timestamp).isoformat(timespec="seconds")
