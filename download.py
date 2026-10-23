# -*- coding: utf-8 -*-
"""Download of the census data on first start.

The plugin package stays small enough for the QGIS plugin repository; the GeoPackage is published as a
separate GitHub release (tag data-vN) and fetched once into the user's QGIS profile. QGIS's own
downloader is used, so proxy and network settings of QGIS apply.
"""
from __future__ import annotations

import glob
import hashlib
import os
import zipfile
from typing import Optional

from qgis.core import QgsApplication, QgsFileDownloader
from qgis.PyQt.QtCore import QEventLoop, Qt, QUrl
from qgis.PyQt.QtWidgets import QMessageBox, QProgressDialog

# Raise DATA_VERSION and replace DATA_SHA256 whenever a new data file is published (see README)
DATA_VERSION = 1
DATA_ASSET = f"cengeobw-data-v{DATA_VERSION}.zip"
DATA_URL = f"https://github.com/arsalanmukhtar/masterarbeit/releases/download/data-v{DATA_VERSION}/{DATA_ASSET}"
DATA_SHA256 = "46284682bf68bfd0072155d968745eadbc8abdc78ab789f6147627c5a0789c46"
DATA_SIZE_MB = 49
FILE_IN_ASSET = "cengeobw.gpkg"
TITLE = "CenGeo BW"


def data_folder() -> str:
    return os.path.join(QgsApplication.qgisSettingsDirPath(), "cengeobw")


def downloaded_path() -> str:
    """Where this plugin version expects its downloaded data file."""
    return os.path.join(data_folder(), f"cengeobw-v{DATA_VERSION}.gpkg")


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(loop: QEventLoop):
    # exec() on Qt6, exec_() on older PyQt5 builds
    (getattr(loop, "exec", None) or loop.exec_)()


def download_data(parent=None) -> Optional[str]:
    """Download, check and unpack the data file. Returns its path, or None when cancelled or failed."""
    folder = data_folder()
    os.makedirs(folder, exist_ok=True)
    archive = os.path.join(folder, DATA_ASSET + ".part")

    progress = QProgressDialog(f"Downloading the census data ({DATA_SIZE_MB} MB). This is needed once.",
                               "Cancel", 0, 100, parent)
    progress.setWindowTitle(TITLE)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setValue(0)

    downloader = QgsFileDownloader(QUrl(DATA_URL), archive, "", True)
    loop = QEventLoop()
    errors, completed, cancelled = [], [], []

    def cancel():
        cancelled.append(True)
        downloader.cancelDownload()

    downloader.downloadProgress.connect(
        lambda received, total: progress.setValue(int(received * 100 / total)) if total > 0 else None)
    downloader.downloadError.connect(lambda messages: errors.extend(messages))
    downloader.downloadCompleted.connect(lambda *_: completed.append(True))
    downloader.downloadExited.connect(loop.quit)
    progress.canceled.connect(cancel)
    downloader.startDownload()
    _run(loop)
    # A progress dialog reports "canceled" when it is closed, so it is disconnected first; otherwise a
    # finished download would be treated as cancelled
    progress.canceled.disconnect(cancel)
    progress.close()

    if cancelled or errors or not completed or not os.path.isfile(archive):
        if os.path.exists(archive):
            os.remove(archive)
        if errors:
            QMessageBox.critical(parent, TITLE, "The census data could not be downloaded:\n" + "\n".join(errors))
        elif not cancelled:
            QMessageBox.critical(parent, TITLE, "The download of the census data did not finish. Please try again.")
        return None

    if _sha256(archive) != DATA_SHA256:
        os.remove(archive)
        QMessageBox.critical(parent, TITLE, "The downloaded census data is incomplete or damaged. Please try again.")
        return None

    target = downloaded_path()
    temporary = target + ".part"
    try:
        with zipfile.ZipFile(archive) as bundle, bundle.open(FILE_IN_ASSET) as source, open(temporary, "wb") as out:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                out.write(block)
        os.replace(temporary, target)
    except (OSError, KeyError, zipfile.BadZipFile) as e:
        if os.path.exists(temporary):
            os.remove(temporary)
        QMessageBox.critical(parent, TITLE, f"The census data could not be unpacked:\n{e}")
        return None
    finally:
        os.remove(archive)

    # Data files of earlier versions are no longer needed
    for old in glob.glob(os.path.join(folder, "cengeobw-v*.gpkg")):
        if os.path.abspath(old) != os.path.abspath(target):
            try:
                os.remove(old)
            except OSError:
                pass
    return target
