# -*- coding: utf-8 -*-
"""Look of the dashboard window: the bundled Inter font and a light or dark stylesheet.

The stylesheet is set on the dashboard window only, so QGIS itself keeps its own theme.
"""
from __future__ import annotations

import os
from typing import Dict

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont, QFontDatabase
from qgis.PyQt.QtWidgets import QApplication

from ..core.style import FONT_DIR, ICON_DIR as _ICON_DIR, THEMES

# Qt stylesheets need forward slashes, also on Windows
ICON_DIR = _ICON_DIR.replace("\\", "/")
THEME_SETTING = "CenGeoBW/theme"


def stylesheet(t: Dict[str, str], family: str) -> str:
    icon = lambda name: f"{ICON_DIR}/{name}{t['icon_suffix']}.svg"  # noqa: E731
    return f"""
QWidget {{ font-family: "{family}"; font-size: 9.5pt; color: {t['ink']}; }}
QMainWindow#Dashboard, QWidget#Page {{ background: {t['plane']}; }}
QMenuBar {{ background: {t['plane']}; color: {t['ink']}; }}
QMenuBar::item:selected {{ background: {t['hover']}; }}
QStatusBar {{ background: {t['plane']}; color: {t['muted']}; }}
QStatusBar QLabel {{ color: {t['muted']}; }}
QToolTip {{ background: {t['inverse']}; color: {t['inverse_text']}; border: none; padding: 4px 6px; }}

QTabWidget::pane {{ border: none; }}
QTabBar {{ background: {t['plane']}; font-size: 10pt; font-weight: 600; }}
QTabBar::tab {{ background: transparent; color: {t['ink_secondary']}; padding: 10px 20px; margin-right: 4px;
               border: none; border-bottom: 3px solid transparent; }}
QTabBar::tab:hover {{ color: {t['ink']}; }}
QTabBar::tab:selected {{ color: {t['ink']}; border-bottom: 3px solid {t['accent']}; }}

QFrame#Card {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; }}
QFrame#Card QLabel {{ background: transparent; }}
QLabel#CardTitle {{ font-size: 10.5pt; font-weight: 600; }}
QLabel#ChartTitle {{ font-size: 13pt; font-weight: 600; }}
QLabel#Subtitle, QLabel#Muted {{ color: {t['muted']}; }}
QLabel#FieldName {{ color: {t['ink_secondary']}; }}
QLabel#TileLabel {{ color: {t['muted']}; font-size: 8.5pt; }}
QLabel#TileValue {{ font-size: 15pt; font-weight: 600; }}
QLabel#TileNote {{ color: {t['ink_secondary']}; font-size: 8.5pt; }}

QComboBox, QSpinBox, QLineEdit {{ background: {t['field']}; border: 1px solid {t['field_border']}; border-radius: 6px;
                                 padding: 4px 8px; min-height: 22px; color: {t['ink']};
                                 selection-background-color: {t['accent_wash']}; selection-color: {t['ink']}; }}
QComboBox:hover, QSpinBox:hover, QLineEdit:hover {{ border-color: {t['field_border_hover']}; }}
QComboBox:focus, QSpinBox:focus, QLineEdit:focus, QComboBox:on {{ border-color: {t['accent']}; }}
QComboBox:disabled, QSpinBox:disabled {{ color: {t['muted']}; background: {t['plane']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({icon('chevron-down')}); width: 12px; height: 12px; }}
QComboBox QLineEdit {{ border: none; padding: 0; background: transparent; }}
QComboBox QAbstractItemView {{ background: {t['field']}; color: {t['ink']}; border: 1px solid {t['field_border']};
                               outline: 0; padding: 4px; selection-background-color: {t['accent_wash']};
                               selection-color: {t['ink']}; }}
QSpinBox {{ padding-right: 20px; }}
QSpinBox::up-button, QSpinBox::down-button {{ border: none; width: 18px; background: transparent; }}
QSpinBox::up-arrow {{ image: url({icon('chevron-up')}); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url({icon('chevron-down')}); width: 10px; height: 10px; }}

QPushButton {{ background: {t['field']}; color: {t['ink']}; border: 1px solid {t['field_border']}; border-radius: 6px;
              padding: 6px 12px; font-weight: 500; outline: none; }}
QPushButton:focus {{ outline: none; }}
QPushButton:hover {{ background: {t['hover']}; }}
QPushButton:pressed {{ background: {t['pressed']}; }}
QPushButton:disabled {{ color: {t['muted']}; background: {t['plane']}; }}
QPushButton:checked {{ background: {t['accent_wash']}; border-color: {t['accent']}; color: {t['accent_text']}; }}
QPushButton#Primary {{ background: {t['accent']}; border-color: {t['accent']}; color: #ffffff; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {t['accent_hover']}; border-color: {t['accent_hover']}; }}
QPushButton#Primary:pressed {{ background: {t['accent_pressed']}; }}
QPushButton#Segment {{ border-radius: 0; padding: 5px 12px; margin: 0; }}
QPushButton#Segment[position="first"] {{ border-top-left-radius: 6px; border-bottom-left-radius: 6px; }}
QPushButton#Segment[position="last"] {{ border-top-right-radius: 6px; border-bottom-right-radius: 6px; }}
QPushButton#Segment:checked {{ background: {t['inverse']}; border-color: {t['inverse']}; color: {t['inverse_text']}; }}
QPushButton#ThemeToggle {{ padding: 5px 12px; margin: 4px 10px 4px 0; min-width: 110px; }}
QPushButton::menu-indicator {{ image: url({icon('chevron-down')}); subcontrol-position: right center;
                               subcontrol-origin: padding; right: 6px; }}
QPushButton#MenuButton {{ padding-right: 24px; }}
QMenu {{ background: {t['field']}; color: {t['ink']}; border: 1px solid {t['field_border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t['accent_wash']}; color: {t['ink']}; }}

QListWidget#ValueList {{ background: {t['field']}; color: {t['ink']}; border: 1px solid {t['field_border']};
                        border-radius: 6px; padding: 4px; outline: 0; }}
QListWidget#ValueList::item {{ padding: 4px 4px; border-radius: 4px; }}
QListWidget#ValueList::item:hover {{ background: {t['hover']}; }}
QListWidget#ValueList::item:selected {{ background: {t['accent_wash']}; color: {t['ink']}; }}
QListWidget#ValueList::item:disabled {{ color: {t['muted']}; }}
QListWidget#ValueList::indicator {{ width: 14px; height: 14px; border: 1px solid {t['field_border_hover']};
                                   border-radius: 3px; background: {t['field']}; }}
QListWidget#ValueList::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']};
                                           image: url({ICON_DIR}/check.svg); }}
QListWidget#ValueList::indicator:disabled {{ border-color: {t['field_border']}; background: {t['plane']}; }}
QTableWidget {{ background: {t['surface']}; color: {t['ink']}; border: 1px solid {t['border']}; border-radius: 8px;
               gridline-color: {t['grid']}; alternate-background-color: {t['alternate_row']};
               selection-background-color: {t['accent_wash']}; selection-color: {t['ink']}; }}
QHeaderView::section {{ background: {t['surface']}; color: {t['ink_secondary']}; border: none;
                       border-bottom: 1px solid {t['axis']}; padding: 6px 8px; font-weight: 600; }}
QTableCornerButton::section {{ background: {t['surface']}; border: none; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QSplitter::handle {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['axis']}; border-radius: 3px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t['axis']}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none;
    border: none; width: 0; height: 0; }}
"""


