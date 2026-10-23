# -*- coding: utf-8 -*-
"""The three chart tabs. They share layout and behaviour through ChartTab and differ only in
which areas are picked and which series and report they produce."""
from __future__ import annotations

from typing import Callable, List, Optional

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QMessageBox, QProgressDialog, QPushButton,
                                 QScrollArea, QSplitter, QVBoxLayout, QWidget)

from ..core.data import CensusData
from ..core.models import LEVELS, ChartQuery, Gemeinde, Series
from ..reports.builders import (STATE_NAME, MapImageCallback, ReportCancelled, gemeinde_comparison_report,
                                gemeinde_report, kreis_land_report)
from .chart_panel import ChartPanel, ChartView, ProfileTiles
from .inputs import Card, ChartSelector, GemeindeDetails, GemeindePicker, label

SIDE_PANEL_MIN_WIDTH = 280


def side_panel(*widgets: QWidget, fill_last: bool = False) -> QScrollArea:
    """Cards stacked at the top of a scrollable column, so small screens can still reach everything.
    With fill_last the last card takes the height left over below the others."""
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 8, 0)
    layout.setSpacing(12)
    for index, widget in enumerate(widgets):
        layout.addWidget(widget, 1 if fill_last and index == len(widgets) - 1 else 0)
    if not fill_last:
        layout.addStretch(1)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(panel)
    scroll.setMinimumWidth(SIDE_PANEL_MIN_WIDTH)
    return scroll


def natural_width(widget: QWidget) -> int:
    """The width a panel needs for its content, measured once fonts and styles are applied; for a scroll
    area this includes its scrollbar."""
    if isinstance(widget, QScrollArea):
        inner = widget.widget()
        inner.ensurePolished()
        for child in inner.findChildren(QWidget):
            child.ensurePolished()
        width = inner.sizeHint().width() + widget.verticalScrollBar().sizeHint().width() + 4
    else:
        widget.ensurePolished()
        width = widget.sizeHint().width()
    return max(width, widget.minimumWidth())


def fit_side_panels(splitter: QSplitter, flexible: int = 1):
    """Give every panel except the flexible one its natural width and the rest of the space to that one."""
    widths = [natural_width(splitter.widget(i)) for i in range(splitter.count())]
    for i, width in enumerate(widths):
        if i != flexible:
            splitter.widget(i).setMinimumWidth(width)
    total = splitter.width() - splitter.handleWidth() * (splitter.count() - 1)
    widths[flexible] = max(total - sum(w for i, w in enumerate(widths) if i != flexible), 300)
    splitter.setSizes(widths)


def page_splitter(*panels: QWidget) -> QSplitter:
    splitter = QSplitter(Qt.Orientation.Horizontal)
    for panel in panels:
        splitter.addWidget(panel)
    for index in range(len(panels)):
        splitter.setStretchFactor(index, 1 if index == 1 else 0)
    splitter.setChildrenCollapsible(False)
    splitter.setHandleWidth(12)
    return splitter


