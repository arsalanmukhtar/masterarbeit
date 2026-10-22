# CenGeo BW: Baden-Württemberg Census Dashboard

A QGIS plugin for exploring official statistics of every Gemeinde in Baden-Württemberg: interactive
charts, comparisons with the Kreis and the whole state, side-by-side comparison of two Gemeinden,
PDF reports and thematic map layers.

The data ships with the plugin as a GeoPackage, so it works offline. No database server, password or
extra Python package is needed.

This repository contains the plugin's source code and the script that extracts the data from the
original PostgreSQL database into the GeoPackage.

## Installation

1. Download the plugin ZIP (for example `CenGeoBW-2.0.0.zip`) from the
   [Releases page](https://github.com/arsalanmukhtar/masterarbeit/releases). Use the release asset,
   not GitHub's "Source code" ZIP, which does not contain the data.
2. In QGIS open *Plugins → Manage and Install Plugins… → Install from ZIP*, choose the file and click
   *Install Plugin*.
3. Start the dashboard from the toolbar icon or *Plugins → CenGeo BW → Census Dashboard*.

**Requirements:** QGIS 3.22 or newer, including QGIS 4. The charts use matplotlib, which is included in
the QGIS installers for Windows and macOS; on Linux install it with the package manager
(e.g. `sudo apt install python3-matplotlib`). The OpenStreetMap basemap needs an internet connection;
everything else works offline.

## Using the dashboard

| Tab | What it does |
|---|---|
| **Visualization** | Charts for one Gemeinde. Pick a category, a chart, the X axis and the value to show; tables with more dimensions get filters (e.g. school type, feature, age range). |
| **Gemeinde · Kreis · Land** | The same value for a Gemeinde, its Kreis and Baden-Württemberg side by side. |
| **Gemeinde · Gemeinde** | Two Gemeinden side by side. |
| **Spatial Query** | Find a Gemeinde by name or by clicking the map (*Identify on map*), see its attributes, and create a thematic layer (one value per Gemeinde for the latest year) saved as GeoPackage or Shapefile and added to the QGIS project. |

- Gemeinde lists are searchable: type any part of the name.
- Charts update as soon as a selection changes; hover over a bar to see its value.
- *Export category report (PDF)* writes a PDF with a map and every chart and table of the selected
  category, plus each chart as a PNG image.
- The window opens at 85 % of the screen. The side panel scrolls on small screens, and the divider
  between panel and chart can be dragged.

## Data and licence

The statistics come from the Statistisches Landesamt Baden-Württemberg and the Gemeinde boundaries from
the LGL Baden-Württemberg, both under *Datenlizenz Deutschland - Namensnennung - Version 2.0*. See
[DATA_LICENSE.md](DATA_LICENSE.md) for the attribution that must accompany the data and anything
produced from it.

## Development

### Repository layout

The repository root is the plugin folder; QGIS expects it to be named `CenGeoBW` once installed.

```
masterarbeit/            (installed as CenGeoBW/)
├── __init__.py          QGIS entry point (classFactory)
├── plugin.py            toolbar/menu action, finding the data file, window lifetime
├── compat.py            the few Qt5/Qt6 differences
├── metadata.txt         plugin metadata (version, QGIS 3.22 to 4.99)
├── core/
│   ├── data.py          CensusData: all queries against the GeoPackage
│   ├── models.py        data classes (Gemeinde, Chart, ChartQuery, Series, ...)
│   └── attribution.py   data credits used in the UI and reports
├── charts/plotting.py   bar charts and hover tooltips (matplotlib)
├── reports/
│   ├── pdf_report.py    PDF pages: title, map, tables, charts
│   └── builders.py      the three report types
├── spatial/layers.py    QGIS layers, thematic layers, file export, map images
├── ui/
│   ├── main_window.py   dashboard window
│   ├── widgets.py       Gemeinde picker, chart selector, chart canvas
│   ├── chart_tabs.py    the three chart tabs (shared base class)
│   └── spatial_tab.py   map tab
├── tools/
│   ├── build_geopackage.py   PostgreSQL dump → data/cengeobw.gpkg
│   └── package_plugin.py     builds the release ZIP
└── data/cengeobw.gpkg   generated, not committed (see below)
```

### Setup

1. Install QGIS (current LTR) and, from *Plugins → Manage and Install Plugins*, the **Plugin Reloader**
   plugin.
2. Clone the repository:
   ```
   git clone https://github.com/arsalanmukhtar/masterarbeit.git
   ```
3. Link the clone into your QGIS profile under the name `CenGeoBW`, so QGIS loads it directly. On
   Windows, in `cmd` (a junction needs no administrator rights):
   ```
   mklink /J "%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\CenGeoBW" "C:\path\to\masterarbeit"
   ```
   On Linux/macOS: `ln -s /path/to/masterarbeit ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/CenGeoBW`
   (macOS: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/CenGeoBW`).
4. Put a data file at `data/cengeobw.gpkg`: build it (next section) or copy it out of a release ZIP.
5. Restart QGIS and enable *CenGeo BW* in the plugin manager. After code changes, reload it with
   Plugin Reloader.

Write Qt code against `qgis.PyQt` with fully scoped enums (`Qt.Orientation.Horizontal`, not
`Qt.Horizontal`) so the plugin keeps working on both QGIS 3 (Qt5) and QGIS 4 (Qt6), and keep the code
compatible with Python 3.9 (the Python of QGIS 3.22).

### Rebuilding the data

The GeoPackage is generated from the original PostgreSQL/PostGIS database dump:

```
createdb bwapp
pg_restore --no-owner -d bwapp bwapp.backup
python tools/build_geopackage.py --dbname bwapp --user postgres
```

On Windows run this in the *OSGeo4W Shell*, which provides Python, psycopg2 and `ogr2ogr`; the password
is read from `PGPASSWORD` or `pgpass.conf`. The script converts numeric text columns to numbers,
simplifies the boundaries (about 10 m, `--tolerance`), adds indexes and checks the row counts.

### Releasing

1. Raise `version` in `metadata.txt` and add a `changelog` line.
2. Run `python tools/package_plugin.py`. It writes `dist/CenGeoBW-2.0.0.zip`, named after the version in `metadata.txt`.
3. Create a GitHub release for the version and attach the ZIP: on GitHub via *Releases → Draft a new
   release*, or with the GitHub CLI:
   ```
   gh release create v2.0.0 dist/CenGeoBW-2.0.0.zip --repo arsalanmukhtar/masterarbeit --title "CenGeo BW 2.0.0" --notes "..."
   ```

The data file and ZIPs are not committed (`.gitignore`): GitHub limits files to 100 MB and every
committed data version would stay in the repository history.
