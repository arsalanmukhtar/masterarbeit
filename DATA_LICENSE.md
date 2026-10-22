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

## Basemap

The Spatial Query tab and the map page of the PDF reports load map tiles from OpenStreetMap
(`tile.openstreetmap.org`) while the plugin is running. No OpenStreetMap data is stored in this repository.

- © OpenStreetMap contributors, data under the Open Database License (ODbL), <https://www.openstreetmap.org/copyright>
- The tile servers are run by volunteers and subject to the tile usage policy,
  <https://operations.osmfoundation.org/policies/tiles/>. For heavy or commercial use, switch the basemap
  URL in `spatial/layers.py` (`OSM_URI`) to a commercial tile provider.

## Using the outputs

Reports, images and layers created with the plugin contain the data above, so the attributions must
stay with them. The plugin prints them at the bottom of every PDF page and shows them in the dashboard's
status bar and *Help → About and data sources*. The wording used there is defined in
`core/attribution.py`.
