# -*- coding: utf-8 -*-
"""Map tab: find a Gemeinde by name or by clicking the map, and colour all Gemeinden by a statistic."""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from qgis.core import (QgsCoordinateTransform, QgsFeatureRequest, QgsGeometry, QgsProject, QgsRectangle,
                       QgsSettings, QgsStyle, QgsVectorLayer)
from qgis.gui import QgsMapCanvas, QgsMapToolEmitPoint
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QAbstractItemView, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
                                 QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                                 QVBoxLayout, QWidget)

from ..charts.plotting import format_number
from ..core.attribution import BASEMAP_CREDIT
from ..core.data import CensusData
from ..core.models import Chart, Gemeinde
from ..reports.pdf_report import safe_file_name
from ..spatial.layers import (CANVAS_COLOURS, DEFAULT_BASEMAPS, HIGHLIGHT_OUTLINE_STYLE, HIGHLIGHT_STYLE, NO_BASEMAP,
                              OUTLINE_STYLES, WEB_MERCATOR, apply_style, basemap_choices, basemap_layer, boundary_layer,
                              save_default_style, set_keys, thematic_layer, to_web_mercator, write_layer)
from .chart_tabs import fit_side_panels, page_splitter, side_panel
from .inputs import Card, GemeindeDetails, GemeindePicker, label, refill, search_combo

AGGREGATE_CHOICES = (("Sum", "SUM"), ("Average", "AVG"))
CLASS_CHOICES = tuple((f"{count} classes", count) for count in range(3, 8))
FILE_FILTERS = "GeoPackage (*.gpkg);;ESRI Shapefile (*.shp)"
BASEMAP_SETTING = "CenGeoBW/basemap"
INFO_MAX_WIDTH = 560


class Legend(Card):
    def __init__(self, parent=None):
        super().__init__("Legend", parent, spacing=6)
        self.caption = label("", "Muted", wrap=True)
        self.body.addWidget(self.caption)
        self._rows = QVBoxLayout()
        self._rows.setSpacing(4)
        self.body.addLayout(self._rows)
        self.setVisible(False)

    def show_entries(self, caption: str, entries):
        while self._rows.count():
            item = self._rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for colour, text in entries:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            swatch = QLabel()
            swatch.setFixedSize(22, 14)
            swatch.setStyleSheet(f"background: {colour}; border-radius: 3px;")
            layout.addWidget(swatch)
            layout.addWidget(label(text))
            layout.addStretch(1)
            self._rows.addWidget(row)
        self.caption.setText(caption)
        self.setVisible(True)


