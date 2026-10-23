# -*- coding: utf-8 -*-
"""The three PDF reports: one Gemeinde, Gemeinde vs. Kreis vs. Land, and Gemeinde vs. Gemeinde.

Each report covers every chart of one category: a cover with maps and key figures, an "at a glance"
page with one line per chart, one or two chart pages per chart with key figures beside the chart, and
a page about the data. The numbers behind every chart are written as CSV files next to the PDF.
"""
from __future__ import annotations

import csv
import os
from typing import Callable, List, Optional, Sequence, Tuple

from ..charts.plotting import chart_kind, draw_chart, draw_panels, draw_pyramid, index_series, light_charts
from ..core.attribution import REPORT_CREDITS
from ..core.data import CensusData
from ..core.insights import (TIME_AXES, KeyFigure, chart_focus, chart_highlight, figures_for, format_value, is_percent,
                             is_total, key_figure, profile_figures)
from ..core.models import LEVELS, Chart, Gemeinde, Series
from .pdf_report import PdfReport, map_sizes, safe_file_name

# (charts done, charts total, current chart title) -> False to cancel
ProgressCallback = Callable[[int, int, str], bool]
# (Gemeinde keys, PNG path, context_keys=..., overview=..., size=...) -> (path, extent shown), or None without a map
MapImageCallback = Callable[..., Optional[str]]

STATE_NAME = "Baden-Württemberg"
INDEX_LABEL = "Index (first year = 100)"
MAX_PANELS = 6
TOP_CATEGORIES = 5
LEGEND_SPACE = 0.045


class ReportCancelled(Exception):
    pass


# --- Shared helpers --------------------------------------------------------------------------------

def _merge(series: Sequence[Series]) -> List[list]:
    """Table rows (x, value of series 1, value of series 2, ...) over the union of all X values."""
    order: List[object] = []
    for item in series:
        order.extend(x for x in item.x if x not in order)
    lookups = [dict(zip(item.x, item.y)) for item in series]
    return [[x, *(lookup.get(x) for lookup in lookups)] for x in order]


def _join(*parts: Optional[str]) -> str:
    return " · ".join(part for part in parts if part)


def _rows_series(data: CensusData, chart: Chart, axis: str, values: Sequence[str], key: Optional[int],
                 filters) -> List[Series]:
    rows = data.grouped_rows(chart.table, axis, list(values), key, filters)
    return [Series(data.label(value, chart.table), [row[0] for row in rows], [row[i + 1] for row in rows])
            for i, value in enumerate(values)]


def _columns(count: int) -> int:
    return 1 if count == 1 else 2 if count in (2, 4) else 3


def _total(series: Series) -> float:
    return sum(y for x, y in zip(series.x, series.y) if y is not None and not is_total(x))


def _shares(series: Series) -> Series:
    """A distribution in percent of its total, so areas of different size can be compared."""
    total = _total(series) or 1
    pairs = [(x, y / total * 100) for x, y in zip(series.x, series.y) if y is not None and not is_total(x)]
    return Series(series.label, [x for x, _ in pairs], [y for _, y in pairs])


class _ReportRun:
    """Shared plumbing: file names, CSV files, progress and cancelling."""

    def __init__(self, output_dir: str, name: str, category: str, progress: Optional[ProgressCallback]):
        self.pdf_path = os.path.join(output_dir, safe_file_name(f"{name} - {category} Report") + ".pdf")
        self.folder_name = safe_file_name(f"{name} - {category} Charts and data")
        self.data_dir = os.path.join(output_dir, self.folder_name)
        self.progress = progress

    def csv(self, name: str, headers: Sequence[str], rows: Sequence[Sequence]):
        os.makedirs(self.data_dir, exist_ok=True)
        # utf-8-sig so Excel shows umlauts correctly
        with open(os.path.join(self.data_dir, safe_file_name(name) + ".csv"), "w", newline="",
                  encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)

    def map_path(self, name: str) -> str:
        os.makedirs(self.data_dir, exist_ok=True)
        return os.path.join(self.data_dir, name)

    def run(self, kicker: str, front: Callable[[PdfReport], None], charts: Sequence[Chart],
            write_chart: Callable[[PdfReport, Chart], None], index_charts: bool) -> str:
        try:
            # Reports are printed and shared, so they always use the light theme
            with light_charts(), PdfReport(self.pdf_path, self.data_dir, REPORT_CREDITS, kicker) as report:
                front(report)
                for number, chart in enumerate(charts):
                    if self.progress and not self.progress(number, len(charts), chart.title):
                        raise ReportCancelled()
                    write_chart(report, chart)
                report.about_page(_about(self.folder_name, index_charts))
                if self.progress:
                    self.progress(len(charts), len(charts), "")
        except ReportCancelled:
            os.remove(self.pdf_path)
            raise
        return self.pdf_path


