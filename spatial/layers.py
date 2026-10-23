# -*- coding: utf-8 -*-
"""QGIS layers for the dashboard: Gemeinde boundaries, the basemap, thematic maps and map images."""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsFillSymbol,
                       QgsGraduatedSymbolRenderer, QgsMapRendererParallelJob, QgsMapSettings, QgsProject,
                       QgsRasterLayer, QgsRectangle, QgsRendererRange, QgsSingleSymbolRenderer, QgsVectorFileWriter,
                       QgsVectorLayer)
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor

from ..charts.plotting import compact
from ..core.style import BLUE_RAMP
from ..core.data import GEMEINDE_LAYER

WEB_MERCATOR = QgsCoordinateReferenceSystem("EPSG:3857")
OSM_URI = "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmin=0&zmax=19"
HIGHLIGHT_STYLE = {"color": "235,104,52,45", "outline_color": "235,104,52,255", "outline_width": "0.9"}
# Boundary outlines per theme: dark lines on the light map, light lines on the dark one
OUTLINE_STYLES = {"light": {"color": "0,0,0,0", "outline_color": "82,81,78,110", "outline_width": "0.18"},
                  "dark": {"color": "0,0,0,0", "outline_color": "220,218,210,90", "outline_width": "0.18"}}
CANVAS_COLOURS = {"light": (252, 252, 251), "dark": (26, 26, 25)}
DEFAULT_BASEMAPS = {"light": "OpenStreetMap, muted", "dark": "OpenStreetMap, dark"}
HIGHLIGHT_OUTLINE_STYLE = {"color": "0,0,0,0", "outline_color": "235,104,52,255", "outline_width": "1.1"}
OUTLINE_STYLE = {"color": "0,0,0,0", "outline_color": "82,81,78,110", "outline_width": "0.18"}
CLASS_OUTLINE = "255,255,255,170"
FILE_DRIVERS = {".gpkg": "GPKG", ".shp": "ESRI Shapefile"}
# Ramp steps used for 3 to 7 classes, spread over the light-to-dark blue ramp
RAMP_STEPS = {3: (1, 3, 5), 4: (0, 2, 4, 6), 5: (0, 2, 3, 4, 6), 6: (0, 1, 2, 3, 4, 6), 7: (0, 1, 2, 3, 4, 5, 6)}

LegendEntry = Tuple[str, str]  # (colour, label)


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


def osm_layer(look: str = "muted") -> QgsRasterLayer:
    """OpenStreetMap tiles in one of three looks: standard, muted (desaturated, so data colours stand out)
    or dark (inverted grey, for the dark theme)."""
    layer = QgsRasterLayer(OSM_URI, "OpenStreetMap", "wms")
    if layer.isValid():
        style_basemap(layer, look)
    return layer


def style_basemap(layer: QgsRasterLayer, look: str):
    hue = layer.hueSaturationFilter()
    dark = look == "dark"
    hue.setSaturation({"standard": 0, "muted": -65, "dark": -100}.get(look, 0))
    if hasattr(hue, "setInvertColors"):
        hue.setInvertColors(dark)
    layer.brightnessFilter().setBrightness(-35 if dark else 0)
    layer.brightnessFilter().setContrast(-20 if dark else 0)
    layer.triggerRepaint()


OSM_LOOKS = (("OpenStreetMap", "standard"), ("OpenStreetMap, muted", "muted"), ("OpenStreetMap, dark", "dark"))
NO_BASEMAP = "No basemap"


def basemap_choices() -> List[str]:
    """Names of the basemaps that can be shown: OpenStreetMap in three looks, the XYZ tile connections set
    up in the QGIS Browser, and the raster layers of the current project."""
    names = [name for name, _ in OSM_LOOKS]
    try:
        from qgis.core import QgsXyzConnectionUtils
        names += [f"XYZ: {name}" for name in QgsXyzConnectionUtils.connectionList()]
    except (ImportError, AttributeError):
        pass
    names += [f"Project: {layer.name()}" for layer in QgsProject.instance().mapLayers().values()
              if isinstance(layer, QgsRasterLayer)]
    return names + [NO_BASEMAP]


