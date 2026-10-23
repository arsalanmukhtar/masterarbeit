# -*- coding: utf-8 -*-
"""QGIS entry point: toolbar button, menu entry and the dashboard window's lifetime."""
from __future__ import annotations

import configparser
import importlib.util
import os
from typing import Optional

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox

from .compat import QAction
from .core.data import CensusData, DataError
from .download import DATA_SIZE_MB, download_data, downloaded_path

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
        self.action.setToolTip("CenGeo BW: Baden-Württemberg Census Dashboard")
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
            from .ui.main_window import DashboardWindow
            self.window = DashboardWindow(self.data, plugin_version(), self.iface.mainWindow(), self.iface)
            # Show the window with its loading page first, then load the charts and maps
            self.window.showMaximized()
            self.window.raise_()
            self.window.activateWindow()
            QTimer.singleShot(50, self.window.load)
            return
        if self.window.isMinimized():
            self.window.showMaximized()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _open_data(self) -> Optional[CensusData]:
        """The data file: one the user chose, a bundled one (development checkout or offline ZIP), or the
        copy downloaded into the QGIS profile. Without any, the user is offered the download."""
        settings = QgsSettings()
        parent = self.iface.mainWindow()
        chosen = settings.value(DATA_PATH_SETTING, "")
        candidates = [chosen] if chosen else []
        candidates += [BUNDLED_DATA, downloaded_path()]
        path = next((candidate for candidate in candidates if os.path.isfile(candidate)), None)
        while True:
            if path is None:
                path = self._ask_for_data(parent)
                if path is None:
                    return None
            try:
                return CensusData(path)
            except DataError as e:
                QMessageBox.critical(parent, TITLE, str(e))
                path = None

    def _ask_for_data(self, parent) -> Optional[str]:
        box = QMessageBox(parent)
        box.setWindowTitle(TITLE)
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(f"The census data ({DATA_SIZE_MB} MB) is downloaded once and then works offline.")
        box.setInformativeText("Download it now, or choose a CenGeo BW data file (cengeobw.gpkg) you already have.")
        download = box.addButton("Download", QMessageBox.ButtonRole.AcceptRole)
        choose = box.addButton("Choose file…", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(download)
        (getattr(box, "exec", None) or box.exec_)()
        if box.clickedButton() is download:
            return download_data(parent)
        if box.clickedButton() is choose:
            path, _ = QFileDialog.getOpenFileName(parent, "Open CenGeo BW data", "", "GeoPackage (*.gpkg)")
            if path:
                QgsSettings().setValue(DATA_PATH_SETTING, path)
                return path
        return None
