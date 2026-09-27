from typing import Callable

from PySide6.QtWidgets import (
    QHeaderView, QTableView, QStyledItemDelegate, QPushButton, QWidget,
    QLabel, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QAbstractItemModel
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QCursor, QFont
from ..styles import (
    COLOR_BLACK, COLOR_TABLE_BORDER, WIDGET_HEIGHT_HEADER, TABLE_BORDER_WIDTH,
    COLOR_TABLE_TEXT, get_prop_font_name, COLOR_TAB_ACTIVE_BG, COLOR_TAB_INACTIVE_BG,
    COLOR_TAB_ACTIVE_TEXT, COLOR_TAB_INACTIVE_TEXT, COLOR_GRAY_LIGHT, COLOR_GRAY_DARK,
    COLOR_BUTTON_HOVER, COLOR_GRAY_HOVER, FONT_SIZE_MEDIUM, SPACING_LARGE, WIDGET_HEIGHT_TAB,
    COLOR_TEXT_NORMAL, COLOR_TEXT_ACCENT, FONT_SIZE_NORMAL,
    get_table_stylesheet, TABLE_ROW_HEIGHT, WIDGET_HEIGHT_SEPARATOR
)

class ResizableHeaderView(QHeaderView):
    def __init__(self, orientation, parent_table=None, border_color=COLOR_BLACK, border_column_count=None, top_border=True):
        super().__init__(orientation, parent_table)
        self.parent_table = parent_table
        self._border_color = border_color
        self._border_column_count = border_column_count
        self._top_border = top_border
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.setSectionsMovable(False)
        self.setSectionsClickable(False)
        self.setFixedHeight(WIDGET_HEIGHT_HEADER)
    
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, False)
        viewport_width = self.viewport().width()
        viewport_height = self.viewport().height()
        num_columns = self._border_column_count if self._border_column_count is not None else self.count()
        actual_table_width = (self.sectionPosition(num_columns - 1) + self.sectionSize(num_columns - 1)) if num_columns > 0 else viewport_width
        border_start_y = TABLE_BORDER_WIDTH
        painter.setPen(QPen(QColor(self._border_color), 1))
        for col in range(num_columns):
            x = self.sectionPosition(col) + self.sectionSize(col) - 1
            if x < viewport_width:
                painter.drawLine(x, border_start_y, x, viewport_height)
        if self._top_border:
            painter.fillRect(0, 0, actual_table_width, TABLE_BORDER_WIDTH, QColor(COLOR_TABLE_BORDER))
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_column_widths()
    
    def _update_column_widths(self):
        raise NotImplementedError("Subclasses must implement _update_column_widths")


