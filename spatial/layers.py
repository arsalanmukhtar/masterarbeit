# -*- coding: utf-8 -*-
"""QGIS layers for the dashboard: Gemeinde boundaries, the OSM basemap, thematic layers and map images."""
from __future__ import annotations

import os
from typing import Dict, Optional, Sequence

from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsFillSymbol,
                       QgsMapRendererParallelJob, QgsMapSettings, QgsProject, QgsRasterLayer, QgsRectangle,
                       QgsSingleSymbolRenderer, QgsVectorFileWriter, QgsVectorLayer)
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor

from ..core.data import GEMEINDE_LAYER

WEB_MERCATOR = QgsCoordinateReferenceSystem("EPSG:3857")
OSM_URI = "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmin=0&zmax=19"
HIGHLIGHT_STYLE = {"color": "255,98,0,50", "outline_color": "255,98,0,255", "outline_width": "0.8"}
OUTLINE_STYLE = {"color": "0,0,0,0", "outline_color": "90,90,90,160", "outline_width": "0.2"}
THEMATIC_STYLE = {"color": "46,134,222,90", "outline_color": "30,60,110,200", "outline_width": "0.2"}
FILE_DRIVERS = {".gpkg": "GPKG", ".shp": "ESRI Shapefile"}


def apply_style(layer: QgsVectorLayer, properties: Dict[str, str]) -> QgsVectorLayer:
    layer.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(properties)))
    return layer


def boundary_layer(data_path: str, name: str = "Gemeinden", style: Optional[Dict[str, str]] = None,
                   keys: Optional[Sequence[int]] = None) -> QgsVectorLayer:
    """Gemeinde boundaries straight from the GeoPackage, optionally limited to some Gemeinden."""
    layer = QgsVectorLayer(f"{data_path}|layername={GEMEINDE_LAYER}", name, "ogr")
    if keys is not None:
        set_keys(layer, keys)
    return apply_style(layer, style or OUTLINE_STYLE)


def set_keys(layer: QgsVectorLayer, keys: Sequence[int]):
    layer.setSubsetString(f"\"g_key\" IN ({', '.join(str(int(key)) for key in keys) or 'NULL'})")


def osm_layer() -> QgsRasterLayer:
    return QgsRasterLayer(OSM_URI, "OpenStreetMap", "wms")


def to_web_mercator(extent: QgsRectangle, source_crs: QgsCoordinateReferenceSystem, padding: float = 0.08) -> QgsRectangle:
    transform = QgsCoordinateTransform(source_crs, WEB_MERCATOR, QgsProject.instance())
    rectangle = transform.transformBoundingBox(extent)
    rectangle.grow(max(rectangle.width(), rectangle.height()) * padding)
    return rectangle


def thematic_layer(source: QgsVectorLayer, values: Dict[int, float], field_name: str, name: str) -> QgsVectorLayer:
    """A memory layer with one feature per Gemeinde that has a value."""
    # Fields are declared in the URI: QgsField type enums differ between QGIS 3 (QVariant) and 4 (QMetaType)
    fields = f"field=g_key:long&field=gemeinde:string&field=kreis:string&field={field_name}:double"
    layer = QgsVectorLayer(f"MultiPolygon?crs={source.crs().authid()}&{fields}", name, "memory")
    provider = layer.dataProvider()
    features = []
    for source_feature in source.getFeatures():
        key = source_feature["g_key"]
        if key not in values:
            continue
        feature = QgsFeature(layer.fields())
        feature.setGeometry(source_feature.geometry())
        feature.setAttributes([key, source_feature["gemeinde_name"], source_feature["kreis_name"], float(values[key])])
        features.append(feature)
    provider.addFeatures(features)
    layer.updateExtents()
    return apply_style(layer, THEMATIC_STYLE)


def write_layer(layer: QgsVectorLayer, path: str) -> Optional[str]:
    """Save a layer as GeoPackage or Shapefile depending on the file extension. Returns an error message or None."""
    driver = FILE_DRIVERS.get(os.path.splitext(path)[1].lower())
    if driver is None:
        return f"Unsupported file type: {path}"
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = driver
    options.fileEncoding = "UTF-8"
    result = QgsVectorFileWriter.writeAsVectorFormatV3(layer, path, QgsProject.instance().transformContext(), options)
    error, message = result[0], result[1]
    # 0 is QgsVectorFileWriter.NoError; the enum's Python name differs between QGIS 3 and 4
    return None if int(error) == 0 else (message or f"Could not write {path}")


def render_map_image(data_path: str, keys: Sequence[int], path: str, size=(1600, 1000)) -> Optional[str]:
    """Render the given Gemeinden over OpenStreetMap to a PNG for the PDF report."""
    highlight = boundary_layer(data_path, "Selection", HIGHLIGHT_STYLE, keys)
    if not highlight.isValid() or highlight.featureCount() == 0:
        return None
    basemap = osm_layer()
    settings = QgsMapSettings()
    settings.setLayers([highlight, basemap] if basemap.isValid() else [highlight])
    settings.setDestinationCrs(WEB_MERCATOR)
    settings.setOutputSize(QSize(*size))
    settings.setBackgroundColor(QColor(255, 255, 255))
    settings.setExtent(to_web_mercator(highlight.extent(), highlight.crs(), padding=0.15))
    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    image = job.renderedImage()
    if image.isNull() or not image.save(path, "PNG"):
        return None
    return path
