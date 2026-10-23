# -*- coding: utf-8 -*-
"""The dashboard window.

It opens at once with a loading page; the chart libraries and the first tab load right after, and the
other tabs are built the first time they are opened. This module itself does not import matplotlib.
"""
from __future__ import annotations

from typing import Callable, Dict, List

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import (QApplication, QLabel, QMainWindow, QMessageBox, QPushButton, QTabWidget, QVBoxLayout,
                                 QWidget)

from ..compat import QAction
from ..core.attribution import REPORT_CREDITS, SHORT_CREDIT
from ..core.data import CensusData
from .theme import apply_theme, save_theme, saved_theme, style_tabs

TITLE = "CenGeo BW: Baden-Württemberg Census Dashboard"
TAB_TITLES = ("Visualization", "Gemeinde · Kreis · Land", "Gemeinde · Gemeinde", "Spatial Query")


class LoadingPage(QWidget):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        title = QLabel(text)
        title.setObjectName("ChartTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note = QLabel("This takes a few seconds the first time.")
        note.setObjectName("Muted")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(note)
        layout.addStretch(1)


class DashboardWindow(QMainWindow):
    def __init__(self, data: CensusData, version: str = "", parent=None, iface=None):
        # Qt.WindowType.Window keeps it a separate window even with the QGIS main window as parent
        super().__init__(parent, Qt.WindowType.Window)
        self.theme = saved_theme()
        apply_theme(self, self.theme)
        self.data = data
        self.iface = iface
        self.version = version
        self.setWindowTitle(TITLE)
        self._built: Dict[int, QWidget] = {}
        self._builders: List[Callable[[], QWidget]] = []

        self.tabs = QTabWidget()
        style_tabs(self.tabs)
        for title in TAB_TITLES:
            self.tabs.addTab(LoadingPage(f"Loading {title}"), title)
        self.setCentralWidget(self.tabs)

        self.theme_button = QPushButton("Dark theme")
        self.theme_button.setObjectName("ThemeToggle")
        self.theme_button.setCheckable(True)
        self.theme_button.setToolTip("Switch between the light and the dark theme")
        self.tabs.setCornerWidget(self.theme_button, Qt.Corner.TopRightCorner)
        self.theme_action = QAction("Dark theme", self)
        self.theme_action.setCheckable(True)
        self.menuBar().addMenu("&View").addAction(self.theme_action)
        for control in (self.theme_button, self.theme_action):
            control.setChecked(self.theme == "dark")
            control.toggled.connect(lambda dark: self.set_theme("dark" if dark else "light"))
        self._label_theme_button()

        about = QAction("About and data sources", self)
        about.triggered.connect(self.show_about)
        self.menuBar().addMenu("&Help").addAction(about)
        self.statusBar().addPermanentWidget(QLabel(SHORT_CREDIT))
        self.statusBar().setSizeGripEnabled(True)
        self.fit_to_screen()

    def load(self):
        """Import the chart and map modules and build the first tab. Called right after the window is shown."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            from ..spatial.layers import render_map_image
            from .chart_tabs import GemeindeComparisonTab, GemeindeTab, KreisLandTab
            from .spatial_tab import SpatialTab

            from ..charts import plotting
            plotting.set_theme(self.theme)
            data = self.data

            def map_image(keys, path):
                return render_map_image(str(data.path), keys, path)

            self._builders = [lambda: GemeindeTab(data, map_image), lambda: KreisLandTab(data, map_image),
                              lambda: GemeindeComparisonTab(data, map_image), lambda: SpatialTab(data, self.iface)]
            self._build(self.tabs.currentIndex())
        finally:
            QApplication.restoreOverrideCursor()
        self.tabs.currentChanged.connect(self._on_tab)

    def _on_tab(self, index: int):
        if index not in self._built and self._builders:
            # Let the loading page paint before the work starts
            QTimer.singleShot(30, lambda: self._build_with_cursor(index))

    def _build_with_cursor(self, index: int):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._build(index)
        finally:
            QApplication.restoreOverrideCursor()

    def _build(self, index: int):
        if index in self._built:
            return
        tab = self._builders[index]()
        if hasattr(tab, "apply_theme"):
            tab.apply_theme(self.theme)
        self._built[index] = tab
        self.tabs.blockSignals(True)
        placeholder = self.tabs.widget(index)
        self.tabs.removeTab(index)
        self.tabs.insertTab(index, tab, TAB_TITLES[index])
        self.tabs.setCurrentIndex(index)
        self.tabs.blockSignals(False)
        placeholder.deleteLater()

    def set_theme(self, name: str):
        if name == self.theme:
            return
        self.theme = name
        save_theme(name)
        for control in (self.theme_button, self.theme_action):
            control.blockSignals(True)
            control.setChecked(name == "dark")
            control.blockSignals(False)
        self._label_theme_button()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            apply_theme(self, name)
            if self._builders:
                from ..charts import plotting
                plotting.set_theme(name)
            for tab in self._built.values():
                if hasattr(tab, "apply_theme"):
                    tab.apply_theme(name)
        finally:
            QApplication.restoreOverrideCursor()

    def _label_theme_button(self):
        # The button names the theme it switches to
        self.theme_button.setText("Light theme" if self.theme == "dark" else "Dark theme")

    def tab(self, index: int) -> QWidget:
        """The tab at index, built if it was not opened yet."""
        if self._builders:
            self._build(index)
        return self.tabs.widget(index)

    def release(self):
        for tab in self._built.values():
            if hasattr(tab, "release"):
                tab.release()

    def fit_to_screen(self):
        """Size used when the window is restored from maximized: 85 % of the screen, centred."""
        screen = self.screen() if hasattr(self, "screen") else None
        screen = screen or QApplication.primaryScreen()
        available = screen.availableGeometry()
        width, height = int(available.width() * 0.85), int(available.height() * 0.85)
        self.setMinimumSize(min(800, available.width()), min(560, available.height()))
        self.resize(width, height)
        self.move(available.x() + (available.width() - width) // 2, available.y() + (available.height() - height) // 2)

    def show_about(self):
        built = self.data.info.get("built")
        credits = "".join(f"<li>{credit}</li>" for credit in REPORT_CREDITS)
        QMessageBox.about(self, "About CenGeo BW", (
            f"<h3>{TITLE}</h3>"
            + (f"<p>Version {self.version}</p>" if self.version else "")
            + f"<p>Data sources:</p><ul>{credits}</ul>"
            + (f"<p>Data file built {built}.</p>" if built else "")
            + "<p>See DATA_LICENSE.md in the plugin folder for the full licence terms.</p>"))


__all__ = ["DashboardWindow", "TAB_TITLES"]
