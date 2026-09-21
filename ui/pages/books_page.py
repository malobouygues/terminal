import asyncio
import logging

from PySide6.QtWidgets import QWidget, QLabel, QSizePolicy, QHBoxLayout, QVBoxLayout
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QMouseEvent
from PySide6.QtWidgets import QDialog
from ..styles import (
    COLOR_TEXT_NORMAL, COLOR_BLACK,
    TABLE_COLUMN_EMPTY_WIDTH, WIDGET_HEIGHT_TAB,
    FONT_SIZE_MEDIUM, SPACING_XS, SPACING_XXLARGE, SPACING_LARGE, SPACING_HUGE,
    get_white_label_style,
)
from ..components.widgets import ClickableLabel, BloombergTableView, TableBorderDelegate, RatioHeaderView, create_bottom_bar
from ..components.dialog import DerivativesDialog, DeltaOneDialog, CashDialog, CheckDialog, OrderDialog
from ..models import BooksModel
from services import ServiceContainer

logger = logging.getLogger(__name__)

_BOOKS_FIXED_WIDTHS = {0: TABLE_COLUMN_EMPTY_WIDTH, 1: 76, 11: TABLE_COLUMN_EMPTY_WIDTH}   # col. 1 : ✕ / ✎
_BOOKS_RATIOS = {2: 1.0, 3: 1.0, 4: 1.2, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.2, 9: 1.2, 10: 1.0}
BOOKS_ROW_HEIGHT = 38     # deux lignes : date + heure


class BooksTableView(BloombergTableView):
    def mouseMoveEvent(self, event: QMouseEvent):
        super().mouseMoveEvent(event)
        index = self.indexAt(event.pos())
        action = index.data(BooksModel.ActionRole) if index.isValid() else None
        self.setCursor(QCursor(Qt.PointingHandCursor if action else Qt.ArrowCursor))


class BooksPage(QWidget):
    ledger_changed = Signal()

    def __init__(self, *, services: ServiceContainer):
        super().__init__()
        self._services = services
        self.function_bar_title = "BOOKS"
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.books_model = BooksModel()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, SPACING_XXLARGE, 0, 0)
        root_layout.setSpacing(SPACING_LARGE)
        create_container = QWidget()
        create_layout = QHBoxLayout(create_container)
        create_layout.setContentsMargins(SPACING_XXLARGE, 0, SPACING_XXLARGE, 0)
        create_layout.setSpacing(SPACING_HUGE)
        add_label = QLabel("Add:")
        add_label.setStyleSheet(get_white_label_style(FONT_SIZE_MEDIUM))
        add_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        add_label.setFixedHeight(WIDGET_HEIGHT_TAB)
        create_layout.addWidget(add_label)
        for text, handler in (("Delta-One", lambda: self._open_trade_dialog(DeltaOneDialog)),
                              ("Derivatives", lambda: self._open_trade_dialog(DerivativesDialog))):
            label = ClickableLabel(text, font_size=FONT_SIZE_MEDIUM)
            label.setStyleSheet(get_white_label_style(FONT_SIZE_MEDIUM))
            label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            label.setFixedHeight(WIDGET_HEIGHT_TAB)
            label.clicked.connect(handler)
            create_layout.addWidget(label)
        create_layout.addStretch()
        check_label = ClickableLabel("Check", font_size=FONT_SIZE_MEDIUM)
        check_label.setStyleSheet(get_white_label_style(FONT_SIZE_MEDIUM))
        check_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        check_label.setFixedHeight(WIDGET_HEIGHT_TAB)
        check_label.clicked.connect(self._show_check)
        create_layout.addWidget(check_label)
        root_layout.addWidget(create_container)
        root_layout.addSpacing(SPACING_XS)

        self.table = BooksTableView(self.books_model, empty_column_widths=_BOOKS_FIXED_WIDTHS)
        self.table.setMouseTracking(True)
        self.table.verticalHeader().setDefaultSectionSize(BOOKS_ROW_HEIGHT)
        header = RatioHeaderView(Qt.Horizontal, self.table, fixed_widths=_BOOKS_FIXED_WIDTHS,
                                 column_ratios=_BOOKS_RATIOS, width_provider=self.width,
                                 border_color=COLOR_BLACK, border_column_count=11)
        self.table.setHorizontalHeader(header)
        QTimer.singleShot(0, header._update_column_widths)
        self.table.setItemDelegate(TableBorderDelegate(border_column_count=11, text_color_fallback=COLOR_TEXT_NORMAL))
        self.table.clicked.connect(self._on_index_clicked)
        root_layout.addWidget(self.table, 1)
        root_layout.addWidget(create_bottom_bar(), 0)
        asyncio.create_task(self._load())

    async def _load(self) -> None:
        try:
            self.books_model.set_entries(await self._services.ledger.list_entries())
        except Exception:
            logger.exception("Failed to load journal entries")

    def refresh(self) -> None:
        asyncio.create_task(self._load())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.table.horizontalHeader()._update_column_widths()

    def _after_dialog(self, dialog) -> None:
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.refresh()
            self.ledger_changed.emit()

    def _open_trade_dialog(self, dialog_cls) -> None:
        self._after_dialog(dialog_cls(self, services=self._services))

    def _show_check(self) -> None:
        CheckDialog(self, services=self._services).exec()

    def _on_index_clicked(self, index) -> None:
        action = index.data(BooksModel.ActionRole) if index.isValid() else None
        if action == BooksModel.OPEN_CASH:
            self._after_dialog(CashDialog(self, ledger=self._services.ledger))
        elif action == "actions":
            entry = index.data(BooksModel.EntryRole)
            x = self.table.viewport().mapFromGlobal(QCursor.pos()).x() - self.table.columnViewportPosition(index.column())
            editable = entry["transaction_type"] in ("DEPOSIT", "WITHDRAWAL", "TRANSFER", "TRADE")
            if editable and x > self.table.columnWidth(index.column()) / 2:
                self._edit_entry(entry)
            else:
                self._delete_entry(entry)

    def _edit_entry(self, entry: dict) -> None:
        if entry["transaction_type"] != "TRADE":
            self._after_dialog(CashDialog(self, ledger=self._services.ledger, entry=entry))
            return
        security = next(ln for ln in entry["lines"] if ln["instrument_conid"])
        dialog_cls = DerivativesDialog if security["instrument_type"] == "DERIVATIVES" else DeltaOneDialog
        self._after_dialog(dialog_cls(self, services=self._services, entry=entry))

    def _delete_entry(self, entry: dict) -> None:
        msg = f"DELETE #{entry['id']}  {entry['date']}  {entry['transaction_type']} ?"
        if OrderDialog(msg, self).exec() != QDialog.DialogCode.Accepted:
            return
        async def _do():
            try:
                await self._services.ledger.delete_entry(entry["id"])
            except Exception:
                logger.exception("Failed to delete entry %s", entry["id"])
                return
            self.refresh()
            self.ledger_changed.emit()
        asyncio.create_task(_do())
