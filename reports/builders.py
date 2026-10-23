# -*- coding: utf-8 -*-
"""The three PDF reports: one Gemeinde, Gemeinde vs. Kreis vs. Land, and Gemeinde vs. Gemeinde.

Each report covers every chart of one category. A chart whose table has a categorical dimension
besides the X axis (e.g. school type) gets one section per value of that dimension; ages that are
not on the axis are summed.
"""
from __future__ import annotations

import itertools
import os
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..charts.plotting import index_series, light_charts
from ..core.attribution import REPORT_CREDITS
from ..core.data import CensusData
from ..core.models import LEVELS, Chart, Gemeinde, Series
from .pdf_report import PdfReport, safe_file_name

# (charts done, charts total, current chart title) -> False to cancel
ProgressCallback = Callable[[int, int, str], bool]
# (Gemeinde keys, PNG path to write) -> the path, or None when no map could be rendered
MapImageCallback = Callable[[Sequence[int], str], Optional[str]]

STATE_NAME = "Baden-Württemberg"
INDEX_LABEL = "Index (first year = 100)"


class ReportCancelled(Exception):
    pass


def _sections(data: CensusData, chart: Chart) -> Tuple[str, List[Tuple[Dict[str, object], str]], Optional[str]]:
    """(X axis, [(filters, description)], note) for one chart."""
    schema = data.schema(chart.table)
    axis = schema.axis_options()[0]
    sums_ages = schema.has_age_range() and axis != "age"
    split = [dim for dim in schema.dimensions if dim != axis and not (dim == "age" and sums_ages)]
    combinations = itertools.product(*(data.dimension_values(chart.table, dim) for dim in split))
    sections = []
    for values in combinations:
        filters = dict(zip(split, values))
        sections.append((filters, ", ".join(f"{data.label(dim, chart.table)}: {value}"
                                            for dim, value in filters.items())))
    return axis, sections, "Summed over all ages" if sums_ages else None


def _merge(series: Sequence[Series]) -> List[list]:
    """Table rows (x, value of series 1, value of series 2, ...) over the union of all X values."""
    order: List[object] = []
    for item in series:
        order.extend(x for x in item.x if x not in order)
    lookups = [dict(zip(item.x, item.y)) for item in series]
    return [[x, *(lookup.get(x) for lookup in lookups)] for x in order]


def _subtitle(*parts: Optional[str]) -> str:
    return " · ".join(part for part in parts if part)


def _image_name(*parts: Optional[str]) -> str:
    return " - ".join(part for part in parts if part)


class _ReportRun:
    """Shared plumbing: file names, title and map pages, progress and cancelling."""

    def __init__(self, data: CensusData, output_dir: str, name: str, category: str,
                 map_image: Optional[MapImageCallback], progress: Optional[ProgressCallback]):
        base = safe_file_name(f"{name} - {category} Report")
        self.pdf_path = os.path.join(output_dir, base + ".pdf")
        self.image_dir = os.path.join(output_dir, safe_file_name(f"{name} - {category} Charts"))
        self.map_image = map_image
        self.progress = progress

    def run(self, title: str, subtitle: str, map_keys: Sequence[int], map_title: str, charts: Sequence[Chart],
            write_chart: Callable[[PdfReport, Chart], None]) -> str:
        try:
            # Reports are printed and shared, so they always use the light theme
            with light_charts(), PdfReport(self.pdf_path, self.image_dir, REPORT_CREDITS) as report:
                report.title_page(title, subtitle)
                if self.map_image:
                    image = self.map_image(map_keys, os.path.join(self.image_dir, "Map.png"))
                    if image:
                        report.image_page(map_title, image)
                for index, chart in enumerate(charts):
                    if self.progress and not self.progress(index, len(charts), chart.title):
                        raise ReportCancelled()
                    write_chart(report, chart)
                if self.progress:
                    self.progress(len(charts), len(charts), "")
        except ReportCancelled:
            os.remove(self.pdf_path)
            raise
        return self.pdf_path


def _series(data: CensusData, chart: Chart, axis: str, value: str, key: Optional[int],
            filters: Dict[str, object], label: str) -> Series:
    rows = data.grouped_rows(chart.table, axis, [value], key, filters)
    return Series(label, [row[0] for row in rows], [row[1] for row in rows])


