# -*- coding: utf-8 -*-
"""QGIS entry point: toolbar button, menu entry and the dashboard window's lifetime."""
from __future__ import annotations

import configparser
import importlib.util
import os
from typing import Optional

from qgis.core import QgsSettings
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox

from .compat import QAction
from .core.data import CensusData, DataError

PLUGIN_DIR = os.path.dirname(__file__)
BUNDLED_DATA = os.path.join(PLUGIN_DIR, "data", "cengeobw.gpkg")
DATA_PATH_SETTING = "CenGeoBW/dataPath"
MENU = "&CenGeo BW"
TITLE = "CenGeo BW"


def plugin_version() -> str:
    metadata = configparser.ConfigParser(interpolation=None)
    metadata.read(os.path.join(PLUGIN_DIR, "metadata.txt"), encoding="utf-8")
    return metadata.get("general", "version", fallback="")


class CenGeoBWPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action: Optional[QAction] = None
        self.window = None
        self.data: Optional[CensusData] = None

    def initGui(self):
        self.action = QAction(QIcon(os.path.join(PLUGIN_DIR, "icon.png")), "Census Dashboard",
                              self.iface.mainWindow())
        self.action.setToolTip("CenGeo BW – Baden-Württemberg Census Dashboard")
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu(MENU, self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.iface.removePluginMenu(MENU, self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.window is not None:
            self.window.release()
            self.window.close()
            self.window.deleteLater()
            self.window = None
        if self.data is not None:
            self.data.close()
            self.data = None

    def run(self):
        if self.window is None:
            # matplotlib is bundled with QGIS on Windows and macOS, but not always on Linux
            if importlib.util.find_spec("matplotlib") is None:
                QMessageBox.critical(self.iface.mainWindow(), TITLE,
                                     "The Python package matplotlib is required for the charts.\n"
                                     "On Linux install it with your package manager, e.g. python3-matplotlib.")
                return
            self.data = self._open_data()
            if self.data is None:
                return
            from .ui.main_window import DashboardWindow  # imported here so a missing matplotlib cannot break loading
            self.window = DashboardWindow(self.data, plugin_version(), self.iface.mainWindow())
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _open_data(self) -> Optional[CensusData]:
        """The bundled GeoPackage, or one the user picked earlier (e.g. a newer data release)."""
        settings = QgsSettings()
        chosen = settings.value(DATA_PATH_SETTING, "")
        if chosen and os.path.isfile(chosen):
            path = chosen
        else:
            path = BUNDLED_DATA
        while True:
            try:
                return CensusData(path)
            except DataError as e:
                answer = QMessageBox.question(
                    self.iface.mainWindow(), TITLE,
                    f"{e}\n\nThe census data file (cengeobw.gpkg) is part of the plugin ZIP from the GitHub "
                    "releases page. Do you want to choose the file yourself?")
                if answer != QMessageBox.StandardButton.Yes:
                    return None
                path, _ = QFileDialog.getOpenFileName(self.iface.mainWindow(), "Open CenGeo BW data", "",
                                                      "GeoPackage (*.gpkg)")
                if not path:
                    return None
                settings.setValue(DATA_PATH_SETTING, path)
