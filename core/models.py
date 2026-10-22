# -*- coding: utf-8 -*-
"""Plain data classes shared by the data layer, charts, reports and UI."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Tuple

# Columns that describe *what* a row is about (the chart axis and filters); everything else is a value
DIMENSION_COLUMNS = ("year", "age", "age_grp", "feature", "schl_type")
# Preferred order when choosing the default X axis
AXIS_PREFERENCE = ("year", "age", "age_grp", "feature", "schl_type")
# Area key column per table level: Gemeinde, Kreis, Land (region tables cover the whole state)
KEY_COLUMNS = {"gmnd": "g_key", "krs": "k_key", "rgn": None}
HIDDEN_COLUMNS = frozenset({"fid", "id", "g_key", "k_key"})
LEVELS = ("gmnd", "krs", "rgn")


@dataclass(frozen=True)
class Gemeinde:
    key: int
    name: str
    kreis_key: int
    kreis_name: str
    region_key: int
    region_name: str


@dataclass(frozen=True)
class Chart:
    """One statistics table and the title shown for it."""
    table: str
    category: str
    base: str
    level: str
    title: str


@dataclass(frozen=True)
class TableSchema:
    table: str
    dimensions: Tuple[str, ...]
    values: Tuple[str, ...]
    numeric: FrozenSet[str]
    key_column: Optional[str]

    def axis_options(self) -> List[str]:
        return sorted(self.dimensions, key=AXIS_PREFERENCE.index)

    def has_age_range(self) -> bool:
        return "age" in self.dimensions and "age" in self.numeric


@dataclass
class ChartQuery:
    """Everything needed to fetch one chart: table, axis, value and the filters on the other dimensions."""
    chart: Chart
    x: str
    y: str
    filters: Dict[str, object] = field(default_factory=dict)
    age_range: Optional[Tuple[int, int]] = None


@dataclass
class Series:
    label: str
    x: List[object]
    y: List[Optional[float]]

    def has_values(self) -> bool:
        return any(value is not None for value in self.y)
