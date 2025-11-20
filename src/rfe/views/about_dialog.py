# Filename: about_dialog.py
# Author: Rich Lewis @RichLewis007
# Description: About dialog displaying application information. Shows version, copyright,
#              license information, and application metadata.

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BADGE_IMAGE_PATH = PROJECT_ROOT / "assets" / "in-app-ghost-pic.png"


class AboutDialog(QDialog):
    # Modal dialog showing application information.

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        version: str = "1.0.0",
        copyright_year: str = "2025",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("About Ghost Files Finder")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.resize(500, 650)

        # Title
        title_label = QLabel("Ghost Files Finder", self)
        title_font = QFont(title_label.font())
        title_font.setPointSize(title_font.pointSize() + 12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Version
        version_label = QLabel(f"Version {version}", self)
        version_font = QFont(version_label.font())
        version_font.setPointSize(version_font.pointSize() + 1)
        version_label.setFont(version_font)
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Author
        author_label = QLabel("by Rich Lewis", self)
        author_font = QFont(author_label.font())
        author_font.setPointSize(author_font.pointSize() + 2)
        author_label.setFont(author_font)
        author_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Image
        image_label = QLabel(self)
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label = image_label
        self._set_image(BADGE_IMAGE_PATH)

        # Copyright
        copyright_label = QLabel(f"Copyright (c) {copyright_year} Rich Lewis", self)
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # License
        license_label = QLabel(
            "This software is licensed under the MIT License.\nSee LICENSE file for details.",
            self,
        )
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        license_label.setWordWrap(True)
        license_font = QFont(license_label.font())
        license_font.setPointSize(license_font.pointSize() - 1)
        license_label.setFont(license_font)

        # OK button
        ok_button = QPushButton("OK", self)
        ok_button.clicked.connect(self.accept)
        ok_button.setDefault(True)
        ok_button.setMinimumSize(QSize(120, 40))  # Make button larger (width, height)
        ok_button_font = ok_button.font()
        ok_button_font.setPointSize(ok_button_font.pointSize() + 2)
        ok_button.setFont(ok_button_font)

        # Layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 32, 32, 32)
        main_layout.setSpacing(16)
        main_layout.addStretch(1)
        main_layout.addWidget(title_label)
        main_layout.addWidget(version_label)
        main_layout.addWidget(author_label)
        main_layout.addSpacing(16)
        main_layout.addWidget(image_label, alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addSpacing(16)
        main_layout.addWidget(copyright_label)
        main_layout.addWidget(license_label)
        main_layout.addStretch(1)

        # Button layout centered at bottom
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(ok_button)
        button_layout.addStretch(1)
        main_layout.addLayout(button_layout)
        main_layout.addStretch(1)

        self.setLayout(main_layout)

    def showEvent(self, event: QShowEvent) -> None:
        # Ensure dialog appears on the same screen as parent window and is centered.
        super().showEvent(event)
        parent = self.parent()
        # Type check to ensure parent is a QWidget with screen() and frameGeometry() methods
        if isinstance(parent, QWidget):
            # Get parent window's screen
            parent_screen = parent.screen()
            if parent_screen is not None:
                # Center dialog on parent window
                parent_geometry = parent.frameGeometry()
                dialog_size = self.size()
                x = parent_geometry.x() + (parent_geometry.width() - dialog_size.width()) // 2
                y = parent_geometry.y() + (parent_geometry.height() - dialog_size.height()) // 2
                # Ensure dialog stays within the screen bounds
                screen_geometry = parent_screen.availableGeometry()
                x = max(screen_geometry.x(), min(x, screen_geometry.right() - dialog_size.width()))
                y = max(
                    screen_geometry.y(), min(y, screen_geometry.bottom() - dialog_size.height())
                )
                self.move(x, y)

    def _set_image(self, path: Path) -> None:
        # Set the badge image to a much larger size.
        if not path.exists():
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        # Scale to a much larger size (300 pixels wide)
        scaled = pixmap.scaledToWidth(300, Qt.TransformationMode.SmoothTransformation)
        if hasattr(self, "_image_label") and self._image_label is not None:
            self._image_label.setPixmap(scaled)
