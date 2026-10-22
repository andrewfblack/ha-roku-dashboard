"""Tests for the theme colours shared by the panel, the API and the Roku."""

from __future__ import annotations

import pytest

from roku_dashboard import api, panel, theme
from roku_dashboard.const import (
    CONF_THEME_ACCENT,
    CONF_THEME_BODY_TEXT,
    CONF_THEME_HEADER_TEXT,
    CONF_THEME_ITEM_BACKGROUND,
)


def test_a_colour_is_read_from_an_rgb_list():
    """Colours stored as RGB lists still work."""
    options = {CONF_THEME_ACCENT: [225, 138, 69]}
    assert api._theme_color(options, CONF_THEME_ACCENT) == "#E18A45"


def test_a_colour_is_read_from_a_hex_string():
    """Colours typed into the options form are hex strings."""
    options = {CONF_THEME_ACCENT: "#e18a45"}
    assert api._theme_color(options, CONF_THEME_ACCENT) == "#E18A45"


def test_a_hex_string_without_a_hash_is_read():
    """The hash is optional."""
    options = {CONF_THEME_ACCENT: "E18A45"}
    assert api._theme_color(options, CONF_THEME_ACCENT) == "#E18A45"


def test_a_broken_colour_falls_back_to_the_default():
    """A colour that makes no sense never reaches the dashboard."""
    options = {CONF_THEME_ACCENT: "not a colour"}
    assert api._theme_color(options, CONF_THEME_ACCENT) == "#E18A45"


def test_a_missing_colour_falls_back_to_the_default():
    """A colour that was never set uses the built-in value."""
    assert api._theme_color({}, CONF_THEME_ACCENT) == "#E18A45"


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ([255, 247, 234], "#FFF7EA"),
        ("#FFF7EA", "#FFF7EA"),
        ("fff7ea", "#FFF7EA"),
        ("nonsense", "#FFF7EA"),
        (None, "#FFF7EA"),
    ],
)
def test_the_panel_shows_every_colour_as_hex(stored, expected):
    """The panel colour inputs always receive a hex value."""
    assert panel._rgb_hex(stored, [255, 247, 234]) == expected


def test_the_panel_accepts_both_shapes():
    """A colour set in the options form is not lost in the panel."""
    options = {CONF_THEME_HEADER_TEXT: "#FFF7EA"}
    assert panel._public_options(options)[CONF_THEME_HEADER_TEXT] == "#FFF7EA"
    options = {CONF_THEME_ITEM_BACKGROUND: [31, 23, 17]}
    assert panel._public_options(options)[CONF_THEME_ITEM_BACKGROUND] == "#1F1711"


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("#1F1711", True),
        ("1F1711", True),
        ("  #1F1711  ", True),
        ("#1f1711", True),
        ("#FFF", False),
        ("#1F17111", False),
        ("nonsense", False),
        ("", False),
        (None, False),
        ([31, 23, 17], False),
    ],
)
def test_a_typed_colour_is_only_accepted_when_it_is_hex(value, valid):
    """The options form rejects anything that is not a hex colour."""
    assert theme.is_hex(value) is valid


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#1F1711", [31, 23, 17]),
        ("1F1711", [31, 23, 17]),
        ([31, 23, 17], [31, 23, 17]),
        ("nonsense", [1, 2, 3]),
        (None, [1, 2, 3]),
        ([300, -5, 0], [255, 0, 0]),
    ],
)
def test_a_colour_converts_to_an_rgb_list(value, expected):
    """The panel stores colours as RGB lists."""
    assert theme.to_rgb(value, [1, 2, 3]) == expected


def test_a_colour_converts_to_a_hex_string():
    """The options form and the API use hex strings."""
    assert theme.to_hex([31, 23, 17], [1, 2, 3]) == "#1F1711"
    assert theme.to_hex("#1f1711", [1, 2, 3]) == "#1F1711"
    assert theme.to_hex("nonsense", [1, 2, 3]) == "#010203"
