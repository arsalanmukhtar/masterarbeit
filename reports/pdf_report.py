# -*- coding: utf-8 -*-
"""Multi-page A4 PDF reports made of title, map, table and chart pages."""
from __future__ import annotations

import datetime
import os
import re
import textwrap
from typing import Optional, Sequence

from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.image import imread
from matplotlib.lines import Line2D

from ..charts.plotting import (AXIS, FONT_FAMILY, GRID, INK, INK_SECONDARY, MUTED, SERIES_COLORS, SURFACE, chart_kind,
                               draw_chart, draw_small_multiples, format_number, render_static, reserve_margins)
from ..core.models import Series

PAGE_SIZE = (11.69, 8.27)  # A4 landscape, inches
ROWS_PER_PAGE = 30
TITLE_SPACE = 0.12   # share of the page height kept for the page title
FOOTER_SPACE = 0.04  # share kept for the credit line


def safe_file_name(name: str) -> str:
    # Gemeinde names such as Lahr/Schwarzwald contain characters that are not allowed in file names
    return re.sub(r'[<>:"/\\|?*]', "-", name).strip()


def _text(figure, x, y, text, size=9, color=INK, weight="normal", **kwargs):
    return figure.text(x, y, text, fontsize=size, color=color, fontweight=weight, fontfamily=FONT_FAMILY, **kwargs)


class PdfReport:
    def __init__(self, pdf_path: str, image_dir: Optional[str] = None, credits: Sequence[str] = ()):
        self.pdf_path = pdf_path
        self.image_dir = image_dir
        self.credits = credits
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

    def _page_figure(self, title: str = "", subtitle: str = "") -> Figure:
        figure = Figure(figsize=PAGE_SIZE)
        figure.set_facecolor(SURFACE)
        if title:
            _text(figure, 0.04, 0.955, textwrap.fill(title, 110), size=14, weight="semibold", va="top")
        if subtitle:
            _text(figure, 0.04, 0.905, textwrap.fill(subtitle, 150), size=9.5, color=MUTED, va="top")
        return figure

    def _save(self, figure: Figure):
        self._page += 1
        _text(figure, 0.96, 0.018, str(self._page), size=7.5, color=MUTED, ha="right", va="bottom")
        if self.credits:
            _text(figure, 0.04, 0.018, " · ".join(self.credits), size=6.5, color=MUTED, ha="left", va="bottom")
        self._pdf.savefig(figure, facecolor=figure.get_facecolor())

    def title_page(self, title: str, subtitle: str = ""):
        figure = self._page_figure()
        figure.add_artist(Line2D([0.08, 0.08], [0.42, 0.62], color=SERIES_COLORS[0], linewidth=4,
                                 transform=figure.transFigure))
        _text(figure, 0.1, 0.6, "CenGeo BW", size=11, color=SERIES_COLORS[0], weight="semibold", va="top")
        _text(figure, 0.1, 0.555, textwrap.fill(title, 55), size=26, weight="bold", va="top")
        if subtitle:
            _text(figure, 0.1, 0.455, subtitle, size=13, color=INK_SECONDARY, va="top")
        _text(figure, 0.1, 0.25, f"Created {datetime.date.today():%d.%m.%Y}", size=9, color=MUTED)
        self._save(figure)

    def image_page(self, title: str, image_path: str, subtitle: str = ""):
        figure = self._page_figure(title, subtitle)
        axes = figure.add_axes([0.04, 0.07, 0.92, 0.8])
        axes.imshow(imread(image_path))
        axes.axis("off")
        self._save(figure)

    def table_pages(self, title: str, headers: Sequence[str], rows: Sequence[Sequence], subtitle: str = "",
                    label_columns: int = 1):
        """The data as tables split across pages. The first label_columns (year, age, ...) are printed as
        they are; in value columns zero is shown as "-" like the printed statistics."""
        def cell(index, value):
            if index < label_columns or not isinstance(value, (int, float)):
                return "" if value is None else str(value)
            return "-" if value == 0 else format_number(value)

        cells = [[cell(index, value) for index, value in enumerate(row)] for row in rows]
        headers = [textwrap.fill(header, 20) for header in headers]
        pages = max(1, -(-len(cells) // ROWS_PER_PAGE))
        # Spread rows evenly, so 31 rows become 16 and 15 rather than 30 and a lone row
        per_page = max(1, -(-len(cells) // pages))
        for page in range(pages):
            chunk = cells[page * per_page:(page + 1) * per_page]
            suffix = f" ({page + 1} of {pages})" if pages > 1 else ""
            figure = self._page_figure(title + suffix, subtitle)
            axes = figure.add_axes([0.04, 0.08, 0.92, 0.78])
            axes.axis("off")
            if not chunk:
                axes.text(0.5, 0.5, "No data", ha="center", va="center", fontfamily=FONT_FAMILY, color=MUTED)
                self._save(figure)
                return
            # Right-aligned so the digits of every column line up
            table = axes.table(cellText=chunk, colLabels=headers, cellLoc="right", colLoc="right", loc="upper center")
            table.auto_set_font_size(False)
            table.set_fontsize(8.5)
            for (row, _), cell_artist in table.get_celld().items():
                cell_artist.visible_edges = "B"
                cell_artist.set_height(0.032 if row else 0.075)
                if row == 0:
                    cell_artist.set_edgecolor(AXIS)
                    cell_artist.set_facecolor(SURFACE)
                    cell_artist.set_text_props(weight="semibold", family=FONT_FAMILY, color=INK_SECONDARY)
                else:
                    cell_artist.set_edgecolor(GRID)
                    cell_artist.set_facecolor("#f7f7f4" if row % 2 == 0 else SURFACE)
                    cell_artist.set_text_props(family=FONT_FAMILY, color=INK)
            self._save(figure)

    def chart_page(self, title: str, series: Sequence[Series], x_label: str, y_label: str, x_dimension: str,
                   subtitle: str = "", baseline: Optional[float] = None, image_name: Optional[str] = None):
        figure = self._page_figure(title, subtitle)
        kind = chart_kind(x_dimension, [x for item in series for x in item.x])
        handle = draw_chart(figure, series, x_label, y_label, kind, baseline=baseline, max_x_labels=24)
        reserve_margins(figure, top=TITLE_SPACE, bottom=FOOTER_SPACE)
        render_static(figure, handle)
        self._finish_chart(figure, image_name)

    def multiples_page(self, title: str, panels: Sequence[Series], x_label: str, x_dimension: str,
                       subtitle: str = "", image_name: Optional[str] = None):
        figure = self._page_figure(title, subtitle)
        draw_small_multiples(figure, panels, x_label, x_dimension, columns=3 if len(panels) > 4 else 2)
        reserve_margins(figure, top=TITLE_SPACE, bottom=FOOTER_SPACE)
        render_static(figure)
        self._finish_chart(figure, image_name)

    def _finish_chart(self, figure: Figure, image_name: Optional[str]):
        self._save(figure)
        if self.image_dir and image_name:
            figure.savefig(os.path.join(self.image_dir, safe_file_name(image_name) + ".png"), dpi=200,
                           facecolor=figure.get_facecolor())
