# Data licence

This file covers the data shipped in `data/cengeobw.gpkg` and everything the plugin produces from it
(charts, PDF reports, PNG images and exported layers). The plugin's source code is licensed separately.

## Statistical data

| | |
|---|---|
| Provider | Statistisches Landesamt Baden-Württemberg, <https://www.statistik-bw.de> |
| Content | Gemeinde, Kreis and Land statistics on demography, education, population forecasts, living, tourism and employment |
| Licence | Datenlizenz Deutschland - Namensnennung - Version 2.0 (`dl-de/by-2-0`), <https://www.govdata.de/dl-de/by-2-0> |
| Attribution | Datenquelle: Statistisches Landesamt Baden-Württemberg, dl-de/by-2-0 |
| Changes | Converted from the original tables into a GeoPackage; numbers stored as text were converted to numeric types. No values were altered. |

## Gemeinde boundaries

| | |
|---|---|
| Provider | Landesamt für Geoinformation und Landentwicklung Baden-Württemberg (LGL), <https://www.lgl-bw.de> |
| Content | Gemeinde boundaries (ALKIS), EPSG:4326 |
| Licence | Datenlizenz Deutschland - Namensnennung - Version 2.0 (`dl-de/by-2-0`), <https://www.govdata.de/dl-de/by-2-0> |
| Attribution | Datenquelle: LGL, www.lgl-bw.de, dl-de/by-2-0 |
| Changes | Geometries simplified with a tolerance of about 10 m (0.0001°); borders shared by neighbouring Gemeinden were kept identical. |

## Basemaps

The maps load tiles from online services while the plugin is running; no tiles are stored in this
repository. The PDF reports always use OpenStreetMap. In the Spatial Query tab the basemap can be chosen,
and the credit of the chosen service is shown under the map:

- OpenStreetMap (`tile.openstreetmap.org`): © OpenStreetMap contributors
- CARTO Positron, Dark Matter and Voyager: © OpenStreetMap contributors © CARTO; free use is subject to the
  CARTO basemap terms, <https://carto.com/basemaps>
- Esri World Imagery, World Topographic and Light Gray Canvas: Esri and its data providers; use is subject
  to the Esri terms of use, <https://www.esri.com/en-us/legal/terms/full-master-agreement>
- OpenTopoMap: © OpenStreetMap contributors, SRTM, map style © OpenTopoMap (CC-BY-SA)

- © OpenStreetMap contributors, data under the Open Database License (ODbL), <https://www.openstreetmap.org/copyright>
- The tile servers are run by volunteers and subject to the tile usage policy,
  <https://operations.osmfoundation.org/policies/tiles/>. For heavy or commercial use, switch the basemap
  URL in `spatial/layers.py` (`OSM_URI`) to a commercial tile provider.

## Using the outputs

Reports, images and layers created with the plugin contain the data above, so the attributions must
stay with them. The plugin prints them at the bottom of every PDF page and shows them in the dashboard's
status bar and *Help → About and data sources*. The wording used there is defined in
`core/attribution.py`.
