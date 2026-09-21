from .colors import (
    COLOR_BACKGROUND, COLOR_BLACK, COLOR_WHITE,
    COLOR_TEXT_NORMAL, COLOR_TEXT_ACCENT,
    COLOR_TABLE_BG, COLOR_TABLE_HEADER_BG, COLOR_TABLE_BORDER, COLOR_TABLE_TEXT,
    COLOR_GRAY_LIGHT, COLOR_GRAY_DARK,
    COLOR_BORDEAUX, COLOR_BORDER_LIGHT, COLOR_BORDER_MEDIUM, COLOR_BORDER_HOVER,
    COLOR_FUNCTION_BAR_BG,
    COLOR_BUTTON_BG, COLOR_BUTTON_HOVER,
    COLOR_CMD_BG, COLOR_LINE_EDIT_BG,
)
from .dimensions import (
    FONT_SIZE_SMALL, FONT_SIZE_LARGE, FONT_SIZE_MEDIUM, FONT_SIZE_XLARGE,
    FONT_SIZE_XXLARGE, FONT_SIZE_HUGE, FONT_SIZE_ENORMOUS,
    PADDING_XS, PADDING_SMALL, PADDING_MEDIUM, PADDING_LARGE,
    TABLE_ITEM_PADDING_VERTICAL, TABLE_ITEM_PADDING_HORIZONTAL,
    TABLE_BORDER_WIDTH,
)
from .fonts import get_prop_font_name


def _font_css() -> str:
    return f"'{get_prop_font_name()}'"


def get_stylesheet(font_family: str) -> str:
    return f"""
QWidget {{ background-color: {COLOR_BACKGROUND}; color: {COLOR_TEXT_NORMAL}; font-family: "{font_family}"; font-size: {FONT_SIZE_SMALL}pt; }}
QLabel {{ background-color: transparent; }}
QMainWindow {{ border: 1px solid {COLOR_BORDEAUX}; }}
QLineEdit {{ background-color: {COLOR_LINE_EDIT_BG}; border: 1px solid {COLOR_BORDER_MEDIUM}; color: {COLOR_TEXT_NORMAL}; padding: {PADDING_XS}px {PADDING_MEDIUM}px; }}
QPushButton {{ background-color: {COLOR_BUTTON_BG}; border: 1px solid {COLOR_BORDER_HOVER}; color: {COLOR_TEXT_NORMAL}; padding: {PADDING_SMALL}px {PADDING_LARGE}px; }}
QPushButton:hover {{ background-color: {COLOR_BUTTON_HOVER}; }}
"""


def get_table_stylesheet() -> str:
    font_name = get_prop_font_name()
    return f"""
QTableView {{ background-color: {COLOR_TABLE_BG}; color: {COLOR_TABLE_TEXT}; border: none; gridline-color: transparent; font-family: "{font_name}"; font-size: {FONT_SIZE_MEDIUM}pt; padding: 0px; margin: 0px; }}
QTableView::item {{ padding: {TABLE_ITEM_PADDING_VERTICAL}px {TABLE_ITEM_PADDING_HORIZONTAL}px; font-family: "{font_name}"; font-size: {FONT_SIZE_MEDIUM}pt; }}
QHeaderView::section {{ background-color: {COLOR_TABLE_HEADER_BG}; color: {COLOR_WHITE}; padding: {TABLE_ITEM_PADDING_VERTICAL}px {TABLE_ITEM_PADDING_HORIZONTAL}px; border-top: {TABLE_BORDER_WIDTH}px solid {COLOR_TABLE_BORDER}; border-right: none; border-bottom: none; font-weight: normal; font-family: "{font_name}"; font-size: {FONT_SIZE_MEDIUM}pt; }}
"""


def get_label_style(color=COLOR_TEXT_ACCENT, font_size=17, font_weight="normal", padding="0px", margin="0px") -> str:
    return f"color: {color}; font-size: {font_size}pt; font-weight: {font_weight}; font-family: {_font_css()}; padding: {padding}; margin: {margin};"


def get_accent_label_style(font_size=17) -> str:
    return get_label_style(COLOR_TEXT_ACCENT, font_size)


def get_white_label_style(font_size=17) -> str:
    return get_label_style(COLOR_WHITE, font_size)


def get_black_label_style(font_size=FONT_SIZE_SMALL) -> str:
    return get_label_style(COLOR_BLACK, font_size, "normal")


def get_line_edit_style(bg_color=COLOR_TEXT_ACCENT, text_color=COLOR_BLACK, font_size=17, border="none", padding="0px 2px") -> str:
    return f"QLineEdit {{ background-color: {bg_color}; color: {text_color}; border: {border}; padding: {padding}; font-family: {_font_css()}; font-size: {font_size}pt; }}"


