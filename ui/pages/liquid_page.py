from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QStackedWidget
from PySide6.QtCore import Signal, Qt
from ..components.widgets import ClickableLabel
from ..styles import get_function_bar_style, get_function_bar_label_style, get_function_bar_button_style, FONT_SIZE_XLARGE, FONT_SIZE_TITLE, SPACING_XLARGE, SPACING_ENORMOUS, SPACING_MEDIUM, get_subtitle_label_style
from services import ServiceContainer

class LiquidPage(QWidget):
    back_clicked = Signal()
    books_clicked = Signal()
    holdings_clicked = Signal()
    performance_clicked = Signal()

    def __init__(self, *, services: ServiceContainer):
        super().__init__()
        self._services = services
        self.setStyleSheet(get_function_bar_style())
        self.books_page = None
        self.performance_page = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addSpacing(SPACING_XLARGE)
        back_bar = QWidget()
        back_bar_layout = QGridLayout(back_bar)
        back_bar_layout.setContentsMargins(10, 0, 10, 0)
        back_bar_layout.setHorizontalSpacing(15)
        back_bar_layout.setColumnStretch(1, 1)
        back_bar_layout.setColumnStretch(2, 1)
        self.btn_back = ClickableLabel("<back>", is_accent=True, font_size=FONT_SIZE_XLARGE)
        self.btn_back.clicked.connect(self.back_clicked.emit)
        back_bar_layout.addWidget(self.btn_back, 0, 0, alignment=Qt.AlignTop | Qt.AlignLeft)
        self.global_equities_label = QLabel("GLOBAL MARKETS")
        self.global_equities_label.setAlignment(Qt.AlignCenter)
        self.global_equities_label.setStyleSheet(get_subtitle_label_style(FONT_SIZE_TITLE))
        back_bar_layout.addWidget(self.global_equities_label, 0, 0, 1, 3, alignment=Qt.AlignCenter)
        layout.addWidget(back_bar)
        layout.addSpacing(SPACING_ENORMOUS)
        function_bar = QWidget()
        function_bar.setObjectName("FunctionBar")
        function_bar_layout = QHBoxLayout(function_bar)
        function_bar_layout.setContentsMargins(10, 0, 10, 0)
        function_bar_layout.setSpacing(15)
        button_style = get_function_bar_button_style()
        for text, is_accent, handler in [("<holdings>", True, self._on_holdings_clicked), ("<books>", False, self._on_books_clicked), ("<performance>", False, self._on_performance_clicked)]:
            btn = ClickableLabel(text, is_accent=is_accent, font_size=FONT_SIZE_XLARGE)
            btn.setStyleSheet(button_style)
            btn.clicked.connect(handler)
            function_bar_layout.addWidget(btn, alignment=Qt.AlignVCenter | Qt.AlignLeft)
            function_bar_layout.addSpacing(SPACING_MEDIUM)
        function_bar_layout.addStretch()
        self.function_bar_label = QLabel("")
        self.function_bar_label.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self.function_bar_label.setStyleSheet(get_function_bar_label_style())
        function_bar_layout.addWidget(self.function_bar_label, alignment=Qt.AlignVCenter | Qt.AlignRight)
        layout.addWidget(function_bar)
        self.content_stack = QStackedWidget()
        from .holdings_page import HoldingsPage
        self.holdings_page = HoldingsPage(services=services)
        self.content_stack.addWidget(self.holdings_page)
        self.content_stack.setCurrentIndex(0)
        self._set_function_bar_from_page(self.holdings_page)
        layout.addWidget(self.content_stack, 1)

    def _on_holdings_clicked(self):
        self._switch_to_page(self.holdings_page, self.holdings_clicked)

    def _on_books_clicked(self):
        if self.books_page is None:
            from .books_page import BooksPage
            self.books_page = BooksPage(services=self._services)
            self.books_page.ledger_changed.connect(self._on_ledger_changed)
            self.content_stack.addWidget(self.books_page)
        self._switch_to_page(self.books_page, self.books_clicked)

    def _on_performance_clicked(self):
        if self.performance_page is None:
            from .performance_page import PerformancePage
            self.performance_page = PerformancePage(services=self._services)
            self.content_stack.addWidget(self.performance_page)
        self._switch_to_page(self.performance_page, self.performance_clicked)

    def _on_ledger_changed(self):
        self.holdings_page.refresh()
        if self.performance_page is not None:
            self.performance_page.refresh()

    def _switch_to_page(self, page, signal):
        self.content_stack.setCurrentWidget(page)
        self._set_function_bar_from_page(page)
        signal.emit()

    def _set_function_bar_from_page(self, page):
        self.function_bar_label.setText(getattr(page, "function_bar_title", ""))
