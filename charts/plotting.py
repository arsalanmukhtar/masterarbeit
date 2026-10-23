# -*- coding: utf-8 -*-
"""Charts for the dashboard and the PDF reports, drawn with matplotlib.

Chart types: line, area, bars, stacked bars, stacked area and donut. Fonts, colours and ticks are
set explicitly on every element, so the global matplotlib settings of QGIS are left untouched.
"""
from __future__ import annotations

import math
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.path import Path
from matplotlib.ticker import MaxNLocator
from matplotlib.transforms import IdentityTransform

from ..core.models import Series
from ..core.style import AXIS, FONT_DIR, GRID, INK, INK_SECONDARY, MUTED, SERIES_COLORS, SURFACE, THEMES

LINE_WIDTH = 2.2
END_DOT_SIZE = 8  # points
BAR_MAX_WIDTH_PX = 28
BAR_GAP_PX = 2
BAR_RADIUS_PT = 3
TIME_DIMENSIONS = ("year", "age")

# Text sizes in points
TICK_SIZE = 9.5
AXIS_LABEL_SIZE = 10.5
LEGEND_SIZE = 10
VALUE_LABEL_SIZE = 10
TOOLTIP_SIZE = 10

KIND_LABELS = {"line": "Line", "area": "Area", "bar": "Bars", "stacked_bar": "Stacked bars",
               "stacked_area": "Stacked area", "donut": "Donut"}
CROSSHAIR_KINDS = ("line", "area", "stacked_area")
# Category rows that hold the sum of the others and must not become a slice or a stacked segment
TOTAL_NAMES = ("insgesamt", "gesamt", "zusammen", "total")
DONUT_MAX_PARTS = 8


def _register_fonts() -> str:
    """Make the bundled Inter font available to matplotlib; DejaVu Sans is the fallback."""
    try:
        for name in sorted(os.listdir(FONT_DIR)):
            if name.lower().endswith(".ttf"):
                font_manager.fontManager.addfont(os.path.join(FONT_DIR, name))
        font_manager.findfont("Inter", fallback_to_default=False)
        return "Inter"
    except (OSError, ValueError, AttributeError):
        return "DejaVu Sans"


FONT_FAMILY = _register_fonts()
current_theme = "light"


def set_theme(name: str):
    """Switch chart colours between the light and dark theme for everything drawn afterwards."""
    global SURFACE, INK, INK_SECONDARY, MUTED, GRID, AXIS, SERIES_COLORS, current_theme
    tokens = THEMES[name]
    SURFACE, INK, INK_SECONDARY = tokens["surface"], tokens["ink"], tokens["ink_secondary"]
    MUTED, GRID, AXIS, SERIES_COLORS = tokens["muted"], tokens["grid"], tokens["axis"], tokens["series"]
    current_theme = name


@contextmanager
def light_charts():
    """Saved images and PDF reports are always drawn in the light theme, whatever the dashboard shows."""
    previous = current_theme
    set_theme("light")
    try:
        yield
    finally:
        set_theme(previous)


# --- Numbers ---------------------------------------------------------------------------------------

