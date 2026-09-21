"""Connexion, référentiels, instruments et lots du ledger.

Trois bases SQLite isolées (jamais d'ATTACH) :
  ledger.db      — source de vérité append-only
  market_data.db — cache refetchable (IB Gateway)
  analytics.db   — performance dérivée, recalculée au démarrage
"""

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("TERMINAL_DATA_DIR", PROJECT_ROOT / "__datacache__"))

LEDGER_PATH    = DATA_DIR / "ledger.db"
MARKET_PATH    = DATA_DIR / "market_data.db"
ANALYTICS_PATH = DATA_DIR / "analytics.db"

_SCHEMA_DIR      = Path(__file__).resolve().parent
LEDGER_SCHEMA    = _SCHEMA_DIR / "ledger.sql"
MARKET_SCHEMA    = _SCHEMA_DIR / "market_data.sql"
ANALYTICS_SCHEMA = _SCHEMA_DIR / "analytics.sql"

ACCOUNTS = ("IBK_LONG", "IBK_LEV")
BASE_CURRENCY = "USD"

LINE_ASSET_CASH     = "ASSET_CASH"
LINE_ASSET_SECURITY = "ASSET_SECURITY"


@dataclass(frozen=True)
class LedgerLine:
    account_id:       str
    instrument_conid: str | None
    lot_id:           str | None
    quantity:         float | None
    cost_basis:       float | None
    currency:         str
    amount:           float
    line_type:        str


# ---------------------------------------------------------------------------
# Connexion / schéma
# ---------------------------------------------------------------------------

def get_conn() -> sqlite3.Connection:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(LEDGER_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_ledger_db() -> None:
    """Applique le schéma (idempotent) et migre une base à l'ancien schéma (stratégies, EUR)."""
    schema = LEDGER_SCHEMA.read_text()
    with get_conn() as conn:
        legacy = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'strategies'").fetchone()
        if legacy:
            _migrate_legacy(conn, schema)
        conn.executescript(schema)
        if conn.execute("SELECT 1 FROM lots WHERE id LIKE 'lot_%'").fetchone():
            _rename_numeric_lots(conn)
        if conn.execute("SELECT 1 FROM lots WHERE id != lower(id)").fetchone():
            _rename_lots(conn, [(r[0], r[0].lower()) for r in conn.execute("SELECT id FROM lots WHERE id != lower(id)")])


def _migrate_legacy(conn: sqlite3.Connection, schema: str) -> None:
    """Ancien schéma → nouveau : lots sans stratégie, ids 'lot_00X', amount unique, created_at."""
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript("""
        ALTER TABLE accounts        RENAME TO accounts_old;
        ALTER TABLE instruments     RENAME TO instruments_old;
        ALTER TABLE lots            RENAME TO lots_old;
        ALTER TABLE lot_instruments RENAME TO lot_instruments_old;
        ALTER TABLE journal_lines   RENAME TO journal_lines_old;
        DROP TABLE strategies;
        DROP INDEX IF EXISTS idx_entries_type;
    """)
    conn.executescript(schema)
    conn.executescript("""
        INSERT INTO instruments (conid, name, type, currency, expiry, strike, "right", multiplier)
            SELECT conid, name, type, currency, expiry, strike, "right", multiplier FROM instruments_old;
        INSERT INTO lots (id, date_open, date_close)
            SELECT 'lot_' || substr('000' || id, -3), date_open, date_close FROM lots_old;
        INSERT INTO lot_instruments (lot_id, instrument_conid)
            SELECT 'lot_' || substr('000' || lot_id, -3), instrument_conid FROM lot_instruments_old;
        INSERT INTO journal_lines (id, entry_id, account_id, instrument_conid, lot_id,
                                   quantity, cost_basis, currency, amount, line_type, created_at)
            SELECT jl.id, jl.entry_id, jl.account_id, jl.instrument_conid,
                   CASE WHEN jl.lot_id IS NULL THEN NULL ELSE 'lot_' || substr('000' || jl.lot_id, -3) END,
                   jl.quantity, jl.cost_basis, jl.currency, jl.amount_txn, jl.line_type,
                   je.date || ' 00:00:00'
            FROM journal_lines_old jl JOIN journal_entries je ON je.id = jl.entry_id;
        DROP TABLE journal_lines_old;
        DROP TABLE lot_instruments_old;
        DROP TABLE lots_old;
        DROP TABLE instruments_old;
        DROP TABLE accounts_old;
    """)
    conn.execute("PRAGMA foreign_keys = ON")


def _rename_numeric_lots(conn: sqlite3.Connection) -> None:
    """'lot_003' → 'Blo_01' : préfixe unique du premier instrument du lot, numéroté par security."""
    rows = conn.execute(
        """
        SELECT l.id, i.name, i.conid FROM lots l
        JOIN lot_instruments li ON li.lot_id = l.id JOIN instruments i ON i.conid = li.instrument_conid
        WHERE l.id LIKE 'lot_%' GROUP BY l.id ORDER BY l.date_open, l.id
        """
    ).fetchall()
    for r in rows:
        prefix = _unique_prefix(conn, r["name"], r["conid"])
        _rename_lots(conn, [(r["id"], f"{prefix}_{_next_number(conn, prefix):02d}")])


def _rename_lots(conn: sqlite3.Connection, renames: list[tuple[str, str]]) -> None:
    conn.execute("PRAGMA foreign_keys = OFF")
    for old, new in renames:
        for table, col in (("lots", "id"), ("lot_instruments", "lot_id"), ("journal_lines", "lot_id")):
            conn.execute(f"UPDATE {table} SET {col} = ? WHERE {col} = ?", (new, old))
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")


# ---------------------------------------------------------------------------
# Référentiels
# ---------------------------------------------------------------------------

def get_currencies() -> list[str]:
    with get_conn() as conn:
        return [r["code"] for r in conn.execute("SELECT code FROM currencies ORDER BY code")]


def get_accounts() -> list[str]:
    with get_conn() as conn:
        return [r["id"] for r in conn.execute("SELECT id FROM accounts ORDER BY id")]


def validate_currency(conn: sqlite3.Connection, code: str) -> None:
    if conn.execute("SELECT 1 FROM currencies WHERE code = ?", (code,)).fetchone() is None:
        raise ValueError(f"Unknown currency: {code!r}")


def validate_account(conn: sqlite3.Connection, account_id: str) -> None:
    if conn.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,)).fetchone() is None:
        raise ValueError(f"Unknown account: {account_id!r}")


# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------

def get_instruments() -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM instruments ORDER BY name")]


def get_instrument(conid: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM instruments WHERE conid = ?", (conid,)).fetchone()
        return dict(row) if row else None


def upsert_instrument(
    conid: str, name: str, type: str, currency: str,
    expiry: str | None = None, strike: float | None = None,
    right: str | None = None, multiplier: float = 1.0, symbol: str | None = None,
) -> None:
    with get_conn() as conn:
        validate_currency(conn, currency)
        conn.execute(
            """
            INSERT INTO instruments (conid, name, symbol, type, currency, expiry, strike, "right", multiplier)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(conid) DO UPDATE SET
                name=excluded.name, symbol=COALESCE(excluded.symbol, instruments.symbol),
                currency=excluded.currency, expiry=excluded.expiry, strike=excluded.strike,
                "right"=excluded."right", multiplier=excluded.multiplier
            """,
            (conid, name, symbol, type, currency, expiry, strike, right, multiplier),
        )
        conn.commit()


def set_instrument_symbol(conid: str, symbol: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE instruments SET symbol = ? WHERE conid = ?", (symbol, conid))
        conn.commit()


# ---------------------------------------------------------------------------
# Lots
# ---------------------------------------------------------------------------

def get_lot(lot_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM lots WHERE id = ?", (lot_id,)).fetchone()
        return dict(row) if row else None


def _unique_prefix(conn: sqlite3.Connection, name: str, conid: str | None) -> str:
    """Trois premières lettres du Name ; si une autre security utilise déjà ce préfixe,
    la troisième lettre tourne dans l'alphabet jusqu'à un préfixe libre."""
    base = name.strip()[:3].lower()
    owners: dict[str, set[str]] = {}
    for lot_id, c in conn.execute("SELECT lot_id, instrument_conid FROM lot_instruments"):
        owners.setdefault(lot_id.split("_")[0], set()).add(c)
    third = base[2] if len(base) > 2 else "a"
    letters = "abcdefghijklmnopqrstuvwxyz"
    start = max(letters.find(third), 0)
    for i in range(len(letters) + 1):
        candidate = base[:2] + (third if i == 0 else letters[(start + i) % len(letters)])
        if candidate not in owners or (conid is not None and conid in owners[candidate]):
            return candidate
    raise ValueError(f"No free lot prefix for {name!r}")


def _next_number(conn: sqlite3.Connection, prefix: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM lots WHERE substr(id, 1, 4) = ?", (prefix + "_",)).fetchone()[0] + 1


def next_lot_id(name: str, conid: str | None = None) -> str:
    """'tes_02' = préfixe unique (minuscules) de la security + n° de la trade idea sur cette security."""
    with get_conn() as conn:
        prefix = _unique_prefix(conn, name, conid)
        return f"{prefix}_{_next_number(conn, prefix):02d}"


def open_lot_for(conid: str) -> str | None:
    """Lot actif contenant l'instrument, s'il existe."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT l.id FROM lots l JOIN lot_instruments li ON li.lot_id = l.id
            WHERE li.instrument_conid = ? AND l.date_close IS NULL
            ORDER BY l.date_open DESC LIMIT 1
            """,
            (conid,),
        ).fetchone()
        return row["id"] if row else None


def create_lot(lot_id: str, date_open: str) -> None:
    with get_conn() as conn:
        conn.execute("INSERT INTO lots (id, date_open) VALUES (?,?)", (lot_id, date_open))
        conn.commit()


def close_lot(lot_id: str, date_close: str) -> None:
    """Seule mutation tolérée sur lots : poser date_close (cycle de vie, pas une écriture comptable)."""
    with get_conn() as conn:
        conn.execute("UPDATE lots SET date_close = ? WHERE id = ?", (date_close, lot_id))
        conn.commit()


def check_lot_open(conn: sqlite3.Connection, lot_id: str) -> None:
    row = conn.execute("SELECT date_close FROM lots WHERE id = ?", (lot_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown lot: {lot_id!r}")
    if row["date_close"] is not None:
        raise ValueError(f"Lot {lot_id!r} is closed (since {row['date_close']})")


def link_lot_instrument(lot_id: str, conid: str) -> None:
    with get_conn() as conn:
        check_lot_open(conn, lot_id)
        conn.execute(
            "INSERT OR IGNORE INTO lot_instruments (lot_id, instrument_conid) VALUES (?,?)",
            (lot_id, conid),
        )
        conn.commit()
