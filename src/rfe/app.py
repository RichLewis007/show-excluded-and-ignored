# Filename: app.py
# Author: Rich Lewis @RichLewis007
# Description: Application entry point for Ghost Files Finder. Handles application initialization,
#              argument parsing, macOS process metadata setup, and QApplication creation.

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .services import config as config_service
from .services import logger as logger_service

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILTER_FILE = REPO_ROOT / "tests" / "data" / "rclone-filter-list.txt"
DEFAULT_ROOT_PATH = Path("/Users/rich/Downloads")
APP_ICON_PATH = REPO_ROOT / "src" / "rfe" / "resources" / "icons" / "GhostFilesFinder.icns"

# Application version - update in pyproject.toml when changing
APP_VERSION = "1.0.0"
COPYRIGHT_YEAR = "2025"


def _build_arg_parser() -> argparse.ArgumentParser:
    # Construct and return the CLI argument parser.
    parser = argparse.ArgumentParser(
        prog="ghost-files-finder",
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


def _set_macos_process_metadata(name: str) -> None:
    # Update the running process metadata so macOS shows our app name.
    if sys.platform != "darwin":
        return
    try:
        from ctypes import CFUNCTYPE, c_char_p, c_void_p, cdll, util
    except ImportError:
        return

    libobjc_path = util.find_library("objc")
    if not libobjc_path:
        return

    try:
        objc = cdll.LoadLibrary(libobjc_path)
    except OSError:
        return

    objc.objc_getClass.restype = c_void_p
    objc.objc_getClass.argtypes = [c_char_p]
    objc.sel_registerName.restype = c_void_p
    objc.sel_registerName.argtypes = [c_char_p]

    msg_send = CFUNCTYPE(c_void_p, c_void_p, c_void_p)(("objc_msgSend", objc))
    msg_send_char = CFUNCTYPE(c_void_p, c_void_p, c_void_p, c_char_p)(("objc_msgSend", objc))
    msg_send_void = CFUNCTYPE(c_void_p, c_void_p, c_void_p, c_void_p)(("objc_msgSend", objc))
    msg_send_void_void = CFUNCTYPE(c_void_p, c_void_p, c_void_p, c_void_p, c_void_p)(
        ("objc_msgSend", objc)
    )

    NSString = objc.objc_getClass(b"NSString")
    if not NSString:
        return

    alloc = objc.sel_registerName(b"alloc")
    init_utf8 = objc.sel_registerName(b"initWithUTF8String:")

    def _ns_string(value: str) -> c_void_p:
        encoded = value.encode("utf-8")
        return msg_send_char(msg_send(NSString, alloc), init_utf8, encoded)

    ns_name = _ns_string(name)
    NSProcessInfo = objc.objc_getClass(b"NSProcessInfo")
    if NSProcessInfo:
        process_info = msg_send(NSProcessInfo, objc.sel_registerName(b"processInfo"))
        if process_info:
            msg_send_void(process_info, objc.sel_registerName(b"setProcessName:"), ns_name)

    NSBundle = objc.objc_getClass(b"NSBundle")
    if not NSBundle:
        return

    main_bundle = msg_send(NSBundle, objc.sel_registerName(b"mainBundle"))
    if not main_bundle:
        return

    info_dict = msg_send(main_bundle, objc.sel_registerName(b"infoDictionary"))
    if not info_dict:
        return

    set_object = objc.sel_registerName(b"setObject:forKey:")
    bundle_name_key = _ns_string("CFBundleName")
    bundle_display_key = _ns_string("CFBundleDisplayName")
    try:
        msg_send_void_void(info_dict, set_object, ns_name, bundle_name_key)
        msg_send_void_void(info_dict, set_object, ns_name, bundle_display_key)
    except (OSError, TypeError, ValueError):
        return


def _ensure_qapp() -> QApplication:
    # Return the active QApplication, creating one if needed.
    existing = QApplication.instance()
    if existing is not None:
        return existing

    app_name = "Ghost Files Finder"
    org_name = "Rich Lewis"
    org_domain = "ghost-files-finder.local"

    # Set macOS process metadata BEFORE creating QApplication for proper dock name
    _set_macos_process_metadata(app_name)

    # Set application metadata on QGuiApplication before QApplication
    QGuiApplication.setApplicationName(app_name)
    QGuiApplication.setApplicationDisplayName(app_name)
    QGuiApplication.setOrganizationName(org_name)
    QGuiApplication.setOrganizationDomain(org_domain)

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    # On macOS, set process name in argv before QApplication reads it
    if sys.platform == "darwin" and sys.argv:
        # Replace the script name with the app name
        sys.argv[0] = app_name

    app = QApplication(sys.argv)
    app.setApplicationName(app_name)
    app.setApplicationDisplayName(app_name)
    app.setOrganizationName(org_name)
    app.setOrganizationDomain(org_domain)
    if APP_ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    return app


def _resolve_defaults(root: Path, filter_file: Path) -> tuple[Path, Path]:
    # Expand user paths and emit warnings for missing paths.
    root = root.expanduser()
    filter_file = filter_file.expanduser()

    if not root.exists():
        logging.getLogger(__name__).warning("Root path %s does not exist.", root)

    if not filter_file.exists():
        logging.getLogger(__name__).warning("Filter file %s does not exist.", filter_file)

    return root, filter_file


def main(argv: list[str] | None = None) -> int:
    # Entry point for console scripts.
    # IMPORTANT: Set macOS process name FIRST, before any other imports or Qt initialization
    # This must happen before QApplication is created for dock/task switcher to show correct name
    if sys.platform == "darwin":
        _set_macos_process_metadata("Ghost Files Finder")

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