def _about(folder: str, index_charts: bool) -> List[Tuple[str, str]]:
    sections = [
        ("Sources", " ".join(f"{credit}." for credit in REPORT_CREDITS)),
        ("Key figures and changes",
         "Changes compare the latest year with the year ten years earlier, or with the first year available when "
         "the series is shorter. Values given in percent change in percentage points. Values that can be zero or "
         "negative, such as net migration, change by their difference. The coloured arrow shows the direction: "
         "green for growth of 2 % or more, yellow for smaller growth, orange for a decline under 2 % and red for "
         "a decline of 2 % or more."),
        ("Charts split by category",
         "Where a statistic is split by category, such as school type or employee group, one page shows the "
         "latest year by category and one page the development of the largest categories. Ages are summed "
         "unless the chart is by age."),
    ]
    if index_charts:
        sections.append(("Index charts",
                         "Comparison charts show every line as an index: its value in the first year is set to 100. "
                         "A value of 113.9 means 13.9 % higher than in the first year, so areas of very different "
                         "size can be compared on one axis. The key figures beside the charts give the actual "
                         "values."))
    sections.append(("Data files", f"The numbers behind every chart are in the folder \"{folder}\" next to this "
                                   "PDF, as CSV files that open in Excel, together with the maps and every chart as "
                                   "an image."))
    return sections


def _cover(report: PdfReport, run: _ReportRun, map_image: Optional[MapImageCallback], title: str, subtitle: str,
           tiles: Sequence[KeyFigure], keys: Sequence[int], selection: str, context_keys: Optional[Sequence[int]] = None,
           context_name: str = ""):
    local = overview = None
    if map_image:
        local_size, overview_size = map_sizes()
        local = map_image(keys, run.map_path("Map.png"), context_keys=context_keys, size=local_size)
        overview = map_image(keys, run.map_path("Map of Baden-Württemberg.png"), context_keys=context_keys,
                             overview=True, size=overview_size)
    legend = [(selection, "#f9d9cb", "#eb6834")]
    if context_keys:
        legend.append((context_name, "#fcefe9", "#f3a585"))
    legend.append(("Gemeinde boundaries", "#ffffff", "#a8a7a1"))
    report.cover_page(title, subtitle, tiles, local, overview, legend)


# --- One Gemeinde ---------------------------------------------------------------------------------

def gemeinde_report(data: CensusData, gemeinde: Gemeinde, category: str, output_dir: str,
                    map_image: Optional[MapImageCallback] = None, progress: Optional[ProgressCallback] = None) -> str:
    run = _ReportRun(output_dir, gemeinde.name, category, progress)
    charts = data.charts_for(category)

    def front(report: PdfReport):
        _cover(report, run, map_image, f"{category} report", f"{gemeinde.name} · {gemeinde.kreis_name}",
               profile_figures(data, gemeinde.key), [gemeinde.key], gemeinde.name)
        rows = []
        for chart in charts:
            label, figure = chart_highlight(data, chart, gemeinde.key)
            rows.append((chart.title, label, [figure]))
        report.glance_page("At a glance", f"{gemeinde.name} · the main value of every chart", [gemeinde.name], rows)

    def write_chart(report: PdfReport, chart: Chart):
        _gemeinde_chart(report, run, data, chart, gemeinde)

    return run.run(category, front, charts, write_chart, index_charts=False)


