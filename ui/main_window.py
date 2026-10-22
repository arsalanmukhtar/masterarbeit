# -*- coding: utf-8 -*-
"""The dashboard window."""
from __future__ import annotations

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QTabWidget

from ..compat import QAction
from ..core.attribution import REPORT_CREDITS, SHORT_CREDIT
from ..core.data import CensusData
from ..spatial.layers import render_map_image
from .chart_tabs import GemeindeComparisonTab, GemeindeTab, KreisLandTab
from .spatial_tab import SpatialTab

TITLE = "CenGeo BW – Baden-Württemberg Census Dashboard"
SCREEN_SHARE = 0.85


class DashboardWindow(QMainWindow):
    def __init__(self, data: CensusData, version: str = "", parent=None):
        # Qt.WindowType.Window keeps it a separate window even with the QGIS main window as parent
        super().__init__(parent, Qt.WindowType.Window)
        self.data = data
        self.version = version
        self.setWindowTitle(TITLE)

        def map_image(keys, path):
            return render_map_image(str(data.path), keys, path)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(GemeindeTab(data, map_image), "Visualization")
        self.tabs.addTab(KreisLandTab(data, map_image), "Gemeinde · Kreis · Land")
        self.tabs.addTab(GemeindeComparisonTab(data, map_image), "Gemeinde · Gemeinde")
        self.tabs.addTab(SpatialTab(data), "Spatial Query")
        self.setCentralWidget(self.tabs)

        about = QAction("About and data sources", self)
        about.triggered.connect(self.show_about)
        self.menuBar().addMenu("&Help").addAction(about)
        credit = QLabel(SHORT_CREDIT)
        credit.setStyleSheet("color: palette(mid);")
        self.statusBar().addPermanentWidget(credit)
        self.fit_to_screen()

    def release(self):
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if hasattr(tab, "release"):
                tab.release()

    def fit_to_screen(self):
        """Open at 85 % of the screen the window is on, centred, never larger than the screen."""
        screen = self.screen() if hasattr(self, "screen") else None
        screen = screen or QApplication.primaryScreen()
        available = screen.availableGeometry()
        width, height = int(available.width() * SCREEN_SHARE), int(available.height() * SCREEN_SHARE)
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
