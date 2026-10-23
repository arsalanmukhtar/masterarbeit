# -*- coding: utf-8 -*-
"""Key figures for reports: the latest value of a series and how it changed.

Changes are worded to suit the value: values in percent change in points, values that can be zero or
negative (net migration, births minus deaths) change by a plain difference, everything else in percent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .data import CensusData
from .models import Chart, Series

TIME_AXES = ("year", "age")
LOOK_BACK_YEARS = 10
TOTAL_NAMES = ("insgesamt", "gesamt", "zusammen", "total")


def format_value(value) -> str:
    if value is None:
        return "-"
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.1f}" if abs(value) >= 100 else f"{value:,.2f}".rstrip("0").rstrip(".")


def is_total(category: object) -> bool:
    return str(category).strip().lower() in TOTAL_NAMES


@dataclass
class KeyFigure:
    label: str
    value: str
    note: str = ""            # e.g. "in 2023"
    change: Optional[float] = None  # drives the arrow colour; percent or points
    change_text: str = ""     # e.g. "+13.0 % since 2013"


def key_figure(label: str, series: Series, percent_values: bool = False) -> KeyFigure:
    """Latest value of a series and its change against the value ten years earlier (or the first one)."""
    points = [(x, y) for x, y in zip(series.x, series.y) if y is not None]
    if not points:
        return KeyFigure(label, "-")
    latest_x, latest = points[-1]
    figure = KeyFigure(label, format_value(latest), f"in {latest_x}")
    if len(points) < 2:
        return figure
    earlier = None
    if isinstance(latest_x, (int, float)):
        earlier = next(((x, y) for x, y in points if x == latest_x - LOOK_BACK_YEARS), None)
    base_x, base = earlier or points[0]
    since = f"since {base_x}"
    difference = latest - base
    if percent_values:
        figure.change = difference
        figure.change_text = f"{difference:+.1f} points {since}"
    elif base <= 0 or any(y < 0 for _, y in points):
        scale = max(abs(y) for _, y in points) or 1
        figure.change = difference / scale * 100
        figure.change_text = f"{'+' if difference >= 0 else '-'}{format_value(abs(difference))} {since}"
    else:
        figure.change = difference / base * 100
        figure.change_text = f"{figure.change:+.1f} % {since}"
    return figure


def is_percent(label: str) -> bool:
    return label.endswith("(%)") or label.lower().startswith("bed occupancy")


@dataclass
class ChartFocus:
    """How a chart is summarised in one line: its axis, main value and the filters that pick one
    consistent slice (the total row of a categorical dimension, or its first category)."""
    axis: str
    value: str
    filters: Dict[str, object]
    description: str


def chart_focus(data: CensusData, chart: Chart) -> ChartFocus:
    schema = data.schema(chart.table)
    axis = schema.axis_options()[0]
    filters, parts = {}, []
    for dimension in schema.dimensions:
        if dimension == axis or (dimension == "age" and schema.has_age_range()):
            continue
        values = data.dimension_values(chart.table, dimension)
        chosen = next((v for v in values if is_total(v)), values[0] if values else None)
        if chosen is not None:
            filters[dimension] = chosen
            parts.append(f"{data.label(dimension, chart.table)}: {chosen}")
    return ChartFocus(axis, schema.values[0], filters, " · ".join(parts))


def focus_series(data: CensusData, chart: Chart, focus: ChartFocus, key: Optional[int], label: str = "") -> Series:
    rows = data.grouped_rows(chart.table, focus.axis, [focus.value], key, focus.filters)
    return Series(label, [row[0] for row in rows], [row[1] for row in rows])


def chart_highlight(data: CensusData, chart: Chart, key: Optional[int]) -> Tuple[str, KeyFigure]:
    """(value label, key figure) of a chart's main value for one area. On an axis that is not time
    (age groups, school types) the figure is the total over the axis."""
    focus = chart_focus(data, chart)
    label = data.label(focus.value, chart.table)
    series = focus_series(data, chart, focus, key)
    if focus.axis not in TIME_AXES:
        values = [y for x, y in zip(series.x, series.y) if y is not None and not is_total(x)]
        total = sum(values) if values else None
        return label, KeyFigure(label, format_value(total), f"total over {data.label(focus.axis, chart.table).lower()}")
    return label, key_figure(label, series, is_percent(label))


def figures_for(series_list: Sequence[Series], labels: Sequence[str]) -> List[KeyFigure]:
    return [key_figure(label, series, is_percent(label)) for series, label in zip(series_list, labels)]


def profile_figures(data: CensusData, key: int) -> List[KeyFigure]:
    """The Gemeinde profile as key figures: population with its ten-year change, average age, area, density."""
    profile = data.profile(key)
    year = profile.get("year")
    figures = []
    if "population" in profile:
        population = KeyFigure("Population", format_value(profile["population"]), f"in {year}")
        if "change_percent" in profile:
            population.change = profile["change_percent"]
            population.change_text = f"{population.change:+.1f} % since {profile['change_year']}"
        figures.append(population)
    if "average_age" in profile:
        figures.append(KeyFigure("Average age", f"{profile['average_age']:.1f} years", f"in {profile['age_year']}"))
    if "area_km2" in profile:
        figures.append(KeyFigure("Area", f"{profile['area_km2']:,.1f} km²"))
    if profile.get("density"):
        figures.append(KeyFigure("Density", f"{format_value(profile['density'])} per km²", f"in {year}"))
    return figures
