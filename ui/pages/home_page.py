from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Signal
from ..components.widgets import ClickableLabel
from ..styles import FONT_SIZE_TITLE, FONT_SIZE_ENORMOUS, SPACING_SMALL, SPACING_HUGE, SPACING_TITLE_LARGE, get_title_label_style, get_subtitle_label_style

class HomePage(QWidget):
    liquid_clicked = Signal()
    illiquid_clicked = Signal()
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 60, 50, 50)
        layout.setSpacing(SPACING_SMALL)
        title = QLabel("PORTFOLIO TERMINAL")
        title.setStyleSheet(get_title_label_style(FONT_SIZE_ENORMOUS))
        layout.addWidget(title)
        subtitle = QLabel("Ailefroide")
        subtitle.setStyleSheet(f"{get_subtitle_label_style()}; margin-left: 1px;")
        layout.addWidget(subtitle)
        layout.addSpacing(SPACING_HUGE + SPACING_TITLE_LARGE)
        menu = QHBoxLayout()
        menu.setSpacing(75)
        menu.addStretch()
        for text, signal in [("<liquid>", self.liquid_clicked), ("<illiquid>", self.illiquid_clicked)]:
            btn = ClickableLabel(text, is_accent=True, font_size=FONT_SIZE_TITLE)
            btn.clicked.connect(signal.emit)
            menu.addWidget(btn)
        menu.addStretch()
        layout.addLayout(menu)
        layout.addStretch()