class RatioHeaderView(ResizableHeaderView):
    """Configurable header that lays out columns from ``fixed_widths`` (pixels)
    and ``column_ratios`` (proportional shares of the remaining space).

    ``width_provider`` is called to read the total available width — pages
    typically pass ``self.width`` so the layout adapts to the page, not the
    viewport (which can be 0 during initial layout).
    """

    def __init__(
        self,
        orientation,
        parent_table=None,
        *,
        fixed_widths: dict[int, int],
        column_ratios: dict[int, float],
        width_provider: Callable[[], int],
        border_color=COLOR_BLACK,
        border_column_count: int | None = None,
        top_border: bool = True,
    ):
        super().__init__(
            orientation,
            parent_table=parent_table,
            border_color=border_color,
            border_column_count=border_column_count,
            top_border=top_border,
        )
        self._fixed_widths = dict(fixed_widths)
        self._column_ratios = dict(column_ratios)
        self._width_provider = width_provider

    def _update_column_widths(self):
        tbl = self.parent_table
        if tbl is None:
            return
        provided = int(self._width_provider() or 0)
        total_width = provided if provided > 0 else tbl.viewport().width()
        if total_width <= 0:
            return
        available_width = total_width - sum(self._fixed_widths.values())
        if available_width <= 0:
            return
        for col, width in self._fixed_widths.items():
            tbl.setColumnWidth(col, width)
            self.setSectionResizeMode(col, QHeaderView.Fixed)
        total_ratio = sum(self._column_ratios.values())
        if total_ratio <= 0:
            return
        widths = {col: int((ratio / total_ratio) * available_width) for col, ratio in self._column_ratios.items()}
        # Les écarts d'arrondi et de barre de défilement sont absorbés par la colonne la plus
        # large, la seule dont le contenu tolère quelques pixels de moins.
        widest = max(self._column_ratios, key=self._column_ratios.get)
        diff = available_width - sum(widths.values())
        if diff and widths:
            widths[widest] += diff
        for col, width in widths.items():
            tbl.setColumnWidth(col, width)
            self.setSectionResizeMode(col, QHeaderView.Fixed)
        # Second pass: absorb rounding vs viewport into the last ratio column.
        viewport_width = tbl.viewport().width()
        column_count = tbl.model().columnCount() if tbl.model() else 0
        if column_count and viewport_width > 0:
            actual_total = sum(tbl.columnWidth(i) for i in range(column_count))
            if actual_total != viewport_width:
                tbl.setColumnWidth(widest, tbl.columnWidth(widest) + (viewport_width - actual_total))


class TableBorderDelegate(QStyledItemDelegate):
    """Model-based delegate. Reads background/foreground/text/alignment from the
    model via ``index.data(role)`` — no widget-item lookup required."""

    def __init__(self, border_column_count: int, text_color_fallback=COLOR_TABLE_TEXT):
        super().__init__()
        self.border_column_count = border_column_count
        self.text_color_fallback = text_color_fallback

    @staticmethod
    def _color_from(value) -> QColor | None:
        if value is None:
            return None
        if isinstance(value, QBrush):
            return value.color()
        if isinstance(value, QColor):
            return value
        return QColor(value)

    def paint(self, painter, option, index):
        rect = option.rect
        bg_color = self._color_from(index.data(Qt.BackgroundRole))

        if bg_color is not None and bg_color.alpha() > 0:
            clipped_rect = rect.adjusted(1, 0, -2, 0)
            painter.save()
            painter.setClipRect(clipped_rect)
            painter.fillRect(clipped_rect, bg_color)
            text = index.data(Qt.DisplayRole) or ""
            if text:
                fg_color = self._color_from(index.data(Qt.ForegroundRole))
                if fg_color is None or fg_color.alpha() == 0:
                    fg_color = QColor(self.text_color_fallback)
                painter.setPen(fg_color)
                alignment = index.data(Qt.TextAlignmentRole)
                if alignment is None:
                    alignment = int(Qt.AlignLeft | Qt.AlignVCenter)
                painter.drawText(clipped_rect, int(alignment), str(text))
            painter.restore()
        else:
            super().paint(painter, option, index)

        if index.column() < self.border_column_count:
            painter.setPen(QPen(QColor(COLOR_TABLE_BORDER), 1))
            painter.drawLine(rect.right(), rect.top(), rect.right(), rect.bottom())