def format_number(value) -> str:
    """Full value with thousands separators, for tables and tooltips."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def compact(value: float) -> str:
    """Short axis label: 950, 1K, 12.9K, 4.8M."""
    magnitude = abs(value)
    for limit, suffix in ((1e6, "M"), (1e3, "K")):
        if magnitude >= limit:
            return f"{value / limit:.1f}".rstrip("0").rstrip(".") + suffix
    if float(value).is_integer():
        return f"{int(value)}"
    return f"{value:.{1 if magnitude >= 100 else 2}f}".rstrip("0").rstrip(".")


def index_series(series: Sequence[Series]) -> List[Series]:
    """Each series relative to its own first value (= 100), so different magnitudes share one axis."""
    indexed = []
    for item in series:
        base = next((y for y in item.y if y not in (None, 0)), None)
        values = [None if y is None or base is None else y / base * 100 for y in item.y]
        indexed.append(Series(item.label, list(item.x), values))
    return indexed


# --- Choosing a chart type ---------------------------------------------------------------------------

def _is_total(category: object) -> bool:
    return str(category).strip().lower() in TOTAL_NAMES


def _non_negative(series: Sequence[Series]) -> bool:
    return all(y is None or y >= 0 for item in series for y in item.y)


def chart_kind(x_dimension: str, categories: Sequence[object]) -> str:
    """Default type: lines for years and ages, horizontal bars for long category names, columns otherwise."""
    if x_dimension in TIME_DIMENSIONS:
        return "line"
    longest = max((len(str(category)) for category in categories), default=0)
    return "barh" if longest > 14 else "bar"


def available_kinds(x_dimension: str, series: Sequence[Series], composition: bool = False) -> List[str]:
    """Chart types that fit the data. composition means the series are parts of one whole
    (several values of one Gemeinde), which allows stacked charts and donuts."""
    time = x_dimension in TIME_DIMENSIONS
    # Overlapping areas hide each other, so an area chart is offered for a single series only
    kinds = (["line", "area", "bar"] if len(series) == 1 else ["line", "bar"]) if time else ["bar"]
    if not _non_negative(series):
        return kinds
    if composition and 2 <= len(series) <= DONUT_MAX_PARTS:
        kinds += ["stacked_bar"] + (["stacked_area"] if time else []) + ["donut"]
    elif len(series) == 1 and not time and 2 <= len(_category_parts(series[0])) <= DONUT_MAX_PARTS:
        kinds.append("donut")
    return kinds


def _category_parts(item: Series) -> List[Tuple[str, float]]:
    return [(str(x), y) for x, y in zip(item.x, item.y) if y and not _is_total(x)]


def donut_parts(series: Sequence[Series]) -> Tuple[List[Tuple[str, float]], Optional[str]]:
    """Slices of a donut and, for several series, the X value whose shares are shown (the latest one
    where every series has a value)."""
    if len(series) == 1:
        return _category_parts(series[0]), None
    lookups = [dict(zip((str(x) for x in item.x), item.y)) for item in series]
    order = [str(x) for x in series[0].x]
    for x in reversed(order):
        if all(lookup.get(x) is not None for lookup in lookups):
            return [(item.label, lookup[x]) for item, lookup in zip(series, lookups) if lookup[x]], x
    return [], None


# --- Rounded bars ----------------------------------------------------------------------------------

class RoundedBar(Patch):
    """A bar or stacked segment with a rounded data end and a square base, sized in screen pixels at
    draw time so the corner radius and the gaps between neighbours stay constant when resizing."""

    def __init__(self, position: float, width: float, value: float, horizontal: bool = False, start: float = 0.0,
                 rounded: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.position, self.width, self.value, self.horizontal = position, width, value, horizontal
        self.start, self.rounded = start, rounded
        self.category = ""
        self.series_label = ""

    def get_transform(self):
        return IdentityTransform()

    def get_path(self):
        transform = self.axes.transData
        dpi = self.figure.dpi if self.figure else 100
        radius = BAR_RADIUS_PT * dpi / 72 if self.rounded else 0
        gap = BAR_GAP_PX * dpi / 100 / 2
        top = self.start + self.value
        if self.horizontal:
            (base, low), (end, high) = transform.transform([(self.start, self.position), (top, self.position + self.width)])
        else:
            (low, base), (high, end) = transform.transform([(self.position, self.start), (self.position + self.width, top)])
        low, high = min(low, high) + gap, max(low, high) - gap
        direction = 1 if end >= base else -1
        if self.start:
            # Stacked segments are separated by a thin gap in the surface colour
            base += direction * gap
            end -= direction * gap
        length = end - base
        if direction * length < 0.5 or high <= low:
            return Path([(0, 0)], [Path.MOVETO])
        radius = min(radius, (high - low) / 2, abs(length))
        corner = end - direction * radius
        points = [(low, base), (low, corner), (low, end), (low + radius, end), (high - radius, end),
                  (high, end), (high, corner), (high, base), (low, base)]
        codes = [Path.MOVETO, Path.LINETO, Path.CURVE3, Path.CURVE3, Path.LINETO, Path.CURVE3, Path.CURVE3,
                 Path.LINETO, Path.CLOSEPOLY]
        if self.horizontal:
            points = [(along, across) for across, along in points]
        return Path(points, codes)


# --- Axes helpers ------------------------------------------------------------------------------------

@dataclass
class ChartHandle:
    """What hover tooltips and resizing need to know about a drawn chart."""
    axes: object
    kind: str
    categories: List[str]
    positions: List[float]
    series: List[Series]
    artists: List[list] = field(default_factory=list)
    horizontal: bool = False
    stacked: bool = False
    note: Optional[str] = None  # e.g. "Shares in 2023" for a donut of several values


def _style_axes(axes, horizontal: bool = False):
    axes.set_facecolor(SURFACE)
    for side in ("top", "right", "left", "bottom"):
        axes.spines[side].set_visible(False)
    axes.tick_params(length=0, pad=7)
    (axes.xaxis if horizontal else axes.yaxis).grid(True, color=GRID, linewidth=0.9, linestyle="-")
    (axes.yaxis if horizontal else axes.xaxis).grid(False)
    axes.set_axisbelow(True)


def _axis_label(axes, method: str, text: str, size: float = AXIS_LABEL_SIZE):
    getattr(axes, method)(text, fontsize=size, color=INK_SECONDARY, fontfamily=FONT_FAMILY, fontweight="medium",
                          labelpad=8)


def _tick_labels(axes, axis: str, ticks, labels, size: float = TICK_SIZE, color: str = INK_SECONDARY, **kwargs):
    getattr(axes, f"set_{axis}ticks")(ticks)
    getattr(axes, f"set_{axis}ticklabels")(labels, fontfamily=FONT_FAMILY, fontsize=size, color=color, **kwargs)


def _value_ticks(axes, low: float, high: float, horizontal: bool, include_zero: bool, count: int = 5,
                 size: float = TICK_SIZE):
    if include_zero:
        low, high = min(low, 0), max(high, 0)
    if low == high:
        low, high = low - 1, high + 1
    ticks = [tick for tick in MaxNLocator(nbins=count, steps=[1, 2, 2.5, 5, 10]).tick_values(low, high)
             if low - (high - low) * 0.001 <= tick <= high + (high - low) * 0.001] or [low, high]
    span = (max(ticks[-1], high) - min(ticks[0], low)) or 1
    limits = (min(ticks[0], low) - (0 if include_zero and low >= 0 else span * 0.04),
              max(ticks[-1], high) + span * 0.05)
    (axes.set_xlim if horizontal else axes.set_ylim)(*limits)
    _tick_labels(axes, "x" if horizontal else "y", ticks, [compact(tick) for tick in ticks], size)


def _year_ticks(axes, positions: Sequence[float], count: int, size: float = TICK_SIZE):
    ticks = [tick for tick in MaxNLocator(nbins=count, integer=True).tick_values(positions[0], positions[-1])
             if positions[0] <= tick <= positions[-1]]
    _tick_labels(axes, "x", ticks, [str(int(tick)) for tick in ticks], size)


def _category_ticks(axes, categories: Sequence[str], positions: Sequence[float], horizontal: bool, max_labels: int,
                    size: float = TICK_SIZE):
    step = max(1, math.ceil(len(categories) / max(max_labels, 1)))
    chosen = list(range(0, len(categories), step))
    labels = [categories[i] for i in chosen]
    if horizontal:
        _tick_labels(axes, "y", [positions[i] for i in chosen], labels, size, INK)
        axes.invert_yaxis()
    else:
        rotate = len(chosen) > 10 or max((len(label) for label in labels), default=0) > 6
        _tick_labels(axes, "x", [positions[i] for i in chosen], labels, size, rotation=40 if rotate else 0,
                     ha="right" if rotate else "center", rotation_mode="anchor")


def _legend(axes, series: Sequence[Series], kind: str):
    if kind in ("line",):
        handles = [Line2D([], [], color=_colour(i), linewidth=3, solid_capstyle="round") for i in range(len(series))]
    else:
        handles = [Line2D([], [], color=_colour(i), linewidth=0, marker="s", markersize=10) for i in range(len(series))]
    legend = axes.legend(handles, [item.label for item in series], loc="lower left", bbox_to_anchor=(0, 1.02),
                         ncol=min(len(series), 4), frameon=False, handlelength=1.3, borderaxespad=0, columnspacing=1.8,
                         handletextpad=0.6, prop={"family": FONT_FAMILY, "size": LEGEND_SIZE})
    for text in legend.get_texts():
        text.set_color(INK)


def _colour(index: int) -> str:
    return SERIES_COLORS[index % len(SERIES_COLORS)]


def _numeric_x(series: Sequence[Series]) -> bool:
    values = [x for item in series for x in item.x]
    return bool(values) and all(isinstance(x, (int, float)) for x in values)


def _categories(series: Sequence[Series]) -> List[str]:
    categories: List[str] = []
    for item in series:
        for x in item.x:
            if str(x) not in categories:
                categories.append(str(x))
    return categories


# --- Drawing -------------------------------------------------------------------------------------

def draw_chart(figure, series: Sequence[Series], x_label: str, y_label: str, kind: str,
               baseline: Optional[float] = None, legend: bool = True, max_x_labels: int = 14) -> ChartHandle:
    """Draw one chart of the given kind. baseline marks a reference value, e.g. 100 for an index."""
    figure.set_facecolor(SURFACE)
    if kind == "donut":
        return _draw_donut(figure, series, legend)
    categories = _categories(series)
    horizontal = kind == "barh" or (kind in ("bar", "stacked_bar") and chart_kind("", categories) == "barh")
    axes = figure.add_subplot(111)
    _style_axes(axes, horizontal)
    time_axis = kind in CROSSHAIR_KINDS and _numeric_x(series)
    positions = [float(c) for c in categories] if time_axis else [float(i) for i in range(len(categories))]
    handle = ChartHandle(axes, "bar" if kind == "barh" else kind, categories, positions, list(series),
                         horizontal=horizontal)
    lookup = [dict(zip((str(x) for x in item.x), item.y)) for item in series]
    values = [y for item in series for y in item.y if y is not None]
    reference = [baseline] if baseline is not None else []

    if kind in CROSSHAIR_KINDS:
        if kind == "stacked_area":
            totals = _draw_stacked_area(axes, handle, lookup)
            low, high, zero = 0, max(totals or [0]), True
        else:
            _draw_lines(axes, handle, lookup, area=kind == "area", baseline=baseline)
            low, high = min(values + reference, default=0), max(values + reference, default=1)
            zero = kind == "area" and baseline is None
            if len(series) <= 3:
                _end_labels(axes, lookup, positions, categories)
        span = (positions[-1] - positions[0]) or 1
        right = 0.1 if kind != "stacked_area" and len(series) <= 3 else 0.015
        axes.set_xlim(positions[0] - span * 0.01, positions[-1] + span * right)
        if time_axis:
            _year_ticks(axes, positions, min(max_x_labels, 10))
        else:
            _category_ticks(axes, categories, positions, False, max_x_labels)
        _value_ticks(axes, low, high, False, include_zero=zero)
    else:
        stacked = kind == "stacked_bar"
        handle.stacked = stacked
        totals = _draw_bars(axes, handle, lookup, stacked)
        (axes.set_ylim if horizontal else axes.set_xlim)(-0.6, len(categories) - 0.4)
        _category_ticks(axes, categories, positions, horizontal, 40 if horizontal else max_x_labels)
        if values:
            _value_ticks(axes, min(values + [0]) if not stacked else 0,
                         max(totals) if stacked else max(values), horizontal, include_zero=True)
        limit_bar_width(handle)

    if baseline is not None:
        (axes.axvline if horizontal else axes.axhline)(baseline, color=AXIS, linewidth=1.2, zorder=2)
    elif kind not in ("line",) or (values and min(values) <= 0 <= max(values)):
        (axes.axvline if horizontal else axes.axhline)(0, color=AXIS, linewidth=1.2, zorder=2)

    if horizontal:
        _axis_label(axes, "set_xlabel", y_label)
    else:
        _axis_label(axes, "set_xlabel", x_label)
        _axis_label(axes, "set_ylabel", y_label)
    if legend and len(series) > 1:
        _legend(axes, series, "line" if kind == "line" else "fill")
    return handle


def _draw_lines(axes, handle: ChartHandle, lookup, area: bool, baseline: Optional[float]):
    for index, item in enumerate(handle.series):
        points = [(p, lookup[index][c]) for p, c in zip(handle.positions, handle.categories)
                  if lookup[index].get(c) is not None]
        if not points:
            handle.artists.append([])
            continue
        xs, ys = zip(*points)
        color = _colour(index)
        line, = axes.plot(xs, ys, color=color, linewidth=LINE_WIDTH, solid_capstyle="round", solid_joinstyle="round",
                          zorder=3)
        if area:
            axes.fill_between(xs, ys, baseline if baseline is not None else 0, color=color,
                              alpha=0.18 if len(handle.series) == 1 else 0.10, linewidth=0, zorder=2)
        axes.scatter([xs[-1]], [ys[-1]], s=END_DOT_SIZE ** 2, color=color, edgecolors=SURFACE, linewidths=2, zorder=4)
        handle.artists.append([line])


def _draw_stacked_area(axes, handle: ChartHandle, lookup) -> List[float]:
    layers = [[lookup[i].get(c) or 0 for c in handle.categories] for i in range(len(handle.series))]
    polygons = axes.stackplot(handle.positions, layers, colors=[_colour(i) for i in range(len(layers))], alpha=0.9,
                              edgecolor=SURFACE, linewidth=1, zorder=3)
    handle.artists = [[polygon] for polygon in polygons]
    return [sum(column) for column in zip(*layers)] if layers else []


def _draw_bars(axes, handle: ChartHandle, lookup, stacked: bool) -> List[float]:
    count = 1 if stacked else max(len(handle.series), 1)
    slot = 0.8 / count
    totals = [0.0] * len(handle.categories)
    handle.artists = [[] for _ in handle.series]
    for column, (position, category) in enumerate(zip(handle.positions, handle.categories)):
        if stacked and _is_total(category):
            continue
        layers = [(index, lookup[index].get(category)) for index in range(len(handle.series))]
        layers = [(index, value) for index, value in layers if value is not None]
        top_index = next((index for index, value in reversed(layers) if value), None)
        for index, value in layers:
            start = totals[column] if stacked else 0.0
            bar = RoundedBar(position - 0.4 + (0 if stacked else index * slot), slot, value, handle.horizontal,
                             start=start, rounded=not stacked or index == top_index, facecolor=_colour(index),
                             edgecolor="none", zorder=3)
            bar.category, bar.series_label = category, handle.series[index].label
            axes.add_patch(bar)
            handle.artists[index].append(bar)
            if stacked:
                totals[column] += value
    return totals if stacked else [0.0]


def _draw_donut(figure, series: Sequence[Series], legend: bool) -> ChartHandle:
    parts, share_x = donut_parts(series)
    axes = figure.add_subplot(111)
    axes.set_facecolor(SURFACE)
    handle = ChartHandle(axes, "donut", [label for label, _ in parts], [], list(series),
                         note=f"Shares in {share_x}" if share_x else None)
    if not parts:
        axes.axis("off")
        return handle
    total = sum(value for _, value in parts)
    wedges, _ = axes.pie([value for _, value in parts], colors=[_colour(i) for i in range(len(parts))], startangle=90,
                         counterclock=False, wedgeprops={"width": 0.36, "edgecolor": SURFACE, "linewidth": 2.5})
    for wedge, (label, value) in zip(wedges, parts):
        wedge.part_label, wedge.part_value, wedge.share = label, value, value / total * 100 if total else 0
    handle.artists = [list(wedges)]
    axes.text(0, 0.08, compact(total), ha="center", va="center", fontsize=18, fontweight="semibold", color=INK,
              fontfamily=FONT_FAMILY)
    axes.text(0, -0.14, "Total", ha="center", va="center", fontsize=LEGEND_SIZE, color=MUTED, fontfamily=FONT_FAMILY)
    axes.set_aspect("equal")
    if legend:
        handles = [Line2D([], [], color=_colour(i), linewidth=0, marker="s", markersize=11) for i in range(len(parts))]
        labels = [f"{label}   {value / total * 100:.1f} %" if total else label for label, value in parts]
        legend_box = axes.legend(handles, labels, loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False,
                                 handletextpad=0.6, labelspacing=0.9, prop={"family": FONT_FAMILY, "size": LEGEND_SIZE})
        for text in legend_box.get_texts():
            text.set_color(INK)
    return handle


def limit_bar_width(handle: ChartHandle):
    """Cap bars at 28 px so wide windows show air between groups instead of fat blocks.
    Call again after the figure changed size."""
    if handle.kind not in ("bar", "stacked_bar") or not handle.categories:
        return
    axes = handle.axes
    extent = axes.get_window_extent()
    pixels_per_unit = (extent.height if handle.horizontal else extent.width) / (len(handle.categories) + 0.2)
    count = 1 if handle.stacked else max(len(handle.series), 1)
    slot = 0.8 / count
    if pixels_per_unit > 0:
        slot = min(slot, BAR_MAX_WIDTH_PX * axes.figure.dpi / 100 / pixels_per_unit)
    centres = dict(zip(handle.categories, handle.positions))
    for index, bars in enumerate(handle.artists):
        for bar in bars:
            bar.position = centres[bar.category] - slot * count / 2 + (0 if handle.stacked else index * slot)
            bar.width = slot


def _end_labels(axes, lookup, positions, categories):
    """The latest value at the end of each line, unless the lines end too close together to read."""
    ends = []
    for values in lookup:
        ends.append(next(((p, values[c]) for p, c in zip(reversed(positions), reversed(categories))
                          if values.get(c) is not None), None))
    finite = sorted(y for _, y in filter(None, ends))
    if not finite:
        return
    scale = max(max(finite) - min(finite), max(abs(v) for v in finite) * 0.25) or 1
    if len(finite) > 1 and min(b - a for a, b in zip(finite, finite[1:])) < scale * 0.08:
        return
    for end in filter(None, ends):
        axes.annotate(compact(end[1]), end, xytext=(9, 0), textcoords="offset points", va="center",
                      fontsize=VALUE_LABEL_SIZE, color=INK, fontfamily=FONT_FAMILY, fontweight="semibold")


def draw_small_multiples(figure, series: Sequence[Series], x_label: str, x_dimension: str, columns: int = 3):
    """One small chart per series, each on its own scale: for values with different units."""
    count = len(series)
    columns = min(columns, count) or 1
    rows = math.ceil(count / columns)
    figure.set_facecolor(SURFACE)
    for index, item in enumerate(series):
        axes = figure.add_subplot(rows, columns, index + 1)
        kind = chart_kind(x_dimension, item.x)
        _draw_panel(axes, item, "bar" if kind == "barh" else kind, max_labels=6 if columns > 1 else 12)
        axes.set_title(item.label, fontsize=10.5, color=INK, fontweight="semibold", fontfamily=FONT_FAMILY, loc="left",
                       pad=7)
        if index >= count - columns:
            _axis_label(axes, "set_xlabel", x_label, size=9.5)


def _draw_panel(axes, item: Series, kind: str, max_labels: int):
    _style_axes(axes)
    categories = [str(x) for x in item.x]
    numeric = kind == "line" and _numeric_x([item])
    positions = [float(c) for c in categories] if numeric else [float(i) for i in range(len(categories))]
    values = [y for y in item.y if y is not None]
    color = SERIES_COLORS[0]
    if kind == "line":
        points = [(p, y) for p, y in zip(positions, item.y) if y is not None]
        if points:
            xs, ys = zip(*points)
            axes.plot(xs, ys, color=color, linewidth=1.9, solid_capstyle="round", zorder=3)
            axes.scatter([xs[-1]], [ys[-1]], s=40, color=color, edgecolors=SURFACE, linewidths=1.5, zorder=4)
        if numeric and positions:
            _year_ticks(axes, positions, 4, size=8.5)
        else:
            _category_ticks(axes, categories, positions, False, max_labels, size=8.5)
        if values:
            _value_ticks(axes, min(values), max(values), False, include_zero=False, count=4, size=8.5)
    else:
        for position, value in zip(positions, item.y):
            if value is not None:
                axes.add_patch(RoundedBar(position - 0.4, 0.8, value, facecolor=color, edgecolor="none", zorder=3))
        axes.set_xlim(-0.6, len(categories) - 0.4)
        _category_ticks(axes, categories, positions, False, max_labels, size=8.5)
        if values:
            _value_ticks(axes, min(values), max(values), False, include_zero=True, count=4, size=8.5)
        axes.axhline(0, color=AXIS, linewidth=1.2, zorder=2)


def reserve_margins(figure, top: float = 0.0, bottom: float = 0.0):
    """Lay out the axes inside the figure, keeping room at the top (title) and bottom (credits)."""
    if hasattr(figure, "set_layout_engine"):
        figure.set_layout_engine("constrained", rect=(0, bottom, 1, 1 - top - bottom))
    else:
        figure.set_constrained_layout(False)
        figure.tight_layout(rect=(0, bottom, 1, 1 - top))


def render_static(figure, handle: Optional[ChartHandle] = None):
    """Lay out a figure that is saved to a file rather than shown, then size its bars."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    FigureCanvasAgg(figure)
    figure.canvas.draw()
    if handle is not None:
        limit_bar_width(handle)


