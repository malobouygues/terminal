"""Snapshot Holdings / Allocation pour l'UI — tout en USD.

Par position (instrument × lot × compte) :
  cost_usd        = Σ (q·cb ou ajustement qty=0) × fx à la date de chaque ligne
  market_value    = qty × last × multiplier × fx courant   (last = prix live sinon dernière clôture)
  unrealized      = market_value − cost_usd  (inclut l'effet de change)
Par lot (le cash rattaché au lot n'est pas attribuable à un instrument) :
  realized  = Σ cash lot-linké (TRADE, MERGER, RIGHTS_ISSUE) × fx + Σ cost_usd résiduel
  income    = Σ DIVIDEND lot-linké × fx ;  fees = Σ FEE lot-linké × fx
  total_return = realized + income + fees + Σ unrealized des instruments du lot
"""

from dataclasses import dataclass
from datetime import date

from database import ledger_db
from .db import fx_at, ledger_conn, load_closes, load_fx, load_live, market_conn, value_at

REALIZED_CASH_TYPES = ("TRADE", "MERGER", "RIGHTS_ISSUE")


@dataclass(frozen=True)
class HoldingRow:
    lot_id:           str | None
    conid:            str
    name:             str
    type:             str
    currency:         str
    qty:              float            # nombre × multiplicateur
    init_buy:         str | None
    last_sell:        str | None
    date_close:       str | None
    last:             float | None
    market_value_usd: float | None
    unrealized_usd:   float | None
    realized_usd:     float            # niveau lot
    total_return_usd: float | None     # niveau lot


def display_name(pos: dict) -> str:
    """DERIVATIVES : '<conid> <strike> DD MM YY / Call|Put' ; sinon le Name."""
    if pos["type"] != "DERIVATIVES":
        return pos["name"]
    expiry = pos.get("expiry") or ""
    if len(expiry) == 10:
        expiry = f"{expiry[8:10]} {expiry[5:7]} {expiry[2:4]}"
    right = {"C": "Call", "P": "Put"}.get(pos.get("right") or "", "")
    strike = f"{pos['strike']:g}" if pos.get("strike") is not None else ""
    return " ".join(p for p in (pos["conid"], strike, expiry) if p) + (f" / {right}" if right else "")


def _lot_aggregates(ledger, fx) -> tuple[dict, dict]:
    """(cost_usd par position, stats par lot) à partir des lignes rattachées à un lot."""
    rows = ledger.execute(
        """
        SELECT je.date, je.transaction_type, jl.lot_id, jl.account_id, jl.instrument_conid,
               jl.line_type, jl.currency, jl.amount, jl.quantity, jl.cost_basis
        FROM journal_lines jl JOIN journal_entries je ON je.id = jl.entry_id
        WHERE jl.lot_id IS NOT NULL
        """
    ).fetchall()
    cost: dict[tuple, float] = {}
    lots: dict[str, dict] = {}
    for r in rows:
        rate = fx_at(fx, r["currency"], r["date"]) or 0.0
        lot = lots.setdefault(r["lot_id"], {"realized": 0.0, "income": 0.0, "fees": 0.0})
        if r["line_type"] == "ASSET_SECURITY":
            basis = r["cost_basis"] if r["quantity"] == 0 else r["quantity"] * r["cost_basis"]
            key = (r["instrument_conid"], r["lot_id"], r["account_id"])
            cost[key] = cost.get(key, 0.0) + basis * rate
            lot["realized"] += basis * rate
        elif r["transaction_type"] in REALIZED_CASH_TYPES:
            lot["realized"] += r["amount"] * rate
        elif r["transaction_type"] == "DIVIDEND":
            lot["income"] += r["amount"] * rate
        elif r["transaction_type"] == "FEE":
            lot["fees"] += r["amount"] * rate
    return cost, lots


