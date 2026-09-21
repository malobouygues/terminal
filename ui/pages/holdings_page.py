import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QStackedWidget
from PySide6.QtCore import Qt, QTimer
from ..styles import (
    COLOR_BLACK, COLOR_TABLE_TEXT, COLOR_GRAY_LIGHT, FONT_SIZE_NORMAL,
    PADDING_XS, SPACING_LARGE, SPACING_XS,
    TABLE_COLUMN_EMPTY_WIDTH, WIDGET_HEIGHT_HEADER, WIDGET_HEIGHT_SEPARATOR,
    get_label_style,
)
from ..components.widgets import BloombergTableView, TableBorderDelegate, TabButton, RatioHeaderView, create_separator_line
from ..components.charts import PieChartWidget
from ..models import HoldingsModel, AllocationModel, AllocationRow, build_holdings_rows, cash_row
from services import ServiceContainer

logger = logging.getLogger(__name__)

_HOLDINGS_FIXED = {0: TABLE_COLUMN_EMPTY_WIDTH, 8: TABLE_COLUMN_EMPTY_WIDTH}
_HOLDINGS_RATIOS = {1: 2.6, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0, 7: 1.0}
_ALLOCATION_FIXED = {0: TABLE_COLUMN_EMPTY_WIDTH, 4: TABLE_COLUMN_EMPTY_WIDTH}
_ALLOCATION_RATIOS = {1: 2.6, 2: 1.0, 3: 1.0}
LIVE_REFRESH_MS = 5 * 60 * 1000


def _make_table(model, fixed, ratios, width_provider, border_columns=None, top_border=True) -> BloombergTableView:
    table = BloombergTableView(model, empty_column_widths=fixed)
    header = RatioHeaderView(Qt.Horizontal, table, fixed_widths=fixed, column_ratios=ratios,
                             width_provider=width_provider, border_color=COLOR_BLACK,
                             border_column_count=model.columnCount(), top_border=top_border)
    table.setHorizontalHeader(header)
    QTimer.singleShot(0, header._update_column_widths)
    table.setItemDelegate(TableBorderDelegate(border_column_count=border_columns or model.columnCount() - 1,
                                              text_color_fallback=COLOR_TABLE_TEXT))
    return table