def _gemeinde_chart(report: PdfReport, run: _ReportRun, data: CensusData, chart: Chart, gemeinde: Gemeinde):
    schema = data.schema(chart.table)
    focus = chart_focus(data, chart)
    axis, table = focus.axis, chart.table
    x_label = data.label(axis, table)
    # Categorical dimensions besides the axis (ages that are not the axis are summed instead)
    split = list(focus.filters)
    age_note = "Summed over all ages" if schema.has_age_range() and axis != "age" else None

    if not split:
        series = _rows_series(data, chart, axis, schema.values, gemeinde.key, {})
        run.csv(chart.title, [x_label, *(item.label for item in series)], _merge(series))
        shown = series[:MAX_PANELS]
        more = f"{len(shown)} of {len(series)} values shown, all in the CSV file" if len(series) > MAX_PANELS else None
        subtitle = _join(gemeinde.name, age_note, more)
        if axis in TIME_AXES:
            if len(shown) == 1:
                def draw(figure, region):
                    return draw_chart(figure, shown, x_label, shown[0].label, "line", rect=region)
            else:
                def draw(figure, region):
                    draw_panels(figure, [(item.label, [item]) for item in shown], x_label, axis, region,
                                _columns(len(shown)))
            report.chart_page(chart.title, subtitle, draw, figures_for(shown, [item.label for item in shown]),
                              image_name=chart.title)
        else:
            chosen = [shown[0], shown[-1]] if len(shown) > 1 else [shown[0]]
            kind = chart_kind(axis, chosen[0].x)

            def draw(figure, region):
                return draw_chart(figure, chosen, x_label, "Value" if len(chosen) > 1 else chosen[0].label, kind,
                                  rect=region)
            figures = [KeyFigure(item.label, format_value(_total(item)), f"total over {x_label.lower()}")
                       for item in chosen]
            report.chart_page(chart.title, _join(subtitle, "First and last value of the chart"), draw, figures,
                              image_name=chart.title)
        _age_pyramid(report, run, data, chart, gemeinde)
        return

    # Split by a category (school type, employee group): latest year by category, then the largest categories
    dimension = split[0]
    fixed = {d: v for d, v in focus.filters.items() if d != dimension}
    main = focus.value
    main_label = data.label(main, table)
    dimension_label = data.label(dimension, table)
    all_categories = data.dimension_values(table, dimension)
    categories = [c for c in all_categories if not is_total(c)]
    total_category = next((c for c in all_categories if is_total(c)), None)
    latest = data.dimension_values(table, axis)[-1] if axis in TIME_AXES else None
    breakdown_filters = dict(fixed, **({axis: latest} if latest is not None else {}))
    rows = data.grouped_rows(table, dimension, [main], gemeinde.key, breakdown_filters)
    rows = [row for row in rows if not is_total(row[0]) and row[1] is not None]
    breakdown = Series(main_label, [row[0] for row in rows], [row[1] for row in rows])

    by_category = {category: _rows_series(data, chart, axis, [main], gemeinde.key,
                                          dict(fixed, **{dimension: category}))[0] for category in categories}
    run.csv(chart.title, [x_label, *categories],
            _merge([Series(category, item.x, item.y) for category, item in by_category.items()]))

    reference = total_category if total_category is not None else categories[0]
    figure_series = _rows_series(data, chart, axis, schema.values[:5], gemeinde.key,
                                 dict(fixed, **{dimension: reference}))
    figures = figures_for(figure_series, [item.label for item in figure_series]) if axis in TIME_AXES else []

    def draw_breakdown(figure, region):
        return draw_chart(figure, [breakdown], dimension_label, main_label, chart_kind(dimension, breakdown.x),
                          rect=region)
    report.chart_page(chart.title, _join(gemeinde.name, f"{main_label} by {dimension_label.lower()}",
                                         f"in {latest}" if latest is not None else None, age_note),
                      draw_breakdown, figures, str(reference), image_name=f"{chart.title} - by {dimension_label}")

    if axis in TIME_AXES and categories:
        latest_values = {c: next((y for y in reversed(s.y) if y is not None), 0) or 0 for c, s in by_category.items()}
        top = sorted(categories, key=lambda c: latest_values[c], reverse=True)[:TOP_CATEGORIES]
        trend = [Series(str(c), by_category[c].x, by_category[c].y) for c in top]

        def draw_trend(figure, region):
            return draw_chart(figure, trend, x_label, main_label, "line", rect=region)
        report.chart_page(chart.title, _join(gemeinde.name, f"{main_label}: the {len(top)} largest categories by "
                                                            f"{dimension_label.lower()}", age_note),
                          draw_trend, figures_for(trend, [str(c) for c in top]), main_label,
                          image_name=f"{chart.title} - largest categories")


