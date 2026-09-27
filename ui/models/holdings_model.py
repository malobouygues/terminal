from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


@dataclass(frozen=True)
class HoldingsRow:
    name: str
    init_buy: str | None
    qty: float | None            # None → vide (ligne principale d'un lot multi-instruments)
    last_sell: str | None
    last: float | None
    market_value: float | None   # USD
    pnl: float | None            # live : latent en % du total return ; hist : réalisé USD
    total_return: float | None   # USD, niveau lot
    sub: bool = False            # sous-ligne (instrument d'un lot multi-instruments)
    cash: bool = False           # ligne devise : Name = devise, Mkt Val = contre-valeur USD


class HoldingsModel(QAbstractTableModel):
    """Table Holdings. ``closed=False`` → lots actifs (LIVE), ``closed=True`` → lots clôturés."""

    LIVE_HEADERS = ("", "Name", "Init Buy", "Qty", "Last", "Mkt Val", "Unrlzd PnL", "Total Return", "")
    HIST_HEADERS = ("", "", "", "Last Sell", "Rlzd PnL", "", "", "", "")     # bandeau sous la table LIVE

    def __init__(self, closed: bool = False, parent=None):
        super().__init__(parent)
        self._closed = closed
        self.headers = self.HIST_HEADERS if closed else self.LIVE_HEADERS
        self._numeric = (4,) if closed else (3, 4, 5, 6, 7)
        self._rows: list[HoldingsRow] = []

    def set_rows(self, rows: list[HoldingsRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = self._rows[index.row()], index.column()
        if role == Qt.DisplayRole:
            return self._format(row, col)
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignRight | Qt.AlignVCenter) if col in self._numeric else int(Qt.AlignLeft | Qt.AlignVCenter)
        return None

    @staticmethod
    def _num(value: float | None, fmt: str) -> str:
        return "—" if value is None else format(value, fmt)

    def _format(self, row: HoldingsRow, col: int) -> str:
        if row.cash:
            return row.name if col == 1 else self._num(row.market_value, ",.0f") if col == 5 else ""
        if col == 1:
            return ("    " if row.sub else "") + row.name
        if col == 2:
            return row.init_buy or ("" if row.qty is None else "—")
        if col == 3:
            if self._closed:
                return row.last_sell or ""
            return "" if row.qty is None else f"{row.qty:,.4f}".rstrip("0").rstrip(".")
        if self._closed:
            return self._num(row.pnl, "+,.0f") if col == 4 else ""
        if col == 4:
            return self._num(row.last, ",.2f")
        if col == 5:
            return self._num(row.market_value, ",.0f")
        if col == 6:
            return self._num(row.pnl, "+.1f") + ("" if row.pnl is None else "%")
        if col == 7:
            return self._num(row.total_return, "+,.0f")
        return ""


def _pct(part: float | None, total: float | None) -> float | None:
    return None if part is None or not total else 100.0 * part / total


def _label(h: dict) -> str:
    """Lot mono-instrument : le Name (complété du Des pour un dérivé, qui le distingue)."""
    return f"{h['name']} {h['des']}".strip() if h["type"] == "DERIVATIVE" else h["name"]


def _sub_labels(hs: list[dict]) -> list[str]:
    """Sous-lignes : le Des, suffixé de la devise quand deux Des sont identiques."""
    dupes = {h["des"] for h in hs if sum(x["des"] == h["des"] for x in hs) > 1}
    return [f"{h['des']} ({h['currency']})" if h["des"] in dupes else h["des"] for h in hs]


def _row(h: dict, closed: bool, label: str | None = None, sub: bool = False) -> HoldingsRow:
    return HoldingsRow(
        name=label or h["name"], init_buy=h["init_buy"], qty=h["qty"], last_sell=h["last_sell"],
        last=h["last"], market_value=h["market_value_usd"],
        pnl=h["realized_usd"] if closed else _pct(h["unrealized_usd"], h["total_return_usd"]),
        total_return=h["total_return_usd"], sub=sub,
    )


def cash_row(currency: str, usd: float) -> HoldingsRow:
    return HoldingsRow(currency, None, None, None, None, usd, None, None, cash=True)


def build_holdings_rows(holdings: list[dict], closed: bool) -> list[HoldingsRow]:
    """Lignes par lot. LIVE : lots triés par valeur de marché décroissante ; HIST : par date
    de clôture décroissante, puis par Name. Un lot multi-instruments = ligne agrégée (Name) +
    une sous-ligne par instrument (Des), par valeur de marché décroissante."""
    lots: dict[str | None, list[dict]] = {}
    for h in holdings:
        if (h["date_close"] is not None) == closed:
            lots.setdefault(h["lot_id"], []).append(h)
    mv = lambda h: h["market_value_usd"] or 0.0
    if closed:
        ordered = sorted(lots.values(), key=lambda hs: min(h["name"] for h in hs))
        ordered.sort(key=lambda hs: max(h["date_close"] for h in hs), reverse=True)
    else:
        ordered = sorted(lots.values(), key=lambda hs: -sum(mv(h) for h in hs))

    rows: list[HoldingsRow] = []
    for hs in ordered:
        hs = sorted(hs, key=lambda h: -mv(h))
        if len(hs) == 1:
            rows.append(_row(hs[0], closed, _label(hs[0])))
            continue
        total_mv = sum(mv(h) for h in hs) if any(h["market_value_usd"] is not None for h in hs) else None
        unrl = None if any(h["unrealized_usd"] is None and h["qty"] for h in hs) \
            else sum(h["unrealized_usd"] or 0.0 for h in hs)
        rows.append(HoldingsRow(
            name=hs[0]["name"], init_buy=None, qty=None, last_sell=None, last=None,
            market_value=total_mv,
            pnl=hs[0]["realized_usd"] if closed else _pct(unrl, hs[0]["total_return_usd"]),
            total_return=hs[0]["total_return_usd"],
        ))
        rows.extend(_row(h, closed, label, sub=True) for h, label in zip(hs, _sub_labels(hs)))
    return rows
