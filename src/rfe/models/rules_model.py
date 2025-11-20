# Filename: rules_model.py
# Author: Rich Lewis @RichLewis007
# Description: Rule model utilities for parsing and representing rclone-style filter rules.
#              Defines the Rule data structure and parsing functions for filter files.

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Rule:
    # Represents a single filter rule.

    action: str
    pattern: str
    lineno: int
    enabled: bool = True
    label: str | None = None
    color: str | None = None

    def display_label(self) -> str:
        # Return a human-friendly label including the action prefix.
        label = self.label or self.pattern
        return f"{self.action} {label}"


def parse_filter_file(path: Path) -> list[Rule]:
    # Parse a rclone filter file into Rule instances.
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

        if action == "+":
            pending_label = None
            pending_color = None
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
    # Split a rule line into its action token and pattern.
    if not line:
        return None, ""
    if line[0] in {"+", "-"}:
        pattern = line[1:].strip()
        pattern = re.split(r"\s+#", pattern, maxsplit=1)[0].rstrip()
        return line[0], pattern
    if line[0] == "!":
        return "!", line[1:].strip()
    return None, line


def _parse_metadata_comment(line: str) -> tuple[str, str] | None:
    # Extract (key, value) metadata from a comment line, if present.
    stripped = line.lstrip("#").strip()
    if ":" not in stripped:
        return None
    key, value = stripped.split(":", 1)
    key = key.strip().lower()
    value = value.strip()
    if key in {"label", "color"}:
        return key, value
    return None
