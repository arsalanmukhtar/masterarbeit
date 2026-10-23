# CenGeo BW: Baden-Württemberg Census Dashboard

A QGIS plugin for exploring official statistics of every Gemeinde in Baden-Württemberg: interactive
charts, comparisons with the Kreis and the whole state, side-by-side comparison of two Gemeinden,
PDF reports and thematic map layers.

The data ships with the plugin as a GeoPackage, so it works offline. No database server, password or
extra Python package is needed.

This repository contains the plugin's source code and the script that extracts the data from the
original PostgreSQL database into the GeoPackage.

## Installation

**From the QGIS plugin repository:** *Plugins → Manage and Install Plugins → All*, search for
*CenGeo BW* and click *Install Plugin*. Updates then appear in the same dialog.

**From a ZIP file:** download `CenGeoBW-2.1.2.zip` from the
[Releases page](https://github.com/arsalanmukhtar/masterarbeit/releases), then in QGIS open
*Plugins → Manage and Install Plugins → Install from ZIP*.

Start the dashboard from the toolbar icon or *Plugins → CenGeo BW → Census Dashboard*. On first start
the plugin offers to download the census data (49 MB, once). It is stored in the QGIS profile folder and
used offline from then on. *Choose file…* in the same dialog opens a data file you already have.

**Requirements:** QGIS 3.22 or newer, including QGIS 4. The charts use matplotlib, which is included in
the QGIS installers for Windows and macOS; on Linux install it with the package manager
(e.g. `sudo apt install python3-matplotlib`). The data download and the OpenStreetMap basemap need an
internet connection; everything else works offline.

## Using the dashboard

| Tab | What it does |
|---|---|
| **Visualization** | A profile of one Gemeinde (population, change in ten years, average age, area, density) and charts of any statistic. Tick several values of a chart to compare them or to show their shares as stacked bars, stacked area or donut. Tables with more dimensions get filters such as school type, employee group or an age range. |
| **Gemeinde · Kreis · Land** | The same value for a Gemeinde, its Kreis and Baden-Württemberg. Opens as an index (first year = 100), so areas of very different size can be compared on one axis; switch to *Values* for the actual numbers. |
| **Gemeinde · Gemeinde** | Two Gemeinden side by side, as values or as an index. |
| **Spatial Query** | Find a Gemeinde by name or by clicking the map (*Identify on map*) and see its attributes. *Thematic map* colours every Gemeinde by a statistic and year in three to seven classes, with a legend and the rank of the selected Gemeinde. *Save as layer* writes it as GeoPackage or Shapefile, keeps the colours and labels and adds it to the QGIS project. *Map layers* picks the basemap (OpenStreetMap standard, muted or dark, the XYZ connections of the QGIS Browser, or a raster layer of the project) and opens the QGIS layer properties of each map layer for symbology, labels and more. |

- Every dropdown is searchable: type any part of an entry.
- Charts update as soon as a selection changes. The chart type menu offers the types that fit the data:
  line, area or bars for years and ages, bars or donut for categories, and stacked bars, stacked area or
  donut when several values of one Gemeinde are shown. Hover over a chart to read exact values, or
  switch to *Table*.
- The ten-year population change carries a coloured arrow: green for growth of 2 % or more, yellow for
  smaller growth, orange for a decline under 2 % and red for a decline of 2 % or more.
- *Export* saves the chart as PNG, SVG or PDF, or its data as CSV (opens in Excel).
- *Create PDF report* writes a PDF with a map and every chart and table of the selected category,
  plus each chart as a PNG image.
- *Dark theme* at the top right of the window (or *View → Dark theme*) switches between a light and a dark
  look; the choice is remembered. Saved chart images and PDF reports always use the light look.
- The window opens maximized and shows a loading page until the first tab is ready; the other tabs are
  prepared when they are first opened. Side panels take the width their content needs and scroll on
  small screens, and the dividers between the panels can be dragged.

## Data and licence

The statistics come from the Statistisches Landesamt Baden-Württemberg and the Gemeinde boundaries from
the LGL Baden-Württemberg, both under *Datenlizenz Deutschland - Namensnennung - Version 2.0*. See
[DATA_LICENSE.md](DATA_LICENSE.md) for the attribution that must accompany the data and anything
produced from it.

The plugin is free software under the GNU General Public License, version 2 or (at your option) any
later version; see [LICENSE](LICENSE). Copyright 2024 to 2026 Muhammad Arsalan Mukhtar.

The interface, charts and reports use the Inter typeface by Rasmus Andersson, included under the SIL
Open Font License 1.1 ([resources/fonts/OFL.txt](resources/fonts/OFL.txt)).

## Development

### Repository layout

The repository root is the plugin folder; QGIS expects it to be named `CenGeoBW` once installed.

```
masterarbeit/            (installed as CenGeoBW/)
├── __init__.py          QGIS entry point (classFactory)
├── plugin.py            toolbar/menu action, finding the data file, window lifetime
├── download.py          downloads and checks the census data on first start
├── compat.py            the few Qt5/Qt6 differences
├── metadata.txt         plugin metadata (version, QGIS 3.22 to 4.99)
├── core/
│   ├── data.py          CensusData: all queries against the GeoPackage
│   ├── models.py        data classes (Gemeinde, Chart, ChartQuery, Series, ...)
│   ├── style.py         colours and font location shared by charts, maps and the window
│   ├── labels.py        display names that correct or tidy the stored column descriptions
│   └── attribution.py   data credits used in the UI and reports
├── charts/plotting.py   line, area, bar, stacked and donut charts, small multiples, hover values
├── reports/
│   ├── pdf_report.py    PDF pages: title, map, tables, charts
│   └── builders.py      the three report types
├── spatial/layers.py    QGIS layers, thematic maps and their classes, file export, map images
├── ui/
│   ├── main_window.py   dashboard window
│   ├── theme.py         stylesheet and font of the dashboard window
│   ├── inputs.py        cards, searchable dropdowns, Gemeinde and value pickers, chart selector
│   ├── chart_panel.py   chart card with chart type, table view, index view and exports; Gemeinde profile
│   ├── chart_tabs.py    the three chart tabs (shared base class)
│   └── spatial_tab.py   map tab
├── resources/           Inter font (with its licence) and interface icons
├── tools/
│   ├── build_geopackage.py   PostgreSQL dump → data/cengeobw.gpkg
│   └── package_plugin.py     builds the release ZIP
└── data/cengeobw.gpkg   generated, not committed; when present it is used instead of the download
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

1. Raise `version` in `metadata.txt` and add a `changelog` line. Versions count up in the last digit from
   0 to 9 and then move on to the next minor version: 2.1.0, 2.1.1, ..., 2.1.9, 2.2.0.
2. Run `python tools/package_plugin.py`. It writes `dist/CenGeoBW-2.1.2.zip` (without data, for the QGIS
   plugin repository), named after the version in `metadata.txt`. `--with-data` adds the data file for an
   offline installation.
3. Create a GitHub release for the version and attach the ZIP: on GitHub via *Releases → Draft a new
   release*, or with the GitHub CLI:
   ```
   gh release create v2.1.2 dist/CenGeoBW-2.1.2.zip --repo arsalanmukhtar/masterarbeit --title "CenGeo BW 2.1.2" --notes-file notes.md
   ```
4. Upload the same ZIP at <https://plugins.qgis.org/plugins/> (log in with your OSGeo ID). After a staff
   member approves it, QGIS users get the update in the plugin manager.

### Publishing new data

1. Rebuild `data/cengeobw.gpkg` (see *Rebuilding the data*).
2. Raise `DATA_VERSION` in `download.py` and run `python tools/package_plugin.py --data-asset`.
3. Put the printed SHA-256 into `DATA_SHA256` in `download.py` and upload `dist/cengeobw-data-vN.zip` to
   a new release tagged `data-vN`:
   ```
   gh release create data-v2 dist/cengeobw-data-v2.zip --repo arsalanmukhtar/masterarbeit --title "Census data v2" --latest=false
   ```
4. Release a new plugin version. Users download the new data once after updating; older data files in the
   profile folder are removed.

The data file and ZIPs are not committed (`.gitignore`): GitHub limits files to 100 MB and every
committed data version would stay in the repository history.
