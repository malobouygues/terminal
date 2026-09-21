from dataclasses import dataclass, field

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from ..components.widgets import TableBorderDelegate
from ..styles import COLOR_TEXT_ACCENT, COLOR_WHITE

EDITABLE_TYPES = ("DEPOSIT", "WITHDRAWAL", "TRANSFER", "TRADE")


@dataclass(frozen=True)
class BookRow:
    kind: str                     # 'cash' | 'entry' | 'line'
    entry: dict | None            # écriture (avec ses lignes) pour les actions supprimer / modifier
    cells: tuple[str, ...]
    time: str = ""                # HH:MM (sous la date)
    sub: bool = False             # ligne d'une écriture multi-lignes


def _num(value, fmt: str) -> str:
    return "" if value is None else format(value, fmt)


def _line_cells(ln: dict) -> tuple[str, ...]:
    return (
        ln["instrument_name"] or "", ln["lot_id"] or "", ln["account_id"],
        _num(ln["quantity"], ",.4f").rstrip("0").rstrip(".") if ln["quantity"] is not None else "",
        _num(ln["cost_basis"], ",.2f"), _num(ln["amount"], "+,.2f"), ln["currency"],
    )


class BooksModel(QAbstractTableModel):
    """journal_entries et leurs journal_lines, à plat. Une écriture à une seule ligne tient
    sur une ligne ; sinon une ligne d'en-tête (actions, date, type) suivie de ses lignes.
    Ligne 0 = sentinelle <cash>."""

    HEADERS = ("", "", "Date", "Type", "Security", "Lot", "Account", "Qty", "Cost Basis", "Amount", "Ccy", "")
    _RIGHT, _CENTER = (8, 9), (5, 6, 7, 10)
    ACTIONS_COL, DATE_COL = 1, 2
    OPEN_CASH = "open_cash_dialog"
    ActionRole = Qt.UserRole + 1
    EntryRole = Qt.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[BookRow] = [BookRow("cash", None, ())]

    def set_entries(self, entries: list[dict]) -> None:
        rows = [BookRow("cash", None, ())]
        for e in entries:
            head = ("", "", e["date"], e["transaction_type"])
            times = [(ln["created_at"] or "")[11:16] for ln in e["lines"]]
            if len(e["lines"]) == 1:
                rows.append(BookRow("entry", e, (*head, *_line_cells(e["lines"][0]), ""), times[0]))
                continue
            rows.append(BookRow("entry", e, (*head, e["external_ref"] or "", "", "", "", "", "", "", ""), min(times)))
            for ln, t in zip(e["lines"], times):
                rows.append(BookRow("line", e, ("", "", "", "", *_line_cells(ln), ""), t, sub=True))
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def row_at(self, row: int) -> BookRow:
        return self._rows[row]

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = self._rows[index.row()], index.column()
        if row.kind == "cash":
            return self._cash_row_data(col, role)
        if role == Qt.DisplayRole:
            if col == self.ACTIONS_COL and row.kind == "entry":
                return "✕   ✎" if row.entry["transaction_type"] in EDITABLE_TYPES else "✕"
            return row.cells[col]
        if role == TableBorderDelegate.SubTextRole and col == self.DATE_COL:
            return row.time
        if role == Qt.TextAlignmentRole:
            if col == self.ACTIONS_COL or col in self._CENTER:
                return int(Qt.AlignCenter)
            return int(Qt.AlignRight | Qt.AlignVCenter) if col in self._RIGHT else int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.ForegroundRole:
            if col == self.ACTIONS_COL:
                return QColor(COLOR_TEXT_ACCENT)
            if row.kind == "entry":
                return QColor(COLOR_WHITE)
        if role == self.EntryRole:
            return row.entry
        if role == self.ActionRole and col == self.ACTIONS_COL and row.kind == "entry":
            return "actions"
        return None

    def _cash_row_data(self, col, role):
        if role == Qt.DisplayRole:
            return "<cash>" if col == 4 else ""
        if role == Qt.ForegroundRole and col == 4:
            return QColor(COLOR_TEXT_ACCENT)
        if role == self.ActionRole and col == 4:
            return self.OPEN_CASH
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignCenter)
        return None
