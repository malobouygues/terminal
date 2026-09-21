from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Signal
from ..components.widgets import ClickableLabel

class TemplatePage(QWidget):
    back_clicked = Signal()
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 50)
        btn_back = ClickableLabel("<back>", is_accent=True, font_size=10)
        btn_back.clicked.connect(self.back_clicked.emit)
        layout.addWidget(btn_back)
        layout.addWidget(QLabel("Contenu de la page"))