class HoldingsPage(QWidget):
    def __init__(self, *, services: ServiceContainer):
        super().__init__()
        self._services = services
        self.function_bar_title = "HOLDINGS"
        self.live_model = HoldingsModel(closed=False)
        self.hist_model = HoldingsModel(closed=True)
        self.allocation_model = AllocationModel()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 25, 0, 15)
        layout.setSpacing(0)
        tabs_container = QWidget()
        tabs_layout = QHBoxLayout(tabs_container)
        tabs_layout.setContentsMargins(10, 0, 10, 0)
        tabs_layout.setSpacing(SPACING_XS)
        self.tabs = [TabButton(text, is_active=i == 0) for i, text in enumerate(["Main View", "Allocation"])]
        for i, tab in enumerate(self.tabs):
            tab.clicked.connect(lambda idx=i: self._switch_tab(idx))
            tabs_layout.addWidget(tab)
        tabs_layout.addStretch()
        self.last_update_label = QLabel("")
        self.last_update_label.setStyleSheet(get_label_style(COLOR_GRAY_LIGHT, FONT_SIZE_NORMAL))
        tabs_layout.addWidget(self.last_update_label, alignment=Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(tabs_container)
        line_container = QWidget()
        line_container.setFixedHeight(WIDGET_HEIGHT_SEPARATOR)
        line_layout = QHBoxLayout(line_container)
        line_layout.setContentsMargins(10 - PADDING_XS, 0, 10 - PADDING_XS, 0)
        line_layout.addWidget(create_separator_line())
        layout.addWidget(line_container)
        layout.addSpacing(SPACING_LARGE)

        self.content_stack = QStackedWidget()
        # --- Main View : LIVE (lots actifs) puis HISTORIQUE (lots clôturés), séparés d'une ligne
        main_view = QWidget()
        main_layout = QVBoxLayout(main_view)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.live_table = _make_table(self.live_model, _HOLDINGS_FIXED, _HOLDINGS_RATIOS, self.width)
        self.live_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        main_layout.addWidget(self.live_table)
        main_layout.addWidget(create_separator_line())
        # Historique : bandeau noir "Last Sell", colonnes jusqu'à "Last" (Rlzd PnL) incluse
        self.hist_table = _make_table(self.hist_model, _HOLDINGS_FIXED, _HOLDINGS_RATIOS, self.width,
                                      border_columns=5, top_border=False)
        self.hist_table.horizontalHeader().setStyleSheet(
            f"QHeaderView::section {{ background-color: {COLOR_BLACK}; color: {COLOR_GRAY_LIGHT}; border-top: none; }}")
        main_layout.addWidget(self.hist_table, 1)
        self.content_stack.addWidget(main_view)

        # --- Allocation : table + camembert
        allocation_view = QWidget()
        allocation_layout = QHBoxLayout(allocation_view)
        allocation_layout.setContentsMargins(0, 0, 0, 0)
        allocation_layout.setSpacing(0)
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        self.allocation_table = _make_table(self.allocation_model, _ALLOCATION_FIXED, _ALLOCATION_RATIOS, table_container.width)
        table_layout.addWidget(self.allocation_table)
        self.pie_chart = PieChartWidget()
        self.pie_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        allocation_layout.addWidget(table_container, 1)
        allocation_layout.addWidget(self.pie_chart, 1)
        self.content_stack.addWidget(allocation_view)
        self.content_stack.setCurrentIndex(0)
        layout.addWidget(self.content_stack, 1)

        self.allocation_model.modelReset.connect(self._sync_pie_chart)
        self.live_model.modelReset.connect(self._fit_live_table)
        self._fit_live_table()
        self._timer = QTimer(self)
        self._timer.timeout.connect(lambda: asyncio.create_task(self._refresh_live()))
        self._timer.start(LIVE_REFRESH_MS)
        asyncio.create_task(self._load())

    async def _load(self) -> None:
        """Charge le snapshot (holdings + allocation) hors thread UI."""
        try:
            holdings, cash, allocation, updated = await asyncio.gather(
                self._services.portfolio.holdings_snapshot(),
                self._services.portfolio.cash(),
                self._services.portfolio.allocation(),
                self._services.market.last_update(),
            )
        except Exception:
            logger.exception("Failed to load portfolio snapshot")
            return
        self.live_model.set_rows(build_holdings_rows(holdings, closed=False)
                                 + [cash_row(ccy, usd) for ccy, _, usd in cash])
        self.hist_model.set_rows(build_holdings_rows(holdings, closed=True))
        self.allocation_model.set_rows([AllocationRow(name, pct, mv) for name, pct, mv in allocation])
        self._set_last_update(updated)

    async def _refresh_live(self) -> None:
        try:
            await self._services.market.refresh_live()
        except Exception:
            logger.exception("Live refresh failed")
        await self._load()

    def refresh(self) -> None:
        asyncio.create_task(self._load())

    def _set_last_update(self, updated: datetime | None) -> None:
        if updated is None:
            self.last_update_label.setText("last update : n/a")
            return
        paris = updated.astimezone(ZoneInfo("Europe/Paris"))
        self.last_update_label.setText(f"last update : {paris:%Y-%m-%d %H:%M} Paris")

    def _fit_live_table(self, *_) -> None:
        """La table LIVE épouse son contenu ; l'HISTORIQUE prend le reste (scrollable)."""
        table = self.live_table
        table.setFixedHeight(WIDGET_HEIGHT_HEADER + table.verticalHeader().length() + 2 * table.frameWidth())

    def _sync_pie_chart(self, *_) -> None:
        self.pie_chart.set_data([(row.name, row.percentage) for row in self.allocation_model.rows()])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for tbl in (self.live_table, self.hist_table, self.allocation_table):
            tbl.horizontalHeader()._update_column_widths()

    def _switch_tab(self, tab_index):
        for i, tab in enumerate(self.tabs):
            tab.set_active(i == tab_index)
        self.content_stack.setCurrentIndex(tab_index)
