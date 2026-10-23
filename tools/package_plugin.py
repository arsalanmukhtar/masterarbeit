#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build release files in dist/.

    python tools/package_plugin.py               # plugin ZIP for the QGIS plugin repository (data downloaded on first start)
    python tools/package_plugin.py --with-data   # plugin ZIP with the data included, for offline installation
    python tools/package_plugin.py --data-asset  # the data download (cengeobw-data-vN.zip) and its SHA-256
"""
import argparse
import configparser
import hashlib
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_FOLDER = "CenGeoBW"
FILES = ["__init__.py", "plugin.py", "compat.py", "download.py", "metadata.txt", "icon.png", "LICENSE", "README.md",
         "DATA_LICENSE.md"]
PACKAGES = ["core", "charts", "reports", "spatial", "ui"]
RESOURCES = "resources"  # fonts, icons and the font licence: every file is included
DATA_FILE = os.path.join("data", "cengeobw.gpkg")


def data_version() -> int:
    with open(os.path.join(ROOT, "download.py"), encoding="utf-8") as handle:
        return int(re.search(r"^DATA_VERSION = (\d+)", handle.read(), re.MULTILINE).group(1))


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_data():
    if not os.path.isfile(os.path.join(ROOT, DATA_FILE)):
        sys.exit(f"{DATA_FILE} is missing: build it with tools/build_geopackage.py")


def build_data_asset():
    require_data()
    output = os.path.join(ROOT, "dist", f"cengeobw-data-v{data_version()}.zip")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.write(os.path.join(ROOT, DATA_FILE), "cengeobw.gpkg")
    print(f"Wrote {output} ({os.path.getsize(output) / 1048576:.1f} MB)")
    print(f"SHA-256: {sha256(output)}")
    print("Put this value into DATA_SHA256 in download.py and upload the file to the release data-v"
          f"{data_version()}.")


def build_plugin(with_data: bool):
    metadata = configparser.ConfigParser(interpolation=None)
    metadata.read(os.path.join(ROOT, "metadata.txt"), encoding="utf-8")
    version = metadata.get("general", "version")

    paths = list(FILES)
    for folder, _, names in os.walk(os.path.join(ROOT, RESOURCES)):
        paths += [os.path.relpath(os.path.join(folder, name), ROOT) for name in names]
    for package in PACKAGES:
        for folder, directories, names in os.walk(os.path.join(ROOT, package)):
            directories[:] = [d for d in directories if d != "__pycache__"]
            paths += [os.path.relpath(os.path.join(folder, name), ROOT) for name in names if name.endswith(".py")]
    if with_data:
        require_data()
        paths.append(DATA_FILE)

    output = os.path.join(ROOT, "dist", f"{PLUGIN_FOLDER}-{version}{'-with-data' if with_data else ''}.zip")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(paths):
            archive.write(os.path.join(ROOT, path), f"{PLUGIN_FOLDER}/{path.replace(os.sep, '/')}")
    print(f"Wrote {output} ({os.path.getsize(output) / 1048576:.1f} MB, {len(paths)} files)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--with-data", action="store_true", help="include data/cengeobw.gpkg in the plugin ZIP")
    group.add_argument("--data-asset", action="store_true", help="build the data download instead of the plugin")
    args = parser.parse_args()
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    if args.data_asset:
        build_data_asset()
    else:
        build_plugin(args.with_data)


if __name__ == "__main__":
    main()
