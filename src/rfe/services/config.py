# Filename: config.py
# Author: Rich Lewis @RichLewis007
# Description: Configuration helpers for persistent application settings. Wraps Qt QSettings
#              for storing window geometry, last-used paths, and user preferences.

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import PlatformDirs
from PySide6.QtCore import QByteArray, QSettings

APP_NAME = "GhostFilesFinder"
ORG_NAME = "Rich Lewis"

_KEY_WINDOW_GEOMETRY = "window/geometry"
_KEY_LAST_ROOT = "paths/last_root"
_KEY_LAST_FILTER = "paths/last_filter"
_KEY_RECENT_ROOTS = "paths/recent_roots"
_KEY_RECENT_FILTERS = "paths/recent_filters"
_KEY_EXPORT_FORMAT = "export/default_format"
_KEY_EXPORT_VISIBLE_ONLY = "export/visible_only"
_KEY_DEBUG_LOG_LEVEL = "logging/debug_level"
_KEY_UI_SOUNDS_ENABLED = "sounds/ui_enabled"
_KEY_COMPLETION_SOUND_ENABLED = "sounds/completion_enabled"

_RECENT_LIMIT = 5


def ensure_app_dirs() -> Path:
    # Ensure the configuration directories exist and return the config path.
    dirs = PlatformDirs(appname=APP_NAME, appauthor=ORG_NAME)
    config_path = Path(dirs.user_config_dir)
    log_path = Path(dirs.user_log_dir)
    data_path = Path(dirs.user_data_dir)

    for path in (config_path, log_path, data_path):
        path.mkdir(parents=True, exist_ok=True)

    return config_path


@dataclass(slots=True)
class SettingsStore:
    # Wrapper around Qt settings for app state persistence.

    filename: str = "settings.ini"
    _path: Path = field(init=False)
    _settings: QSettings = field(init=False)

    def __post_init__(self) -> None:
        # Initialise the underlying Qt settings store.
        config_dir = ensure_app_dirs()
        object.__setattr__(self, "_path", config_dir / self.filename)
        object.__setattr__(
            self,
            "_settings",
            QSettings(str(self._path), QSettings.Format.IniFormat),
        )

    # ------------------------------------------------------------------
    # Window geometry

    def load_window_geometry(self) -> QByteArray | None:
        # Return the previously stored window geometry, if any.
        value = self._settings.value(_KEY_WINDOW_GEOMETRY)
        if isinstance(value, QByteArray):
            return value
        return None

    def save_window_geometry(self, geometry: QByteArray) -> None:
        # Persist the provided window geometry snapshot.
        self._settings.setValue(_KEY_WINDOW_GEOMETRY, geometry)
        self._settings.sync()

    @property
    def path(self) -> Path:
        # Return the filesystem path backing the settings file.
        return self._path

    # ------------------------------------------------------------------
    # Last-used paths & recents

    def load_last_paths(self) -> tuple[Path | None, Path | None]:
        # Fetch the last-used root and filter file paths.
        root = self._settings.value(_KEY_LAST_ROOT, type=str)
        filt = self._settings.value(_KEY_LAST_FILTER, type=str)
        return (
            Path(root) if isinstance(root, str) and root else None,
            Path(filt) if isinstance(filt, str) and filt else None,
        )

    def save_last_paths(self, root: Path, filter_file: Path) -> None:
        # Persist the most recent root/filter combination and update recents.
        self._settings.setValue(_KEY_LAST_ROOT, str(root))
        self._settings.setValue(_KEY_LAST_FILTER, str(filter_file))
        self._settings.setValue(
            _KEY_RECENT_ROOTS,
            self._merge_recent(self.recent_roots(), str(root)),
        )
        self._settings.setValue(
            _KEY_RECENT_FILTERS,
            self._merge_recent(self.recent_filters(), str(filter_file)),
        )
        self._settings.sync()

    def recent_roots(self) -> list[str]:
        # Return the list of recently used root paths.
        return self._read_recent_list(_KEY_RECENT_ROOTS)

    def recent_filters(self) -> list[str]:
        # Return the list of recently used filter files.
        return self._read_recent_list(_KEY_RECENT_FILTERS)

    def _read_recent_list(self, key: str) -> list[str]:
        # Read and normalise a list setting from Qt.
        value = self._settings.value(key)
        if isinstance(value, list):
            return [str(item) for item in value if isinstance(item, str)]
        if isinstance(value, str):
            return [value]
        return []

    def _merge_recent(self, existing: Iterable[str], new_path: str) -> list[str]:
        # Insert new_path at the front of the recents list.
        items = [new_path]
        for item in existing:
            if item not in items:
                items.append(item)
        return items[:_RECENT_LIMIT]

    # ------------------------------------------------------------------
    # Export preferences

    def load_export_format(self, default: str = "lines") -> str:
        # Fetch the preferred export format, defaulting to default.
        value = self._settings.value(_KEY_EXPORT_FORMAT, type=str)
        return value or default

    def save_export_format(self, fmt: str) -> None:
        # Persist the preferred export format.
        self._settings.setValue(_KEY_EXPORT_FORMAT, fmt)
        self._settings.sync()

    def load_export_visible_only(self, default: bool = True) -> bool:
        # Return whether exports should default to visible rows only.
        value = self._settings.value(_KEY_EXPORT_VISIBLE_ONLY)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return default

    def save_export_visible_only(self, visible_only: bool) -> None:
        # Persist the user's export scope preference.
        self._settings.setValue(_KEY_EXPORT_VISIBLE_ONLY, visible_only)
        self._settings.sync()

    # ------------------------------------------------------------------
    # Sound preferences

    def load_ui_sounds_enabled(self, default: bool = True) -> bool:
        # Return whether UI sounds are enabled, defaulting to default.
        value = self._settings.value(_KEY_UI_SOUNDS_ENABLED)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return default

    def save_ui_sounds_enabled(self, enabled: bool) -> None:
        # Persist the user's UI sounds preference.
        self._settings.setValue(_KEY_UI_SOUNDS_ENABLED, enabled)
        self._settings.sync()

    def load_completion_sound_enabled(self, default: bool = True) -> bool:
        # Return whether completion sound is enabled, defaulting to default.
        value = self._settings.value(_KEY_COMPLETION_SOUND_ENABLED)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return default

    def save_completion_sound_enabled(self, enabled: bool) -> None:
        # Persist the user's completion sound preference.
        self._settings.setValue(_KEY_COMPLETION_SOUND_ENABLED, enabled)
        self._settings.sync()

    # ------------------------------------------------------------------
    # Logging preferences

    def load_debug_log_level(self, default: bool = False) -> bool:
        # Return whether debug log level is enabled, defaulting to default.
        value = self._settings.value(_KEY_DEBUG_LOG_LEVEL)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return default

    def save_debug_log_level(self, enabled: bool) -> None:
        # Persist the user's debug log level preference.
        self._settings.setValue(_KEY_DEBUG_LOG_LEVEL, enabled)
        self._settings.sync()
