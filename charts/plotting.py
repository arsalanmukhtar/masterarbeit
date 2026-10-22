# -*- coding: utf-8 -*-
"""Bar charts drawn with matplotlib, shared by the dashboard and the PDF reports."""
from __future__ import annotations

import math
import textwrap
from typing import List, Optional, Sequence

from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter

from ..core.models import Series

# Charts use Inter when it is installed and fall back to matplotlib's bundled DejaVu Sans
FONT_FAMILY = "Inter" if any(font.name == "Inter" for font in font_manager.fontManager.ttflist) else "DejaVu Sans"
PALETTE = ("#2e86de", "#f39c12", "#27ae60", "#c0392b", "#8e44ad", "#16a085", "#d35400", "#7f8c8d")
MAX_TICK_LABELS = 30


def format_number(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


def use_constrained_layout(figure):
    # set_layout_engine replaced set_constrained_layout in matplotlib 3.6; older QGIS builds ship 3.5
    if hasattr(figure, "set_layout_engine"):
        figure.set_layout_engine("constrained")
    else:
        figure.set_constrained_layout(True)


def reserve_bottom(figure, fraction: float):
    """Keep the bottom of the figure free, e.g. for the credit line on PDF pages."""
    if hasattr(figure, "set_layout_engine"):
        figure.set_layout_engine("constrained", rect=(0, fraction, 1, 1 - fraction))
    else:
        figure.set_constrained_layout(False)
        figure.tight_layout(rect=(0, fraction, 1, 1))


def draw_bar_chart(figure, series: Sequence[Series], title: str, x_label: str, y_label: str,
                   note: Optional[str] = None):
    """Draw one bar group per X value with one bar per series. Returns (axes, categories, bar containers)."""
    figure.clear()
    use_constrained_layout(figure)
    axes = figure.add_subplot(111)

    categories: List[str] = []
    for item in series:
        for x in item.x:
            if str(x) not in categories:
                categories.append(str(x))

    count = max(len(series), 1)
    width = 0.8 / count
    containers = []
    for index, item in enumerate(series):
        values = dict(zip((str(x) for x in item.x), item.y))
        offsets = [position + (index - (count - 1) / 2) * width for position in range(len(categories))]
        heights = [float("nan") if values.get(category) is None else float(values[category]) for category in categories]
        containers.append(axes.bar(offsets, heights, width, label=item.label, color=PALETTE[index % len(PALETTE)]))

    step = max(1, math.ceil(len(categories) / MAX_TICK_LABELS))
    axes.set_xticks(range(0, len(categories), step))
    longest = max((len(category) for category in categories), default=0)
    rotate = len(categories) > 12 or longest > 8
    axes.set_xticklabels(categories[::step], rotation=45 if rotate else 0, ha="right" if rotate else "center")

    axes.set_title(textwrap.fill(title, 90), fontsize=12, fontweight="bold", family=FONT_FAMILY)
    axes.set_xlabel(x_label, fontsize=10, fontweight="bold", family=FONT_FAMILY)
    axes.set_ylabel(y_label, fontsize=10, fontweight="bold", family=FONT_FAMILY)
    axes.tick_params(labelsize=8)
    axes.yaxis.set_major_formatter(FuncFormatter(lambda value, _: format_number(value)))
    axes.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.5)
    axes.set_axisbelow(True)
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)

    if len(series) > 1 or note:
        axes.legend(title=note, loc="upper center", bbox_to_anchor=(0.5, -0.15 if rotate else -0.1),
                    ncol=min(len(series), 4), frameon=False, fontsize=8, title_fontsize=8)
    return axes, categories, containers


class HoverTooltips:
    """Shows "X: value" next to the bar under the mouse on an interactive canvas."""

    def __init__(self, canvas):
        self._canvas = canvas
        self._connection = None
        self._annotation = None
        self._bars = []

    def attach(self, axes, categories, containers, series):
        self.detach()
        self._bars = [
            (bar, category, item.label, value)
            for container, item in zip(containers, series)
            for bar, category in zip(container, categories)
            for value in [dict(zip((str(x) for x in item.x), item.y)).get(category)]
            if value is not None
        ]
        self._annotation = axes.annotate("", xy=(0, 0), xytext=(8, 8), textcoords="offset points", fontsize=8,
                                         bbox={"boxstyle": "round", "fc": "white", "ec": "#888888", "alpha": 0.9})
        self._annotation.set_visible(False)
        self._multiple = len(series) > 1
        self._connection = self._canvas.mpl_connect("motion_notify_event", self._on_move)

    def detach(self):
        if self._connection is not None:
            self._canvas.mpl_disconnect(self._connection)
        self._connection, self._annotation, self._bars = None, None, []

    def _on_move(self, event):
        if self._annotation is None:
            return
        for bar, category, label, value in self._bars:
            if bar.contains(event)[0]:
                prefix = f"{label}\n" if self._multiple else ""
                self._annotation.xy = (bar.get_x() + bar.get_width() / 2, bar.get_height())
                self._annotation.set_text(f"{prefix}{category}: {format_number(value)}")
                self._annotation.set_visible(True)
                self._canvas.draw_idle()
                return
        if self._annotation.get_visible():
            self._annotation.set_visible(False)
            self._canvas.draw_idle()
