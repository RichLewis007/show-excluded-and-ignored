# Filename: sounds.py
# Author: Rich Lewis @RichLewis007
# Description: Sound manager for UI audio feedback. Manages playback of sound effects for
#              user interactions using Qt Multimedia components.

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


@dataclass(slots=True)
class _PlayerBundle:
    player: QMediaPlayer
    output: QAudioOutput


@dataclass(slots=True)
class _SoundEntry:
    path: Path
    volume: float
    bundles: list[_PlayerBundle] = field(default_factory=list)


class SoundManager(QObject):
    """Centralised helper that manages UI sound effects."""

    def __init__(
        self,
        sounds: Mapping[str, Path],
        *,
        default_volume: float = 0.6,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._entries: dict[str, _SoundEntry] = {}
        self._enabled = True
        self._default_volume = max(0.0, min(default_volume, 1.0))
        for name, path in sounds.items():
            self.register(name, path)

    def register(self, name: str, path: Path, *, volume: float | None = None) -> None:
        if not path.exists():
            return
        entry = _SoundEntry(path=path, volume=self._normalise_volume(volume))
        entry.bundles.append(self._create_bundle(entry))
        self._entries[name] = entry

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_volume(self, volume: float) -> None:
        normalised = self._normalise_volume(volume)
        self._default_volume = normalised
        for entry in self._entries.values():
            entry.volume = normalised
            for bundle in entry.bundles:
                bundle.output.setVolume(normalised)

    def play(self, name: str) -> None:
        if not self._enabled:
            return
        entry = self._entries.get(name)
        if entry is None:
            return
        bundle = self._acquire_bundle(entry)
        if bundle is None:
            return
        self._start_bundle(bundle)

    def _acquire_bundle(self, entry: _SoundEntry) -> _PlayerBundle | None:
        for bundle in entry.bundles:
            if bundle.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                return bundle
        new_bundle = self._create_bundle(entry)
        entry.bundles.append(new_bundle)
        return new_bundle

    def _start_bundle(self, bundle: _PlayerBundle) -> None:
        player = bundle.player
        # Ensure playback starts from the beginning even if the player was paused.
        player.setPosition(0)
        player.play()

    def _normalise_volume(self, volume: float | None) -> float:
        if volume is None:
            return self._default_volume
        return min(max(volume, 0.0), 1.0)

    def _create_bundle(self, entry: _SoundEntry) -> _PlayerBundle:
        audio = QAudioOutput(self)
        audio.setVolume(entry.volume)

        player = QMediaPlayer(self)
        player.setAudioOutput(audio)
        player.setSource(QUrl.fromLocalFile(str(entry.path)))
        player.setLoops(1)
        player.setPlaybackRate(1.0)

        return _PlayerBundle(player=player, output=audio)

    # Backwards compatibility shim: older runtime builds may still try to call
    # the legacy slot used with QSoundEffect. Make it a no-op to avoid crashes.
    def _on_effect_status_changed(self, *_args: Any, **_kwargs: Any) -> None:
        return


def build_default_sound_manager(parent: QObject | None = None) -> SoundManager:
    """Factory that initialises the standard application sound set."""

    audio_root = Path(__file__).resolve().parents[1] / "resources" / "audio"
    sounds = {
        "primary": audio_root / "tone-primary.wav",
        "secondary": audio_root / "tone-secondary.wav",
        "pause": audio_root / "pause-button.wav",
        "cancel": audio_root / "cancel-button.wav",
        "complete": audio_root / "scan-complete-successful.wav",
    }
    return SoundManager(sounds, parent=parent)
