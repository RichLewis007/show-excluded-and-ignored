# Filename: scan_progress_dialog.py
# Author: Rich Lewis @RichLewis007
# Description: Scan progress dialog showing scanning status and statistics. Displays progress,
#              file counts, size of matches, elapsed time, and provides pause/resume/cancel controls.

from __future__ import annotations

from collections.abc import Callable
from html import escape
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPaintEvent, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from rfe.services.formatting import format_match_bytes

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class TransparentOverlay(QWidget):
    # Widget with semi-transparent background for overlay effect.

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._background_color = QColor(240, 240, 240, 128)  # 50% opacity

    def setBackgroundColor(self, color: QColor) -> None:
        # Set the semi-transparent background color.
        self._background_color = color
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        # Paint semi-transparent background.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self._background_color)
        super().paintEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        # Update when resized.
        super().resizeEvent(event)
        self.update()


BADGE_RUNNING_PATH = PROJECT_ROOT / "assets" / "in-app-ghost-pic.png"
BADGE_FINISHED_PATH = Path(__file__).resolve().parents[1] / "resources" / "ghost-scan-finished.png"
FEATHER_ICON_DIR = Path(__file__).resolve().parents[1] / "resources" / "icons" / "feather"


class ScanProgressDialog(QDialog):
    # Modal dialog showing background scan progress and controls.

    scanRequested = Signal()
    pauseRequested = Signal()
    resumeRequested = Signal()
    cancelRequested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        play_sound: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)

        # ------------------------------------------------------------------
        # "Scanning" modal dialog
        # ------------------------------------------------------------------

        self.setWindowTitle("Scaning Dialog")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.resize(800, 300)
        self._play_sound = play_sound

        # ------------------------------------------------------------------
        # scanning title

        self._summary_label = QLabel("Scanning...", self)
        self._summary_label.setWordWrap(True)
        summary_font = self._summary_label.font()
        summary_font.setPointSize(int(summary_font.pointSize() * 2))
        summary_font.setBold(True)
        self._summary_label.setFont(summary_font)
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._summary_label.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        )

        # ------------------------------------------------------------------
        # source folder

        bold_font = QFont(self.font())
        bold_font.setBold(True)

        self._source_value = QLabel("", self)
        self._source_value.setFont(bold_font)
        self._source_value.setWordWrap(True)
        self._source_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._source_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._source_value.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        )

        source_line = QHBoxLayout()
        source_line.setSpacing(6)
        source_prefix = QLabel("Scanning source folder:", self)
        source_line.addWidget(source_prefix, 0)
        source_line.addWidget(self._source_value, 1)

        # ------------------------------------------------------------------
        # rules file

        self._rules_value = QLabel("", self)
        self._rules_value.setFont(bold_font)
        self._rules_value.setWordWrap(True)
        self._rules_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._rules_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._rules_value.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        )

        rules_line = QHBoxLayout()
        rules_line.setSpacing(6)
        rules_prefix = QLabel("Rules file:", self)
        rules_line.addWidget(rules_prefix, 0)
        rules_line.addWidget(self._rules_value, 1)

        # ------------------------------------------------------------------
        # details box
        counts_layout = QVBoxLayout()
        counts_layout.setSpacing(6)
        counts_layout.setContentsMargins(16, 12, 16, 12)

        self._files_value = QLabel("0", self)
        self._files_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        digits_sample = "9,999,999,999"
        width_sample = self._files_value.fontMetrics().horizontalAdvance(digits_sample)
        self._files_value.setFixedWidth(width_sample)

        self._folders_value = QLabel("0", self)
        self._folders_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._folders_value.setFixedWidth(
            self._folders_value.fontMetrics().horizontalAdvance(digits_sample)
        )

        self._matches_value = QLabel("0", self)
        self._matches_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._matches_value.setFixedWidth(
            self._matches_value.fontMetrics().horizontalAdvance(digits_sample)
        )

        self._size_value = QLabel(format_match_bytes(0), self)
        self._size_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        size_sample = "999,999 PB"
        self._size_value.setFixedWidth(
            self._size_value.fontMetrics().horizontalAdvance(size_sample)
        )

        self._time_value = QLabel("0s", self)
        self._time_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._time_value.setFixedWidth(
            self._time_value.fontMetrics().horizontalAdvance(f"{digits_sample}s")
        )

        def add_count_row(label_text: str, value_widget: QLabel, *, bold: bool = False) -> None:
            row = QHBoxLayout()
            row.setSpacing(6)
            label = QLabel(label_text, self)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            label.setMinimumWidth(label.fontMetrics().horizontalAdvance("Time elapsed:"))
            if bold:
                label_font = QFont(label.font())
                label_font.setBold(True)
                label.setFont(label_font)
                value_font = QFont(value_widget.font())
                value_font.setBold(True)
                value_widget.setFont(value_font)
            row.addWidget(label)
            row.addWidget(value_widget)
            row.addStretch(1)
            counts_layout.addLayout(row)

        add_count_row("Files:", self._files_value)
        add_count_row("Folders:", self._folders_value)
        add_count_row("Matches:", self._matches_value, bold=True)
        add_count_row("Size of matches:", self._size_value, bold=True)
        add_count_row("Time elapsed:", self._time_value)

        self._path_label = QLabel("", self)
        self._path_label.setWordWrap(True)
        self._path_label.setTextFormat(Qt.TextFormat.RichText)
        self._path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._path_label.setMinimumHeight(52)
        self._path_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._path_label.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        )

        # ------------------------------------------------------------------
        # badge image at top right

        self._badge_label = QLabel(self)
        self._badge_label.setVisible(False)
        self._set_badge_image(BADGE_RUNNING_PATH)

        # ------------------------------------------------------------------
        # buttons

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        # Add stretch at the beginning to center the buttons
        button_layout.addStretch(1)

        self._pause_button = QPushButton("Pause", self)
        self._pause_button.setIcon(self._load_icon("pause"))
        self._pause_button.setIconSize(QSize(28, 28))
        self._pause_button.clicked.connect(self._on_pause_clicked)
        button_layout.addWidget(self._pause_button)

        self._cancel_button = QPushButton("Cancel", self)
        self._cancel_button.setIcon(self._load_icon("x-circle"))
        self._cancel_button.setIconSize(QSize(28, 28))
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        button_layout.addWidget(self._cancel_button)

        # Add stretch at the end to center the buttons
        button_layout.addStretch(1)
        self._paused = False

        # ------------------------------------------------------------------
        # details box

        details_layout = QVBoxLayout()
        details_layout.setSpacing(12)
        details_layout.addLayout(source_line)
        details_layout.addLayout(rules_line)
        counts_frame = QFrame(self)
        counts_frame.setFrameShape(QFrame.Shape.Box)
        counts_frame.setLineWidth(1)
        counts_frame.setLayout(counts_layout)
        counts_frame.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        )
        details_layout.addSpacing(10)  # add vertical spacing above counters box
        details_layout.addWidget(counts_frame, alignment=Qt.AlignmentFlag.AlignHCenter)
        details_layout.addStretch(1)

        self._details_widget = QWidget(self)
        self._details_widget.setLayout(details_layout)

        # ------------------------------------------------------------------
        # Top row: title (centered) and badge (right-aligned)
        # To truly center the title, we need to account for the badge width

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)

        # Add invisible spacer on left to match badge width (for true centering)
        left_spacer = QWidget(self)
        left_spacer.setFixedWidth(0)  # Will be updated when badge is set
        self._left_spacer = left_spacer
        top_row.addWidget(left_spacer)

        # Add stretch, title, stretch to center the title
        top_row.addStretch(1)
        top_row.addWidget(self._summary_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        top_row.addStretch(1)

        # Badge on the right
        top_row.addWidget(
            self._badge_label,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
        )
        self._badge_container = top_row  # Keep reference for compatibility

        # ------------------------------------------------------------------
        # Main vertical layout: top row, details, path, status, buttons
        # ------------------------------------------------------------------

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)
        main_layout.addLayout(top_row)
        main_layout.addWidget(self._details_widget)
        main_layout.addWidget(self._path_label)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)
        self.set_running(False)

        # ------------------------------------------------------------------
        # overlay message for processing scanned files
        # ------------------------------------------------------------------

        # Create overlay widget with semi-transparent background
        self._processing_overlay = TransparentOverlay(self)
        self._processing_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Create label for the text inside the overlay
        overlay_label = QLabel(self._processing_overlay)
        # Use rich text/HTML to set background color behind just the text
        overlay_label.setTextFormat(Qt.TextFormat.RichText)
        overlay_label.setText(
            '<span style="background-color: #f2f2f2; padding: 10px 20px;">Please wait while scanned files are processed..</span>'
        )
        overlay_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_label.setWordWrap(True)
        overlay_label.setStyleSheet(
            """
            QLabel {
                background-color: transparent;
                color: #333333;
                border: none;
                padding: 40px;
                font-size: 24px;
                font-weight: bold;
            }
            """
        )
        processing_font = self.font()
        processing_font.setPointSize(processing_font.pointSize() + 4)
        processing_font.setBold(True)
        overlay_label.setFont(processing_font)

        overlay_layout = QVBoxLayout(self._processing_overlay)
        # Set margins: (left, top, right, bottom)
        # Increase top margin to move text down, decrease to move it up
        overlay_layout.setContentsMargins(
            0, -40, 0, 0
        )  # Adjust top value (currently 100) to control vertical position
        overlay_layout.addWidget(overlay_label)

        self._processing_overlay.setVisible(False)
        self._processing_overlay.raise_()  # Ensure it's on top

    # ------------------------------------------------------------------
    # State helpers

    def prepare_for_scan(self, root_path: Path, filter_path: Path | None) -> None:
        # Prime the dialog before a new scan begins.
        self._summary_label.setText("Scanning...")
        self._source_value.setText(str(root_path))
        if filter_path is not None:
            self._rules_value.setText(str(filter_path))
        else:
            self._rules_value.setText("Not selected")
        self._path_label.setText(self._wrap_path(""))
        self._files_value.setText("0")
        self._folders_value.setText("0")
        self._matches_value.setText("0")
        self._size_value.setText(format_match_bytes(0))
        self._time_value.setText("0s")
        self._set_badge_image(BADGE_RUNNING_PATH)
        self.set_running(True)
        self.set_paused(False)

    def set_running(self, running: bool) -> None:
        # Toggle button availability based on scan activity.
        self._pause_button.setEnabled(running)
        self._cancel_button.setEnabled(True)
        self._cancel_button.setText("Cancel" if running else "Close")
        if not running:
            self.set_paused(False)

    def set_paused(self, paused: bool) -> None:
        # Update pause button state to reflect paused/resumed modes.
        self._paused = paused
        self._pause_button.setText("Resume" if paused else "Pause")

    def update_progress(
        self,
        files: int,
        folders: int,
        matches: int,
        matched_bytes: int,
        elapsed: float,
        current_path: str,
    ) -> None:
        # Update the progress details shown in the dialog.
        self._files_value.setText(f"{files:,}")
        self._folders_value.setText(f"{folders:,}")
        self._matches_value.setText(f"{matches:,}")
        self._size_value.setText(format_match_bytes(matched_bytes))
        self._time_value.setText(self._format_elapsed(elapsed))
        if current_path and current_path not in {"", "done"}:
            self._path_label.setText(self._wrap_path(current_path))
        else:
            self._path_label.setText(self._wrap_path(""))

    def _format_elapsed(self, elapsed: float) -> str:
        total_seconds = max(round(elapsed), 0)
        if total_seconds < 60:
            return f"{total_seconds:,}s"
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:,}m {seconds:02d}s"

    def resizeEvent(self, event: QResizeEvent) -> None:
        # Update overlay position and size when dialog is resized
        super().resizeEvent(event)
        if self._processing_overlay.isVisible():
            self._processing_overlay.setGeometry(0, 0, self.width(), self.height())

    def show_processing(self) -> None:
        # Display processing message overlay and grey out the dialog while files are processed.
        # Position overlay to cover entire dialog
        self._processing_overlay.setGeometry(0, 0, self.width(), self.height())
        self._processing_overlay.setVisible(True)
        self._processing_overlay.raise_()  # Bring to front

        # Grey out the dialog by applying a stylesheet that makes everything appear disabled
        # Use a muted color scheme and reduced contrast
        self.setStyleSheet(
            """
            ScanProgressDialog {
                background-color: #f0f0f0;
                color: #666666;
            }
            QLabel {
                color: #666666;
            }
            QPushButton {
                background-color: #e0e0e0;
                color: #999999;
                border: 1px solid #cccccc;
            }
            QFrame {
                border-color: #cccccc;
                background-color: #f8f8f8;
            }
            """
        )
        # Disable all buttons during processing
        self._pause_button.setEnabled(False)
        self._cancel_button.setEnabled(False)
        # Force immediate repaint so user sees the processing state
        self.repaint()

    def _show_completion(self, message: str, badge_path: Path) -> None:
        # Display completion message and reset controls.
        # Hide processing overlay if visible
        self._processing_overlay.setVisible(False)

        self._summary_label.setText(message)
        # Clear path label
        self._path_label.clear()
        self._set_badge_image(badge_path)
        # Clear any processing stylesheet
        self.setStyleSheet("")
        self.set_running(False)

    def show_finished(self) -> None:
        # Display completion message and reset controls.
        self._show_completion("Finished Scanning", BADGE_FINISHED_PATH)

    def show_error(self, message: str) -> None:
        # Display error feedback and reset controls.
        self._show_completion(message, BADGE_RUNNING_PATH)

    def show_cancelled(self) -> None:
        # Display cancellation message and reset controls.
        self._show_completion("Scan cancelled", BADGE_RUNNING_PATH)

    def _load_icon(self, name: str) -> QIcon:
        icon_path = FEATHER_ICON_DIR / f"{name}.svg"
        if icon_path.exists():
            return QIcon(str(icon_path))
        return QIcon()

    def _wrap_path(self, path: str) -> str:
        escaped = escape(path)
        escaped = escaped.replace("/", "/<wbr>").replace("\\", "\\<wbr>")
        return (
            "<div style='display:inline-block; width:100%; max-width:100%; "
            "box-sizing:border-box; word-wrap:break-word; word-break:break-all; "
            "text-align:left; padding:0 16px;'>"
            f"{escaped}"
            "</div>"
        )

    def _set_badge_image(self, path: Path) -> None:
        if not path.exists():
            if hasattr(self, "_left_spacer"):
                self._left_spacer.setFixedWidth(0)
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            if hasattr(self, "_left_spacer"):
                self._left_spacer.setFixedWidth(0)
            return
        scaled = pixmap.scaledToHeight(128, Qt.TransformationMode.SmoothTransformation)
        self._badge_label.setPixmap(scaled)
        self._badge_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self._badge_label.setVisible(True)
        # Update left spacer to match badge width for true centering
        if hasattr(self, "_left_spacer"):
            self._left_spacer.setFixedWidth(scaled.width())

    def _trigger_sound(self, sound_id: str) -> None:
        if self._play_sound is not None:
            self._play_sound(sound_id)

    def _on_pause_clicked(self) -> None:
        if self._paused:
            self._trigger_sound("primary")
            self.resumeRequested.emit()
        else:
            self._trigger_sound("secondary")
            self.pauseRequested.emit()

    def _on_cancel_clicked(self) -> None:
        self._trigger_sound("cancel")
        self.cancelRequested.emit()
