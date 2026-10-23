# -*- coding: utf-8 -*-
"""Multi-page A4 PDF reports: cover, at a glance, chart pages with key figures, and notes on the data.

Pages are laid out in fixed areas (figure fractions), so they look the same on every matplotlib version.
"""
from __future__ import annotations

import datetime
import math
import os
import re
import textwrap
from typing import Callable, List, Optional, Sequence, Tuple

from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.image import imread
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle

from ..charts.plotting import FONT_FAMILY, render_static
from ..core.insights import KeyFigure
from ..core.style import GRID, INK, INK_SECONDARY, MUTED, SERIES_COLORS, SURFACE, trend_arrow

PAGE_SIZE = (11.69, 8.27)  # A4 landscape, inches
LEFT = 0.045
RIGHT = 0.955
CONTENT_TOP = 0.80
CONTENT_BOTTOM = 0.09
FIGURES_LEFT = 0.735
ACCENT = SERIES_COLORS[0]
STATE_LABEL = "Baden-Württemberg"
GLANCE_ROWS_PER_PAGE = 8

# Draws a chart into an area (left, bottom, width, height); returns a chart handle when bars need sizing
DrawCallback = Callable[[Figure, Tuple[float, float, float, float]], object]
# A rendered map: PNG path and the extent shown (xmin, ymin, xmax, ymax in EPSG:3857)
MapImage = Tuple[str, Tuple[float, float, float, float]]
# Legend entries of the cover map: (label, fill colour, outline colour)
LegendEntry = Tuple[str, str, str]

# Cover map frame and the overview inset in its lower right corner, in figure fractions
COVER_MAP = (0.535, 0.1, 0.42, 0.8)
OVERVIEW_WIDTH = 0.115
OVERVIEW_ASPECT = 0.86  # width / height of Baden-Württemberg in Web Mercator
EARTH_RADIUS = 6378137.0
GRATICULE_STEPS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1.0, 2.0)
SCALE_STEPS = (0.5, 1, 2, 5, 10, 20, 25, 50, 100)
MAP_INK = "#2f2e2b"


def _overview_rect() -> Tuple[float, float, float, float]:
    left, bottom, width, _ = COVER_MAP
    height = OVERVIEW_WIDTH / OVERVIEW_ASPECT * PAGE_SIZE[0] / PAGE_SIZE[1]
    return left + width - OVERVIEW_WIDTH - 0.008, bottom + 0.012, OVERVIEW_WIDTH, height


