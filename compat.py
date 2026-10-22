# -*- coding: utf-8 -*-
"""The few imports that differ between QGIS 3 (Qt5) and QGIS 4 (Qt6).

Everything else imports Qt through qgis.PyQt and uses fully scoped enums
(e.g. Qt.Orientation.Horizontal), which work on both.
"""

try:
    from qgis.PyQt.QtGui import QAction  # Qt6
except ImportError:
    from qgis.PyQt.QtWidgets import QAction  # Qt5


def figure_canvas_class():
    """matplotlib's Qt canvas; imported lazily so the plugin still loads when matplotlib is missing."""
    try:
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # matplotlib >= 3.5, Qt5 and Qt6
    except ImportError:
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    return FigureCanvasQTAgg


__all__ = ["QAction", "figure_canvas_class"]