def _age_pyramid(report: PdfReport, run: _ReportRun, data: CensusData, chart: Chart, gemeinde: Gemeinde):
    """An age pyramid of the latest year for tables with population by age and gender."""
    schema = data.schema(chart.table)
    if not (schema.has_age_range() and "year" in schema.dimensions
            and {"pop_mle", "pop_fml"} <= set(schema.values)):
        return
    year = data.dimension_values(chart.table, "year")[-1]
    extra = [value for value in ("frgnr_tgthr",) if value in schema.values]
    rows = data.grouped_rows(chart.table, "age", ["pop_mle", "pop_fml", *extra], gemeinde.key, {"year": year})
    ages = [row[0] for row in rows]
    male, female = [row[1] for row in rows], [row[2] for row in rows]
    run.csv(f"{chart.title} - age pyramid {year}", ["Age", "Male", "Female"],
            [[age, m, f] for age, m, f in zip(ages, male, female)])
    total_male, total_female = sum(v or 0 for v in male), sum(v or 0 for v in female)
    total = (total_male + total_female) or 1
    figures = [KeyFigure("Male", format_value(total_male), f"{total_male / total * 100:.1f} % of the population"),
               KeyFigure("Female", format_value(total_female), f"{total_female / total * 100:.1f} % of the population")]
    if extra:
        foreigners = sum(row[3] or 0 for row in rows)
        figures.append(KeyFigure("Foreigners", format_value(foreigners),
                                 f"{foreigners / total * 100:.1f} % of the population"))
    older = sum((m or 0) + (f or 0) for age, m, f in zip(ages, male, female)
                if isinstance(age, (int, float)) and age >= 65)
    figures.append(KeyFigure("Aged 65 and over", format_value(older), f"{older / total * 100:.1f} % of the population"))

    def draw(figure, region):
        draw_pyramid(figure, ages, male, female, "Male", "Female", region)
    report.chart_page(f"{chart.title}: age structure", _join(gemeinde.name, f"Population by age and gender in {year}"),
                      draw, figures, f"In {year}", image_name=f"{chart.title} - age pyramid {year}")


# --- Gemeinde, Kreis and Land ---------------------------------------------------------------------

def kreis_land_report(data: CensusData, gemeinde: Gemeinde, category: str, output_dir: str,
                      map_image: Optional[MapImageCallback] = None, progress: Optional[ProgressCallback] = None) -> str:
    run = _ReportRun(output_dir, gemeinde.name, f"{category} Kreis-Land", progress)
    charts = data.charts_for(category, LEVELS)
    names = [gemeinde.name, f"{gemeinde.kreis_name} (Kreis)", STATE_NAME]
    kreis_keys = [g.key for g in data.gemeinden if g.kreis_key == gemeinde.kreis_key]

    def areas(chart: Chart):
        return [(chart, gemeinde.key), (data.variant(chart, "krs"), gemeinde.kreis_key),
                (data.variant(chart, "rgn"), None)]

    def front(report: PdfReport):
        _cover(report, run, map_image, f"{category}: Gemeinde, Kreis and Land",
               f"{gemeinde.name} · {gemeinde.kreis_name} · {STATE_NAME}", profile_figures(data, gemeinde.key),
               [gemeinde.key], gemeinde.name, kreis_keys, f"Kreis {gemeinde.kreis_name}")
        rows = []
        for chart in charts:
            figures = [chart_highlight(data, variant, key)[1] for variant, key in areas(chart)]
            rows.append((chart.title, data.label(chart_focus(data, chart).value, chart.table), figures))
        report.glance_page("At a glance", "The main value of every chart for the Gemeinde, its Kreis and the Land",
                           names, rows)

    def write_chart(report: PdfReport, chart: Chart):
        _comparison_chart(report, run, data, chart, areas(chart), names,
                          f"{gemeinde.name}, {gemeinde.kreis_name} and {STATE_NAME}")

    return run.run(category, front, charts, write_chart, index_charts=True)


