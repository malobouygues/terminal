from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QComboBox, QDateEdit, QDateTimeEdit, QSizePolicy
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem
from PySide6.QtCore import QSize, Qt, QDate
from PySide6.QtGui import QFocusEvent


class DateEditNoAutoSelect(QDateEdit):
    """QDateEdit qui n'auto-sélectionne pas la section année au focus (comportement Qt par défaut)."""

    def focusInEvent(self, event: QFocusEvent):
        super().focusInEvent(event)
        self.setSelectedSection(QDateTimeEdit.Section.NoSection)  # évite la sélection auto de l'année


from ...styles import (
    get_field_label_style, get_white_field_label_style, get_white_label_style,
    get_line_edit_style, get_accent_line_edit_style, get_combo_box_style,
)
from .dialog_constants import SECTION_MARGIN_LEFT, SECTION_SPACING

class NoCheckmarkItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def paint(self, painter, option, index):
        option.showDecorationSelected = False
        option.decorationSize = QSize(0, 0)
        option.features = option.features & ~QStyleOptionViewItem.HasCheckIndicator
        super().paint(painter, option, index)

def create_combo_small(items, editable=False):
    combo = QComboBox()
    combo.addItems(items)
    combo.setItemDelegate(NoCheckmarkItemDelegate())
    view = combo.view()
    if view:
        view.setItemDelegate(NoCheckmarkItemDelegate())
    combo.setFixedSize(155, 20)
    combo.setStyleSheet(get_combo_box_style())
    combo.setEditable(editable)
    return combo


def apply_combo_line_edit_style(combo, style_sheet=None) -> None:
    """
    Apply the line edit stylesheet for a QComboBox when it's in editable mode.
    Qt can recreate the internal QLineEdit after toggling editable state,
    which may lead to inconsistent text rendering unless we restyle it.
    """
    if style_sheet is None:
        style_sheet = get_line_edit_style()
    line_edit = combo.lineEdit() if combo.isEditable() else None
    if line_edit is not None:
        # Compensate for an implicit left offset observed on QLineEdit inside an
        # editable QComboBox (cursor/selection rendering area).
        adjusted = style_sheet + "\nQLineEdit { margin-left: -5px; }"
        line_edit.setStyleSheet(adjusted)
        # QLineEdit has internal textMargins that can differ between editable/non-editable
        # combo rendering. Force them to 0 so the first glyph aligns consistently.
        line_edit.setTextMargins(0, 0, 0, 0)

def create_combo_large(items, editable=False):
    from .dialog_constants import INPUT_WIDTH_LARGE
    combo = create_combo_small(items, editable)
    combo.setFixedSize(INPUT_WIDTH_LARGE, 20)
    if editable:
        apply_combo_line_edit_style(combo)
    return combo

def create_input_small():
    edit = QLineEdit()
    edit.setFixedSize(180, 20)
    edit.setStyleSheet(get_accent_line_edit_style())
    edit.setTextMargins(0, 0, 0, 0)
    return edit

def create_date_input_small():
    from .dialog_constants import INPUT_WIDTH_SMALL
    date_edit = DateEditNoAutoSelect()
    date_edit.setFixedSize(INPUT_WIDTH_SMALL, 20)
    date_edit.setDisplayFormat("yyyy-MM-dd")
    date_edit.setDate(QDate.currentDate())
    date_edit.setCalendarPopup(True)
    date_edit.setStyleSheet(get_accent_line_edit_style().replace("QLineEdit", "QDateEdit"))
    return date_edit

def create_date_input_large():
    from .dialog_constants import INPUT_WIDTH_LARGE
    date_edit = DateEditNoAutoSelect()
    date_edit.setFixedSize(INPUT_WIDTH_LARGE, 20)
    date_edit.setDisplayFormat("yyyy-MM-dd")
    date_edit.setDate(QDate.currentDate())
    date_edit.setCalendarPopup(True)
    date_style = get_line_edit_style().replace("QLineEdit", "QDateEdit")
    date_style += """
        QDateEdit { margin: 0px; padding-left: 2px; padding-right: 2px; padding-top: 0px; padding-bottom: 0px; }
    """
    date_edit.setStyleSheet(date_style)
    return date_edit

def create_input_large():
    from .dialog_constants import INPUT_WIDTH_LARGE
    edit = QLineEdit()
    edit.setFixedSize(INPUT_WIDTH_LARGE, 20)
    style = get_line_edit_style() + """
        QLineEdit { margin: 0px; padding-left: 2px; padding-right: 2px; padding-top: 0px; padding-bottom: 0px; }
    """
    edit.setStyleSheet(style)
    edit.setContentsMargins(0, 0, 0, 0)
    edit.setTextMargins(0, 0, 0, 0)
    return edit

def create_label_large(width=None):
    from .dialog_constants import LABEL_WIDTH_MEDIUM
    if width is None:
        width = LABEL_WIDTH_MEDIUM
    label = QLabel()
    label.setStyleSheet(get_field_label_style())
    label.setFixedWidth(width)
    label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    return label

def create_value_label_small(value="XX,XXX.XX", align_left=False):
    from .dialog_constants import VALUE_WIDTH_SMALL
    container = QWidget()
    container.setFixedWidth(VALUE_WIDTH_SMALL)
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    if not align_left:
        layout.addStretch()
    label = QLabel(value)
    alignment = Qt.AlignLeft | Qt.AlignVCenter if align_left else Qt.AlignRight | Qt.AlignVCenter
    label.setAlignment(alignment)
    label.setStyleSheet(get_white_field_label_style())
    layout.addWidget(label, stretch=0)
    container.label = label
    return container

def create_value_label_large(value="XX,XXX.XX", align_left=False):
    from .dialog_constants import VALUE_WIDTH_LARGE
    container = QWidget()
    container.setFixedWidth(VALUE_WIDTH_LARGE)
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    if not align_left:
        layout.addStretch()
    label = QLabel(value)
    alignment = Qt.AlignLeft | Qt.AlignVCenter if align_left else Qt.AlignRight | Qt.AlignVCenter
    label.setAlignment(alignment)
    label.setStyleSheet(get_white_field_label_style())
    layout.addWidget(label, stretch=0)
    container.label = label
    return container

class GridRow:
    def __init__(self, left_margin=0):
        self.widget = QWidget()
        self.layout = QHBoxLayout(self.widget)
        self.layout.setContentsMargins(left_margin, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignLeft)
    
    def add_col(self, widget, width=None):
        if width:
            widget.setFixedWidth(width)
        self.layout.addWidget(widget)
        return widget
    
    def add_spacer(self, width):
        spacer = QWidget()
        spacer.setFixedWidth(width)
        self.layout.addWidget(spacer)
    
    def get_widget(self):
        return self.widget

class DialogSection:
    def __init__(self, title="", top_margin=0, left_margin=None, spacing=None):
        self.widget = QWidget()
        self.widget.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.layout = QVBoxLayout(self.widget)
        self.section_left_margin = left_margin if left_margin is not None else SECTION_MARGIN_LEFT
        self.layout.setContentsMargins(self.section_left_margin, top_margin, 0, 0)
        self.layout.setSpacing(spacing if spacing is not None else SECTION_SPACING)
        if title:
            self._add_title(title)
    
    def _add_title(self, title):
        title_bar = QWidget()
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(10)
        title_label = QLabel(title)
        title_label.setStyleSheet(get_white_label_style())
        title_layout.addWidget(title_label)
        self.layout.addWidget(title_bar)
    
    def add_field(self, field_widget):
        self.layout.addWidget(field_widget)
    
    def get_widget(self):
        return self.widget