class ChartTab(QWidget):
    area_title = "Gemeinde"
    levels = ("gmnd",)
    allow_index = False
    default_scale = "values"
    multi_value = False

    def __init__(self, data: CensusData, map_image: Optional[MapImageCallback] = None, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.data = data
        self.map_image = map_image
        self._sized = False

        area = Card(self.area_title)
        self.build_area(area.body)
        chart_card = Card("Chart")
        self.selector = ChartSelector(data, self.levels, self.multi_value)
        chart_card.body.addWidget(self.selector)
        report = Card("Report")
        report.body.addWidget(label("A PDF with a map and every chart and table of the selected category, "
                                    "plus each chart as an image.", "Muted", wrap=True))
        self.export_button = QPushButton("Create PDF report")
        self.export_button.setObjectName("Primary")
        report.body.addWidget(self.export_button)

        self.panel = ChartPanel(allow_index=self.allow_index)
        self.panel.set_scale(self.default_scale)
        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)
        self.build_main(main_layout)
        main_layout.addWidget(self.panel, 1)

        self.splitter = page_splitter(side_panel(area, chart_card, report), main)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.addWidget(self.splitter)

        self.selector.changed.connect(self.refresh)
        self.export_button.clicked.connect(self.export_report)
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._sized:
            # Measured after the first show, when the stylesheet's fonts and paddings are in effect
            self._sized = True
            QTimer.singleShot(0, lambda: fit_side_panels(self.splitter))

    def apply_theme(self, name: str):
        """Redraw the chart in the colours of the theme the window just switched to."""
        self.refresh()

    # --- To implement per tab -------------------------------------------------------------------

    def build_area(self, layout: QVBoxLayout):
        raise NotImplementedError

    def build_main(self, layout: QVBoxLayout):
        """Widgets above the chart; none by default."""

    def build_view(self, query: ChartQuery) -> ChartView:
        raise NotImplementedError

    def write_report(self, folder: str, progress: Callable[[int, int, str], bool]) -> str:
        raise NotImplementedError

    # --- Shared behaviour -----------------------------------------------------------------------

    def view_for(self, query: ChartQuery, series: List[Series], subtitle: str, name: str,
                 composition: bool = False) -> ChartView:
        table = query.chart.table
        filters = self.selector.describe()
        y_label = self.data.label(query.y, table) if len(query.values) == 1 else "Value"
        return ChartView(title=query.chart.title, subtitle=" · ".join(filter(None, [subtitle, filters])),
                         series=series, x_label=self.data.label(query.x, table), y_label=y_label,
                         x_dimension=query.x, composition=composition,
                         file_name=f"{query.chart.title} - {y_label} - {name}")

    def refresh(self):
        query = self.selector.query()
        if query is None:
            self.panel.show_message("No chart is available for this selection.")
            return
        try:
            view = self.build_view(query)
        except Exception as e:  # shown in the chart area rather than as a popup while the user is browsing
            self.panel.show_message(f"Could not load this chart:\n{e}")
            return
        if not any(item.has_values() for item in view.series):
            self.panel.show_message("There is no data for this selection.")
            return
        self.panel.show_view(view)

    def export_report(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder for the report")
        if not folder:
            return
        progress = QProgressDialog("Preparing the report", "Cancel", 0, 1, self)
        progress.setWindowTitle("Create PDF report")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        def on_progress(done: int, total: int, title: str) -> bool:
            progress.setMaximum(max(total, 1))
            progress.setValue(done)
            progress.setLabelText(title or "Finishing")
            QApplication.processEvents()
            return not progress.wasCanceled()

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            path = self.write_report(folder, on_progress)
        except ReportCancelled:
            return
        except Exception as e:
            QMessageBox.critical(self, "Create PDF report", f"The report could not be created:\n{e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
            progress.close()
        QMessageBox.information(self, "Create PDF report", f"The report was saved as:\n{path}")


class GemeindeTab(ChartTab):
    """Statistics for one Gemeinde, with its headline figures above the chart. Several values of a chart
    can be shown together, which also allows stacked charts and donuts of their shares."""

    multi_value = True

    def build_area(self, layout: QVBoxLayout):
        self.picker = GemeindePicker(self.data.gemeinden)
        self.details = GemeindeDetails()
        layout.addWidget(self.picker)
        layout.addWidget(self.details)
        self.details.show_gemeinde(self.picker.gemeinde())
        self.picker.gemeindeChanged.connect(self._on_gemeinde)

    def build_main(self, layout: QVBoxLayout):
        self.profile = ProfileTiles(self.data)
        self.profile.show_gemeinde(self.picker.gemeinde())
        layout.addWidget(self.profile)

    def _on_gemeinde(self, gemeinde: Gemeinde):
        self.details.show_gemeinde(gemeinde)
        if hasattr(self, "profile"):
            self.profile.show_gemeinde(gemeinde)
        self.refresh()

    def build_view(self, query: ChartQuery) -> ChartView:
        gemeinde = self.picker.gemeinde()
        table = query.chart.table
        rows = self.data.grouped_rows(table, query.x, query.values, gemeinde.key, query.filters, query.age_range)
        series = [Series(self.data.label(value, table), [row[0] for row in rows], [row[i + 1] for row in rows])
                  for i, value in enumerate(query.values)]
        if len(series) == 1:
            series[0].label = gemeinde.name
        return self.view_for(query, series, gemeinde.name, gemeinde.name, composition=len(series) > 1)

    def write_report(self, folder, progress) -> str:
        return gemeinde_report(self.data, self.picker.gemeinde(), self.selector.current_category(), folder,
                               self.map_image, progress)


class KreisLandTab(GemeindeTab):
    """One Gemeinde next to its Kreis and the state of Baden-Württemberg."""

    levels = LEVELS
    allow_index = True
    default_scale = "index"
    multi_value = False

    def build_main(self, layout: QVBoxLayout):
        """No profile tiles: the chart compares three areas."""

    def build_view(self, query: ChartQuery) -> ChartView:
        gemeinde = self.picker.gemeinde()
        series = [self.data.series(query, "gmnd", gemeinde.name, gemeinde.key),
                  self.data.series(query, "krs", f"{gemeinde.kreis_name} (Kreis)", gemeinde.kreis_key),
                  self.data.series(query, "rgn", STATE_NAME)]
        return self.view_for(query, series, f"{gemeinde.name}, {gemeinde.kreis_name} and {STATE_NAME}",
                             f"{gemeinde.name} Kreis Land")

    def write_report(self, folder, progress) -> str:
        return kreis_land_report(self.data, self.picker.gemeinde(), self.selector.current_category(), folder,
                                 self.map_image, progress)


class GemeindeComparisonTab(ChartTab):
    """Two Gemeinden side by side."""

    area_title = "Gemeinden"
    allow_index = True

    def build_area(self, layout: QVBoxLayout):
        self.pickers = []
        for index, title in enumerate(("First Gemeinde", "Second Gemeinde")):
            picker = GemeindePicker(self.data.gemeinden)
            picker.setCurrentIndex(min(index, picker.count() - 1))
            kreis = label("", "Muted")
            layout.addWidget(label(title, "FieldName"))
            layout.addWidget(picker)
            layout.addWidget(kreis)
            picker.gemeindeChanged.connect(lambda gemeinde, note=kreis: self._on_gemeinde(gemeinde, note))
            kreis.setText(picker.gemeinde().kreis_name if picker.gemeinde() else "")
            self.pickers.append(picker)

    def _on_gemeinde(self, gemeinde: Gemeinde, note):
        note.setText(gemeinde.kreis_name if gemeinde else "")
        self.refresh()

    def build_view(self, query: ChartQuery) -> ChartView:
        first, second = (picker.gemeinde() for picker in self.pickers)
        series = [self.data.series(query, "gmnd", first.name, first.key),
                  self.data.series(query, "gmnd", second.name, second.key)]
        return self.view_for(query, series, f"{first.name} and {second.name}", f"{first.name} and {second.name}")

    def write_report(self, folder, progress) -> str:
        first, second = (picker.gemeinde() for picker in self.pickers)
        return gemeinde_comparison_report(self.data, first, second, self.selector.current_category(), folder,
                                          self.map_image, progress)
