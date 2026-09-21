import os
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase


DEFAULT_FONT_PATH = Path("/Users/malo/Library/Fonts/bloomberg-prop-unicode-n.otf")
FALLBACK_FAMILIES = ("Monaco", "Menlo", "Consolas", "Courier New")

_loaded_family: str | None = None


def load_bloomberg_font() -> str:
    """Load the Bloomberg Prop font when available, else fall back to a system
    monospace family. Always returns a usable family name — never None.

    The path can be overridden via the ``BLOOMBERG_FONT_PATH`` env var.
    """
    global _loaded_family
    if _loaded_family is not None:
        return _loaded_family

    candidates: list[Path] = []
    override = os.getenv("BLOOMBERG_FONT_PATH")
    if override:
        candidates.append(Path(override))
    candidates.append(DEFAULT_FONT_PATH)

    for path in candidates:
        if path.exists():
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    _loaded_family = families[0]
                    return _loaded_family

    available = set(QFontDatabase.families())
    for family in FALLBACK_FAMILIES:
        if family in available:
            _loaded_family = family
            return _loaded_family

    _loaded_family = QFont().family()
    return _loaded_family


def get_prop_font_name() -> str:
    if _loaded_family is None:
        return load_bloomberg_font()
    return _loaded_family


def get_prop_font(size: int = 10) -> QFont:
    return QFont(get_prop_font_name(), size)
