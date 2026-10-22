# -*- coding: utf-8 -*-
"""Multi-page A4 PDF reports made of title, map, table and chart pages."""
from __future__ import annotations

import os
import re
import textwrap
from typing import Optional, Sequence

from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.image import imread

from ..charts.plotting import FONT_FAMILY, draw_bar_chart, format_number, reserve_bottom
from ..core.models import Series

PAGE_SIZE = (11.69, 8.27)  # A4 landscape, inches
ROWS_PER_PAGE = 26


def safe_file_name(name: str) -> str:
    # Gemeinde names such as Lahr/Schwarzwald contain characters that are not allowed in file names
    return re.sub(r'[<>:"/\\|?*]', "-", name).strip()


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

    def _save(self, figure: Figure):
        self._page += 1
        figure.text(0.99, 0.01, str(self._page), ha="right", va="bottom", fontsize=7, color="#777777")
        if self.credits:
            figure.text(0.01, 0.01, " · ".join(self.credits), ha="left", va="bottom", fontsize=6, color="#777777")
        self._pdf.savefig(figure)

    def title_page(self, title: str, subtitle: str = ""):
        figure = Figure(figsize=PAGE_SIZE)
        figure.text(0.5, 0.55, textwrap.fill(title, 60), ha="center", va="center", fontsize=22, fontweight="bold",
                    family=FONT_FAMILY)
        if subtitle:
            figure.text(0.5, 0.42, subtitle, ha="center", va="center", fontsize=12, color="#555555", family=FONT_FAMILY)
        self._save(figure)

    def image_page(self, title: str, image_path: str):
        figure = Figure(figsize=PAGE_SIZE)
        axes = figure.add_axes([0.05, 0.06, 0.9, 0.84])
        axes.imshow(imread(image_path))
        axes.axis("off")
        figure.suptitle(title, fontsize=14, fontweight="bold", family=FONT_FAMILY)
        self._save(figure)

    def table_pages(self, title: str, headers: Sequence[str], rows: Sequence[Sequence], label_columns: int = 1):
        """The data as tables, split across pages. The first label_columns (year, age, ...) are printed as they
        are; in value columns zero is shown as "-" like the printed statistics."""
        def cell(index, value):
            if index < label_columns or not isinstance(value, (int, float)):
                return "" if value is None else str(value)
            return "-" if value == 0 else format_number(value)

        cells = [[cell(index, value) for index, value in enumerate(row)] for row in rows]
        wrapped_headers = [textwrap.fill(header, 18) for header in headers]
        for start in range(0, max(len(cells), 1), ROWS_PER_PAGE):
            chunk = cells[start:start + ROWS_PER_PAGE]
            figure = Figure(figsize=PAGE_SIZE)
            figure.suptitle(textwrap.fill(title, 110), fontsize=12, fontweight="bold", family=FONT_FAMILY)
            axes = figure.add_axes([0.03, 0.06, 0.94, 0.84])
            axes.axis("off")
            if not chunk:
                axes.text(0.5, 0.5, "No data", ha="center", va="center")
                self._save(figure)
                return
            table = axes.table(cellText=chunk, colLabels=wrapped_headers, cellLoc="left", loc="upper center")
            table.auto_set_font_size(False)
            table.set_fontsize(8)
            for (row, _), cell in table.get_celld().items():
                cell.set_edgecolor("none")
                cell.set_height(0.032 if row else 0.07)
                if row == 0:
                    cell.set_text_props(weight="bold", family=FONT_FAMILY)
                else:
                    cell.set_text_props(family=FONT_FAMILY)
                    cell.set_facecolor("#f0f0f0" if row % 2 else "#ffffff")
            self._save(figure)

    def chart_page(self, title: str, series: Sequence[Series], x_label: str, y_label: str,
                   note: Optional[str] = None, image_name: Optional[str] = None):
        figure = Figure(figsize=PAGE_SIZE)
        draw_bar_chart(figure, series, title, x_label, y_label, note)
        reserve_bottom(figure, 0.04)
        self._save(figure)
        if self.image_dir and image_name:
            figure.savefig(os.path.join(self.image_dir, safe_file_name(image_name) + ".png"), dpi=200)
