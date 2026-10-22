"""Helpers for the dashboard theme colours.

A colour is stored either as a hex string (``#1F1711``) or as an RGB list
(``[31, 23, 17]``). The options flow writes hex strings, the panel writes RGB
lists, and every reader accepts both.
"""

from __future__ import annotations

from typing import Any


def is_hex(value: Any) -> bool:
    """Return True when a value is a hex colour such as #1F1711."""
    if not isinstance(value, str):
        return False
    text = value.strip().lstrip("#")
    if len(text) != 6:
        return False
    try:
        int(text, 16)
    except ValueError:
        return False
    return True


def to_hex(value: Any, fallback: list[int]) -> str:
    """Return a colour as #RRGGBB, whatever shape it is stored in."""
    if isinstance(value, str):
        text = value.strip().lstrip("#")
        if len(text) == 6:
            try:
                return "#" + "".join(
                    f"{int(text[index:index + 2], 16):02X}" for index in (0, 2, 4)
                )
            except ValueError:
                pass
        value = fallback
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        value = fallback
    try:
        rgb = [max(0, min(255, int(channel))) for channel in value]
    except (TypeError, ValueError):
        rgb = [max(0, min(255, int(channel))) for channel in fallback]
    return "#" + "".join(f"{channel:02X}" for channel in rgb)


def to_rgb(value: Any, fallback: list[int]) -> list[int]:
    """Return a colour as an RGB list, whatever shape it is stored in."""
    if isinstance(value, str):
        text = value.strip().lstrip("#")
        if len(text) == 6:
            try:
                return [
                    max(0, min(255, int(text[index:index + 2], 16)))
                    for index in (0, 2, 4)
                ]
            except ValueError:
                pass
        value = fallback
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        value = fallback
    try:
        return [max(0, min(255, int(channel))) for channel in value]
    except (TypeError, ValueError):
        return [max(0, min(255, int(channel))) for channel in fallback]
