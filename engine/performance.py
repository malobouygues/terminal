"""Performance globale du portefeuille — NAV et TWR quotidiens en USD.

Pour chaque jour ouvré depuis la première écriture jusqu'à la dernière clôture :
  securities_usd = Σ qty × close × multiplier × fx   (dernier cours ≤ date)
  cash_usd       = Σ solde par devise × fx
  flows_usd      = dépôts − retraits du jour
  r_t            = (NAV_t − NAV_t−1 − flows_t) / NAV_t−1
  twr_t          = (1 + twr_t−1) × (1 + r_t) − 1
La table analytics.performance est réécrite intégralement (idempotent).
"""

import logging
from datetime import date, timedelta

from .db import analytics_conn, fx_at, ledger_conn, load_closes, load_fx, market_conn, value_at

logger = logging.getLogger(__name__)


def _business_days(start: str, end: str) -> list[str]:
    d, last, days = date.fromisoformat(start), date.fromisoformat(end), []
    while d <= last:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += timedelta(days=1)
    return days


def recompute() -> int:
    """Recalcule toute la série. Retourne le nombre de jours écrits (0 si aucune donnée de marché)."""
    ledger, market, analytics = ledger_conn(), market_conn(), analytics_conn()
    try:
        first = ledger.execute("SELECT MIN(date) AS d FROM journal_entries").fetchone()["d"]
        last = market.execute("SELECT MAX(date) AS d FROM close_prices").fetchone()["d"]
        if first is None or last is None:
            logger.warning("Performance: pas de données (ledger vide ou aucune clôture en cache)")
            return 0

        closes, fx = load_closes(market), load_fx(market)
        securities = ledger.execute(
            """
            SELECT je.date, jl.instrument_conid AS conid, i.currency, i.multiplier, jl.quantity
            FROM journal_lines jl JOIN journal_entries je ON je.id = jl.entry_id
            JOIN instruments i ON i.conid = jl.instrument_conid
            WHERE jl.line_type = 'ASSET_SECURITY' ORDER BY je.date
            """
        ).fetchall()
        cash = ledger.execute(
            """
            SELECT je.date, jl.currency, jl.amount, je.transaction_type
            FROM journal_lines jl JOIN journal_entries je ON je.id = jl.entry_id
            WHERE jl.line_type = 'ASSET_CASH' ORDER BY je.date
            """
        ).fetchall()

        positions: dict[str, float] = {}          # conid → qty
        meta: dict[str, tuple[str, float]] = {}   # conid → (currency, multiplier)
        balances: dict[str, float] = {}           # currency → solde
        rows, prev_nav, twr, si, ci = [], None, 0.0, 0, 0
        for day in _business_days(first, max(last, first)):
            while si < len(securities) and securities[si]["date"] <= day:
                s = securities[si]
                positions[s["conid"]] = positions.get(s["conid"], 0.0) + float(s["quantity"])
                meta[s["conid"]] = (s["currency"], float(s["multiplier"]))
                si += 1
            flows = 0.0
            while ci < len(cash) and cash[ci]["date"] <= day:
                c = cash[ci]
                balances[c["currency"]] = balances.get(c["currency"], 0.0) + float(c["amount"])
                if c["transaction_type"] in ("DEPOSIT", "WITHDRAWAL") and c["date"] == day:
                    flows += float(c["amount"]) * (fx_at(fx, c["currency"], day) or 0.0)
                ci += 1

            sec_usd = 0.0
            for conid, qty in positions.items():
                if abs(qty) < 1e-9:
                    continue
                ccy, mult = meta[conid]
                close, rate = value_at(closes, conid, day), fx_at(fx, ccy, day)
                if close is None or rate is None:
                    continue
                sec_usd += qty * close * mult * rate
            cash_usd = sum(bal * (fx_at(fx, ccy, day) or 0.0) for ccy, bal in balances.items())
            nav = sec_usd + cash_usd

            daily = (nav - prev_nav - flows) / prev_nav if prev_nav else None
            if daily is not None:
                twr = (1 + twr) * (1 + daily) - 1
            rows.append((day, sec_usd, cash_usd, nav, flows, daily, twr))
            prev_nav = nav

        with analytics:
            analytics.execute("DELETE FROM performance")
            analytics.executemany("INSERT INTO performance VALUES (?,?,?,?,?,?,?)", rows)
        logger.info("Performance recalculée : %d jours, NAV %.0f USD, TWR %+.2f%%", len(rows), rows[-1][3], twr * 100)
        return len(rows)
    finally:
        ledger.close(); market.close(); analytics.close()


def daily_table(start: str, end: str) -> tuple[list[str], list[list]]:
    """Données brutes par jour ouvré, du plus récent au plus ancien : clôture des titres détenus
    (symbole), solde cash par devise, FX USD de toutes les devises. Colonnes par ordre
    alphabétique décroissant ; une cellule est vide tant que la position / le solde n'existe pas."""
    ledger, market = ledger_conn(), market_conn()
    try:
        closes, fx = load_closes(market), load_fx(market)
        symbols = {r["conid"]: r["symbol"] or r["name"][:8] for r in ledger.execute("SELECT conid, symbol, name FROM instruments")}
        securities = ledger.execute(
            """
            SELECT je.date, jl.instrument_conid AS conid, jl.quantity
            FROM journal_lines jl JOIN journal_entries je ON je.id = jl.entry_id
            WHERE jl.line_type = 'ASSET_SECURITY' ORDER BY je.date
            """
        ).fetchall()
        cash = ledger.execute(
            """
            SELECT je.date, jl.currency, jl.amount
            FROM journal_lines jl JOIN journal_entries je ON je.id = jl.entry_id
            WHERE jl.line_type = 'ASSET_CASH' ORDER BY je.date
            """
        ).fetchall()
    finally:
        ledger.close(); market.close()

    positions: dict[str, float] = {}
    balances: dict[str, float] = {}
    days, si, ci = [], 0, 0
    for day in _business_days(start, end):
        while si < len(securities) and securities[si]["date"] <= day:
            s = securities[si]
            positions[s["conid"]] = positions.get(s["conid"], 0.0) + float(s["quantity"])
            si += 1
        while ci < len(cash) and cash[ci]["date"] <= day:
            c = cash[ci]
            balances[c["currency"]] = balances.get(c["currency"], 0.0) + float(c["amount"])
            ci += 1
        days.append((
            day,
            {symbols[c]: value_at(closes, c, day) for c, q in positions.items() if abs(q) > 1e-9},
            {ccy: bal for ccy, bal in balances.items() if abs(bal) >= 0.01},
            {ccy: value_at(fx, ccy, day) for ccy in fx},
        ))
    sec_cols = sorted({k for _, sec, _, _ in days for k in sec}, reverse=True)
    cash_cols = sorted({k for _, _, bal, _ in days for k in bal}, reverse=True)
    fx_cols = sorted(fx, reverse=True)
    headers = ["Date", *sec_cols, *(f"Cash {c}" for c in cash_cols), *(f"{c}/USD" for c in fx_cols)]
    rows = [[day, *(sec.get(c) for c in sec_cols), *(bal.get(c) for c in cash_cols), *(rates.get(c) for c in fx_cols)]
            for day, sec, bal, rates in reversed(days)]
    return headers, rows


def load() -> list[dict]:
    analytics = analytics_conn()
    try:
        return [dict(r) for r in analytics.execute("SELECT * FROM performance ORDER BY date")]
    finally:
        analytics.close()
