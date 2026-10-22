#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create the release ZIP in dist/ (CenGeoBW-2.0.0.zip for version 2.0.0), ready for QGIS "Install from ZIP" and for a GitHub release.

    python tools/package_plugin.py              # plugin with the data file (normal release)
    python tools/package_plugin.py --no-data    # code only
"""
import argparse
import configparser
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_FOLDER = "CenGeoBW"
FILES = ["__init__.py", "plugin.py", "compat.py", "metadata.txt", "icon.png", "README.md", "DATA_LICENSE.md"]
PACKAGES = ["core", "charts", "reports", "spatial", "ui"]
DATA_FILE = os.path.join("data", "cengeobw.gpkg")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-data", action="store_true", help="leave out data/cengeobw.gpkg")
    args = parser.parse_args()

    metadata = configparser.ConfigParser(interpolation=None)
    metadata.read(os.path.join(ROOT, "metadata.txt"), encoding="utf-8")
    version = metadata.get("general", "version")

    paths = list(FILES)
    for package in PACKAGES:
        for folder, directories, names in os.walk(os.path.join(ROOT, package)):
            directories[:] = [d for d in directories if d != "__pycache__"]
            paths += [os.path.relpath(os.path.join(folder, name), ROOT) for name in names if name.endswith(".py")]
    if not args.no_data:
        if not os.path.isfile(os.path.join(ROOT, DATA_FILE)):
            sys.exit(f"{DATA_FILE} is missing: build it with tools/build_geopackage.py or use --no-data")
        paths.append(DATA_FILE)

    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    output = os.path.join(ROOT, "dist", f"{PLUGIN_FOLDER}-{version}{'-no-data' if args.no_data else ''}.zip")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(paths):
            archive.write(os.path.join(ROOT, path), f"{PLUGIN_FOLDER}/{path.replace(os.sep, '/')}")
    print(f"Wrote {output} ({os.path.getsize(output) / 1048576:.1f} MB, {len(paths)} files)")


if __name__ == "__main__":
    main()