def get_combo_box_style(bg_color=COLOR_TEXT_ACCENT, text_color=COLOR_BLACK, font_size=17, border="none", padding="0px 2px", drop_down_bg=COLOR_TEXT_ACCENT) -> str:
    return f"""
QComboBox {{ background-color: {bg_color}; color: {text_color}; border: {border}; padding: {padding}; font-family: {_font_css()}; font-size: {font_size}pt; }}
QComboBox::drop-down {{ border: none; background-color: {drop_down_bg}; }}
QComboBox::down-arrow {{ image: none; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 5px solid {COLOR_BLACK}; width: 0; height: 0; }}
QComboBox QAbstractItemView {{ background-color: {COLOR_GRAY_LIGHT}; color: {COLOR_BLACK}; selection-background-color: {COLOR_TEXT_ACCENT}; selection-color: {COLOR_BLACK}; border: none; }}
QComboBox QAbstractItemView::indicator {{ width: 0px; height: 0px; }}
"""


def get_button_style(bg_color=COLOR_GRAY_DARK, text_color=COLOR_GRAY_LIGHT, hover_bg=COLOR_GRAY_LIGHT, font_size=FONT_SIZE_SMALL, padding="0px 15px") -> str:
    return f"QPushButton {{ background-color: {bg_color}; color: {text_color}; border: none; font-family: {_font_css()}; font-size: {font_size}pt; font-weight: normal; padding: {padding}; }} QPushButton:hover {{ background-color: {hover_bg}; }}"


def get_title_label_style(font_size=FONT_SIZE_ENORMOUS, color=COLOR_WHITE, margin_left="0px") -> str:
    return f"color: {color}; font-size: {font_size}pt; font-family: {_font_css()}; margin-left: {margin_left};"


def get_subtitle_label_style(font_size=FONT_SIZE_HUGE, color=COLOR_WHITE) -> str:
    return f"color: {color}; font-size: {font_size}pt; font-family: {_font_css()};"


def get_function_bar_style() -> str:
    return f"QWidget#FunctionBar {{ background-color: {COLOR_FUNCTION_BAR_BG}; min-height: 40px; }} QWidget#FunctionBar QLabel {{ background-color: {COLOR_FUNCTION_BAR_BG}; }}"


def get_function_bar_label_style(font_size=FONT_SIZE_XXLARGE) -> str:
    return f"font-size: {font_size}pt; color: {COLOR_WHITE}; font-weight: bold; font-family: {_font_css()};"


def get_function_bar_button_style(font_size=FONT_SIZE_XLARGE) -> str:
    return f"color: {COLOR_WHITE}; font-weight: normal; font-size: {font_size}pt; font-family: {_font_css()};"


def get_separator_line_style() -> str:
    return f"background-color: {COLOR_GRAY_LIGHT};"


def get_bottom_bar_style() -> str:
    return f"background-color: {COLOR_TABLE_HEADER_BG};"


def get_dialog_style() -> str:
    return f"QDialog {{ background-color: {COLOR_BLACK}; border: none; }}"


def get_dialog_border_frame_style() -> str:
    return f"QFrame#borderFrame {{ background-color: {COLOR_BLACK}; border: 2px solid {COLOR_BORDER_LIGHT}; }}"


def get_title_bar_style() -> str:
    return f"background-color: {COLOR_BORDER_LIGHT};"


def get_radio_button_style() -> str:
    return f"QRadioButton {{ color: {COLOR_WHITE}; font-family: {_font_css()}; font-size: {FONT_SIZE_LARGE}pt; }} QRadioButton::indicator {{ width: 15px; height: 15px; }} QRadioButton::indicator::unchecked {{ background-color: {COLOR_GRAY_DARK}; border: 2px solid {COLOR_GRAY_LIGHT}; border-radius: 7px; }} QRadioButton::indicator::checked {{ background-color: {COLOR_TEXT_ACCENT}; border: 2px solid {COLOR_TEXT_ACCENT}; border-radius: 7px; }}"


def get_text_area_style() -> str:
    return f"QTextEdit {{ background-color: {COLOR_CMD_BG}; color: {COLOR_WHITE}; border: 1px solid {COLOR_BORDER_LIGHT}; padding: 5px; font-family: {_font_css()}; font-size: {FONT_SIZE_LARGE}pt; }}"


def get_accent_line_edit_style() -> str:
    return f"QLineEdit {{ background-color: {COLOR_TEXT_ACCENT}; color: {COLOR_BLACK}; border: none; padding: 0px 2px; font-family: {_font_css()}; font-size: {FONT_SIZE_LARGE}pt; }}"


def get_loading_screen_style() -> str:
    return f"background-color: {COLOR_BACKGROUND};"


def get_loading_label_style() -> str:
    return f"color: {COLOR_TEXT_NORMAL}; font-size: {FONT_SIZE_LARGE}pt;"


def get_field_label_style(color=COLOR_TEXT_ACCENT, font_size=FONT_SIZE_LARGE) -> str:
    return f"color: {color}; font-size: {font_size}pt; font-family: {_font_css()}; padding: 0px; margin: 0px;"


def get_white_field_label_style(font_size=FONT_SIZE_LARGE) -> str:
    return get_field_label_style(COLOR_WHITE, font_size)
