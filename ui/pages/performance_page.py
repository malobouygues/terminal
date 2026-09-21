import asyncio
import logging
from datetime import date, timedelta

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
from ..styles import (
    COLOR_WHITE, FONT_SIZE_MEDIUM, PADDING_XS, SPACING_LARGE, SPACING_XS, WIDGET_HEIGHT_SEPARATOR,
    get_label_style,
)
from ..components.widgets import TabButton, create_separator_line
from ..components.charts import LineChartWidget
from services import ServiceContainer

logger = logging.getLogger(__name__)

PERIODS = ("All-time", "5Y", "1Y", "YTD", "6M", "3M", "1M")
_PERIOD_DAYS = {"5Y": 5 * 365, "1Y": 365, "6M": 182, "3M": 91, "1M": 30}
METRICS = ("Value", "Performance")


class PerformancePage(QWidget):
    """Value = NAV USD ; Performance = TWR rebasé à 0 au début de la période — YTD et Performance par défaut."""

    def __init__(self, *, services: ServiceContainer):
        super().__init__()
        self._services = services
        self.function_bar_title = "PERFORMANCE"
        self._series: list[dict] = []
        self._period, self._metric = "YTD", "Performance"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 25, 0, 15)
        layout.setSpacing(0)
        bar = QWidget()
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(10, 0, 10, 0)
        bar_layout.setSpacing(SPACING_XS)
        self.period_tabs = {p: TabButton(p, is_active=p == self._period) for p in PERIODS}
        for period, tab in self.period_tabs.items():
            tab.clicked.connect(lambda p=period: self._select(period=p))
            bar_layout.addWidget(tab)
        bar_layout.addStretch()
        self.value_label = QLabel("")
        self.value_label.setStyleSheet(get_label_style(COLOR_WHITE, FONT_SIZE_MEDIUM))
        bar_layout.addWidget(self.value_label, alignment=Qt.AlignVCenter)
        bar_layout.addSpacing(SPACING_LARGE)
        self.metric_tabs = {m: TabButton(m, is_active=m == self._metric) for m in METRICS}
        for metric, tab in self.metric_tabs.items():
            tab.clicked.connect(lambda m=metric: self._select(metric=m))
            bar_layout.addWidget(tab)
        layout.addWidget(bar)
        line_container = QWidget()
        line_container.setFixedHeight(WIDGET_HEIGHT_SEPARATOR)
        line_layout = QHBoxLayout(line_container)
        line_layout.setContentsMargins(10 - PADDING_XS, 0, 10 - PADDING_XS, 0)
        line_layout.addWidget(create_separator_line())
        layout.addWidget(line_container)
        layout.addSpacing(SPACING_LARGE)
        self.chart = LineChartWidget()
        layout.addWidget(self.chart, 1)
        asyncio.create_task(self._load())

    async def _load(self) -> None:
        try:
            self._series = await self._services.portfolio.performance()
        except Exception:
            logger.exception("Failed to load performance series")
            return
        self._apply()

    def refresh(self) -> None:
        asyncio.create_task(self._load())

    def _select(self, period: str | None = None, metric: str | None = None) -> None:
        self._period, self._metric = period or self._period, metric or self._metric
        for p, tab in self.period_tabs.items():
            tab.set_active(p == self._period)
        for m, tab in self.metric_tabs.items():
            tab.set_active(m == self._metric)
        self._apply()

    def _start_date(self, last: str) -> str:
        if self._period == "All-time":
            return ""
        if self._period == "YTD":
            return f"{last[:4]}-01-01"
        return (date.fromisoformat(last) - timedelta(days=_PERIOD_DAYS[self._period])).isoformat()

    def _apply(self) -> None:
        if not self._series:
            self.chart.set_series([], [], lambda v: "")
            self.value_label.setText("")
            return
        start = self._start_date(self._series[-1]["date"])
        before = [p for p in self._series if p["date"] < start]
        points = ([before[-1]] if before else []) + [p for p in self._series if p["date"] >= start]
        dates = [p["date"] for p in points]
        if self._metric == "Performance":
            base = 1 + points[0]["twr_cumul"]
            values = [((1 + p["twr_cumul"]) / base - 1) * 100 for p in points]
            fmt = lambda v: f"{v:+.1f}%"
        else:
            values = [p["nav_usd"] for p in points]
            fmt = lambda v: f"{v:,.0f}"
        self.chart.set_series(dates, values, fmt)
        self.value_label.setText(f"{self._metric} {self._period}  {fmt(values[-1])}" + ("" if self._metric == "Performance" else " USD"))
