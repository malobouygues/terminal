from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QFrame, QSizePolicy, QLabel, QPushButton
)
from PySide6.QtCore import Qt

from ...styles import (
    COLOR_BORDER_LIGHT, COLOR_GRAY_DARK, COLOR_WHITE, COLOR_BUTTON_HOVER,
    get_dialog_style, get_dialog_border_frame_style, get_title_bar_style,
    get_black_label_style, get_button_style,
)
from .dialog_constants import (
    BORDER_WIDTH, BUTTON_WIDTH, BUTTON_HEIGHT,
    BUTTON_MARGIN_RIGHT, BUTTON_MARGIN_BOTTOM, BUTTON_SPACING,
)


class FramelessDialog(QDialog):
    """Frameless, draggable, centered modal dialog.

    Subclasses populate ``self.content_layout`` with their fields, then call
    ``self.add_buttons_row([...])`` once to lay out the action row.

    If ``title`` is provided, a draggable title bar is rendered at the top and
    captures drag events. Otherwise drag events are bound to the border frame.
    """

    def __init__(
        self,
        parent=None,
        *,
        size: tuple[int, int],
        title: str | None = None,
    ):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setFixedSize(*size)
        self.setModal(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet(get_dialog_style())
        self._drag_position = None
        self._dragging = False
        self._centered_once = False

        border_frame = QFrame()
        border_frame.setObjectName("borderFrame")
        border_frame.setFrameShape(QFrame.Box)
        border_frame.setLineWidth(BORDER_WIDTH)
        border_frame.setStyleSheet(get_dialog_border_frame_style())
        border_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(border_frame)

        self._root_layout = QVBoxLayout(border_frame)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        if title:
            drag_target = self._build_title_bar(title)
        else:
            drag_target = border_frame

        drag_target.mousePressEvent = self._drag_press
        drag_target.mouseMoveEvent = self._drag_move
        drag_target.mouseReleaseEvent = self._drag_release

        content_container = QWidget()
        content_container.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.content_layout = QVBoxLayout(content_container)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.content_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._root_layout.addWidget(content_container)

    def _build_title_bar(self, title: str) -> QWidget:
        title_bar = QWidget()
        title_bar.setFixedHeight(18)
        title_bar.setStyleSheet(
            f"{get_title_bar_style()} "
            f"border-left: {BORDER_WIDTH}px solid {COLOR_BORDER_LIGHT}; "
            f"border-bottom: {BORDER_WIDTH}px solid {COLOR_BORDER_LIGHT}; "
            f"border-right: {BORDER_WIDTH}px solid {COLOR_BORDER_LIGHT};"
        )
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(8, 0, 20, 0)
        title_label = QLabel(title)
        title_label.setStyleSheet(get_black_label_style(font_size=13))
        layout.addWidget(title_label)
        self._root_layout.addWidget(title_bar)
        return title_bar

    @staticmethod
    def make_button(label: str, handler=None) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedSize(BUTTON_WIDTH, BUTTON_HEIGHT)
        btn.setStyleSheet(get_button_style(COLOR_GRAY_DARK, COLOR_WHITE, COLOR_BUTTON_HOVER, 12, "0px"))
        if handler is not None:
            btn.clicked.connect(handler)
        return btn

    def add_buttons_row(self, buttons: list[QPushButton], top_margin: int = 0) -> None:
        layout = QHBoxLayout()
        layout.setContentsMargins(20, top_margin, BUTTON_MARGIN_RIGHT, BUTTON_MARGIN_BOTTOM)
        layout.setSpacing(BUTTON_SPACING)
        layout.setAlignment(Qt.AlignRight)
        for btn in buttons:
            layout.addWidget(btn)
        self._root_layout.addLayout(layout)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._centered_once:
            self._center_on_parent()
            self._centered_once = True
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def _center_on_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        window = parent.window()
        if window is None:
            return
        geo = window.geometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        self.move(x, y)

    def _drag_press(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _drag_move(self, event):
        if self._dragging and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            self.raise_()
            self.activateWindow()
            event.accept()

    def _drag_release(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.raise_()
            self.activateWindow()
            event.accept()