def holdings() -> list[HoldingRow]:
    ledger, market = ledger_conn(), market_conn()
    try:
        closes, fx = load_closes(market), load_fx(market)
        live, _ = load_live(market)
    finally:
        ledger.close(); market.close()
    today = date.today().isoformat()
    ledger = ledger_conn()
    try:
        cost, lots = _lot_aggregates(ledger, fx)
    finally:
        ledger.close()

    rows = []
    for pos in ledger_db.get_positions(open_only=False):
        qty, mult = float(pos["qty"]), float(pos["multiplier"])
        if abs(qty) < 1e-9 and pos["date_close"] is None:
            continue                                   # instrument soldé dans un lot encore actif
        last = live.get(pos["conid"], value_at(closes, pos["conid"], today))
        rate = live.get(f"FX:{pos['currency']}", fx_at(fx, pos["currency"], today))
        mv = unrl = None
        if abs(qty) < 1e-9:
            qty, last = 0.0, None
        elif last is not None and rate is not None:
            mv = qty * last * mult * rate
            unrl = mv - cost.get((pos["conid"], pos["lot_id"], pos["account_id"]), 0.0)
        lot = lots.get(pos["lot_id"], {"realized": 0.0, "income": 0.0, "fees": 0.0})
        rows.append(HoldingRow(
            pos["lot_id"], pos["conid"], display_name(pos), pos["type"], pos["currency"],
            qty * mult, pos["first_buy"], pos["last_sell"], pos["date_close"], last, mv, unrl,
            lot["realized"], lot["realized"] + lot["income"] + lot["fees"],
        ))

    # Total return du lot = réalisé + income + fees + Σ latent des instruments du lot.
    unrl_by_lot: dict[str | None, float | None] = {}
    for r in rows:
        if r.lot_id in unrl_by_lot and unrl_by_lot[r.lot_id] is None:
            continue
        if r.unrealized_usd is None and r.qty != 0:
            unrl_by_lot[r.lot_id] = None
        else:
            unrl_by_lot[r.lot_id] = unrl_by_lot.get(r.lot_id, 0.0) + (r.unrealized_usd or 0.0)
    return [
        HoldingRow(**{**r.__dict__, "total_return_usd":
                      None if unrl_by_lot[r.lot_id] is None else r.total_return_usd + unrl_by_lot[r.lot_id]})
        for r in rows
    ]


def cash() -> list[tuple[str, float, float | None]]:
    """[(devise, solde, valeur USD ou None sans FX)] tous comptes confondus, tri par valeur USD
    décroissante. Soldes IB (cash_balances, dernier sync) s'ils existent, sinon soldes du ledger."""
    market = market_conn()
    try:
        fx = load_fx(market)
        live, _ = load_live(market)
        ib_cash = market.execute("SELECT currency, SUM(amount) AS balance FROM cash_balances GROUP BY currency").fetchall()
    finally:
        market.close()
    today = date.today().isoformat()
    totals: dict[str, float] = {}
    for b in ib_cash or ledger_db.get_cash_balances():
        totals[b["currency"]] = totals.get(b["currency"], 0.0) + b["balance"]
    rows = []
    for ccy, amount in totals.items():
        rate = live.get(f"FX:{ccy}", fx_at(fx, ccy, today))
        usd = None if rate is None else amount * rate
        if usd is None or abs(usd) >= 0.5:       # ignore les poussières de devise
            rows.append((ccy, amount, usd))
    return sorted(rows, key=lambda r: -(r[2] or 0.0))


def allocation() -> list[tuple[str, float, float]]:
    """[(Name, % du portefeuille, valeur USD)] — titres en portefeuille + cash, tri décroissant."""
    totals: dict[str, float] = {}
    for r in holdings():
        if r.date_close is None and r.market_value_usd is not None:
            totals[r.name] = totals.get(r.name, 0.0) + r.market_value_usd
    total_cash = sum(usd for _, _, usd in cash() if usd)
    if total_cash > 0:
        totals["Cash"] = total_cash
    totals = {n: v for n, v in totals.items() if v > 0}
    grand = sum(totals.values())
    if grand <= 0:
        return []
    return sorted(((n, 100.0 * v / grand, v) for n, v in totals.items()), key=lambda x: -x[1])
