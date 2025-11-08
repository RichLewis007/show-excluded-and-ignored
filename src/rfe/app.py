"""Application entry point for Show Excluded and Ignored."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .services import config as config_service
from .services import logger as logger_service

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILTER_FILE = REPO_ROOT / "rclone-filter-list.txt"
DEFAULT_ROOT_PATH = Path("/Users/rich/Downloads")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="show-excluded-and-ignored",
        description="Visualize files and folders matched by rclone-style filter rules.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT_PATH,
        help="Root directory to scan (default: %(default)s).",
    )
    parser.add_argument(
        "--filter-file",
        type=Path,
        default=DEFAULT_FILTER_FILE,
        help="Filter file containing rclone-style glob rules (default: %(default)s).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set application log level.",
    )
    return parser


def _ensure_qapp() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("Show Excluded and Ignored")
    app.setOrganizationName("RichLewis")
    app.setOrganizationDomain("show-excluded-and-ignored.local")
    return app


def _resolve_defaults(root: Path, filter_file: Path) -> tuple[Path, Path]:
    root = root.expanduser()
    filter_file = filter_file.expanduser()

    if not root.exists():
        logging.getLogger(__name__).warning("Root path %s does not exist.", root)

    if not filter_file.exists():
        logging.getLogger(__name__).warning("Filter file %s does not exist.", filter_file)

    return root, filter_file


def main(argv: list[str] | None = None) -> int:
    """Entry point for console scripts."""
    if argv is None:
        argv = sys.argv[1:]

    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logger_service.configure(log_level=args.log_level)
    logger = logging.getLogger(__name__)
    logger.debug("Starting application with argv=%s", argv)

    config_dir = config_service.ensure_app_dirs()
    logger.debug("Config directory located at %s", config_dir)

    root_path, filter_file = _resolve_defaults(args.root, args.filter_file)

    app = _ensure_qapp()
    window = MainWindow(
        root_path=root_path,
        filter_file=filter_file,
        settings_store=config_service.SettingsStore(),
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
