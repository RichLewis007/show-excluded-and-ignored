"""Rule model utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Rule:
    """Represents a single filter rule."""

    action: str
    pattern: str
    lineno: int
    enabled: bool = True
    label: str | None = None
    color: str | None = None

    def display_label(self) -> str:
        label = self.label or self.pattern
        return f"{self.action} {label}"


def parse_filter_file(path: Path) -> list[Rule]:
    """Parse a rclone filter file into Rule instances."""
    rules: list[Rule] = []
    pending_label: str | None = None
    pending_color: str | None = None

    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            pending_label = None
            pending_color = None
            continue

        if line.startswith("#"):
            key_value = _parse_metadata_comment(line)
            if key_value:
                key, value = key_value
                if key == "label":
                    pending_label = value
                elif key == "color":
                    pending_color = value
            continue

        action, pattern = _parse_rule_line(line)
        if action is None:
            continue

        rule = Rule(
            action=action,
            pattern=pattern,
            lineno=lineno,
            label=pending_label,
            color=pending_color,
        )
        rules.append(rule)
        pending_label = None
        pending_color = None

    return rules


def _parse_rule_line(line: str) -> tuple[str | None, str]:
    if not line:
        return None, ""
    if line[0] in {"+", "-"}:
        return line[0], line[1:].strip()
    if line[0] == "!":
        return "!", line[1:].strip()
    return None, line


def _parse_metadata_comment(line: str) -> tuple[str, str] | None:
    stripped = line.lstrip("#").strip()
    if ":" not in stripped:
        return None
    key, value = stripped.split(":", 1)
    key = key.strip().lower()
    value = value.strip()
    if key in {"label", "color"}:
        return key, value
    return None
