from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


@dataclass(frozen=True)
class AllocationRow:
    name: str
    percentage: float
    market_value: float      # USD


class AllocationModel(QAbstractTableModel):
    HEADERS = ("", "Name", "% Port.", "Mkt Val", "")

    def __init__(self, rows: list[AllocationRow] | None = None, parent=None):
        super().__init__(parent)
        self._rows: list[AllocationRow] = list(rows) if rows else []

    def rows(self) -> list[AllocationRow]:
        return list(self._rows)

    def set_rows(self, rows: list[AllocationRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

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
        if role == Qt.DisplayRole:
            if col == 1:
                return row.name
            if col == 2:
                return f"{row.percentage:.1f}%"
            if col == 3:
                return f"{row.market_value:,.0f}"
            return ""
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignRight | Qt.AlignVCenter) if col in (2, 3) else int(Qt.AlignLeft | Qt.AlignVCenter)
        return None
