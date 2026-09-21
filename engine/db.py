"""Connexions du moteur et lectures market_data (base USD).

Cotation manquante → dernier cours disponible avant la date (price_at / fx_at).
"""

import bisect
import sqlite3
from pathlib import Path

from database.ledger_con import (  # noqa: F401
    ANALYTICS_PATH, ANALYTICS_SCHEMA, LEDGER_PATH, MARKET_PATH, MARKET_SCHEMA,
    BASE_CURRENCY, init_ledger_db,
)


def _conn(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def ledger_conn() -> sqlite3.Connection:
    return _conn(LEDGER_PATH)


def market_conn() -> sqlite3.Connection:
    return _conn(MARKET_PATH)


def analytics_conn() -> sqlite3.Connection:
    return _conn(ANALYTICS_PATH)


def ensure_schemas() -> None:
    """Applique les trois schémas (idempotent) ; migre les bases à l'ancien schéma EUR."""
    init_ledger_db()
    market = market_conn()
    try:
        legacy = market.execute("SELECT 1 FROM pragma_table_info('fx_rates') WHERE name = 'quote'").fetchone()
        if legacy:
            market.executescript("DROP TABLE fx_rates; DROP TABLE close_prices;")
        market.executescript(MARKET_SCHEMA.read_text())
    finally:
        market.close()
    analytics = analytics_conn()
    try:
        analytics.executescript(ANALYTICS_SCHEMA.read_text())
    finally:
        analytics.close()


# ---------------------------------------------------------------------------
# Séries de marché — {clé: ([dates triées], [valeurs])}
# ---------------------------------------------------------------------------

Series = dict[str, tuple[list[str], list[float]]]


def load_closes(market: sqlite3.Connection) -> Series:
    return _series(market.execute("SELECT conid, date, close FROM close_prices ORDER BY conid, date"))


def load_fx(market: sqlite3.Connection) -> Series:
    return _series(market.execute("SELECT currency, date, rate_usd FROM fx_rates ORDER BY currency, date"))


def _series(rows) -> Series:
    out: Series = {}
    for key, date, value in rows:
        dates, values = out.setdefault(key, ([], []))
        dates.append(date)
        values.append(float(value))
    return out


def value_at(series: Series, key: str, date: str) -> float | None:
    """Dernière valeur connue à la date ou avant."""
    if key not in series:
        return None
    dates, values = series[key]
    i = bisect.bisect_right(dates, date)
    return values[i - 1] if i else None


def fx_at(fx: Series, currency: str, date: str) -> float | None:
    return 1.0 if currency == BASE_CURRENCY else value_at(fx, currency, date)


def load_live(market: sqlite3.Connection) -> tuple[dict[str, float], str | None]:
    """Prix intraday (conid → prix, 'FX:CCY' → taux USD) et horodatage du dernier refresh."""
    rows = market.execute("SELECT key, price, updated_at FROM live_prices").fetchall()
    prices = {r["key"]: float(r["price"]) for r in rows}
    updated = max((r["updated_at"] for r in rows), default=None)
    return prices, updated
