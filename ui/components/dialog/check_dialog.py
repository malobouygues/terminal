import asyncio
import logging
from datetime import date

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ...styles import COLOR_BLACK, COLOR_TABLE_TEXT, TABLE_COLUMN_EMPTY_WIDTH
from ...components.widgets import BloombergTableView, ResizableHeaderView, TableBorderDelegate
from ...models import GridModel
from services import ServiceContainer
from .dialog_components import create_date_input_small
from .frameless_dialog import FramelessDialog

logger = logging.getLogger(__name__)
_DATE_COL_WIDTH = 150
_COL_WIDTH = 130


class _FixedHeaderView(ResizableHeaderView):
    """Colonnes à largeur fixe : la table défile horizontalement."""

    def _update_column_widths(self):
        for col in range(self.count()):
            self.parent_table.setColumnWidth(col, _DATE_COL_WIDTH if col == 0 else _COL_WIDTH)


class CheckDialog(FramelessDialog):
    """Données brutes journalières du calcul de performance sur une plage de dates : clôtures
    des titres détenus, cash par devise, FX USD. Du plus récent au plus ancien."""

    def __init__(self, parent=None, *, services: ServiceContainer):
        super().__init__(parent, size=(1100, 640), title="Check — daily data")
        self.setWindowTitle("Check")
        self._services = services
        self.model = GridModel()

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(15, 12, 15, 0)
        layout.setSpacing(10)
        dates = QHBoxLayout()
        dates.setSpacing(10)
        dates.addStretch()
        self.start_edit, self.end_edit = create_date_input_small(), create_date_input_small()
        self.start_edit.setDate(QDate(date.today().year, 1, 1))
        for edit in (self.start_edit, self.end_edit):
            edit.setFixedWidth(_DATE_COL_WIDTH)
            edit.setFocusPolicy(Qt.ClickFocus)
            dates.addWidget(edit)
        layout.addLayout(dates)

        self.table = BloombergTableView(self.model, empty_column_widths={0: _DATE_COL_WIDTH})
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.header = _FixedHeaderView(Qt.Horizontal, self.table, border_color=COLOR_BLACK, border_column_count=1)
        self.table.setHorizontalHeader(self.header)
        layout.addWidget(self.table, 1)
        self.content_layout.addWidget(container)
        self.add_buttons_row([self.make_button("Cancel", self.reject)], top_margin=10)

        self.model.modelReset.connect(self._fit_columns)
        for edit in (self.start_edit, self.end_edit):
            edit.dateChanged.connect(lambda _: asyncio.create_task(self._load()))
        asyncio.create_task(self._load())

    async def _load(self) -> None:
        start, end = self.start_edit.date().toString("yyyy-MM-dd"), self.end_edit.date().toString("yyyy-MM-dd")
        try:
            headers, rows = await self._services.portfolio.daily_table(start, end)
        except Exception:
            logger.exception("Failed to load daily data")
            return
        self.model.set_data(headers, rows)

    def _fit_columns(self) -> None:
        n = self.model.columnCount()
        self.header._border_column_count = n
        self.table.setItemDelegate(TableBorderDelegate(border_column_count=n, text_color_fallback=COLOR_TABLE_TEXT))
        QTimer.singleShot(0, self.header._update_column_widths)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.header._update_column_widths()