class SpatialTab(QWidget):
    def __init__(self, data: CensusData, iface=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.data = data
        self.iface = iface
        data_path = str(data.path)
        self._charts: List[Chart] = []
        self._values: Dict[int, float] = {}
        self._value_title = ""
        self._theme = "light"
        # Layers whose style the user edited keep it when the theme or the selection changes
        self._customised = set()
        self._thematic_key = None

        # Map: selected Gemeinde over the thematic layer over all boundaries over the basemap
        self.outlines = boundary_layer(data_path, "Gemeinde boundaries")
        self.highlight = boundary_layer(data_path, "Selected Gemeinde", HIGHLIGHT_STYLE, keys=[])
        self.basemap_name = QgsSettings().value(BASEMAP_SETTING, "") or DEFAULT_BASEMAPS["light"]
        self.basemap = basemap_layer(self.basemap_name)
        self.thematic: Optional[QgsVectorLayer] = None
        self.map = QgsMapCanvas()
        self.map.setCanvasColor(QColor(252, 252, 251))
        self.map.enableAntiAliasing(True)
        # Cached layers are reused, so selecting a Gemeinde redraws only the highlight, and while the view
        # moves the previous image stays visible until the new one is ready
        self.map.setCachingEnabled(True)
        self.map.setParallelRenderingEnabled(True)
        self.map.setPreviewJobsEnabled(True)
        self.map.setMapUpdateInterval(200)
        self.map.setDestinationCrs(WEB_MERCATOR)
        self._update_map_layers()
        self.map.setExtent(to_web_mercator(self.outlines.extent(), self.outlines.crs(), padding=0.02))
        map_card = Card(spacing=6)
        map_card.body.setContentsMargins(6, 6, 6, 6)
        map_card.body.addWidget(self.map, 1)
        credit = label(BASEMAP_CREDIT, "Muted")
        credit.setAlignment(Qt.AlignmentFlag.AlignRight)
        map_card.body.addWidget(credit)

        # Gemeinde card
        gemeinde_card = Card("Gemeinde")
        self.picker = GemeindePicker(data.gemeinden)
        self.details = GemeindeDetails()
        self.zoom_button = QPushButton("Zoom to Gemeinde")
        self.identify_button = QPushButton("Identify on map")
        self.identify_button.setCheckable(True)
        self.identify_button.setToolTip("Click a Gemeinde on the map to select it")
        buttons = QHBoxLayout()
        buttons.addWidget(self.zoom_button)
        buttons.addWidget(self.identify_button)
        gemeinde_card.body.addWidget(self.picker)
        gemeinde_card.body.addWidget(self.details)
        gemeinde_card.body.addLayout(buttons)

        # Thematic map card
        thematic_card = Card("Thematic map")
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(8)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.category = search_combo()
        self.chart = search_combo()
        self.attribute = search_combo()
        self.year = search_combo()
        self.aggregate = search_combo()
        self.classes = search_combo()
        refill(self.category, [(category, category) for category in data.categories()])
        refill(self.aggregate, AGGREGATE_CHOICES)
        refill(self.classes, CLASS_CHOICES, current=2)
        self.year_label = label("Year", "FieldName")
        for title, widget in (("Category", self.category), ("Chart", self.chart), ("Value", self.attribute)):
            form.addRow(label(title, "FieldName"), widget)
        form.addRow(self.year_label, self.year)
        form.addRow(label("Combine other dimensions by", "FieldName"), self.aggregate)
        form.addRow(label("Classes", "FieldName"), self.classes)
        thematic_card.body.addLayout(form)
        self.show_button = QPushButton("Show on map")
        self.show_button.setObjectName("Primary")
        self.clear_button = QPushButton("Clear")
        self.save_button = QPushButton("Save as layer")
        self.save_button.setToolTip("Save the thematic map as GeoPackage or Shapefile, styled, and add it to the project")
        actions = QHBoxLayout()
        actions.addWidget(self.show_button, 1)
        actions.addWidget(self.clear_button)
        thematic_card.body.addLayout(actions)
        thematic_card.body.addWidget(self.save_button)
        self.legend = Legend()

        # Map layers card: basemap choice and the style of every layer on the dashboard map
        layers_card = Card("Map layers")
        layers_card.body.addWidget(label("Basemap", "FieldName"))
        self.basemap_combo = search_combo()
        layers_card.body.addWidget(self.basemap_combo)
        layers_card.body.addWidget(label("Symbology, labels and other layer properties open in the QGIS layer "
                                         "properties dialog.", "Muted", wrap=True))
        self.style_buttons = {}
        for key, title in (("thematic", "Thematic map"), ("outlines", "Gemeinde boundaries"),
                           ("highlight", "Selected Gemeinde"), ("basemap", "Basemap")):
            row = QHBoxLayout()
            row.addWidget(label(title), 1)
            button = QPushButton("Style…")
            button.clicked.connect(lambda _=False, layer_key=key: self.edit_layer(layer_key))
            row.addWidget(button)
            layers_card.body.addLayout(row)
            self.style_buttons[key] = button
        self._fill_basemaps()

        # Selected Gemeinde card
        info_card = Card("Selected Gemeinde")
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Attribute", "Value"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        info_card.body.addWidget(self.table, 1)
        info_card.setMinimumWidth(320)
        self.info_card = info_card

        # Right column: attributes of the selected Gemeinde, with the map layers below
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        right_layout.addWidget(info_card, 1)
        right_layout.addWidget(layers_card)

        self.splitter = page_splitter(side_panel(gemeinde_card, thematic_card, self.legend), map_card, right)
        self._sized = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.addWidget(self.splitter)

        self.identify_tool = QgsMapToolEmitPoint(self.map)
        self.identify_tool.canvasClicked.connect(self._identify)
        self.identify_tool.deactivated.connect(lambda: self.identify_button.setChecked(False))
        self.identify_button.toggled.connect(self._toggle_identify)
        self.zoom_button.clicked.connect(lambda: self.show_gemeinde(self.picker.gemeinde(), zoom=True))
        self.picker.gemeindeChanged.connect(lambda gemeinde: self.show_gemeinde(gemeinde, zoom=True))
        self.category.currentIndexChanged.connect(self._fill_charts)
        self.chart.currentIndexChanged.connect(self._fill_attributes)
        self.show_button.clicked.connect(self.show_thematic)
        self.clear_button.clicked.connect(self.clear_thematic)
        self.save_button.clicked.connect(self.save_thematic)
        self.basemap_combo.currentIndexChanged.connect(lambda _: self.set_basemap(self.basemap_combo.currentText()))
        self._fill_charts()
        self.show_gemeinde(self.picker.gemeinde(), zoom=False)

    def showEvent(self, event):
        super().showEvent(event)
        # Raster layers of the project may have changed since the tab was last open
        self._fill_basemaps()
        if not self._sized:
            self._sized = True
            QTimer.singleShot(0, lambda: fit_side_panels(self.splitter))

    def apply_theme(self, name: str):
        """Map background and boundary lines in the colours of the light or dark theme. The basemap follows
        the theme only until the user picks one."""
        self._theme = name
        self.map.setCanvasColor(QColor(*CANVAS_COLOURS[name]))
        if "outlines" not in self._customised:
            apply_style(self.outlines, OUTLINE_STYLES[name])
            self.outlines.triggerRepaint()
        if not QgsSettings().value(BASEMAP_SETTING, "") and self.basemap_name != DEFAULT_BASEMAPS[name]:
            self.set_basemap(DEFAULT_BASEMAPS[name], remember=False)
        self.map.refresh()

    # --- Basemap and layer styles -------------------------------------------------------------------

    def _fill_basemaps(self):
        names = basemap_choices()
        if self.basemap_name not in names:
            names.insert(0, self.basemap_name)
        refill(self.basemap_combo, [(name, name) for name in names], names.index(self.basemap_name))

    def set_basemap(self, name: str, remember: bool = True):
        if not name or (name == self.basemap_name and remember is False):
            return
        if remember:
            QgsSettings().setValue(BASEMAP_SETTING, name)
        if name == self.basemap_name and self.basemap is not None:
            return
        self.basemap_name = name
        self.basemap = None if name == NO_BASEMAP else basemap_layer(name)
        self._customised.discard("basemap")
        self._update_map_layers()
        index = self.basemap_combo.findText(name)
        if index >= 0 and index != self.basemap_combo.currentIndex():
            self.basemap_combo.blockSignals(True)
            self.basemap_combo.setCurrentIndex(index)
            self.basemap_combo.blockSignals(False)

    def edit_layer(self, key: str):
        """Open the QGIS layer properties (symbology, labels, ...) for a layer of the dashboard map."""
        layer = {"thematic": self.thematic, "outlines": self.outlines, "highlight": self.highlight,
                 "basemap": self.basemap}[key]
        if layer is None:
            QMessageBox.information(self, "Layer style", "Show a thematic map first." if key == "thematic"
                                    else "No basemap is shown.")
            return
        if self.iface is not None and hasattr(self.iface, "showLayerProperties"):
            self.iface.showLayerProperties(layer)
        elif isinstance(layer, QgsVectorLayer):
            from qgis.gui import QgsRendererPropertiesDialog
            dialog = QgsRendererPropertiesDialog(layer, QgsStyle.defaultStyle(), False, self)
            (getattr(dialog, "exec", None) or dialog.exec_)()
        else:
            return
        self._customised.add(key)
        layer.triggerRepaint()
        self.map.refresh()

    def release(self):
        """Drop the map layers now. QGIS 3.22 crashes on exit when layers outlive its data providers."""
        self.map.unsetMapTool(self.identify_tool)
        self.map.setLayers([])
        self.outlines = self.highlight = self.basemap = self.thematic = None

    def _update_map_layers(self):
        layers = [self.highlight] + ([self.thematic] if self.thematic else []) + [self.outlines]
        basemap = [self.basemap] if self.basemap is not None and self.basemap.isValid() else []
        self.map.setLayers(layers + basemap)

    # --- Gemeinde -------------------------------------------------------------------------------

    def show_gemeinde(self, gemeinde: Optional[Gemeinde], zoom: bool = True):
        self.details.show_gemeinde(gemeinde)
        if gemeinde is None:
            return
        set_keys(self.highlight, [gemeinde.key])
        self.highlight.triggerRepaint()
        self._fill_table(gemeinde)
        if zoom and self.highlight.featureCount() > 0:
            self.map.setExtent(to_web_mercator(self.highlight.extent(), self.highlight.crs(), padding=0.25))

    def _fill_table(self, gemeinde: Gemeinde):
        rows = self.data.gemeinde_details(gemeinde.key) or [("Gemeinde", gemeinde.name),
                                                             ("Boundary", "Not available for this Gemeinde")]
        if self._values:
            value = self._values.get(gemeinde.key)
            ranked = sorted(self._values.values(), reverse=True)
            rows = [(self._value_title, format_number(value)),
                    ("Rank", f"{ranked.index(value) + 1:,} of {len(ranked):,}" if value is not None else "-")] + rows
        self.table.setRowCount(len(rows))
        for row, (name, value) in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem("" if value is None else str(value)))
        self.table.resizeRowsToContents()
        # Wide enough for the longest value (e.g. the GML ID) without cutting it off
        needed = sum(self.table.sizeHintForColumn(column) for column in (0, 1)) + 70
        self.info_card.setMinimumWidth(max(320, min(needed, INFO_MAX_WIDTH)))

    def _toggle_identify(self, active: bool):
        if active:
            self.map.setMapTool(self.identify_tool)
        elif self.map.mapTool() is self.identify_tool:
            self.map.unsetMapTool(self.identify_tool)

    def _identify(self, point, _button=None):
        transform = QgsCoordinateTransform(self.map.mapSettings().destinationCrs(), self.outlines.crs(),
                                           QgsProject.instance())
        point = transform.transform(point)
        request = QgsFeatureRequest().setFilterRect(QgsRectangle(point.x(), point.y(), point.x(), point.y()))
        clicked = QgsGeometry.fromPointXY(point)
        for feature in self.outlines.getFeatures(request):
            if feature.geometry().contains(clicked):
                self.picker.set_gemeinde(int(feature["g_key"]))
                return

    # --- Thematic map -----------------------------------------------------------------------------

    def _current_chart(self) -> Optional[Chart]:
        index = self.chart.currentIndex()
        return self._charts[index] if 0 <= index < len(self._charts) else None

    def _fill_charts(self):
        self._charts = self.data.charts_for(self.category.currentText())
        refill(self.chart, [(chart.title, chart.table) for chart in self._charts])
        self._fill_attributes()

    def _fill_attributes(self):
        chart = self._current_chart()
        schema = self.data.schema(chart.table) if chart else None
        refill(self.attribute, [(self.data.label(v, chart.table), v) for v in schema.values] if schema else [])
        years = self.data.dimension_values(chart.table, "year") if schema and "year" in schema.dimensions else []
        refill(self.year, [(str(year), year) for year in years], len(years) - 1)
        self.year.setVisible(bool(years))
        self.year_label.setVisible(bool(years))
        # Averages make sense for average-age tables; everything else defaults to sums
        self.aggregate.setCurrentIndex(1 if chart and chart.base.endswith("avg_age") else 0)

    def _build_thematic(self):
        chart, column = self._current_chart(), self.attribute.currentData()
        if chart is None or column is None:
            return None
        year = self.year.currentData() if self.year.count() else None
        values, year = self.data.area_values(chart.table, column, self.aggregate.currentData(), year)
        value_label = self.data.label(column, chart.table)
        title = f"{chart.title}: {value_label}" + (f", {year}" if year else "")
        # Shapefile field names are limited to 10 characters
        layer, legend = thematic_layer(self.outlines, values, column[:10], title, self.classes.currentData())
        self._last_key = (chart.table, column, self.aggregate.currentData(), year, self.classes.currentData())
        return layer, legend, values, title, value_label + (f" ({year})" if year else "")

    def show_thematic(self):
        built = self._build_thematic()
        if built is None:
            return
        layer, legend, values, title, value_title = built
        self.thematic = layer
        self._thematic_key = self._last_key
        self._customised.discard("thematic")
        self._values, self._value_title = values, value_title
        if "highlight" not in self._customised:
            apply_style(self.highlight, HIGHLIGHT_OUTLINE_STYLE)
        self._update_map_layers()
        self.legend.show_entries(f"{title}. Each class holds about the same number of Gemeinden.", legend)
        self.show_gemeinde(self.picker.gemeinde(), zoom=False)

    def clear_thematic(self):
        self.thematic, self._values, self._value_title, self._thematic_key = None, {}, "", None
        if "highlight" not in self._customised:
            apply_style(self.highlight, HIGHLIGHT_STYLE)
        self.legend.setVisible(False)
        self._update_map_layers()
        self.show_gemeinde(self.picker.gemeinde(), zoom=False)

    def save_thematic(self):
        built = self._build_thematic()
        if built is None:
            return
        layer, _, values, title, _ = built
        path, chosen_filter = QFileDialog.getSaveFileName(self, "Save thematic layer", safe_file_name(title) + ".gpkg",
                                                          FILE_FILTERS)
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".shp" if "Shapefile" in chosen_filter else ".gpkg"
        error = write_layer(layer, path)
        if error:
            QMessageBox.critical(self, "Save as layer", f"The layer could not be saved:\n{error}")
            return
        saved = QgsVectorLayer(path, title, "ogr")
        if not saved.isValid():
            QMessageBox.critical(self, "Save as layer", f"The saved layer could not be opened:\n{path}")
            return
        # The map on screen, with any symbology and labels the user set, when it is the one being saved
        styled = self.thematic if self.thematic is not None and self._thematic_key == self._last_key else layer
        saved.setRenderer(styled.renderer().clone())
        if styled.labeling() is not None:
            saved.setLabeling(styled.labeling().clone())
            saved.setLabelsEnabled(styled.labelsEnabled())
        save_default_style(saved, path)
        QgsProject.instance().addMapLayer(saved)
        QMessageBox.information(self, "Save as layer",
                                f"{len(values):,} Gemeinden saved to:\n{path}\n\nThe layer was added to the QGIS project.")
