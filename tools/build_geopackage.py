#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build data/cengeobw.gpkg from the CenGeo BW PostgreSQL database.

1. Restore bwapp.backup into PostgreSQL (with PostGIS), e.g.
       createdb bwapp && pg_restore --no-owner -d bwapp bwapp.backup
2. Run this script (on Windows from the OSGeo4W Shell, which has Python, psycopg2 and ogr2ogr):
       python tools/build_geopackage.py --dbname bwapp --user postgres
   The password is taken from PGPASSWORD or pgpass.conf.

The database is only read. Statistics stored as text are converted to numbers, and the Gemeinde
boundaries are simplified so the file stays small enough to share.
"""
import argparse
import datetime
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

import psycopg2
from psycopg2 import sql

DATA_SCHEMAS = ("demography", "education", "forecast", "living", "tourism", "working")
TEXT_COLUMNS = {"feature", "schl_type", "age_grp"}
NUMBER_PATTERN = r"^[+-]?[0-9]+(\.[0-9]+)?$"
DEFAULT_OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cengeobw.gpkg")
# About 10 m in degrees: plenty for dashboard maps, and shared borders stay shared
DEFAULT_TOLERANCE = 0.0001

CATALOG_QUERIES = {
    "charts": """
        SELECT replace(tble, '.', '_') AS table_name,
               initcap(split_part(tble, '.', 1)) AS category,
               replace(regexp_replace(tble, '_[^_]+$', ''), '.', '_') AS base,
               substring(tble from '_([^_]+)$') AS level,
               title
        FROM public.chart_titles ORDER BY tble""",
    "attributes": "SELECT attribute, description FROM public.attributes_list ORDER BY id",
    "gemeinden": "SELECT g_key, g_name, k_key, k_name, r_key, r_name FROM public.gemeindeschlussel ORDER BY g_key",
}


def column_select(cursor, schema, table, column, data_type):
    """SELECT expression that turns all-numeric text columns into bigint or double precision."""
    identifier = sql.Identifier(column)
    if data_type != "text" or column in TEXT_COLUMNS:
        return sql.SQL("{}").format(identifier)
    cursor.execute(sql.SQL(
        "SELECT count(*) FILTER (WHERE NULLIF({c}, '') IS NOT NULL AND {c} !~ %s), "
        "bool_or({c} LIKE '%%.%%') FROM {s}.{t}").format(c=identifier, s=sql.Identifier(schema), t=sql.Identifier(table)),
        (NUMBER_PATTERN,))
    non_numeric, has_decimals = cursor.fetchone()
    if non_numeric:
        return sql.SQL("{}").format(identifier)
    target = "double precision" if has_decimals else "bigint"
    return sql.SQL("NULLIF({c}, '')::{t} AS {c}").format(c=identifier, t=sql.SQL(target))


def ogr2ogr(connection, output, layer_name, query, spatial=False):
    command = ["ogr2ogr", "-f", "GPKG", output, connection, "-sql", query, "-nln", layer_name, "-gt", "100000"]
    if os.path.exists(output):
        command.insert(1, "-update")
    if spatial:
        # The CRS of a computed geometry column cannot be detected, so it is declared (the source is EPSG:4326)
        command += ["-lco", "GEOMETRY_NAME=geom", "-nlt", "MULTIPOLYGON", "-a_srs", "EPSG:4326"]
    subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default="5432")
    parser.add_argument("--dbname", default="bwapp")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE,
                        help="boundary simplification in degrees, 0 to keep full detail")
    args = parser.parse_args()

    database = psycopg2.connect(host=args.host, port=args.port, dbname=args.dbname, user=args.user)
    cursor = database.cursor()
    connection = f"PG:host={args.host} port={args.port} dbname={args.dbname} user={args.user}"
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    work = tempfile.mkdtemp(prefix="cengeobw_")
    output = os.path.join(work, "cengeobw.gpkg")

    # Statistics tables listed in the chart catalog
    cursor.execute("SELECT split_part(tble, '.', 1), split_part(tble, '.', 2) FROM public.chart_titles ORDER BY tble")
    tables = [(schema, table) for schema, table in cursor.fetchall() if schema in DATA_SCHEMAS]
    expected = {}
    for schema, table in tables:
        cursor.execute("SELECT column_name, data_type FROM information_schema.columns "
                       "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position", (schema, table))
        columns = [column_select(cursor, schema, table, column, data_type) for column, data_type in cursor.fetchall()]
        query = sql.SQL("SELECT {} FROM {}.{}").format(sql.SQL(", ").join(columns), sql.Identifier(schema),
                                                         sql.Identifier(table)).as_string(database)
        print(f"{schema}.{table}")
        ogr2ogr(connection, output, f"{schema}_{table}", query)
        cursor.execute(sql.SQL("SELECT count(*) FROM {}.{}").format(sql.Identifier(schema), sql.Identifier(table)))
        expected[f"{schema}_{table}"] = cursor.fetchone()[0]

    for name, query in CATALOG_QUERIES.items():
        print(name)
        ogr2ogr(connection, output, name, query)

    # Gemeinde boundaries; ST_CoverageSimplify (PostGIS 3.4+, GEOS 3.12+) keeps neighbouring borders identical
    geometry = "geom"
    if args.tolerance > 0:
        try:
            cursor.execute("SELECT ST_CoverageSimplify(geom, 0) OVER () FROM public.gemeinde_shape LIMIT 1")
            geometry = f"ST_CoverageSimplify(geom, {args.tolerance}) OVER ()"
        except psycopg2.Error:
            database.rollback()
            print("ST_CoverageSimplify is not available, using ST_SimplifyPreserveTopology")
            geometry = f"ST_SimplifyPreserveTopology(geom, {args.tolerance})"
    print("gemeinde_shape")
    ogr2ogr(connection, output, "gemeinde_shape", f"""
        SELECT gemeinde_id::bigint AS g_key, gemeinde_name, kreis_name, regb_id, regb_name,
               gemarkung_id, gemarkung_name, gml_id, created_time, ST_Multi({geometry}) AS geom
        FROM public.gemeinde_shape""", spatial=True)

    # Indexes for the per-Gemeinde queries, build information, and a compact file
    gpkg = sqlite3.connect(output)
    for name in expected:
        columns = {row[1] for row in gpkg.execute(f'PRAGMA table_info("{name}")')}
        for key in ("g_key", "k_key"):
            if key in columns:
                gpkg.execute(f'CREATE INDEX "{name}_{key}" ON "{name}" ("{key}")')
        count = gpkg.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
        if count != expected[name]:
            sys.exit(f"{name}: {count} rows written, {expected[name]} expected")
    gpkg.execute("CREATE TABLE dataset_info (key TEXT PRIMARY KEY, value TEXT)")
    gpkg.executemany("INSERT INTO dataset_info VALUES (?, ?)", [
        ("built", datetime.date.today().isoformat()),
        ("source_database", args.dbname),
        ("boundary_tolerance_degrees", str(args.tolerance)),
    ])
    gpkg.commit()
    gpkg.execute("ANALYZE")
    gpkg.execute("VACUUM")
    gpkg.close()

    if os.path.exists(args.output):
        os.remove(args.output)
    shutil.move(output, args.output)
    print(f"Wrote {args.output} ({os.path.getsize(args.output) / 1048576:.1f} MB)")


if __name__ == "__main__":
    main()
