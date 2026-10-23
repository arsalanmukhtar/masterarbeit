# -*- coding: utf-8 -*-
"""Input widgets: cards, searchable dropdowns, Gemeinde and value pickers, and the chart selector."""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

from qgis.PyQt.QtCore import QEvent, QRectF, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPainterPath, QPen
from qgis.PyQt.QtWidgets import (QAbstractItemView, QButtonGroup, QStyle, QStyledItemDelegate, QComboBox, QCompleter, QFormLayout, QFrame, QHBoxLayout, QLabel,
                                 QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QSpinBox,
                                 QVBoxLayout, QWidget)

from ..core.data import CensusData
from ..core.models import Chart, ChartQuery, Gemeinde
from .theme import CURRENT_THEME

MAX_VALUES = 8  # one per series colour


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def compact_combo(combo: QComboBox, characters: int = 20) -> QComboBox:
    """A dropdown that does not force the side panel wider than the screen; its open list is as wide as
    the longest entry, so long chart names stay readable."""
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(characters)
    combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return combo


def make_searchable(combo: QComboBox) -> QComboBox:
    """Typing any part of an entry filters the list; text that matches no entry is reset on leaving."""
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    combo.lineEdit().setPlaceholderText("Type to search")
    completer = combo.completer()
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

    def restore():
        index = combo.findText(combo.lineEdit().text(), Qt.MatchFlag.MatchFixedString)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.lineEdit().setText(combo.itemText(combo.currentIndex()))

    combo.lineEdit().editingFinished.connect(restore)
    return combo


def search_combo(characters: int = 20) -> QComboBox:
    return make_searchable(compact_combo(QComboBox(), characters))


def fit_popup(combo: QComboBox):
    """Make the open list wide enough for its longest entry."""
    view = combo.view()
    view.setMinimumWidth(min(view.sizeHintForColumn(0) + 40, 700))


def refill(combo: QComboBox, items: Sequence[Tuple[str, object]], current: int = 0):
    combo.blockSignals(True)
    combo.clear()
    for text, value in items:
        combo.addItem(text, value)
        combo.setItemData(combo.count() - 1, text, Qt.ItemDataRole.ToolTipRole)
    combo.setCurrentIndex(min(current, combo.count() - 1))
    if combo.isEditable():
        combo.lineEdit().setText(combo.itemText(combo.currentIndex()))
        combo.lineEdit().setCursorPosition(0)
    combo.blockSignals(False)
    fit_popup(combo)


class Card(QFrame):
    """A white panel with an optional title."""

    def __init__(self, title: str = "", parent=None, spacing: int = 10):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 12, 14, 14)
        self.body.setSpacing(spacing)
        if title:
            self.body.addWidget(label(title, "CardTitle"))


