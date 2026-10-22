# -*- coding: utf-8 -*-
"""Map tab: find a Gemeinde by name or by clicking the map, and turn a statistic into a map layer."""
from __future__ import annotations

import os
from typing import Optional

from qgis.core import QgsCoordinateTransform, QgsFeatureRequest, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer
from qgis.gui import QgsMapCanvas, QgsMapToolEmitPoint
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QFormLayout, QFrame, QGroupBox,
                                 QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QScrollArea, QSplitter,
                                 QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..core.attribution import BASEMAP_CREDIT
from ..core.data import CensusData
from ..core.models import Gemeinde
from ..reports.pdf_report import safe_file_name
from ..spatial.layers import (HIGHLIGHT_STYLE, THEMATIC_STYLE, WEB_MERCATOR, apply_style, boundary_layer, osm_layer,
                              set_keys, thematic_layer, to_web_mercator, write_layer)
from .widgets import GemeindeDetails, GemeindePicker, _compact, _refill
from .chart_tabs import SIDE_PANEL_MIN_WIDTH

AGGREGATE_CHOICES = (("Sum", "SUM"), ("Average", "AVG"))
FILE_FILTERS = "GeoPackage (*.gpkg);;ESRI Shapefile (*.shp)"


class SpatialTab(QWidget):
    def __init__(self, data: CensusData, parent=None):
        super().__init__(parent)
        self.data = data
        data_path = str(data.path)

        # Map: selected Gemeinde over all boundaries over OpenStreetMap
        self.outlines = boundary_layer(data_path)
        self.highlight = boundary_layer(data_path, "Selected Gemeinde", HIGHLIGHT_STYLE, keys=[])
        self.basemap = osm_layer()
        self.thematic: Optional[QgsVectorLayer] = None
        self.map = QgsMapCanvas()
        self.map.setCanvasColor(QColor(255, 255, 255))
        self.map.enableAntiAliasing(True)
        self.map.setDestinationCrs(WEB_MERCATOR)
        self._update_map_layers()
        self.map.setExtent(to_web_mercator(self.outlines.extent(), self.outlines.crs(), padding=0.02))
        credit = QLabel(BASEMAP_CREDIT)
        credit.setAlignment(Qt.AlignmentFlag.AlignRight)
        credit.setStyleSheet("color: palette(mid); font-size: 8pt;")
        map_area = QWidget()
        map_layout = QVBoxLayout(map_area)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.addWidget(self.map, 1)
        map_layout.addWidget(credit)

        # Gemeinde box
        gemeinde_box = QGroupBox("Gemeinde")
        gemeinde_layout = QVBoxLayout(gemeinde_box)
        self.picker = GemeindePicker(data.gemeinden)
        self.details = GemeindeDetails()
        self.zoom_button = QPushButton("Zoom to Gemeinde")
        self.identify_button = QPushButton("Identify on map")
        self.identify_button.setCheckable(True)
        self.identify_button.setToolTip("Click a Gemeinde on the map to select it")
        buttons = QHBoxLayout()
        buttons.addWidget(self.zoom_button)
        buttons.addWidget(self.identify_button)
        gemeinde_layout.addWidget(self.picker)
        gemeinde_layout.addWidget(self.details)
        gemeinde_layout.addLayout(buttons)

        # Thematic layer box
        thematic_box = QGroupBox("Thematic layer")
        thematic_form = QFormLayout(thematic_box)
        thematic_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.category = _compact(QComboBox())
        self.chart = _compact(QComboBox())
        self.attribute = _compact(QComboBox())
        self.aggregate = _compact(QComboBox())
        _refill(self.category, [(category, category) for category in data.categories()])
        _refill(self.aggregate, AGGREGATE_CHOICES)
        self.create_button = QPushButton("Add layer to project…")
        self.create_button.setToolTip("One value per Gemeinde for the latest year, saved as GeoPackage or Shapefile")
        for title, widget in (("Category", self.category), ("Chart", self.chart), ("Attribute", self.attribute),
                              ("Aggregate", self.aggregate)):
            thematic_form.addRow(title, widget)
        thematic_form.addRow(self.create_button)

        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.addWidget(gemeinde_box)
        panel_layout.addWidget(thematic_box)
        panel_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(panel)
        scroll.setMinimumWidth(SIDE_PANEL_MIN_WIDTH)

        # Attribute table of the selected Gemeinde
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Attribute", "Value"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumWidth(220)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        for widget in (scroll, map_area, self.table):
            splitter.addWidget(widget)
        splitter.setStretchFactor(1, 1)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([340, 900, 300])
        QVBoxLayout(self).addWidget(splitter)

        self.identify_tool = QgsMapToolEmitPoint(self.map)
        self.identify_tool.canvasClicked.connect(self._identify)
        self.identify_tool.deactivated.connect(lambda: self.identify_button.setChecked(False))
        self.identify_button.toggled.connect(self._toggle_identify)
        self.zoom_button.clicked.connect(lambda: self.show_gemeinde(self.picker.gemeinde(), zoom=True))
        self.picker.gemeindeChanged.connect(lambda gemeinde: self.show_gemeinde(gemeinde, zoom=True))
        self.category.currentIndexChanged.connect(self._fill_charts)
        self.chart.currentIndexChanged.connect(self._fill_attributes)
        self.create_button.clicked.connect(self.create_thematic_layer)
        self._fill_charts()
        self.show_gemeinde(self.picker.gemeinde(), zoom=False)

    def release(self):
        """Drop the map layers now. QGIS 3.22 crashes on exit when layers outlive its data providers."""
        self.map.unsetMapTool(self.identify_tool)
        self.map.setLayers([])
        self.outlines = self.highlight = self.basemap = self.thematic = None

    def _update_map_layers(self):
        layers = [self.highlight] + ([self.thematic] if self.thematic else []) + [self.outlines]
        self.map.setLayers(layers + ([self.basemap] if self.basemap.isValid() else []))

    # --- Gemeinde -------------------------------------------------------------------------------

    def show_gemeinde(self, gemeinde: Optional[Gemeinde], zoom: bool = True):
        self.details.show_gemeinde(gemeinde)
        if gemeinde is None:
            return
        set_keys(self.highlight, [gemeinde.key])
        self.highlight.triggerRepaint()
        details = self.data.gemeinde_details(gemeinde.key) or [("Gemeinde", gemeinde.name),
                                                                ("Boundary", "Not available for this Gemeinde")]
        self.table.setRowCount(len(details))
        for row, (label, value) in enumerate(details):
            self.table.setItem(row, 0, QTableWidgetItem(label))
            self.table.setItem(row, 1, QTableWidgetItem("" if value is None else str(value)))
        if zoom and self.highlight.featureCount() > 0:
            self.map.setExtent(to_web_mercator(self.highlight.extent(), self.highlight.crs(), padding=0.25))
        self.map.refresh()

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

    # --- Thematic layer -------------------------------------------------------------------------

    def _fill_charts(self):
        self._charts = self.data.charts_for(self.category.currentText())
        _refill(self.chart, [(chart.title, chart.table) for chart in self._charts])
        self._fill_attributes()

    def _fill_attributes(self):
        index = self.chart.currentIndex()
        chart = self._charts[index] if 0 <= index < len(self._charts) else None
        schema = self.data.schema(chart.table) if chart else None
        _refill(self.attribute, [(self.data.label(value), value) for value in schema.values] if schema else [])
        # Averages make sense for average-age tables; everything else defaults to sums
        self.aggregate.setCurrentIndex(1 if chart and chart.base.endswith("avg_age") else 0)

    def create_thematic_layer(self):
        index = self.chart.currentIndex()
        if not 0 <= index < len(self._charts) or self.attribute.currentData() is None:
            return
        chart, column = self._charts[index], self.attribute.currentData()
        aggregate = self.aggregate.currentData()
        values, year = self.data.area_values(chart.table, column, aggregate)
        name = f"{chart.title.replace(' in Gemeinde', '')} - {self.data.label(column)}" + (f" {year}" if year else "")
        path, chosen_filter = QFileDialog.getSaveFileName(self, "Save thematic layer", safe_file_name(name) + ".gpkg",
                                                          FILE_FILTERS)
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".shp" if "Shapefile" in chosen_filter else ".gpkg"
        # Shapefile field names are limited to 10 characters
        layer = thematic_layer(self.outlines, values, column[:10], name)
        error = write_layer(layer, path)
        if error:
            QMessageBox.critical(self, "Thematic layer", f"The layer could not be saved:\n{error}")
            return
        saved = QgsVectorLayer(path, name, "ogr")
        if not saved.isValid():
            QMessageBox.critical(self, "Thematic layer", f"The saved layer could not be opened:\n{path}")
            return
        QgsProject.instance().addMapLayer(saved)
        # The dashboard map gets its own copy, so removing the layer from the project cannot break it
        self.thematic = apply_style(QgsVectorLayer(path, name, "ogr"), THEMATIC_STYLE)
        self._update_map_layers()
        self.map.refresh()
        QMessageBox.information(self, "Thematic layer",
                                f"{len(values)} Gemeinden saved to:\n{path}\n\nThe layer was added to the QGIS project.")