def load_fonts() -> str:
    """Register the bundled Inter font with Qt; returns the family to use."""
    families = []
    for name in sorted(os.listdir(FONT_DIR)):
        if name.lower().endswith(".ttf"):
            font_id = QFontDatabase.addApplicationFont(os.path.join(FONT_DIR, name))
            if font_id >= 0:
                families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return "Inter" if "Inter" in families else QFont().defaultFamily()


def saved_theme() -> str:
    """The theme chosen last time; the first time, the one matching the QGIS interface."""
    saved = QgsSettings().value(THEME_SETTING, "")
    if saved in THEMES:
        return saved
    return "dark" if QApplication.palette().window().color().lightness() < 128 else "light"


def save_theme(name: str):
    QgsSettings().setValue(THEME_SETTING, name)


def apply_theme(window, name: str = "light"):
    family = load_fonts()
    font = QFont(family)
    font.setPointSizeF(9.5)
    window.setFont(font)
    window.setObjectName("Dashboard")
    # With a stylesheet in place Qt takes widget fonts from it, so the family is set there as well
    window.setStyleSheet(stylesheet(THEMES[name], family))


def style_tabs(tabs):
    """Tabs keep their full text width; when the window is too narrow they scroll instead of eliding."""
    bar = tabs.tabBar()
    bar.setElideMode(Qt.TextElideMode.ElideNone)
    bar.setExpanding(False)
    bar.setUsesScrollButtons(True)
    bar.setDrawBase(False)
    # Document mode makes the tab widget draw its own base line across the window, so it stays off;
    # the stylesheet already removes the pane frame
    tabs.setDocumentMode(False)