# --- Two Gemeinden ---------------------------------------------------------------------------------

def gemeinde_comparison_report(data: CensusData, first: Gemeinde, second: Gemeinde, category: str, output_dir: str,
                               map_image: Optional[MapImageCallback] = None,
                               progress: Optional[ProgressCallback] = None) -> str:
    run = _ReportRun(output_dir, f"{first.name} and {second.name}", category, progress)
    charts = data.charts_for(category)
    names = [first.name, second.name]

    def front(report: PdfReport):
        tiles = []
        for gemeinde in (first, second):
            for item in profile_figures(data, gemeinde.key)[:3]:
                tiles.append(KeyFigure(f"{item.label}, {gemeinde.name}", item.value, item.note, item.change,
                                       item.change_text))
        _cover(report, run, map_image, f"{category} report", f"{first.name} and {second.name}", tiles,
               [first.key, second.key], f"{first.name} and {second.name}")
        rows = []
        for chart in charts:
            figures = [chart_highlight(data, chart, gemeinde.key)[1] for gemeinde in (first, second)]
            rows.append((chart.title, data.label(chart_focus(data, chart).value, chart.table), figures))
        report.glance_page("At a glance", f"The main value of every chart for {first.name} and {second.name}",
                           names, rows)

    def write_chart(report: PdfReport, chart: Chart):
        _comparison_chart(report, run, data, chart, [(chart, first.key), (chart, second.key)], names,
                          f"{first.name} and {second.name}")

    return run.run(category, front, charts, write_chart, index_charts=True)


def _comparison_chart(report: PdfReport, run: _ReportRun, data: CensusData, chart: Chart,
                      areas: Sequence[Tuple[Chart, Optional[int]]], names: Sequence[str], subtitle: str):
    """Development of every value as index lines per area (time axes), or the distribution in percent
    (other axes); key figures give the actual values of the main value for each area."""
    schema = data.schema(chart.table)
    focus = chart_focus(data, chart)
    axis, table = focus.axis, chart.table
    x_label = data.label(axis, table)
    note = _join(focus.description, "Summed over all ages" if schema.has_age_range() and axis != "age" else None,
                 f"{MAX_PANELS} of {len(schema.values)} values shown, all in the CSV file"
                 if len(schema.values) > MAX_PANELS else None)

    per_value = []
    for value in schema.values:
        series = []
        for (variant, key), name in zip(areas, names):
            item = _rows_series(data, variant, axis, [value], key, focus.filters)[0]
            series.append(Series(name, item.x, item.y))
        per_value.append((data.label(value, table), series))
    flat = [Series(f"{label}: {item.label}", item.x, item.y) for label, series in per_value for item in series]
    run.csv(chart.title, [x_label, *(item.label for item in flat)], _merge(flat))

    main_label, main_series = per_value[0]
    if axis in TIME_AXES:
        panels = [(label, index_series(series)) for label, series in per_value[:MAX_PANELS]]
        figures = [key_figure(item.label, item, is_percent(main_label)) for item in main_series]
        page_subtitle = _join(subtitle, INDEX_LABEL, note)

        def draw(figure, region):
            left, bottom, width, height = region
            # Room above the panels for the legend that names the areas
            draw_panels(figure, panels, x_label, axis, (left, bottom, width, height - LEGEND_SPACE),
                        _columns(len(panels)), baseline=100, legend_at=(left, bottom + height + 0.01))
    else:
        shares = [_shares(item) for item in main_series]
        figures = [KeyFigure(item.label, format_value(_total(item)), f"{main_label}, total") for item in main_series]
        page_subtitle = _join(subtitle, f"{main_label}: share of each {x_label.lower()} in percent", note)

        def draw(figure, region):
            return draw_chart(figure, shares, x_label, "Share (%)", chart_kind(axis, shares[0].x), rect=region)
    report.chart_page(chart.title, page_subtitle, draw, figures, main_label, image_name=chart.title)
