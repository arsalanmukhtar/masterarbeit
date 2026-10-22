# -*- coding: utf-8 -*-
"""Read-only access to the CenGeo BW GeoPackage.

All SQL in the plugin lives here. Table and column names are only ever taken from the
GeoPackage's own catalog and are checked against it before use; values are always bound
as parameters.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import (DIMENSION_COLUMNS, HIDDEN_COLUMNS, KEY_COLUMNS, LEVELS, Chart, ChartQuery, Gemeinde,
                     Series, TableSchema)

GEMEINDE_LAYER = "gemeinde_shape"
AGGREGATES = ("SUM", "AVG")

# Columns of the boundary layer shown in the Spatial tab, with their display names
GEMEINDE_DETAIL_COLUMNS = (
    ("g_key", "Gemeinde key"),
    ("gemeinde_name", "Gemeinde"),
    ("kreis_name", "Kreis"),
    ("regb_id", "Regierungsbezirk key"),
    ("regb_name", "Regierungsbezirk"),
    ("gemarkung_id", "Gemarkung key"),
    ("gemarkung_name", "Gemarkung"),
    ("gml_id", "GML ID"),
    ("created_time", "Created"),
)


class DataError(Exception):
    """The GeoPackage is missing, unreadable or does not have the expected content."""


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


class CensusData:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_file():
            raise DataError(f"Data file not found: {self.path}")
        try:
            self._db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
            self.attribute_labels: Dict[str, str] = dict(self._rows("SELECT attribute, description FROM attributes"))
            self.charts: List[Chart] = [
                Chart(*row) for row in self._rows("SELECT table_name, category, base, level, title FROM charts ORDER BY category, title")
            ]
            self.gemeinden: List[Gemeinde] = [
                Gemeinde(*row)
                for row in self._rows("SELECT g_key, g_name, k_key, k_name, r_key, r_name FROM gemeinden ORDER BY g_name, k_name")
            ]
            self.info: Dict[str, str] = dict(self._rows("SELECT key, value FROM dataset_info"))
        except sqlite3.Error as e:
            raise DataError(f"{self.path} is not a valid CenGeo BW data file: {e}") from e
        self._tables = {name for (name,) in self._rows("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self._gemeinden_by_key = {gemeinde.key: gemeinde for gemeinde in self.gemeinden}
        self._charts_by_base = {(chart.base, chart.level): chart for chart in self.charts}
        self._schemas: Dict[str, TableSchema] = {}

    def close(self):
        self._db.close()

    def _rows(self, sql: str, params: Sequence = ()) -> List[tuple]:
        return self._db.execute(sql, params).fetchall()

    # --- Catalog -------------------------------------------------------------------------------

    def label(self, column: str) -> str:
        return self.attribute_labels.get(column, column)

    def gemeinde(self, key: int) -> Optional[Gemeinde]:
        return self._gemeinden_by_key.get(key)

    def categories(self) -> List[str]:
        return sorted({chart.category for chart in self.charts})

    def charts_for(self, category: str, levels: Iterable[str] = ("gmnd",)) -> List[Chart]:
        """Gemeinde-level charts of a category for which every requested level exists."""
        levels = tuple(levels)
        return [
            chart for chart in self.charts
            if chart.category == category and chart.level == "gmnd"
            and all(self.variant(chart, level) is not None for level in levels)
        ]

    def variant(self, chart: Chart, level: str) -> Optional[Chart]:
        """The same statistic at another level, e.g. the Kreis table for a Gemeinde chart."""
        return self._charts_by_base.get((chart.base, level))

    def schema(self, table: str) -> TableSchema:
        if table not in self._schemas:
            if table not in self._tables:
                raise DataError(f"Unknown table: {table}")
            columns = self._rows(f"PRAGMA table_info({_quote(table)})")
            names = [name for _, name, *_ in columns]
            # SQLite type affinity: any declared type containing INT (MEDIUMINT, BIGINT, ...) is an integer
            numeric = frozenset(name for _, name, col_type, *_ in columns
                                if any(part in col_type.upper() for part in ("INT", "REAL", "DOUB", "FLOA", "NUM")))
            level = table.rsplit("_", 1)[-1]
            key_column = KEY_COLUMNS.get(level)
            self._schemas[table] = TableSchema(
                table=table,
                dimensions=tuple(name for name in names if name in DIMENSION_COLUMNS),
                values=tuple(name for name in names if name not in DIMENSION_COLUMNS and name not in HIDDEN_COLUMNS),
                numeric=numeric,
                key_column=key_column if key_column in names else None,
            )
        return self._schemas[table]

    # --- Dimension values --------------------------------------------------------------------

    def dimension_values(self, table: str, column: str) -> List[object]:
        """Distinct values of a dimension in the order they appear in the source data."""
        schema = self.schema(table)
        self._check_columns(schema, [column])
        return [value for (value,) in self._rows(
            f"SELECT {_quote(column)} FROM {_quote(table)} WHERE {_quote(column)} IS NOT NULL "
            f"GROUP BY {_quote(column)} ORDER BY MIN(id)")]

    def value_range(self, table: str, column: str) -> Tuple[int, int]:
        self._check_columns(self.schema(table), [column])
        low, high = self._rows(f"SELECT MIN({_quote(column)}), MAX({_quote(column)}) FROM {_quote(table)}")[0]
        return int(low), int(high)

    # --- Chart and report data ---------------------------------------------------------------

    def grouped_rows(self, table: str, x: str, values: Sequence[str], key: Optional[int] = None,
                     filters: Optional[Dict[str, object]] = None, age_range: Optional[Tuple[int, int]] = None,
                     aggregate: str = "SUM") -> List[tuple]:
        """Rows of (x, value1, value2, ...) for one area, summed over every dimension that is not
        the axis or filtered to a single value."""
        schema = self.schema(table)
        filters = filters or {}
        self._check_columns(schema, [x, *values, *filters])
        if aggregate not in AGGREGATES:
            raise DataError(f"Unknown aggregate: {aggregate}")

        where, params = [], []
        if key is not None and schema.key_column:
            where.append(f"{_quote(schema.key_column)} = ?")
            params.append(key)
        for column, value in filters.items():
            where.append(f"{_quote(column)} = ?")
            params.append(value)
        if age_range is not None and schema.has_age_range():
            where.append('"age" BETWEEN ? AND ?')
            params.extend(age_range)

        selected = ", ".join(f"{aggregate}({_quote(value)})" for value in values)
        order = _quote(x) if x in schema.numeric else "MIN(id)"
        sql = (f"SELECT {_quote(x)}, {selected} FROM {_quote(table)}"
               + (f" WHERE {' AND '.join(where)}" if where else "")
               + f" GROUP BY {_quote(x)} ORDER BY {order}")
        return self._rows(sql, params)

    def series(self, query: ChartQuery, level: str, label: str, key: Optional[int] = None) -> Series:
        chart = query.chart if level == query.chart.level else self.variant(query.chart, level)
        if chart is None:
            raise DataError(f"No {level} table for {query.chart.title}")
        rows = self.grouped_rows(chart.table, query.x, [query.y], key, query.filters, query.age_range)
        return Series(label, [row[0] for row in rows], [row[1] for row in rows])

    def area_values(self, table: str, column: str, aggregate: str = "SUM") -> Tuple[Dict[int, float], Optional[object]]:
        """One value per Gemeinde for a thematic map, using the latest year when the table has years."""
        schema = self.schema(table)
        self._check_columns(schema, [column])
        if aggregate not in AGGREGATES or schema.key_column != "g_key":
            raise DataError(f"Cannot map {table}.{column}")
        year = None
        where, params = "", []
        if "year" in schema.dimensions:
            year = self._rows(f"SELECT year FROM {_quote(table)} GROUP BY year ORDER BY MIN(id) DESC LIMIT 1")[0][0]
            where, params = " WHERE year = ?", [year]
        rows = self._rows(f"SELECT g_key, {aggregate}({_quote(column)}) FROM {_quote(table)}{where} GROUP BY g_key", params)
        return {key: value for key, value in rows if value is not None}, year

    def gemeinde_details(self, key: int) -> List[Tuple[str, object]]:
        columns = ", ".join(_quote(column) for column, _ in GEMEINDE_DETAIL_COLUMNS)
        rows = self._rows(f"SELECT {columns} FROM {GEMEINDE_LAYER} WHERE g_key = ?", (key,))
        if not rows:
            return []
        return [(label, value) for (_, label), value in zip(GEMEINDE_DETAIL_COLUMNS, rows[0])]

    def has_boundary(self, key: int) -> bool:
        return bool(self._rows(f"SELECT 1 FROM {GEMEINDE_LAYER} WHERE g_key = ?", (key,)))

    def _check_columns(self, schema: TableSchema, columns: Iterable[str]):
        known = set(schema.dimensions) | set(schema.values)
        unknown = [column for column in columns if column not in known]
        if unknown:
            raise DataError(f"Unknown column(s) {', '.join(unknown)} in {schema.table}")


__all__ = ["CensusData", "DataError", "GEMEINDE_LAYER", "AGGREGATES", "LEVELS"]