def map_sizes(width_px: int = 1400) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Pixel sizes for the cover map and the overview map, in the proportions of their frames on the page,
    so the rendered images fill the frames exactly."""
    def size(rect, width):
        aspect = (rect[2] * PAGE_SIZE[0]) / (rect[3] * PAGE_SIZE[1])
        return width, round(width / aspect)
    return size(COVER_MAP, width_px), size(_overview_rect(), width_px // 2)


def _longitude(x: float) -> float:
    return math.degrees(x / EARTH_RADIUS)


def _latitude(y: float) -> float:
    return math.degrees(2 * math.atan(math.exp(y / EARTH_RADIUS)) - math.pi / 2)


def _mercator_x(longitude: float) -> float:
    return math.radians(longitude) * EARTH_RADIUS


def _mercator_y(latitude: float) -> float:
    return EARTH_RADIUS * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))


def _graticule(low: float, high: float) -> List[float]:
    """Round degree values between low and high, three to five of them."""
    span = high - low
    step = next((step for step in GRATICULE_STEPS if span / step <= 5), GRATICULE_STEPS[-1])
    first = math.ceil(low / step) * step
    return [round(first + i * step, 6) for i in range(int((high - first) / step) + 1)]


def _degrees(value: float, positive: str, negative: str) -> str:
    text = f"{abs(value):.2f}".rstrip("0").rstrip(".")
    return f"{text}°{positive if value >= 0 else negative}"


def safe_file_name(name: str) -> str:
    # Gemeinde names such as Lahr/Schwarzwald contain characters that are not allowed in file names
    return re.sub(r'[<>:"/\\|?*]', "-", name).strip()


def _text(figure, x, y, text, size=9.0, color=INK, weight="normal", **kwargs):
    return figure.text(x, y, text, fontsize=size, color=color, fontweight=weight, fontfamily=FONT_FAMILY, **kwargs)


def _lines(text: str, width: int) -> Tuple[str, int]:
    wrapped = textwrap.fill(text, width)
    return wrapped, wrapped.count("\n") + 1


class PdfReport:
    def __init__(self, pdf_path: str, image_dir: Optional[str] = None, credits: Sequence[str] = (),
                 kicker: str = ""):
        self.pdf_path = pdf_path
        self.image_dir = image_dir
        self.credits = credits
        self.kicker = kicker.upper()
        self._pdf = None
        self._page = 0

    def __enter__(self):
        if self.image_dir:
            os.makedirs(self.image_dir, exist_ok=True)
        self._pdf = PdfPages(self.pdf_path)
        return self

    def __exit__(self, *exc):
        self._pdf.close()
        return False

    # --- Page frame ---------------------------------------------------------------------------------

    def _page_figure(self, title: str = "", subtitle: str = "") -> Figure:
        figure = Figure(figsize=PAGE_SIZE)
        figure.set_facecolor(SURFACE)
        if title:
            if self.kicker:
                _text(figure, LEFT, 0.948, self.kicker, 8.5, ACCENT, "semibold", va="top")
            _text(figure, LEFT, 0.922, textwrap.fill(title, 95), 18, INK, "semibold", va="top")
            if subtitle:
                _text(figure, LEFT, 0.858, textwrap.fill(subtitle, 160), 10, MUTED, va="top")
            figure.add_artist(Line2D([LEFT, RIGHT], [0.825, 0.825], color=GRID, linewidth=0.8,
                                     transform=figure.transFigure))
        return figure

    def _save(self, figure: Figure):
        self._page += 1
        _text(figure, RIGHT, 0.025, str(self._page), 8, MUTED, ha="right", va="bottom")
        if self.credits:
            _text(figure, LEFT, 0.025, " · ".join(self.credits), 6.5, MUTED, ha="left", va="bottom")
        self._pdf.savefig(figure, facecolor=figure.get_facecolor())

    def _save_image(self, figure: Figure, name: Optional[str]):
        if self.image_dir and name:
            figure.savefig(os.path.join(self.image_dir, safe_file_name(name) + ".png"), dpi=200,
                           facecolor=figure.get_facecolor())

    # --- Building blocks -------------------------------------------------------------------------

    def _tile(self, figure, x, y, width, height, item: KeyFigure):
        figure.add_artist(FancyBboxPatch((x, y), width, height, boxstyle="round,pad=0,rounding_size=0.012",
                                         transform=figure.transFigure, facecolor="#ffffff", edgecolor=GRID,
                                         linewidth=0.9))
        _text(figure, x + 0.012, y + height - 0.02, textwrap.shorten(item.label, 30, placeholder="…"), 8.5, MUTED,
              va="top")
        _text(figure, x + 0.012, y + height * 0.42, item.value, 16, INK, "semibold", va="center")
        self._change_line(figure, x + 0.012, y + 0.018, item, 8.5)

    def _change_line(self, figure, x, y, item: KeyFigure, size: float):
        if item.change is not None:
            arrow, colour = trend_arrow(item.change)
            _text(figure, x, y, arrow, size, colour, va="baseline")
            _text(figure, x + 0.014, y, item.change_text, size, INK_SECONDARY, va="baseline")
        elif item.note:
            _text(figure, x, y, item.note, size, MUTED, va="baseline")

    def _key_figures(self, figure, items: Sequence[KeyFigure], title: str = "Key figures"):
        figure.add_artist(Line2D([FIGURES_LEFT - 0.022] * 2, [CONTENT_BOTTOM + 0.01, CONTENT_TOP - 0.01], color=GRID,
                                 linewidth=0.8, transform=figure.transFigure))
        _text(figure, FIGURES_LEFT, CONTENT_TOP - 0.01, title.upper(), 8.5, MUTED, "semibold", va="top")
        y = CONTENT_TOP - 0.065
        step = min(0.125, (CONTENT_TOP - CONTENT_BOTTOM - 0.06) / max(len(items), 1))
        value_size = 17 if step >= 0.1 else 14
        for item in items:
            text, lines = _lines(item.label, 34)
            _text(figure, FIGURES_LEFT, y, text, 9, INK_SECONDARY, va="top", linespacing=1.3)
            label_height = 0.022 * lines
            _text(figure, FIGURES_LEFT, y - label_height - 0.004, item.value, value_size, INK, "semibold", va="top")
            self._change_line(figure, FIGURES_LEFT, y - label_height - 0.052, item, 8.5)
            y -= max(step, label_height + 0.085)

    # --- Pages ---------------------------------------------------------------------------------

    def _cover_map(self, figure, local: MapImage, overview: Optional[MapImage], legend: Sequence[LegendEntry]):
        """The map with graticule, legend, north arrow, scale bar and the overview inset."""
        path, (xmin, ymin, xmax, ymax) = local
        axes = figure.add_axes(COVER_MAP)
        axes.imshow(imread(path), extent=(xmin, xmax, ymin, ymax), interpolation="lanczos", zorder=1)
        axes.set_xlim(xmin, xmax)
        axes.set_ylim(ymin, ymax)
        for spine in axes.spines.values():
            spine.set_edgecolor(MAP_INK)
            spine.set_linewidth(0.9)

        # Graticule: meridians and parallels are straight lines in Web Mercator
        longitudes = _graticule(_longitude(xmin), _longitude(xmax))
        latitudes = _graticule(_latitude(ymin), _latitude(ymax))
        axes.set_xticks([_mercator_x(value) for value in longitudes])
        axes.set_xticklabels([_degrees(value, "E", "W") for value in longitudes])
        axes.set_yticks([_mercator_y(value) for value in latitudes])
        axes.set_yticklabels([_degrees(value, "N", "S") for value in latitudes], rotation=90, va="center")
        axes.tick_params(axis="both", length=3, width=0.8, color=MAP_INK, labelsize=7, labelcolor=INK_SECONDARY,
                         pad=2, top=True, right=True)
        for tick in axes.get_xticklabels() + axes.get_yticklabels():
            tick.set_fontfamily(FONT_FAMILY)
        axes.grid(True, color=MAP_INK, linewidth=0.4, alpha=0.4, linestyle=(0, (4, 3)), zorder=2)

        # Legend, top left
        handles = [Rectangle((0, 0), 1, 1, facecolor=fill, edgecolor=outline, linewidth=1.2)
                   for _, fill, outline in legend]
        if handles:
            map_legend = axes.legend(handles, [name for name, _, _ in legend], loc="upper left",
                                     frameon=True, fancybox=True, framealpha=0.94, edgecolor=GRID, borderpad=0.7,
                                     handlelength=1.6, handleheight=1.0, prop={"family": FONT_FAMILY, "size": 7.5},
                                     title="Legend")
            title = map_legend.get_title()
            title.set_fontfamily(FONT_FAMILY)
            title.set_fontsize(8)
            title.set_fontweight("semibold")
            title.set_color(INK)
            map_legend._legend_box.align = "left"
            map_legend.set_zorder(6)

        # North arrow, top right: a split arrowhead with N above it
        x, y, size = 0.94, 0.86, 0.045
        aspect = (COVER_MAP[2] * PAGE_SIZE[0]) / (COVER_MAP[3] * PAGE_SIZE[1])
        half = size * 0.42 / aspect
        for points, colour in (([(x - half, y), (x, y + size), (x, y + size * 0.3)], MAP_INK),
                               ([(x + half, y), (x, y + size), (x, y + size * 0.3)], "#ffffff")):
            axes.add_patch(Polygon(points, closed=True, transform=axes.transAxes, facecolor=colour, edgecolor=MAP_INK,
                                   linewidth=0.8, zorder=7))
        axes.text(x, y + size + 0.008, "N", transform=axes.transAxes, ha="center", va="bottom", fontsize=10,
                  fontweight="bold", color=MAP_INK, fontfamily=FONT_FAMILY, zorder=7,
                  bbox=dict(boxstyle="circle,pad=0.15", facecolor="#ffffff", edgecolor="none", alpha=0.8))

        # Scale bar, bottom left: ground distance at the map centre (Web Mercator stretches with latitude)
        stretch = math.cos(math.radians(_latitude((ymin + ymax) / 2)))
        width_km = (xmax - xmin) * stretch / 1000
        length = max([step for step in SCALE_STEPS if step <= width_km / 4] or [SCALE_STEPS[0]])
        bar = length * 1000 / stretch
        x0 = xmin + (xmax - xmin) * 0.04
        y0 = ymin + (ymax - ymin) * 0.045
        height = (ymax - ymin) * 0.009
        axes.add_patch(Rectangle((x0 - (xmax - xmin) * 0.015, y0 - (ymax - ymin) * 0.018),
                                 bar + (xmax - xmin) * 0.075, (ymax - ymin) * 0.06, facecolor="#ffffff",
                                 edgecolor=GRID, alpha=0.9, zorder=6))
        for part in range(4):
            axes.add_patch(Rectangle((x0 + part * bar / 4, y0), bar / 4, height, zorder=7, linewidth=0.7,
                                     facecolor=MAP_INK if part % 2 == 0 else "#ffffff", edgecolor=MAP_INK))
        unit = "km" if length >= 1 else "m"
        for fraction, value in ((0, 0), (0.5, length / 2), (1, length)):
            shown = value if unit == "km" else value * 1000
            text = f"{shown:g}" + (f" {unit}" if fraction == 1 else "")
            axes.text(x0 + bar * fraction, y0 + height * 1.6, text, ha="center", va="bottom", fontsize=7,
                      color=MAP_INK, fontfamily=FONT_FAMILY, zorder=7)

        if overview:
            inset = figure.add_axes(_overview_rect())
            inset.imshow(imread(overview[0]), interpolation="lanczos")
            inset.set_xticks([])
            inset.set_yticks([])
            inset.set_zorder(8)
            for spine in inset.spines.values():
                spine.set_edgecolor(MAP_INK)
                spine.set_linewidth(0.8)
            inset.text(0.04, 0.97, STATE_LABEL, transform=inset.transAxes, ha="left", va="top", fontsize=6.5,
                       color=INK_SECONDARY, fontfamily=FONT_FAMILY)

    def cover_page(self, title: str, subtitle: str, tiles: Sequence[KeyFigure], local: Optional[MapImage] = None,
                   overview: Optional[MapImage] = None, legend: Sequence[LegendEntry] = ()):
        figure = self._page_figure()
        figure.add_artist(Line2D([LEFT, LEFT], [0.6, 0.86], color=ACCENT, linewidth=5, transform=figure.transFigure))
        _text(figure, LEFT + 0.018, 0.86, "CenGeo BW", 11, ACCENT, "semibold", va="top")
        _text(figure, LEFT + 0.018, 0.815, textwrap.fill(title, 26), 28, INK, "bold", va="top", linespacing=1.15)
        _text(figure, LEFT + 0.018, 0.64, textwrap.fill(subtitle, 48), 13, INK_SECONDARY, va="top")
        _text(figure, LEFT + 0.018, 0.575, f"Created {datetime.date.today():%d.%m.%Y}", 9, MUTED, va="top")
        tile_w, tile_h, gap = 0.138, 0.135, 0.012
        for index, item in enumerate(list(tiles)[:6]):
            row, column = divmod(index, 3)
            self._tile(figure, LEFT + column * (tile_w + gap), 0.36 - row * (tile_h + gap), tile_w, tile_h, item)
        if local:
            self._cover_map(figure, local, overview, legend)
        self._save(figure)

    def glance_page(self, title: str, subtitle: str, columns: Sequence[str],
                    rows: Sequence[Tuple[str, str, Sequence[KeyFigure]]]):
        """One row per chart: title, value name and the key figure of every area in columns."""
        for start in range(0, max(len(rows), 1), GLANCE_ROWS_PER_PAGE):
            chunk = rows[start:start + GLANCE_ROWS_PER_PAGE]
            figure = self._page_figure(title, subtitle)
            cell_left, cell_width = 0.45, (RIGHT - 0.45) / max(len(columns), 1)
            for index, name in enumerate(columns):
                _text(figure, cell_left + index * cell_width, CONTENT_TOP - 0.005, name, 9, MUTED, "semibold", va="top")
            y = CONTENT_TOP - 0.05
            row_height = (CONTENT_TOP - 0.05 - CONTENT_BOTTOM) / GLANCE_ROWS_PER_PAGE
            for chart_title, value_label, figures in chunk:
                _text(figure, LEFT, y - 0.006, textwrap.fill(chart_title, 52), 10.5, INK, "semibold", va="top")
                _text(figure, LEFT, y - 0.034 - 0.018 * chart_title.count("\n"), value_label, 8.5, MUTED, va="top")
                for index, item in enumerate(figures):
                    x = cell_left + index * cell_width
                    _text(figure, x, y - 0.004, item.value, 13.5, INK, "semibold", va="top")
                    self._change_line(figure, x, y - 0.058, item, 8.5)
                y -= row_height
                figure.add_artist(Line2D([LEFT, RIGHT], [y + 0.012, y + 0.012], color=GRID, linewidth=0.7,
                                         transform=figure.transFigure))
            self._save(figure)

    def chart_page(self, title: str, subtitle: str, draw: DrawCallback, figures: Sequence[KeyFigure] = (),
                   figures_title: str = "Key figures", image_name: Optional[str] = None):
        figure = self._page_figure(title, subtitle)
        right = FIGURES_LEFT - 0.05 if figures else RIGHT
        region = (LEFT, CONTENT_BOTTOM, right - LEFT, CONTENT_TOP - 0.035 - CONTENT_BOTTOM)
        handle = draw(figure, region)
        if figures:
            self._key_figures(figure, figures, figures_title)
        render_static(figure, handle if hasattr(handle, "kind") else None)
        self._save(figure)
        self._save_image(figure, image_name)

    def about_page(self, sections: Sequence[Tuple[str, str]]):
        figure = self._page_figure("About the data", "Sources, licences and how to read this report")
        y = CONTENT_TOP - 0.01
        for heading, text in sections:
            _text(figure, LEFT, y, heading, 11, INK, "semibold", va="top")
            wrapped, lines = _lines(text, 150)
            _text(figure, LEFT, y - 0.035, wrapped, 9.5, INK_SECONDARY, va="top", linespacing=1.45)
            y -= 0.07 + 0.026 * lines
        self._save(figure)


__all__ = ["PdfReport", "safe_file_name", "map_sizes", "DrawCallback", "MapImage", "LegendEntry"]
