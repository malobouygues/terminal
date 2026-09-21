from PySide6.QtWidgets import QLabel

from ...styles import COLOR_WHITE, FONT_SIZE_MEDIUM
from .frameless_dialog import FramelessDialog


class OrderDialog(FramelessDialog):
    """Confirmation d'ordre : affiche le message + Cancel / OK."""

    def __init__(self, order_message: str, parent=None):
        super().__init__(parent, size=(420, 180))
        self.setWindowTitle("Order Message")
        self.content_layout.setContentsMargins(20, 24, 20, 0)
        self.content_layout.setSpacing(12)

        title = QLabel("Order Message:")
        title.setStyleSheet(f"color: {COLOR_WHITE}; font-size: {FONT_SIZE_MEDIUM}pt;")
        self.content_layout.addWidget(title)
        msg_label = QLabel(order_message)
        msg_label.setStyleSheet(f"color: {COLOR_WHITE}; font-size: {FONT_SIZE_MEDIUM}pt;")
        msg_label.setWordWrap(True)
        self.content_layout.addWidget(msg_label)
        self.content_layout.addStretch()

        self.add_buttons_row(
            [
                self.make_button("Cancel", self.reject),
                self.make_button("OK", self.accept),
            ],
            top_margin=8,
        )
