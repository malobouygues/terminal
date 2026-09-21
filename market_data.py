"""IB Gateway → market_data.db.

  connect()          connexion API (lecture seule)
  sync_history(ib)   clôtures journalières de tous les CONID du ledger + FX (base USD)
  sync_cash(ib)      cash IB par compte et devise
  refresh_live(ib)   derniers prix / FX intraday (toutes les 5 min depuis l'UI)
  contract_details() détails d'un CONID (trade ticket)

Une cotation manquante n'est jamais inventée : les lecteurs (engine.db) prennent
le dernier cours disponible avant la date.
"""

import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone

from ib_async import IB, Contract, Forex

from database import ledger_db
from engine.db import BASE_CURRENCY, ledger_conn, market_conn

logger = logging.getLogger(__name__)

MARKET_DATA_TYPE = 3          # 1 live, 3 delayed (gratuit) — IB renvoie le live si l'abonnement existe
DERIVATIVE_SECTYPES = ("OPT", "FOP", "FUT", "WAR")
_fx_cache: dict[str, tuple[Contract, bool] | None] = {}   # devise → (contrat, inverser ?)


async def connect(host: str, port: int, client_id: int) -> IB | None:
    ib = IB()
    try:
        await ib.connectAsync(host, port, clientId=client_id, timeout=15, readonly=True)
    except Exception as ex:
        logger.warning("IB Gateway indisponible sur %s:%s (%s)", host, port, ex)
        return None
    logger.info("IB Gateway connecté — comptes %s", ib.managedAccounts())
    return ib


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _duration(start: date, end: date) -> str:
    days = (end - start).days + 1
    return f"{days} D" if days <= 365 else f"{-(-days // 365)} Y"


def _end_datetime(end: date) -> datetime | str:
    return "" if end >= date.today() else datetime(end.year, end.month, end.day, 23, 59)


async def _fx_contract(ib: IB, currency: str) -> tuple[Contract, bool] | None:
    """Paire IDEALPRO cotant `currency` contre USD ; invert=True si la paire est USD.XXX."""
    if currency not in _fx_cache:
        _fx_cache[currency] = None
        for pair, invert in ((f"{currency}USD", False), (f"USD{currency}", True)):
            contract = Forex(pair)
            if await ib.qualifyContractsAsync(contract):
                _fx_cache[currency] = (contract, invert)
                break
        else:
            logger.warning("Pas de paire FX IB pour %s", currency)
    return _fx_cache[currency]


async def _daily_closes(ib: IB, contract: Contract, start: date, end: date, what: str) -> list[tuple[str, float]]:
    try:
        bars = await ib.reqHistoricalDataAsync(
            contract, endDateTime=_end_datetime(end), durationStr=_duration(start, end),
            barSizeSetting="1 day", whatToShow=what, useRTH=True, formatDate=1,
        )
    except Exception as ex:
        logger.warning("Historique %s indisponible (%s)", contract.localSymbol or contract.conId, ex)
        return []
    return [(b.date.isoformat(), float(b.close)) for b in bars
            if start.isoformat() <= b.date.isoformat() <= end.isoformat()]


# ---------------------------------------------------------------------------
# Synchronisations
# ---------------------------------------------------------------------------

async def sync_history(ib: IB) -> None:
    """Clôtures manquantes pour chaque instrument (de son premier trade à aujourd'hui, ou à
    sa dernière cession s'il est soldé) puis FX de toutes les devises du référentiel."""
    ledger, market = ledger_conn(), market_conn()
    try:
        spans = ledger.execute(
            """
            SELECT jl.instrument_conid AS conid, i.type, i.symbol,
                   MIN(je.date) AS first, MAX(je.date) AS last, ROUND(SUM(jl.quantity), 8) AS qty
            FROM journal_lines jl JOIN journal_entries je ON je.id = jl.entry_id
            JOIN instruments i ON i.conid = jl.instrument_conid
            WHERE jl.line_type = 'ASSET_SECURITY' GROUP BY jl.instrument_conid
            """
        ).fetchall()
        inception = ledger.execute("SELECT MIN(date) AS d FROM journal_entries").fetchone()["d"]
        currencies = {r[0] for r in ledger.execute("SELECT code FROM currencies")}
        last_close = dict(market.execute("SELECT conid, MAX(date) FROM close_prices GROUP BY conid").fetchall())
        last_fx = dict(market.execute("SELECT currency, MAX(date) FROM fx_rates GROUP BY currency").fetchall())
    finally:
        ledger.close(); market.close()
    today = date.today()

    for s in spans:
        start = date.fromisoformat(s["first"])
        if s["conid"] in last_close:
            start = max(start, date.fromisoformat(last_close[s["conid"]]) + timedelta(days=1))
        end = today if s["qty"] != 0 else date.fromisoformat(s["last"])
        if start > end:
            continue
        contract = Contract(conId=int(s["conid"]), includeExpired=True)
        if not await ib.qualifyContractsAsync(contract):
            logger.warning("CONID %s inconnu chez IB", s["conid"])
            continue
        if not s["symbol"]:
            _set_symbol(s["conid"], contract)
        what = "MIDPOINT" if s["type"] == "DERIVATIVES" else "TRADES"
        closes = await _daily_closes(ib, contract, start, end, what)
        _store(market_conn(), "INSERT OR REPLACE INTO close_prices (date, conid, close) VALUES (?,?,?)",
               [(d, s["conid"], c) for d, c in closes])
        logger.info("Clôtures %s : %d jours (%s → %s)", contract.symbol, len(closes), start, end)

    for ccy in sorted(currencies - {BASE_CURRENCY}):
        pair = await _fx_contract(ib, ccy)
        if pair is None or inception is None:
            continue
        start = date.fromisoformat(inception)
        if ccy in last_fx:
            start = max(start, date.fromisoformat(last_fx[ccy]) + timedelta(days=1))
        if start > today:
            continue
        contract, invert = pair
        closes = await _daily_closes(ib, contract, start, today, "MIDPOINT")
        _store(market_conn(), "INSERT OR REPLACE INTO fx_rates (date, currency, rate_usd) VALUES (?,?,?)",
               [(d, ccy, 1 / c if invert else c) for d, c in closes if c])
        (logger.info if closes else logger.warning)("FX %s/USD : %d jours (%s)", ccy, len(closes), contract.pair())


