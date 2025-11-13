from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QSoundEffect


class SoundManager(QObject):
    """Centralised helper that manages short UI sound effects."""

    def __init__(
        self,
        sounds: Mapping[str, Path],
        *,
        default_volume: float = 0.6,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._effects: dict[str, QSoundEffect] = {}
        self._enabled = True
        self._default_volume = max(0.0, min(default_volume, 1.0))
        for name, path in sounds.items():
            self.register(name, path)

    def register(self, name: str, path: Path, *, volume: float | None = None) -> None:
        if not path.exists():
            return
        effect = QSoundEffect(self)
        effect.setSource(QUrl.fromLocalFile(str(path)))
        effect.setMuted(False)
        effect.setLoopCount(1)
        effect.setVolume(self._normalise_volume(volume))
        self._effects[name] = effect

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_volume(self, volume: float) -> None:
        normalised = self._normalise_volume(volume)
        self._default_volume = normalised
        for effect in self._effects.values():
            effect.setVolume(normalised)

    def play(self, name: str) -> None:
        if not self._enabled:
            return
        effect = self._effects.get(name)
        if effect is None or effect.source().isEmpty():
            return
        if effect.isPlaying():
            effect.stop()
        effect.play()

    def _normalise_volume(self, volume: float | None) -> float:
        if volume is None:
            return self._default_volume
        return min(max(volume, 0.0), 1.0)


def build_default_sound_manager(parent: QObject | None = None) -> SoundManager:
    """Factory that initialises the standard application sound set."""

    audio_root = Path(__file__).resolve().parents[1] / "resources" / "audio"
    sounds = {
        "primary": audio_root / "tone-primary.wav",
        "secondary": audio_root / "tone-secondary.wav",
    }
    return SoundManager(sounds, parent=parent)
