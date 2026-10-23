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


OSM_CREDIT = "© OpenStreetMap contributors"
OSM_LOOKS = {"OpenStreetMap": "standard", "OpenStreetMap, muted": "muted", "OpenStreetMap, dark": "dark"}

# Open tile services: (URL template, highest zoom, credit to show under the map)
TILE_SERVICES = {
    "CARTO Positron (light)": ("https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png", 20,
                               "© OpenStreetMap contributors © CARTO"),
    "CARTO Dark Matter (dark)": ("https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png", 20,
                                 "© OpenStreetMap contributors © CARTO"),
    "CARTO Voyager": ("https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png", 20,
                      "© OpenStreetMap contributors © CARTO"),
    "Esri World Imagery (satellite)": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", 19,
        "Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"),
    "Esri World Topographic": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}", 19,
        "Source: Esri and its data providers"),
    "Esri Light Gray Canvas": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        16, "Source: Esri, HERE, Garmin, © OpenStreetMap contributors"),
    "OpenTopoMap": ("https://tile.opentopomap.org/{z}/{x}/{y}.png", 17,
                    "© OpenStreetMap contributors, SRTM · Map style © OpenTopoMap (CC-BY-SA)"),
}


def basemap_choices() -> List[str]:
    """Names of the basemaps that can be shown: OpenStreetMap in three looks, open tile services (CARTO,
    Esri, OpenTopoMap), the XYZ tile connections set up in the QGIS Browser and the raster layers of the
    current project."""
    names = list(OSM_LOOKS) + list(TILE_SERVICES)
    try:
        from qgis.core import QgsXyzConnectionUtils
        names += [f"XYZ: {name}" for name in QgsXyzConnectionUtils.connectionList()]
    except (ImportError, AttributeError):
        pass
    names += [f"Project: {layer.name()}" for layer in QgsProject.instance().mapLayers().values()
              if isinstance(layer, QgsRasterLayer)]
    return names


def basemap_layer(name: str) -> Optional[QgsRasterLayer]:
    """A new basemap layer for a name from basemap_choices(), owned by the caller (not added to the project)."""
    if name in OSM_LOOKS:
        return osm_layer(OSM_LOOKS[name])
    if name in TILE_SERVICES:
        url, zoom, _ = TILE_SERVICES[name]
        return QgsRasterLayer(f"type=xyz&url={url}&zmin=0&zmax={zoom}", name, "wms")
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


def basemap_credit(name: str) -> str:
    if name in OSM_LOOKS:
        return f"Basemap: {OSM_CREDIT}"
    if name in TILE_SERVICES:
        return f"Basemap: {TILE_SERVICES[name][2]}"
    if name.startswith("XYZ: "):
        return f"Basemap: {name[5:]}"
    if name.startswith("Project: "):
        return f"Basemap: {name[9:]}"
    return f"Basemap: {name}"


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


CONTEXT_STYLE = {"color": "235,104,52,22", "outline_color": "235,104,52,150", "outline_width": "0.35"}
OVERVIEW_STYLE = {"color": "225,224,217,255", "outline_color": "255,255,255,255", "outline_width": "0.12"}
OVERVIEW_CONTEXT_STYLE = {"color": "246,196,170,255", "outline_color": "255,255,255,255", "outline_width": "0.12"}
OVERVIEW_HIGHLIGHT_STYLE = {"color": "235,104,52,255", "outline_color": "200,80,30,255", "outline_width": "0.3"}


def render_map_image(data_path: str, keys: Sequence[int], path: str, size=(1600, 1000),
                     context_keys: Optional[Sequence[int]] = None, overview: bool = False
                     ) -> Optional[Tuple[str, Tuple[float, float, float, float]]]:
    """Map image for PDF reports, rendered at exactly size so it fills its frame. Returns the image path and
    the extent shown (xmin, ymin, xmax, ymax in EPSG:3857), which reports use for the scale bar and the
    graticule. The local map shows the given Gemeinden over the basemap, with an optional surrounding area
    (e.g. their Kreis) shaded lightly; the overview shows all of Baden-Württemberg without basemap."""
    if overview:
        highlight = boundary_layer(data_path, "Selection", OVERVIEW_HIGHLIGHT_STYLE, keys)
        context = boundary_layer(data_path, "Context", OVERVIEW_CONTEXT_STYLE, context_keys) if context_keys else None
        state = boundary_layer(data_path, "Baden-Württemberg", OVERVIEW_STYLE)
        layers = [highlight] + ([context] if context else []) + [state]
        extent_layer, padding = state, 0.03
    else:
        highlight = boundary_layer(data_path, "Selection", HIGHLIGHT_STYLE, keys)
        context = boundary_layer(data_path, "Context", CONTEXT_STYLE, context_keys) if context_keys else None
        outlines = boundary_layer(data_path, "Gemeinden")
        basemap = osm_layer("muted")
        layers = [highlight] + ([context] if context else []) + [outlines] + ([basemap] if basemap.isValid() else [])
        extent_layer, padding = highlight, 0.45
    if not highlight.isValid() or highlight.featureCount() == 0:
        return None
    settings = QgsMapSettings()
    settings.setLayers(layers)
    settings.setDestinationCrs(WEB_MERCATOR)
    settings.setOutputSize(QSize(*size))
    settings.setBackgroundColor(QColor(255, 255, 255) if overview else QColor(252, 252, 251))
    settings.setExtent(to_web_mercator(extent_layer.extent(), extent_layer.crs(), padding=padding))
    shown = settings.visibleExtent()
    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    image = job.renderedImage()
    if image.isNull() or not image.save(path, "PNG"):
        return None
    return path, (shown.xMinimum(), shown.yMinimum(), shown.xMaximum(), shown.yMaximum())
