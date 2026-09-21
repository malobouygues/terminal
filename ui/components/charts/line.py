import math
from typing import Callable

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPolygonF

from ...styles import (
    get_prop_font_name,
    COLOR_TEXT_ACCENT, COLOR_GRAY_LIGHT, COLOR_TABLE_BORDER, COLOR_BLACK, COLOR_WHITE,
    FONT_SIZE_NORMAL,
)

_MARGIN_LEFT, _MARGIN_RIGHT, _MARGIN_TOP, _MARGIN_BOTTOM = 80, 50, 20, 32


def _nice_step(span: float, ticks: int = 5) -> float:
    raw = span / ticks
    exp = math.floor(math.log10(raw))
    frac = raw / 10 ** exp
    nice = 1 if frac < 1.5 else 2 if frac < 3.5 else 5 if frac < 7.5 else 10
    return nice * 10 ** exp


class LineChartWidget(QWidget):
    """Courbe temporelle interactive : échelle adaptée aux données, survol → date et valeur."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._dates: list[str] = []
        self._values: list[float] = []
        self._fmt: Callable[[float], str] = lambda v: f"{v:,.0f}"
        self._hover: int | None = None

    def set_series(self, dates: list[str], values: list[float], fmt: Callable[[float], str]) -> None:
        self._dates, self._values, self._fmt, self._hover = list(dates), list(values), fmt, None
        self.update()

    def _plot_rect(self) -> QRectF:
        return QRectF(_MARGIN_LEFT, _MARGIN_TOP, self.width() - _MARGIN_LEFT - _MARGIN_RIGHT,
                      self.height() - _MARGIN_TOP - _MARGIN_BOTTOM)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setFont(QFont(get_prop_font_name(), FONT_SIZE_NORMAL))
        area = self._plot_rect()
        if len(self._values) < 2:
            painter.setPen(QColor(COLOR_GRAY_LIGHT))
            painter.drawText(area, Qt.AlignCenter, "no data")
            return

        lo, hi = min(self._values), max(self._values)
        step = _nice_step(hi - lo) if hi > lo else 1.0
        lo, hi = math.floor(lo / step) * step, math.ceil(hi / step) * step
        if hi == lo:
            hi = lo + step
        x_of = lambda i: area.left() + area.width() * i / (len(self._values) - 1)
        y_of = lambda v: area.bottom() - area.height() * (v - lo) / (hi - lo)

        painter.setPen(QPen(QColor(COLOR_TABLE_BORDER), 1))
        tick = lo
        while tick <= hi + step / 2:
            y = y_of(tick)
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            painter.setPen(QColor(COLOR_GRAY_LIGHT))
            painter.drawText(QRectF(0, y - 10, _MARGIN_LEFT - 8, 20), Qt.AlignRight | Qt.AlignVCenter, self._fmt(tick))
            painter.setPen(QPen(QColor(COLOR_TABLE_BORDER), 1))
            tick += step
        n_ticks = min(6, len(self._dates))
        for k in range(n_ticks):
            i = round(k * (len(self._dates) - 1) / max(n_ticks - 1, 1))
            painter.setPen(QColor(COLOR_GRAY_LIGHT))
            painter.drawText(QRectF(x_of(i) - 45, area.bottom() + 6, 90, 20), Qt.AlignCenter, self._dates[i])

        painter.setPen(QPen(QColor(COLOR_TEXT_ACCENT), 2))
        painter.drawPolyline(QPolygonF([QPointF(x_of(i), y_of(v)) for i, v in enumerate(self._values)]))

        if self._hover is not None:
            i = self._hover
            x, y = x_of(i), y_of(self._values[i])
            painter.setPen(QPen(QColor(COLOR_GRAY_LIGHT), 1, Qt.DashLine))
            painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
            painter.setPen(QPen(QColor(COLOR_WHITE), 1))
            painter.setBrush(QColor(COLOR_TEXT_ACCENT))
            painter.drawEllipse(QPointF(x, y), 4, 4)
            text = f"{self._dates[i]}   {self._fmt(self._values[i])}"
            box = QRectF(min(x + 10, area.right() - 190), area.top(), 180, 22)
            painter.fillRect(box, QColor(COLOR_BLACK))
            painter.setPen(QColor(COLOR_WHITE))
            painter.drawText(box, Qt.AlignCenter, text)

    def mouseMoveEvent(self, event):
        if len(self._values) < 2:
            return
        area = self._plot_rect()
        ratio = (event.position().x() - area.left()) / max(area.width(), 1)
        self._hover = min(max(round(ratio * (len(self._values) - 1)), 0), len(self._values) - 1)
        self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()
