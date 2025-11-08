"""Configuration helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import PlatformDirs
from PySide6.QtCore import QByteArray, QSettings

APP_NAME = "ShowExcludedAndIgnored"
ORG_NAME = "RichLewis"


def ensure_app_dirs() -> Path:
    """Ensure the configuration directories exist and return the config path."""
    dirs = PlatformDirs(appname=APP_NAME, appauthor=ORG_NAME)
    config_path = Path(dirs.user_config_dir)
    log_path = Path(dirs.user_log_dir)
    data_path = Path(dirs.user_data_dir)

    for path in (config_path, log_path, data_path):
        path.mkdir(parents=True, exist_ok=True)

    return config_path


@dataclass(slots=True)
class SettingsStore:
    """Wrapper around Qt settings for app state persistence."""

    filename: str = "settings.ini"
    _path: Path = field(init=False)
    _settings: QSettings = field(init=False)

    def __post_init__(self) -> None:
        config_dir = ensure_app_dirs()
        object.__setattr__(self, "_path", config_dir / self.filename)
        object.__setattr__(
            self,
            "_settings",
            QSettings(str(self._path), QSettings.Format.IniFormat),
        )

    def load_window_geometry(self) -> QByteArray | None:
        value = self._settings.value("window/geometry")
        if isinstance(value, QByteArray):
            return value
        return None

    def save_window_geometry(self, geometry: QByteArray) -> None:
        self._settings.setValue("window/geometry", geometry)
        self._settings.sync()

    @property
    def path(self) -> Path:
        return self._path
