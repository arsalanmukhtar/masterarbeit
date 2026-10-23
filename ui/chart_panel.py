# -*- coding: utf-8 -*-
"""The chart card (title, chart type, chart or table view, index view, exports) and the Gemeinde profile."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from matplotlib.figure import Figure
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QMenu,
                                 QMessageBox, QPushButton, QSizePolicy, QStackedWidget, QTableWidget, QTableWidgetItem,
                                 QVBoxLayout, QWidget)

from ..charts.plotting import (FONT_FAMILY, KIND_LABELS, ChartHover, available_kinds, chart_kind, draw_chart,
                               draw_message, format_number, index_series, light_charts, limit_bar_width,
                               render_static, reserve_margins)
from ..compat import figure_canvas_class
from ..core.data import CensusData
from ..core.models import Gemeinde, Series
from ..core.style import INK, MUTED, TREND_DOWN, TREND_STRONG_DOWN, TREND_STRONG_UP, TREND_UP
from .inputs import Card, Segmented, compact_combo, label, refill

FigureCanvas = figure_canvas_class()
INDEX_LABEL = "Index (first year = 100)"
TREND_STEP = 2.0  # percent: above it the change counts as strong
INDEX_KINDS = ("line", "area", "bar")


# --- Gemeinde profile ------------------------------------------------------------------------------

class StatTile(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        self.title = label(title, "TileLabel")
        self.value = label("", "TileValue")
        self.value.setTextFormat(Qt.TextFormat.RichText)
        self.note = label("", "TileNote")
        for widget in (self.title, self.value, self.note):
            widget.setMinimumWidth(10)
            layout.addWidget(widget)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set(self, value: str, note: str = "", tooltip: str = ""):
        self.value.setText(value)
        self.note.setText(note)
        self.setToolTip(tooltip)


def trend_arrow(change: float) -> Tuple[str, str]:
    """Arrow and colour for a percentage change: strong or slight growth, slight or strong decline."""
    if change >= TREND_STEP:
        return "▲", TREND_STRONG_UP
    if change >= 0:
        return "▲", TREND_UP
    if change > -TREND_STEP:
        return "▼", TREND_DOWN
    return "▼", TREND_STRONG_DOWN


TREND_HELP = (f"Green: growth of {TREND_STEP:g} % or more · Yellow: growth below {TREND_STEP:g} % · "
              f"Orange: decline below {TREND_STEP:g} % · Red: decline of {TREND_STEP:g} % or more")


class ProfileTiles(QWidget):
    """Headline figures of one Gemeinde: population, ten-year change, average age, area, density.
    The tiles wrap into more rows when the window is narrow."""

    TILE_MIN_WIDTH = 175

    def __init__(self, data: CensusData, parent=None):
        super().__init__(parent)
        self._data = data
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)
        self._columns = 0
        self.tiles = {key: StatTile(title) for key, title in (
            ("population", "Population"), ("change", "Change in ten years"), ("age", "Average age"),
            ("area", "Area"), ("density", "Density"))}
        self._arrange(len(self.tiles))

    def _arrange(self, columns: int):
        if columns == self._columns:
            return
        self._columns = columns
        for tile in self.tiles.values():
            self._layout.removeWidget(tile)
        for column in range(len(self.tiles)):
            self._layout.setColumnStretch(column, 1 if column < columns else 0)
        for index, tile in enumerate(self.tiles.values()):
            self._layout.addWidget(tile, index // columns, index % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = max(1, min(len(self.tiles), event.size().width() // self.TILE_MIN_WIDTH))
        # 5 tiles fit as 5, 3 + 2 or 2 + 2 + 1
        self._arrange({4: 3}.get(columns, columns))

    def show_gemeinde(self, gemeinde: Optional[Gemeinde]):
        profile = self._data.profile(gemeinde.key) if gemeinde else {}
        year = profile.get("year")
        self.tiles["population"].set(format_number(profile["population"]) if "population" in profile else "-",
                                     f"in {year}" if year else "")
        if "change_percent" in profile:
            change = profile["change_percent"]
            arrow, colour = trend_arrow(change)
            self.tiles["change"].set(f'<span style="color:{colour}">{arrow}</span> {abs(change):.1f} %',
                                     f"{profile['change_year']} to {year}", TREND_HELP)
        else:
            self.tiles["change"].set("-")
        self.tiles["age"].set(f"{profile['average_age']:.1f} years" if "average_age" in profile else "-",
                              f"in {profile['age_year']}" if "age_year" in profile else "")
        self.tiles["area"].set(f"{profile['area_km2']:,.1f} km²" if "area_km2" in profile else "-")
        self.tiles["density"].set(f"{format_number(profile['density'])} per km²" if profile.get("density") else "-",
                                  f"in {year}" if year else "")


# --- Chart ------------------------------------------------------------------------------------

@dataclass
class ChartView:
    """A chart ready to show: what is plotted and how it is labelled. composition marks series that are
    parts of one whole (several values of one Gemeinde), which allows stacked charts and donuts."""
    title: str
    subtitle: str
    series: List[Series]
    x_label: str
    y_label: str
    x_dimension: str
    file_name: str = "chart"
    composition: bool = False
    extra: Dict[str, object] = field(default_factory=dict)


class ChartCanvas(FigureCanvas):
    """matplotlib chart that grows and shrinks with the window."""

    def __init__(self, parent=None):
        super().__init__(Figure())
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 220)
        self._hover = ChartHover(self)
        self.handle = None
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(80)
        self._resize_timer.timeout.connect(self._after_resize)

    def show_chart(self, series: Sequence[Series], x_label: str, y_label: str, kind: str,
                   baseline: Optional[float] = None):
        self.figure.clear()
        self.handle = draw_chart(self.figure, series, x_label, y_label, kind, baseline=baseline,
                                 max_x_labels=max(4, self.width() // 75))
        reserve_margins(self.figure)
        self._hover.attach(self.handle)
        self.draw()
        self._after_resize()

    def show_message(self, text: str):
        self._hover.detach()
        self.handle = None
        self.figure.clear()
        draw_message(self.figure, text)
        self.draw_idle()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()

    def _after_resize(self):
        # Bars are capped in pixels, so their width is recalculated for the new size
        if self.handle is not None and self.handle.kind in ("bar", "stacked_bar"):
            limit_bar_width(self.handle)
            self.draw_idle()


class DataTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

    def show_rows(self, headers: Sequence[str], rows: Sequence[Sequence]):
        self.clear()
        self.setColumnCount(len(headers))
        self.setRowCount(len(rows))
        self.setHorizontalHeaderLabels(list(headers))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(str(value) if c == 0 else format_number(value))
                if c > 0:
                    item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
                self.setItem(r, c, item)


def table_rows(series: Sequence[Series]) -> List[list]:
    """Rows of (x, value of each series) over all X values, in order of appearance."""
    order: List[object] = []
    for item in series:
        order.extend(x for x in item.x if x not in order)
    lookups = [dict(zip(item.x, item.y)) for item in series]
    return [[x, *(lookup.get(x) for lookup in lookups)] for x in order]


class ChartPanel(Card):
    """Chart card: title and subtitle, chart type, chart or table view, optional index view, and exports."""

    def __init__(self, allow_index: bool = False, parent=None):
        super().__init__(parent=parent, spacing=8)
        self._view: Optional[ChartView] = None
        self._allow_index = allow_index
        self._preferred_kind: Optional[str] = None

        header = QHBoxLayout()
        header.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = label("", "ChartTitle", wrap=True)
        self.subtitle = label("", "Subtitle", wrap=True)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        header.addLayout(titles, 1)
        self.kind = compact_combo(QComboBox(), 12)
        self.kind.setToolTip("Chart type")
        self.kind.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.scale = Segmented((("Values", "values"), ("Index", "index")))
        self.scale.setToolTip("Index: every line starts at 100, so areas of different size can be compared")
        self.scale.setVisible(allow_index)
        self.view_mode = Segmented((("Chart", "chart"), ("Table", "table")))
        self.export_button = QPushButton("Export")
        self.export_button.setObjectName("MenuButton")
        menu = QMenu(self.export_button)
        menu.addAction("Save chart as image…", self.save_image)
        menu.addAction("Export data as CSV…", self.save_csv)
        self.export_button.setMenu(menu)
        for widget in (self.kind, self.scale, self.view_mode, self.export_button):
            header.addWidget(widget, 0, Qt.AlignmentFlag.AlignTop)
        self.body.addLayout(header)

        self.canvas = ChartCanvas()
        self.table = DataTable()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.canvas)
        self.stack.addWidget(self.table)
        self.body.addWidget(self.stack, 1)
        self.view_mode.changed.connect(lambda mode: self.stack.setCurrentIndex(0 if mode == "chart" else 1))
        self.scale.changed.connect(lambda _: self._render())
        self.kind.activated.connect(self._on_kind_chosen)

    def set_scale(self, value: str):
        self.scale.set_value(value)

    def show_view(self, view: ChartView):
        self._view = view
        kinds = available_kinds(view.x_dimension, view.series, view.composition)
        default = self._preferred_kind if self._preferred_kind in kinds else kinds[0]
        refill(self.kind, [(KIND_LABELS[kind], kind) for kind in kinds], kinds.index(default))
        self.kind.setEnabled(len(kinds) > 1)
        self._render()

    def show_message(self, text: str):
        self._view = None
        self.title.setText("")
        self.subtitle.setText("")
        self.canvas.show_message(text)
        self.table.show_rows([], [])
        self.export_button.setEnabled(False)
        self.scale.setEnabled(False)
        self.kind.setEnabled(False)

    def current_kind(self) -> str:
        return self.kind.currentData() or "line"

    def _on_kind_chosen(self, _index: int):
        self._preferred_kind = self.current_kind()
        self._render()

    def displayed(self) -> Tuple[List[Series], str, str, Optional[float]]:
        """Series, Y label, subtitle and baseline as currently shown (values or index)."""
        view = self._view
        indexable = self._allow_index and view.x_dimension == "year" and self.current_kind() in INDEX_KINDS
        self.scale.setEnabled(indexable)
        if indexable and self.scale.value() == "index":
            subtitle = " · ".join(filter(None, [view.subtitle, f"{view.y_label}, {INDEX_LABEL}"]))
            return index_series(view.series), INDEX_LABEL, subtitle, 100.0
        return view.series, view.y_label, view.subtitle, None

    def _render(self):
        if self._view is None:
            return
        series, y_label, subtitle, baseline = self.displayed()
        kind = self.current_kind()
        if kind == "bar":
            kind = chart_kind("", [x for item in series for x in item.x])
        self.canvas.show_chart(series, self._view.x_label, y_label, kind, baseline)
        note = self.canvas.handle.note if self.canvas.handle else None
        self.title.setText(self._view.title)
        subtitle = " · ".join(filter(None, [subtitle, note]))
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))
        self.table.show_rows([self._view.x_label] + [item.label for item in series], table_rows(series))
        self.export_button.setEnabled(True)

    def save_image(self):
        if self._view is None:
            return
        path, chosen = QFileDialog.getSaveFileName(self, "Save chart", self._view.file_name + ".png",
                                                   "PNG image (*.png);;SVG image (*.svg);;PDF document (*.pdf)")
        if not path:
            return
        if "." not in path.replace("\\", "/").rsplit("/", 1)[-1]:
            path += ".svg" if "SVG" in chosen else ".pdf" if "PDF" in chosen else ".png"
        series, y_label, subtitle, baseline = self.displayed()
        kind = self.current_kind()
        if kind == "bar":
            kind = chart_kind("", [x for item in series for x in item.x])
        # Saved images use the light theme, so they print well and match the PDF reports
        with light_charts():
            figure = Figure(figsize=(11, 6.2), dpi=150)
            handle = draw_chart(figure, series, self._view.x_label, y_label, kind, baseline=baseline)
            subtitle = " · ".join(filter(None, [subtitle, handle.note]))
            figure.text(0.012, 0.975, self._view.title, ha="left", va="top", fontsize=15, fontweight="semibold",
                        color=INK, fontfamily=FONT_FAMILY)
            if subtitle:
                figure.text(0.012, 0.925, subtitle, ha="left", va="top", fontsize=10.5, color=MUTED,
                            fontfamily=FONT_FAMILY)
            reserve_margins(figure, top=0.11)
            render_static(figure, handle)
            figure.savefig(path, facecolor=figure.get_facecolor())

    def save_csv(self):
        if self._view is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export data", self._view.file_name + ".csv", "CSV file (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        series, *_ = self.displayed()
        try:
            # utf-8-sig so Excel shows umlauts correctly
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow([self._view.x_label] + [item.label for item in series])
                writer.writerows(table_rows(series))
        except OSError as e:
            QMessageBox.critical(self, "Export data", f"The file could not be written:\n{e}")
