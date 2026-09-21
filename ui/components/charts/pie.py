import math

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont

from ...styles import (
    get_prop_font_name,
    COLOR_BLACK, COLOR_WHITE, COLOR_TEXT_ACCENT, COLOR_GRAY_LIGHT, COLOR_GRAY_DARK,
    COLOR_BORDEAUX, COLOR_BORDER_HOVER, COLOR_TABLE_HEADER_BG,
    FONT_SIZE_MEDIUM, WIDGET_MIN_HEIGHT_PIE_CHART,
)

_PALETTE = [COLOR_TEXT_ACCENT, COLOR_GRAY_LIGHT, COLOR_GRAY_DARK, COLOR_WHITE,
            COLOR_BORDEAUX, "#B86F1A", COLOR_BORDER_HOVER, COLOR_TABLE_HEADER_BG]
_MAX_LABEL = 16
_LABEL_GAP = 14


class PieChartWidget(QWidget):
    """Camembert : ``set_data([(name, pct), …])`` — première tranche en haut, sens horaire."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(WIDGET_MIN_HEIGHT_PIE_CHART, WIDGET_MIN_HEIGHT_PIE_CHART)
        self._data: list[tuple[str, float]] = []

    def set_data(self, data: list[tuple[str, float]]) -> None:
        self._data = list(data)
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        size = max(min(self.width() - 2 * (_LABEL_GAP + 170), self.height() - 60), 60)   # place pour les libellés
        rect = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)
        center_x, center_y = self.width() / 2, self.height() / 2
        start_angle = 90 * 16
        font = QFont(get_prop_font_name(), FONT_SIZE_MEDIUM)
        font.setBold(True)
        for i, (name, percentage) in enumerate(self._data):
            span_angle = -int(percentage * 360 * 16 / 100)     # négatif = sens horaire
            painter.setBrush(QBrush(QColor(_PALETTE[i % len(_PALETTE)])))
            painter.setPen(QPen(QColor(COLOR_BLACK), 2))
            painter.drawPie(rect, start_angle, span_angle)
            if percentage >= 2:
                mid = math.radians(90 - (start_angle + span_angle / 2) / 16.0)
                edge_x = center_x + (size / 2 + _LABEL_GAP) * math.sin(mid)
                edge_y = center_y - (size / 2 + _LABEL_GAP) * math.cos(mid)
                label = name if len(name) <= _MAX_LABEL else name[:_MAX_LABEL - 1] + "…"
                painter.setPen(QPen(QColor(COLOR_WHITE), 1))
                painter.setFont(font)
                # le bord du texte le plus proche du camembert est à _LABEL_GAP du disque
                if math.sin(mid) > 0.2:
                    painter.drawText(int(edge_x), int(edge_y - 12), 160, 24, Qt.AlignLeft | Qt.AlignVCenter, label)
                elif math.sin(mid) < -0.2:
                    painter.drawText(int(edge_x - 160), int(edge_y - 12), 160, 24, Qt.AlignRight | Qt.AlignVCenter, label)
                else:
                    painter.drawText(int(edge_x - 80), int(edge_y - 12), 160, 24, Qt.AlignCenter, label)
            start_angle += span_angle
