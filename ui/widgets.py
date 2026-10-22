# -*- coding: utf-8 -*-
"""Reusable widgets: Gemeinde picker and details, chart selector and chart canvas."""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

from matplotlib.figure import Figure
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (QComboBox, QCompleter, QFormLayout, QHBoxLayout, QLabel, QSizePolicy, QSpinBox,
                                 QWidget)

from ..charts.plotting import HoverTooltips, draw_bar_chart
from ..compat import figure_canvas_class
from ..core.data import CensusData
from ..core.models import Chart, ChartQuery, Gemeinde, Series

FigureCanvas = figure_canvas_class()


def _compact(combo: QComboBox, characters: int = 14) -> QComboBox:
    # Long chart titles must not force the side panel wider than the screen
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(characters)
    combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return combo


def _refill(combo: QComboBox, items: Sequence[Tuple[str, object]], current: int = 0):
    combo.blockSignals(True)
    combo.clear()
    for text, value in items:
        combo.addItem(text, value)
        combo.setItemData(combo.count() - 1, text, Qt.ItemDataRole.ToolTipRole)
    combo.setCurrentIndex(min(current, combo.count() - 1))
    combo.blockSignals(False)


class GemeindePicker(QComboBox):
    """Searchable Gemeinde dropdown: typing any part of the name filters the list."""

    gemeindeChanged = pyqtSignal(object)

    def __init__(self, gemeinden: Sequence[Gemeinde], parent=None):
        super().__init__(parent)
        _compact(self)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.lineEdit().setPlaceholderText("Search Gemeinde…")
        self._gemeinden = list(gemeinden)
        # A few names exist in more than one Kreis; show the Kreis for those
        duplicates = {name for name, count in Counter(g.name for g in self._gemeinden).items() if count > 1}
        for gemeinde in self._gemeinden:
            self.addItem(f"{gemeinde.name} ({gemeinde.kreis_name})" if gemeinde.name in duplicates else gemeinde.name,
                         gemeinde.key)
        completer = self.completer()
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.currentIndexChanged.connect(lambda _: self.gemeindeChanged.emit(self.gemeinde()))
        self.lineEdit().editingFinished.connect(self._restore_text)

    def gemeinde(self) -> Optional[Gemeinde]:
        index = self.currentIndex()
        return self._gemeinden[index] if 0 <= index < len(self._gemeinden) else None

    def set_gemeinde(self, key: int):
        index = self.findData(key)
        if index >= 0:
            self.setCurrentIndex(index)

    def _restore_text(self):
        # Free text that is not a Gemeinde is replaced by the selected Gemeinde again
        text = self.lineEdit().text()
        index = self.findText(text, Qt.MatchFlag.MatchFixedString)
        if index >= 0:
            self.setCurrentIndex(index)
        self.lineEdit().setText(self.itemText(self.currentIndex()))


class GemeindeDetails(QWidget):
    FIELDS = (("Landkreis", "kreis_name"), ("Region", "region_name"), ("Gemeinde key (GS)", "key"),
              ("Kreis key (KR)", "kreis_key"), ("Region key (RN)", "region_key"))

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._labels: Dict[str, QLabel] = {}
        for title, attribute in self.FIELDS:
            label = QLabel()
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setWordWrap(True)
            layout.addRow(title, label)
            self._labels[attribute] = label

    def show_gemeinde(self, gemeinde: Optional[Gemeinde]):
        for attribute, label in self._labels.items():
            label.setText("" if gemeinde is None else str(getattr(gemeinde, attribute)))


