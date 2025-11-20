# Filename: formatting.py
# Author: Rich Lewis @RichLewis007
# Description: Formatting helpers for user-facing values. Provides functions to format
#              file sizes, byte counts, and other numeric values for display in the UI.

from __future__ import annotations

from typing import Final

_SIZE_UNITS: Final[tuple[str, ...]] = ("B", "KB", "MB", "GB", "TB", "PB", "EB")
_ONE_MEGABYTE: Final[int] = 1024**2


def format_bytes(
    num_bytes: int | float | None,
    *,
    empty: str = "",
    decimals: int = 2,
) -> str:
    """Return a human-friendly string for a byte count.

    The result always includes thousands separators and two decimal places,
    using binary multiples (powers of 1024) up to exabytes.
    """
    if num_bytes is None:
        return empty

    value = float(max(num_bytes, 0))
    decimals = max(decimals, 0)

    for unit in _SIZE_UNITS:
        if value < 1024 or unit == _SIZE_UNITS[-1]:
            return f"{value:,.{decimals}f} {unit}"
        value /= 1024

    # Fallback; loop always returns before reaching this line.
    return f"{value:,.{decimals}f} {_SIZE_UNITS[-1]}"


def format_match_bytes(num_bytes: int | float | None) -> str:
    """Return a match-size string with special handling under 1 MB."""
    if num_bytes is None or num_bytes < _ONE_MEGABYTE:
        return "<1 MB"
    return format_bytes(num_bytes, decimals=0)


__all__ = ["format_bytes", "format_match_bytes"]