def basemap_layer(name: str) -> Optional[QgsRasterLayer]:
    """A new basemap layer for a name from basemap_choices(), owned by the caller (not added to the project)."""
    looks = dict(OSM_LOOKS)
    if name in looks:
        return osm_layer(looks[name])
    if name.startswith("XYZ: "):
        try:
            from qgis.core import QgsXyzConnectionUtils
            connection = QgsXyzConnectionUtils.connection(name[5:])
            return QgsRasterLayer(connection.encodedUri(), name[5:], "wms")
        except (ImportError, AttributeError):
            return None
    if name.startswith("Project: "):
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsRasterLayer) and layer.name() == name[9:]:
                # A copy, so removing the layer from the project cannot break the dashboard map
                return layer.clone()
    return None


def to_web_mercator(extent: QgsRectangle, source_crs: QgsCoordinateReferenceSystem, padding: float = 0.08) -> QgsRectangle:
    transform = QgsCoordinateTransform(source_crs, WEB_MERCATOR, QgsProject.instance())
    rectangle = transform.transformBoundingBox(extent)
    rectangle.grow(max(rectangle.width(), rectangle.height()) * padding)
    return rectangle


# --- Thematic maps ---------------------------------------------------------------------------------

def quantile_breaks(values: Sequence[float], classes: int) -> List[float]:
    """Class limits so each class holds about the same number of Gemeinden; duplicates are merged."""
    ordered = sorted(values)
    if not ordered:
        return []
    breaks = [ordered[0]]
    for step in range(1, classes + 1):
        value = ordered[min(len(ordered) - 1, round(step * len(ordered) / classes) - 1)]
        if value > breaks[-1]:
            breaks.append(value)
    if len(breaks) == 1:
        breaks.append(ordered[-1])
    return breaks


def graduated_renderer(field_name: str, values: Sequence[float], classes: int = 5
                       ) -> Tuple[QgsGraduatedSymbolRenderer, List[LegendEntry]]:
    breaks = quantile_breaks(values, classes)
    count = max(min(len(breaks) - 1, 7), 1)
    colours = [BLUE_RAMP[i] for i in RAMP_STEPS.get(count, RAMP_STEPS[7])[:count]] if count >= 3 else \
        [BLUE_RAMP[2], BLUE_RAMP[5]][:count]
    ranges, legend = [], []
    for index, colour in enumerate(colours):
        lower, upper = breaks[index], breaks[index + 1]
        text = f"{compact(lower)} to {compact(upper)}"
        symbol = QgsFillSymbol.createSimple({"color": colour, "outline_color": CLASS_OUTLINE, "outline_width": "0.12"})
        ranges.append(QgsRendererRange(lower, upper, symbol, text))
        legend.append((colour, text))
    return QgsGraduatedSymbolRenderer(field_name, ranges), legend


def thematic_layer(source: QgsVectorLayer, values: Dict[int, float], field_name: str, name: str,
                   classes: int = 5) -> Tuple[QgsVectorLayer, List[LegendEntry]]:
    """A memory layer with one feature per Gemeinde that has a value, styled in quantile classes."""
    # Fields are declared in the URI: QgsField type enums differ between QGIS 3 (QVariant) and 4 (QMetaType)
    fields = f"field=g_key:long&field=gemeinde:string&field=kreis:string&field={field_name}:double"
    layer = QgsVectorLayer(f"MultiPolygon?crs={source.crs().authid()}&{fields}", name, "memory")
    features = []
    for source_feature in source.getFeatures():
        key = source_feature["g_key"]
        if key not in values:
            continue
        feature = QgsFeature(layer.fields())
        feature.setGeometry(source_feature.geometry())
        feature.setAttributes([key, source_feature["gemeinde_name"], source_feature["kreis_name"], float(values[key])])
        features.append(feature)
    layer.dataProvider().addFeatures(features)
    layer.updateExtents()
    renderer, legend = graduated_renderer(field_name, list(values.values()), classes)
    layer.setRenderer(renderer)
    return layer, legend


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


def save_default_style(layer: QgsVectorLayer, path: str):
    """Store the layer's style with the file so it opens styled later: inside a GeoPackage, or as a
    .qml file next to a Shapefile."""
    if path.lower().endswith(".gpkg"):
        try:
            layer.saveStyleToDatabase("CenGeo BW", "Thematic map from the CenGeo BW dashboard", True, "")
            return
        except Exception:
            pass
    layer.saveNamedStyle(os.path.splitext(path)[0] + ".qml")


def render_map_image(data_path: str, keys: Sequence[int], path: str, size=(1600, 1000)) -> Optional[str]:
    """Render the given Gemeinden over the basemap to a PNG for the PDF report."""
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