class ChartSelector(QWidget):
    """Category → chart → X axis → Y axis, plus a filter for every other dimension of the table."""

    changed = pyqtSignal()

    def __init__(self, data: CensusData, levels: Sequence[str] = ("gmnd",), parent=None):
        super().__init__(parent)
        self._data = data
        self._levels = tuple(levels)
        self._charts: List[Chart] = []
        self._filters: Dict[str, QComboBox] = {}
        self._age: Optional[Tuple[QSpinBox, QSpinBox]] = None
        self._filter_rows: List[QWidget] = []

        self.category = _compact(QComboBox())
        self.chart = _compact(QComboBox())
        self.x_axis = _compact(QComboBox())
        self.y_axis = _compact(QComboBox())
        self._form = QFormLayout(self)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for title, combo in (("Category", self.category), ("Chart", self.chart), ("X axis", self.x_axis),
                             ("Y axis", self.y_axis)):
            self._form.addRow(title, combo)

        categories = [c for c in data.categories() if data.charts_for(c, self._levels)]
        _refill(self.category, [(category, category) for category in categories])
        self.category.currentIndexChanged.connect(self._fill_charts)
        self.chart.currentIndexChanged.connect(self._fill_axes)
        self.x_axis.currentIndexChanged.connect(self._fill_filters)
        self.y_axis.currentIndexChanged.connect(self.changed)
        self._fill_charts()

    # --- Public -------------------------------------------------------------------------------

    def current_category(self) -> str:
        return self.category.currentText()

    def current_chart(self) -> Optional[Chart]:
        index = self.chart.currentIndex()
        return self._charts[index] if 0 <= index < len(self._charts) else None

    def query(self) -> Optional[ChartQuery]:
        chart = self.current_chart()
        if chart is None or self.x_axis.currentData() is None or self.y_axis.currentData() is None:
            return None
        age_range = (self._age[0].value(), self._age[1].value()) if self._age else None
        filters = {dimension: combo.currentData() for dimension, combo in self._filters.items()}
        return ChartQuery(chart, self.x_axis.currentData(), self.y_axis.currentData(), filters, age_range)

    def describe(self) -> Optional[str]:
        """Filter summary for the chart legend, e.g. "Feature: Berufseinpendler · Age 20–40"."""
        parts = [f"{self._data.label(dimension)}: {combo.currentText()}" for dimension, combo in self._filters.items()]
        if self._age:
            low, high = self._age[0].value(), self._age[1].value()
            if (low, high) != (self._age[0].minimum(), self._age[0].maximum()):
                parts.append(f"Age {low}–{high}")
            elif self.x_axis.currentData() != "age":
                parts.append("All ages")
        return " · ".join(parts) or None

    # --- Filling the dropdowns ------------------------------------------------------------------

    def _fill_charts(self):
        self._charts = self._data.charts_for(self.category.currentText(), self._levels)
        _refill(self.chart, [(chart.title, chart.table) for chart in self._charts])
        self._fill_axes()

    def _fill_axes(self):
        chart = self.current_chart()
        schema = self._data.schema(chart.table) if chart else None
        _refill(self.x_axis, [(self._data.label(d), d) for d in schema.axis_options()] if schema else [])
        _refill(self.y_axis, [(self._data.label(v), v) for v in schema.values] if schema else [])
        self._fill_filters()

    def _fill_filters(self):
        for widget in self._filter_rows:
            self._form.removeRow(widget)
        self._filter_rows, self._filters, self._age = [], {}, None
        chart = self.current_chart()
        if chart is not None:
            schema = self._data.schema(chart.table)
            x = self.x_axis.currentData()
            for dimension in schema.dimensions:
                if dimension == "age" and schema.has_age_range():
                    self._add_age_range(*self._data.value_range(chart.table, "age"))
                elif dimension != x:
                    self._add_value_filter(chart, dimension)
        self.changed.emit()

    def _add_value_filter(self, chart: Chart, dimension: str):
        values = self._data.dimension_values(chart.table, dimension)
        combo = _compact(QComboBox())
        # Years default to the latest, everything else to the first value
        _refill(combo, [(str(value), value) for value in values], len(values) - 1 if dimension == "year" else 0)
        combo.currentIndexChanged.connect(self.changed)
        self._form.addRow(self._data.label(dimension), combo)
        self._filters[dimension] = combo
        self._filter_rows.append(combo)

    def _add_age_range(self, low: int, high: int):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        start, end = QSpinBox(), QSpinBox()
        for spin, value in ((start, low), (end, high)):
            spin.setRange(low, high)
            spin.setValue(value)
            spin.setKeyboardTracking(False)
        layout.addWidget(start)
        layout.addWidget(QLabel("to"))
        layout.addWidget(end)
        start.valueChanged.connect(lambda value: end.setValue(max(value, end.value())))
        end.valueChanged.connect(lambda value: start.setValue(min(value, start.value())))
        start.valueChanged.connect(self.changed)
        end.valueChanged.connect(self.changed)
        self._form.addRow("Age range", row)
        self._age = (start, end)
        self._filter_rows.append(row)


class ChartCanvas(FigureCanvas):
    """matplotlib chart that grows and shrinks with the window."""

    def __init__(self, parent=None):
        super().__init__(Figure())
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 240)
        self._tooltips = HoverTooltips(self)

    def show_chart(self, series: Sequence[Series], title: str, x_label: str, y_label: str, note: Optional[str] = None):
        axes, categories, containers = draw_bar_chart(self.figure, series, title, x_label, y_label, note)
        self._tooltips.attach(axes, categories, containers, series)
        self.draw_idle()

    def show_message(self, text: str):
        self._tooltips.detach()
        self.figure.clear()
        self.figure.text(0.5, 0.5, text, ha="center", va="center", fontsize=11, color="#777777", wrap=True)
        self.draw_idle()