class Segmented(QWidget):
    """Joined toggle buttons, one of them checked."""

    changed = pyqtSignal(object)

    def __init__(self, options: Sequence[Tuple[str, object]], parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._group = QButtonGroup(self)
        self._values = []
        for index, (text, value) in enumerate(options):
            button = QPushButton(text)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setProperty("position", "first" if index == 0 else "last" if index == len(options) - 1 else "middle")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(button, index)
            layout.addWidget(button)
            self._values.append(value)
        self._group.button(0).setChecked(True)
        self._group.buttonClicked.connect(lambda button: self.changed.emit(self.value()))

    def value(self):
        return self._values[self._group.checkedId()]

    def set_value(self, value):
        self._group.button(self._values.index(value)).setChecked(True)

    def button(self, index: int) -> QPushButton:
        return self._group.button(index)


class GemeindePicker(QComboBox):
    """Searchable Gemeinde dropdown."""

    gemeindeChanged = pyqtSignal(object)

    def __init__(self, gemeinden: Sequence[Gemeinde], parent=None):
        super().__init__(parent)
        compact_combo(self)
        self._gemeinden = list(gemeinden)
        # A few names exist in more than one Kreis; show the Kreis for those
        duplicates = {name for name, count in Counter(g.name for g in self._gemeinden).items() if count > 1}
        for gemeinde in self._gemeinden:
            self.addItem(f"{gemeinde.name} ({gemeinde.kreis_name})" if gemeinde.name in duplicates else gemeinde.name,
                         gemeinde.key)
        make_searchable(self)
        self.lineEdit().setPlaceholderText("Search Gemeinde")
        fit_popup(self)
        self.currentIndexChanged.connect(lambda _: self.gemeindeChanged.emit(self.gemeinde()))

    def gemeinde(self) -> Optional[Gemeinde]:
        index = self.currentIndex()
        return self._gemeinden[index] if 0 <= index < len(self._gemeinden) else None

    def set_gemeinde(self, key: int):
        index = self.findData(key)
        if index >= 0:
            self.setCurrentIndex(index)


class GemeindeDetails(QWidget):
    FIELDS = (("Landkreis", "kreis_name"), ("Region", "region_name"), ("Gemeinde key", "key"),
              ("Kreis key", "kreis_key"), ("Region key", "region_key"))

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(4)
        self._labels: Dict[str, QLabel] = {}
        for title, attribute in self.FIELDS:
            value = label("", wrap=True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addRow(label(title, "FieldName"), value)
            self._labels[attribute] = value

    def show_gemeinde(self, gemeinde: Optional[Gemeinde]):
        for attribute, value in self._labels.items():
            value.setText("" if gemeinde is None else str(getattr(gemeinde, attribute)))


def _is_checked(state) -> bool:
    # PyQt5 gives the check state as an int, PyQt6 as an enum
    return getattr(state, "value", state) == 2


class CheckRowDelegate(QStyledItemDelegate):
    """Rows of a value list, painted directly so they look the same on every system: a rounded checkbox
    with a tick, then the text. A click anywhere on a row toggles it."""

    BOX = 16
    ROW_PADDING = 12

    def sizeHint(self, option, index):
        width = option.fontMetrics.horizontalAdvance(index.data() or "") + self.BOX + 28
        return QSize(width, option.fontMetrics.height() + self.ROW_PADDING)

    def paint(self, painter, option, index):
        t = CURRENT_THEME["tokens"]
        enabled = bool(index.flags() & Qt.ItemFlag.ItemIsEnabled)
        checked = _is_checked(index.data(Qt.ItemDataRole.CheckStateRole))
        hovered = enabled and bool(option.state & QStyle.StateFlag.State_MouseOver)
        row = QRectF(option.rect).adjusted(1, 1, -1, -1)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t["hover"]))
            painter.drawRoundedRect(row, 5, 5)

        box = QRectF(row.left() + 8, row.center().y() - self.BOX / 2, self.BOX, self.BOX)
        if checked:
            colour = QColor(t["accent_hover"] if hovered else t["accent"]) if enabled else QColor(t["field_border_hover"])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            painter.drawRoundedRect(box, 4, 4)
            tick = QPainterPath()
            tick.moveTo(box.left() + 4.2, box.top() + 8.3)
            tick.lineTo(box.left() + 6.9, box.top() + 11)
            tick.lineTo(box.left() + 11.9, box.top() + 5.3)
            pen = QPen(QColor("#ffffff"), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(tick)
        else:
            border = QColor(t["accent"] if hovered else t["field_border_hover"] if enabled else t["field_border"])
            painter.setPen(QPen(border, 1.3))
            painter.setBrush(QColor(t["field"] if enabled else t["plane"]))
            painter.drawRoundedRect(box.adjusted(0.65, 0.65, -0.65, -0.65), 3.5, 3.5)

        text_rect = row.adjusted(self.BOX + 18, 0, -6, 0)
        painter.setPen(QColor(t["ink"] if enabled else t["muted"]))
        painter.setFont(option.font)
        text = option.fontMetrics.elidedText(index.data() or "", Qt.TextElideMode.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if not index.flags() & Qt.ItemFlag.ItemIsEnabled:
            return False
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            return True
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            state = Qt.CheckState.Unchecked if _is_checked(index.data(Qt.ItemDataRole.CheckStateRole)) \
                else Qt.CheckState.Checked
            model.setData(index, state, Qt.ItemDataRole.CheckStateRole)
            return True
        return False


class ValuePicker(QWidget):
    """Several values of one chart, ticked in a searchable list (at most one per series colour)."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Type to search")
        self.search.setClearButtonEnabled(True)
        self.list = QListWidget()
        self.list.setObjectName("ValueList")
        self.list.setItemDelegate(CheckRowDelegate(self.list))
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setMouseTracking(True)
        self.list.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.hint = label("", "Muted", wrap=True)
        layout.addWidget(self.search)
        layout.addWidget(self.list)
        layout.addWidget(self.hint)
        self.search.textChanged.connect(self._filter)
        self.list.itemChanged.connect(self._on_item_changed)

    def set_values(self, items: Sequence[Tuple[str, str]], checked: Sequence[str] = ()):
        self.list.blockSignals(True)
        self.list.clear()
        checked = [value for value in checked if value in {v for _, v in items}] or [items[0][1]] if items else []
        for text, value in items:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if value in checked else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        rows = min(max(len(items), 3), 7)
        # Row height from the font plus the stylesheet's item padding, which is not applied yet at this point
        self.list.setFixedHeight(rows * (self.list.fontMetrics().height() + 12) + 12)
        self.search.setVisible(len(items) > 7)
        self.list.blockSignals(False)
        self._update_limits()

    def values(self) -> List[str]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]

    def _filter(self, text: str):
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def _on_item_changed(self, item):
        count = len(self.values())
        if count == 0 or count > MAX_VALUES:
            # At least one value stays selected, and at most one per series colour
            self.list.blockSignals(True)
            item.setCheckState(Qt.CheckState.Checked if count == 0 else Qt.CheckState.Unchecked)
            self.list.blockSignals(False)
            return
        self._update_limits()
        self.changed.emit()

    def _update_limits(self):
        full = len(self.values()) >= MAX_VALUES
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.checkState() != Qt.CheckState.Checked:
                flags = item.flags() & ~Qt.ItemFlag.ItemIsEnabled if full else item.flags() | Qt.ItemFlag.ItemIsEnabled
                item.setFlags(flags)
        self.list.blockSignals(False)
        count = len(self.values())
        self.hint.setText(f"{count} of at most {MAX_VALUES} values selected" if count > 1 else
                          "Tick several values to compare them or show their shares")


class ChartSelector(QWidget):
    """Category, chart, value(s) and X axis, plus a filter for every other dimension of the table."""

    changed = pyqtSignal()

    def __init__(self, data: CensusData, levels: Sequence[str] = ("gmnd",), multi_value: bool = False, parent=None):
        super().__init__(parent)
        self._data = data
        self._levels = tuple(levels)
        self._multi = multi_value
        self._charts: List[Chart] = []
        self._filters: Dict[str, QComboBox] = {}
        self._age: Optional[Tuple[QSpinBox, QSpinBox]] = None
        self._filter_rows: List[QWidget] = []

        self.category = search_combo()
        self.chart = search_combo()
        self.x_axis = search_combo()
        self.y_axis = search_combo()
        self.values = ValuePicker()
        self._form = QFormLayout(self)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setVerticalSpacing(8)
        self._form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        value_widget = self.values if multi_value else self.y_axis
        for title, widget in (("Category", self.category), ("Chart", self.chart),
                              ("Values" if multi_value else "Value", value_widget), ("Over", self.x_axis)):
            self._form.addRow(label(title, "FieldName"), widget)
        (self.y_axis if multi_value else self.values).setVisible(False)

        categories = [c for c in data.categories() if data.charts_for(c, self._levels)]
        refill(self.category, [(category, category) for category in categories])
        self.category.currentIndexChanged.connect(self._fill_charts)
        self.chart.currentIndexChanged.connect(self._fill_axes)
        self.x_axis.currentIndexChanged.connect(self._fill_filters)
        self.y_axis.currentIndexChanged.connect(self.changed)
        self.values.changed.connect(self.changed)
        self._fill_charts()

    def current_category(self) -> str:
        return self.category.currentText()

    def current_chart(self) -> Optional[Chart]:
        index = self.chart.currentIndex()
        return self._charts[index] if 0 <= index < len(self._charts) else None

    def selected_values(self) -> List[str]:
        if self._multi:
            return self.values.values()
        value = self.y_axis.currentData()
        return [value] if value is not None else []

    def query(self) -> Optional[ChartQuery]:
        chart = self.current_chart()
        values = self.selected_values()
        if chart is None or self.x_axis.currentData() is None or not values:
            return None
        age_range = (self._age[0].value(), self._age[1].value()) if self._age else None
        filters = {dimension: combo.currentData() for dimension, combo in self._filters.items()}
        return ChartQuery(chart, self.x_axis.currentData(), values[0], filters, age_range, values)

    def describe(self) -> str:
        """Filter summary for the chart subtitle, e.g. "School type: Grundschulen · Age 20 to 40"."""
        chart = self.current_chart()
        table = chart.table if chart else None
        parts = [f"{self._data.label(dimension, table)}: {combo.currentText()}"
                 for dimension, combo in self._filters.items()]
        if self._age:
            low, high = self._age[0].value(), self._age[1].value()
            if (low, high) != (self._age[0].minimum(), self._age[0].maximum()):
                parts.append(f"Age {low} to {high}")
            elif self.x_axis.currentData() != "age":
                parts.append("All ages")
        return " · ".join(parts)

    def _fill_charts(self):
        self._charts = self._data.charts_for(self.category.currentText(), self._levels)
        refill(self.chart, [(chart.title, chart.table) for chart in self._charts])
        self._fill_axes()

    def _fill_axes(self):
        chart = self.current_chart()
        schema = self._data.schema(chart.table) if chart else None
        table = chart.table if chart else None
        refill(self.x_axis, [(self._data.label(d, table), d) for d in schema.axis_options()] if schema else [])
        items = [(self._data.label(v, table), v) for v in schema.values] if schema else []
        refill(self.y_axis, items)
        self.values.set_values(items)
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
        combo = search_combo()
        # Years default to the latest, everything else to the first value
        refill(combo, [(str(value), value) for value in values], len(values) - 1 if dimension == "year" else 0)
        combo.currentIndexChanged.connect(self.changed)
        self._form.addRow(label(self._data.label(dimension, chart.table), "FieldName"), combo)
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
            spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(start)
        layout.addWidget(label("to", "Muted"))
        layout.addWidget(end)
        start.valueChanged.connect(lambda value: end.setValue(max(value, end.value())))
        end.valueChanged.connect(lambda value: start.setValue(min(value, start.value())))
        start.valueChanged.connect(self.changed)
        end.valueChanged.connect(self.changed)
        self._form.addRow(label("Age range", "FieldName"), row)
        self._age = (start, end)
        self._filter_rows.append(row)
