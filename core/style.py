# -*- coding: utf-8 -*-
"""Colours and font location shared by the charts, the maps and the dashboard window.

Kept free of matplotlib and Qt imports so the window can open before the chart libraries load.
The module-level colours are the light theme; THEMES holds both themes for switching.
"""
import os

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "fonts")
ICON_DIR = os.path.join(os.path.dirname(FONT_DIR), "icons")

LIGHT = {
    "plane": "#f3f3f0",
    "surface": "#fcfcfb",
    "ink": "#0b0b0b",
    "ink_secondary": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
    "border": "rgba(11, 11, 11, 0.10)",
    "field": "#ffffff",
    "field_border": "#d6d5ce",
    "field_border_hover": "#b5b4ab",
    "hover": "#ecebe6",
    "pressed": "#e1e0d9",
    "alternate_row": "#f7f7f4",
    "accent": "#2a78d6",
    "accent_hover": "#256abf",
    "accent_pressed": "#1c5cab",
    "accent_wash": "#e6effa",
    "accent_text": "#1c5cab",
    "inverse": "#0b0b0b",
    "inverse_text": "#ffffff",
    "icon_suffix": "",
    # Categorical series colours in a fixed order that keeps neighbours distinguishable for colour-blind readers
    "series": ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"),
}

DARK = {
    "plane": "#121211",
    "surface": "#1a1a19",
    "ink": "#f0efec",
    "ink_secondary": "#c3c2b7",
    "muted": "#9a9891",
    "grid": "#2c2c2a",
    "axis": "#4a4a46",
    "border": "rgba(255, 255, 255, 0.10)",
    "field": "#232321",
    "field_border": "#3a3a37",
    "field_border_hover": "#58584f",
    "hover": "#2a2a28",
    "pressed": "#33332f",
    "alternate_row": "#1f1f1d",
    "accent": "#3987e5",
    "accent_hover": "#5598e7",
    "accent_pressed": "#2a78d6",
    "accent_wash": "#1d2c40",
    "accent_text": "#86b6ef",
    "inverse": "#f0efec",
    "inverse_text": "#0b0b0b",
    "icon_suffix": "-dark",
    # The same eight hues, stepped for a dark background
    "series": ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"),
}

THEMES = {"light": LIGHT, "dark": DARK}

SURFACE = LIGHT["surface"]
INK = LIGHT["ink"]
INK_SECONDARY = LIGHT["ink_secondary"]
MUTED = LIGHT["muted"]
GRID = LIGHT["grid"]
AXIS = LIGHT["axis"]
SERIES_COLORS = LIGHT["series"]
# Single-hue blue ramp, light to dark, for maps
BLUE_RAMP = ("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b")

# Trend colours, always shown with an arrow so colour never carries the meaning alone
TREND_STRONG_UP = "#0ca30c"
TREND_UP = "#fab219"
TREND_DOWN = "#ec835a"
TREND_STRONG_DOWN = "#d03b3b"
TREND_STEP = 2.0  # percent (or points): above it a change counts as strong
TREND_HELP = (f"Green: growth of {TREND_STEP:g} % or more · Yellow: growth below {TREND_STEP:g} % · "
              f"Orange: decline below {TREND_STEP:g} % · Red: decline of {TREND_STEP:g} % or more")


def trend_arrow(change: float):
    """Arrow and colour for a change: strong or slight growth, slight or strong decline."""
    if change >= TREND_STEP:
        return "▲", TREND_STRONG_UP
    if change >= 0:
        return "▲", TREND_UP
    if change > -TREND_STEP:
        return "▼", TREND_DOWN
    return "▼", TREND_STRONG_DOWN