def draw_message(figure, text: str):
    figure.set_facecolor(SURFACE)
    figure.text(0.5, 0.5, text, ha="center", va="center", fontsize=11, color=MUTED, fontfamily=FONT_FAMILY, wrap=True)


# --- Hover ---------------------------------------------------------------------------------------

class ChartHover:
    """Tooltips: every series at the nearest X for lines and areas, the bar or slice under the mouse
    for bar charts and donuts."""

    def __init__(self, canvas):
        self._canvas = canvas
        self._connection = None
        self._handle: Optional[ChartHandle] = None
        self._tooltip = None
        self._crosshair = None

    def attach(self, handle: ChartHandle):
        self.detach()
        self._handle = handle
        self._tooltip = handle.axes.annotate(
            "", xy=(0, 0), xytext=(14, 14), textcoords="offset points", fontsize=TOOLTIP_SIZE, fontfamily=FONT_FAMILY,
            color=INK, zorder=10, annotation_clip=False, linespacing=1.5,
            bbox={"boxstyle": "round,pad=0.6,rounding_size=0.4", "fc": SURFACE, "ec": AXIS, "lw": 1})
        self._tooltip.set_visible(False)
        if handle.kind in CROSSHAIR_KINDS and handle.positions:
            self._crosshair = handle.axes.axvline(handle.positions[0], color=INK_SECONDARY, linewidth=1, alpha=0.5,
                                                  zorder=5)
            self._crosshair.set_visible(False)
        self._connection = self._canvas.mpl_connect("motion_notify_event", self._on_move)

    def detach(self):
        if self._connection is not None:
            self._canvas.mpl_disconnect(self._connection)
        self._connection, self._handle, self._tooltip, self._crosshair = None, None, None, None

    def _hide(self):
        if self._tooltip is not None and self._tooltip.get_visible():
            self._tooltip.set_visible(False)
            if self._crosshair is not None:
                self._crosshair.set_visible(False)
            self._canvas.draw_idle()

    def _on_move(self, event):
        handle = self._handle
        if handle is None or event.inaxes is not handle.axes or event.xdata is None:
            self._hide()
            return
        if handle.kind == "donut":
            for wedge in handle.artists[0] if handle.artists else []:
                if wedge.contains(event)[0]:
                    text = f"{wedge.part_label}\n{format_number(wedge.part_value)}  ({wedge.share:.1f} %)"
                    self._show(text, (event.xdata, event.ydata), event)
                    return
            self._hide()
            return
        if handle.kind in CROSSHAIR_KINDS:
            if not handle.positions:
                return
            index = min(range(len(handle.positions)), key=lambda i: abs(handle.positions[i] - event.xdata))
            category = handle.categories[index]
            lines, total, top = [category], 0.0, None
            for item in handle.series:
                value = dict(zip((str(x) for x in item.x), item.y)).get(category)
                lines.append((f"{item.label}: " if len(handle.series) > 1 else "") + format_number(value))
                if value is not None:
                    total += value
                    top = value if top is None else max(top, value)
            if handle.kind == "stacked_area":
                lines.append(f"Total: {format_number(total)}")
                top = total
            self._crosshair.set_xdata([handle.positions[index]] * 2)
            self._crosshair.set_visible(True)
            self._show("\n".join(lines), (handle.positions[index], top if top is not None else event.ydata), event)
            return
        for bars in handle.artists:
            for bar in bars:
                if bar.contains(event)[0]:
                    prefix = f"{bar.series_label}\n" if len(handle.series) > 1 else ""
                    middle = bar.position + bar.width / 2
                    end = bar.start + bar.value
                    xy = (end, middle) if handle.horizontal else (middle, end)
                    self._show(f"{prefix}{bar.category}: {format_number(bar.value)}", xy, event)
                    return
        self._hide()

    def _show(self, text, xy, event):
        box = self._handle.axes.get_window_extent()
        right = event.x > box.x0 + box.width * 0.6
        upper = event.y > box.y0 + box.height * 0.7
        self._tooltip.xy = xy
        self._tooltip.set_text(text)
        self._tooltip.set_position((-14 if right else 14, -14 if upper else 14))
        self._tooltip.set_horizontalalignment("right" if right else "left")
        self._tooltip.set_verticalalignment("top" if upper else "bottom")
        self._tooltip.set_visible(True)
        self._canvas.draw_idle()