def gemeinde_report(data: CensusData, gemeinde: Gemeinde, category: str, output_dir: str,
                    map_image: Optional[MapImageCallback] = None, progress: Optional[ProgressCallback] = None) -> str:
    def write_chart(report: PdfReport, chart: Chart):
        schema = data.schema(chart.table)
        axis, sections, note = _sections(data, chart)
        x_label = data.label(axis, chart.table)
        headers = [x_label] + [data.label(value, chart.table) for value in schema.values]
        for filters, description in sections:
            rows = data.grouped_rows(chart.table, axis, schema.values, gemeinde.key, filters)
            subtitle = _subtitle(gemeinde.name, description, note)
            report.table_pages(chart.title, headers, rows, subtitle)
            panels = [Series(data.label(value, chart.table), [row[0] for row in rows], [row[i + 1] for row in rows])
                      for i, value in enumerate(schema.values)]
            image = _image_name(chart.title, description)
            if len(panels) == 1:
                report.chart_page(chart.title, panels, x_label, panels[0].label, axis, subtitle, image_name=image)
            else:
                report.multiples_page(chart.title, panels, x_label, axis, subtitle, image_name=image)

    run = _ReportRun(data, output_dir, gemeinde.name, category, map_image, progress)
    return run.run(f"{category} report", f"{gemeinde.name} · {gemeinde.kreis_name}",
                   [gemeinde.key], f"Map of {gemeinde.name}", data.charts_for(category), write_chart)


def kreis_land_report(data: CensusData, gemeinde: Gemeinde, category: str, output_dir: str,
                      map_image: Optional[MapImageCallback] = None, progress: Optional[ProgressCallback] = None) -> str:
    labels = [gemeinde.name, f"{gemeinde.kreis_name} (Kreis)", STATE_NAME]

    def write_chart(report: PdfReport, chart: Chart):
        schema = data.schema(chart.table)
        kreis_chart, land_chart = data.variant(chart, "krs"), data.variant(chart, "rgn")
        axis, sections, note = _sections(data, chart)
        x_label = data.label(axis, chart.table)
        for filters, description in sections:
            for value in schema.values:
                value_label = data.label(value, chart.table)
                series = [
                    _series(data, chart, axis, value, gemeinde.key, filters, labels[0]),
                    _series(data, kreis_chart, axis, value, gemeinde.kreis_key, filters, labels[1]),
                    _series(data, land_chart, axis, value, None, filters, labels[2]),
                ]
                title = f"{chart.title}: {value_label}"
                subtitle = _subtitle(", ".join(labels), description, note)
                report.table_pages(title, [x_label, *labels], _merge(series), subtitle)
                image = _image_name(chart.title, value_label, description)
                if axis == "year":
                    # Gemeinde, Kreis and Land differ by orders of magnitude; an index puts them on one axis
                    report.chart_page(title, index_series(series), x_label, INDEX_LABEL, axis,
                                      _subtitle(subtitle, f"{value_label}, {INDEX_LABEL}"), baseline=100,
                                      image_name=image)
                else:
                    report.multiples_page(title, series, x_label, axis, subtitle, image_name=image)

    run = _ReportRun(data, output_dir, gemeinde.name, f"{category} Kreis-Land", map_image, progress)
    return run.run(f"{category}: Gemeinde, Kreis and Land", f"{gemeinde.name} · {gemeinde.kreis_name} · {STATE_NAME}",
                   [gemeinde.key], f"Map of {gemeinde.name}", data.charts_for(category, LEVELS), write_chart)


def gemeinde_comparison_report(data: CensusData, first: Gemeinde, second: Gemeinde, category: str, output_dir: str,
                               map_image: Optional[MapImageCallback] = None,
                               progress: Optional[ProgressCallback] = None) -> str:
    def write_chart(report: PdfReport, chart: Chart):
        schema = data.schema(chart.table)
        axis, sections, note = _sections(data, chart)
        x_label = data.label(axis, chart.table)
        for filters, description in sections:
            for value in schema.values:
                value_label = data.label(value, chart.table)
                series = [_series(data, chart, axis, value, first.key, filters, first.name),
                          _series(data, chart, axis, value, second.key, filters, second.name)]
                title = f"{chart.title}: {value_label}"
                subtitle = _subtitle(f"{first.name} and {second.name}", description, note)
                report.table_pages(title, [x_label, first.name, second.name], _merge(series), subtitle)
                report.chart_page(title, series, x_label, value_label, axis, subtitle,
                                  image_name=_image_name(chart.title, value_label, description))

    run = _ReportRun(data, output_dir, f"{first.name} and {second.name}", category, map_image, progress)
    return run.run(f"{category} report", f"{first.name} and {second.name}", [first.key, second.key],
                   f"Map of {first.name} and {second.name}", data.charts_for(category), write_chart)