class BloombergTableView(QTableView):
    """Model-driven Bloomberg-styled table. Takes a QAbstractItemModel and
    supports partial updates via dataChanged."""

    def __init__(self, model: QAbstractItemModel, empty_column_widths=None, parent=None):
        super().__init__(parent)
        self.setModel(model)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setEditTriggers(QTableView.NoEditTriggers)
        self.setSelectionMode(QTableView.NoSelection)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        if empty_column_widths:
            for col, width in empty_column_widths.items():
                self.setColumnWidth(col, width)
        self.setStyleSheet(get_table_stylesheet())
        self.verticalHeader().setDefaultSectionSize(TABLE_ROW_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFrameShape(QTableView.NoFrame)
        self.setViewportMargins(0, 0, 0, 0)
        self.setContentsMargins(0, 0, 0, 0)


class TabButton(QPushButton):
    clicked = Signal()
    _font_name = None

    @classmethod
    def _get_font_name(cls):
        if cls._font_name is None:
            cls._font_name = get_prop_font_name()
        return cls._font_name

    def __init__(self, text, is_active=False, parent=None, font_size=FONT_SIZE_MEDIUM, enable_hover=False, use_checkable=False):
        super().__init__(text, parent)
        self._is_active = is_active
        self._font_size = font_size
        self._enable_hover = enable_hover
        self._use_checkable = use_checkable
        self.setFixedHeight(WIDGET_HEIGHT_TAB)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        if use_checkable:
            self.setCheckable(True)
            self.setChecked(is_active)
        self._update_style()

    def _update_style(self):
        font_name = self._get_font_name()
        if self._enable_hover:
            is_selected = self.isChecked() if self._use_checkable else self._is_active
            if is_selected:
                style = f"QPushButton {{ background-color: {COLOR_GRAY_LIGHT}; color: {COLOR_BLACK}; border: none; font-family: '{font_name}'; font-size: {self._font_size}pt; padding: 0px {SPACING_LARGE}px; }}"
            else:
                style = f"QPushButton {{ background-color: {COLOR_GRAY_DARK}; color: {COLOR_GRAY_LIGHT}; border: none; font-family: '{font_name}'; font-size: {self._font_size}pt; padding: 0px {SPACING_LARGE}px; }} QPushButton:hover {{ background-color: {COLOR_BUTTON_HOVER}; }}"
        else:
            if self._is_active:
                style = f"QPushButton {{ background-color: {COLOR_TAB_ACTIVE_BG}; color: {COLOR_TAB_ACTIVE_TEXT}; padding: 0px {SPACING_LARGE}px; font-size: {self._font_size}pt; font-family: '{font_name}'; border: none; }}"
            else:
                style = f"QPushButton {{ background-color: {COLOR_TAB_INACTIVE_BG}; color: {COLOR_TAB_INACTIVE_TEXT}; padding: 0px {SPACING_LARGE}px; font-size: {self._font_size}pt; font-family: '{font_name}'; border: none; }} QPushButton:hover {{ background-color: {COLOR_GRAY_HOVER}; }}"
        self.setStyleSheet(style)

    def set_active(self, active):
        self._is_active = active
        if self._use_checkable:
            self.setChecked(active)
        self._update_style()

    def setSelected(self, selected):
        if self._use_checkable:
            self.setChecked(selected)
        else:
            self._is_active = selected
        self._update_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._use_checkable:
            self.clicked.emit()
        super().mousePressEvent(event)


class ClickableLabel(QLabel):
    clicked = Signal()
    _font_name = None

    @classmethod
    def _get_font_name(cls):
        if cls._font_name is None:
            cls._font_name = get_prop_font_name()
        return cls._font_name

    def __init__(self, text, parent=None, is_accent=False, font_size=FONT_SIZE_NORMAL):
        super().__init__(text, parent)
        color = COLOR_TEXT_ACCENT if is_accent else COLOR_TEXT_NORMAL
        weight = "bold" if is_accent else "normal"
        font_name = self._get_font_name()
        self.setStyleSheet(f"color: {color}; font-weight: {weight}; font-size: {font_size}pt; font-family: '{font_name}';")
        self.setFont(QFont(font_name, font_size))
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


def create_separator_line(height=WIDGET_HEIGHT_SEPARATOR):
    from ..styles import get_separator_line_style
    line = QWidget()
    line.setFixedHeight(height)
    line.setStyleSheet(get_separator_line_style())
    return line

def create_bottom_bar():
    from ..styles import get_bottom_bar_style, WIDGET_HEIGHT_BUTTON
    bar = QWidget()
    bar.setFixedHeight(WIDGET_HEIGHT_BUTTON)
    bar.setStyleSheet(get_bottom_bar_style())
    return bar
