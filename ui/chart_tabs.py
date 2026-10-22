# -*- coding: utf-8 -*-
"""The three chart tabs. They share layout and behaviour through ChartTab and differ only in
which areas are picked and which series and report they produce."""
from __future__ import annotations

from typing import Callable, List, Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QApplication, QFileDialog, QFrame, QGroupBox, QLabel, QMessageBox, QProgressDialog,
                                 QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget)

from ..core.data import CensusData
from ..core.models import LEVELS, ChartQuery, Series
from ..reports.builders import (STATE_NAME, MapImageCallback, ReportCancelled, gemeinde_comparison_report,
                                gemeinde_report, kreis_land_report)
from .widgets import ChartCanvas, ChartSelector, GemeindeDetails, GemeindePicker

SIDE_PANEL_MIN_WIDTH = 260


class ChartTab(QWidget):
    area_title = "Gemeinde"
    levels = ("gmnd",)

    def __init__(self, data: CensusData, map_image: Optional[MapImageCallback] = None, parent=None):
        super().__init__(parent)
        self.data = data
        self.map_image = map_image

        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        area_box = QGroupBox(self.area_title)
        self.build_area(QVBoxLayout(area_box))
        chart_box = QGroupBox("Chart")
        self.selector = ChartSelector(data, self.levels)
        QVBoxLayout(chart_box).addWidget(self.selector)
        self.export_button = QPushButton("Export category report (PDF)…")
        self.export_button.setToolTip("Creates a PDF with every chart of the selected category, plus PNG images")
        panel_layout.addWidget(area_box)
        panel_layout.addWidget(chart_box)
        panel_layout.addWidget(self.export_button)
        panel_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(panel)
        scroll.setMinimumWidth(SIDE_PANEL_MIN_WIDTH)
        self.canvas = ChartCanvas()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(scroll)
        splitter.addWidget(self.canvas)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([340, 1000])
        QVBoxLayout(self).addWidget(splitter)

        self.selector.changed.connect(self.refresh)
        self.export_button.clicked.connect(self.export_report)
        self.refresh()

    # --- To implement per tab -------------------------------------------------------------------

    def build_area(self, layout: QVBoxLayout):
        raise NotImplementedError

    def build_series(self, query: ChartQuery) -> List[Series]:
        raise NotImplementedError

    def chart_title(self, query: ChartQuery) -> str:
        raise NotImplementedError

    def write_report(self, folder: str, progress: Callable[[int, int, str], bool]) -> str:
        raise NotImplementedError

    # --- Shared behaviour -----------------------------------------------------------------------

    def refresh(self):
        query = self.selector.query()
        if query is None:
            self.canvas.show_message("No chart is available for this selection.")
            return
        try:
            series = self.build_series(query)
        except Exception as e:  # shown in the chart area rather than as a popup while the user is browsing
            self.canvas.show_message(f"Could not load this chart:\n{e}")
            return
        if not any(item.has_values() for item in series):
            self.canvas.show_message("There is no data for this selection.")
            return
        self.canvas.show_chart(series, self.chart_title(query), self.data.label(query.x), self.data.label(query.y),
                               self.selector.describe())

    def export_report(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder for the report")
        if not folder:
            return
        progress = QProgressDialog("Preparing the report…", "Cancel", 0, 1, self)
        progress.setWindowTitle("Export report")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        def on_progress(done: int, total: int, title: str) -> bool:
            progress.setMaximum(max(total, 1))
            progress.setValue(done)
            progress.setLabelText(f"{title}" if title else "Finishing…")
            QApplication.processEvents()
            return not progress.wasCanceled()

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            path = self.write_report(folder, on_progress)
        except ReportCancelled:
            return
        except Exception as e:
            QMessageBox.critical(self, "Export report", f"The report could not be created:\n{e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
            progress.close()
        QMessageBox.information(self, "Export report", f"The report was saved as:\n{path}")


class GemeindeTab(ChartTab):
    """Statistics for one Gemeinde."""

    def build_area(self, layout: QVBoxLayout):
        self.picker = GemeindePicker(self.data.gemeinden)
        self.details = GemeindeDetails()
        layout.addWidget(self.picker)
        layout.addWidget(self.details)
        self.details.show_gemeinde(self.picker.gemeinde())
        self.picker.gemeindeChanged.connect(self._on_gemeinde)

    def _on_gemeinde(self, gemeinde):
        self.details.show_gemeinde(gemeinde)
        self.refresh()

    def build_series(self, query: ChartQuery) -> List[Series]:
        gemeinde = self.picker.gemeinde()
        return [self.data.series(query, "gmnd", gemeinde.name, gemeinde.key)]

    def chart_title(self, query: ChartQuery) -> str:
        return f"{query.chart.title}: {self.picker.gemeinde().name}"

    def write_report(self, folder, progress) -> str:
        return gemeinde_report(self.data, self.picker.gemeinde(), self.selector.current_category(), folder,
                               self.map_image, progress)


class KreisLandTab(GemeindeTab):
    """One Gemeinde next to its Kreis and the state of Baden-Württemberg."""

    levels = LEVELS

    def build_series(self, query: ChartQuery) -> List[Series]:
        gemeinde = self.picker.gemeinde()
        return [self.data.series(query, "gmnd", f"{gemeinde.name} (Gemeinde)", gemeinde.key),
                self.data.series(query, "krs", f"{gemeinde.kreis_name} (Kreis)", gemeinde.kreis_key),
                self.data.series(query, "rgn", STATE_NAME)]

    def chart_title(self, query: ChartQuery) -> str:
        return f"{self.data.label(query.y)}: {query.chart.title.replace(' in Gemeinde', '')}, Gemeinde, Kreis and Land"

    def write_report(self, folder, progress) -> str:
        return kreis_land_report(self.data, self.picker.gemeinde(), self.selector.current_category(), folder,
                                 self.map_image, progress)


class GemeindeComparisonTab(ChartTab):
    """Two Gemeinden side by side."""

    area_title = "Gemeinden"

    def build_area(self, layout: QVBoxLayout):
        self.pickers = []
        for index, title in enumerate(("Gemeinde A", "Gemeinde B")):
            picker = GemeindePicker(self.data.gemeinden)
            picker.setCurrentIndex(min(index, picker.count() - 1))
            kreis = QLabel()
            kreis.setStyleSheet("color: palette(mid);")
            layout.addWidget(QLabel(f"<b>{title}</b>"))
            layout.addWidget(picker)
            layout.addWidget(kreis)
            picker.gemeindeChanged.connect(lambda gemeinde, label=kreis: self._on_gemeinde(gemeinde, label))
            kreis.setText(picker.gemeinde().kreis_name if picker.gemeinde() else "")
            self.pickers.append(picker)

    def _on_gemeinde(self, gemeinde, label: QLabel):
        label.setText(gemeinde.kreis_name if gemeinde else "")
        self.refresh()

    def build_series(self, query: ChartQuery) -> List[Series]:
        return [self.data.series(query, "gmnd", picker.gemeinde().name, picker.gemeinde().key)
                for picker in self.pickers]

    def chart_title(self, query: ChartQuery) -> str:
        first, second = (picker.gemeinde().name for picker in self.pickers)
        return f"{self.data.label(query.y)}: {query.chart.title.replace(' in Gemeinde', '')}, {first} and {second}"

    def write_report(self, folder, progress) -> str:
        first, second = (picker.gemeinde() for picker in self.pickers)
        return gemeinde_comparison_report(self.data, first, second, self.selector.current_category(), folder,
                                          self.map_image, progress)
