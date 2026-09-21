from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class GridModel(QAbstractTableModel):
    """Grille en lecture seule : en-têtes + lignes de valeurs (None → vide, float → ',.2f')."""

    def __init__(self, headers: list[str] | None = None, rows: list[list] | None = None, parent=None):
        super().__init__(parent)
        self._headers = list(headers or [])
        self._rows = list(rows or [])

    def set_data(self, headers: list[str], rows: list[list]) -> None:
        self.beginResetModel()
        self._headers, self._rows = list(headers), list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._headers[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        value = self._rows[index.row()][index.column()]
        if role == Qt.DisplayRole:
            return "" if value is None else f"{value:,.4f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value)
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignLeft | Qt.AlignVCenter) if index.column() == 0 else int(Qt.AlignRight | Qt.AlignVCenter)
        return None