def _set_symbol(conid: str, contract: Contract) -> None:
    symbol = contract.localSymbol if contract.secType in DERIVATIVE_SECTYPES else contract.symbol
    try:
        ledger_db.set_instrument_symbol(conid, symbol)
    except sqlite3.IntegrityError:
        logger.warning("Symbole %s déjà utilisé — CONID %s laissé sans symbole", symbol, conid)


def _store(market: sqlite3.Connection, sql: str, rows: list[tuple]) -> None:
    try:
        with market:
            market.executemany(sql, rows)
    finally:
        market.close()


async def sync_cash(ib: IB, account_map: dict[str, str]) -> None:
    """Cash IB par (compte ledger, devise). account_map : id IB → id ledger."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows, unknown = [], set()
    values = ib.accountValues() or await ib.accountSummaryAsync()   # accountValues porte l'id de compte réel
    for v in values:
        if v.tag != "CashBalance" or v.currency in ("BASE", ""):
            continue
        account = account_map.get(v.account)
        if account is None:
            unknown.add(v.account)
            continue
        rows.append((account, v.currency, float(v.value), now))
    if unknown:
        logger.warning("Comptes IB non mappés (IB_ACCOUNTS dans main.py) : %s", sorted(unknown))
    market = market_conn()
    try:
        with market:
            market.execute("DELETE FROM cash_balances")
            market.executemany("INSERT INTO cash_balances VALUES (?,?,?,?)", rows)
    finally:
        market.close()
    logger.info("Cash IB : %d soldes", len(rows))


def cash_balances(account_id: str) -> dict[str, float]:
    market = market_conn()
    try:
        rows = market.execute(
            "SELECT currency, amount FROM cash_balances WHERE account_id = ? ORDER BY currency", (account_id,)
        ).fetchall()
        return {r["currency"]: r["amount"] for r in rows}
    finally:
        market.close()


async def refresh_live(ib: IB) -> datetime:
    """Snapshot des derniers prix des positions ouvertes et des FX → live_prices."""
    positions = ledger_db.get_positions()
    conids = sorted({p["conid"] for p in positions})
    currencies = sorted({p["currency"] for p in positions} | {b["currency"] for b in ledger_db.get_cash_balances()})
    ib.reqMarketDataType(MARKET_DATA_TYPE)

    keys: dict[int, tuple[str, bool]] = {}        # conId IB → (clé live_prices, inverser ?)
    contracts = []
    for c in await ib.qualifyContractsAsync(*[Contract(conId=int(c)) for c in conids]):
        keys[c.conId] = (str(c.conId), False)
        contracts.append(c)
    for ccy in currencies:
        pair = await _fx_contract(ib, ccy) if ccy != BASE_CURRENCY else None
        if pair:
            keys[pair[0].conId] = (f"FX:{ccy}", pair[1])
            contracts.append(pair[0])

    now = datetime.now(timezone.utc)
    rows = []
    for t in await ib.reqTickersAsync(*contracts):
        price = t.marketPrice()
        if price != price:                         # NaN → dernier close connu d'IB
            price = t.close
        if price != price or not price or price <= 0:   # IB renvoie -1 sans donnée
            continue
        key, invert = keys[t.contract.conId]
        rows.append((key, 1 / price if invert else price, now.isoformat(timespec="seconds")))
    market = market_conn()
    try:
        with market:
            market.execute("DELETE FROM live_prices")
            market.executemany("INSERT INTO live_prices (key, price, updated_at) VALUES (?,?,?)", rows)
    finally:
        market.close()
    logger.info("Prix live : %d/%d", len(rows), len(contracts))
    return now


async def contract_details(ib: IB, conid: str) -> dict | None:
    details = await ib.reqContractDetailsAsync(Contract(conId=int(conid), includeExpired=True))
    if not details:
        return None
    c = details[0].contract
    deriv = c.secType in DERIVATIVE_SECTYPES
    expiry = c.lastTradeDateOrContractMonth
    return {
        "conid": conid,
        "name": details[0].longName or c.symbol,
        "symbol": c.localSymbol if deriv else c.symbol,
        "type": "DERIVATIVES" if deriv else "DELTA_ONE",
        "currency": c.currency,
        "multiplier": float(c.multiplier or 1.0),
        "expiry": f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:8]}" if len(expiry) >= 8 else None,
        "strike": c.strike or None,
        "right": (c.right or "")[:1] or None,
    }
