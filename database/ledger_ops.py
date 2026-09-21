"""Écritures du ledger.

  · Une écriture (entry + lignes) est insérée d'un bloc ; elle se corrige en
    la supprimant (delete_entry) ou en la remplaçant (replace_id) — jamais ligne à ligne.
  · Idempotence des imports via journal_entries.external_ref UNIQUE.
  · Un TRADE écrit deux lignes (ASSET_SECURITY + ASSET_CASH opposée) ; les flux
    externes (DEPOSIT, DIVIDEND, FEE, TAX) une seule ligne ASSET_CASH.
  · Les ajustements de coût sans mouvement de quantité portent quantity = 0 et
    un cost_basis TOTAL — neutres pour le WAC SUM(q·cb)/SUM(q).
  · Un lot clôturé (date_close) n'accepte plus aucune écriture.
"""

import sqlite3
from datetime import datetime

from .ledger_con import (
    LedgerLine, LINE_ASSET_CASH, LINE_ASSET_SECURITY,
    get_conn, check_lot_open, validate_account, validate_currency,
)

MERGER_MODES = frozenset({"SHARES", "CASH", "MIX"})
RIGHTS_MODES = frozenset({"SELL", "EXERCISE"})


class DuplicateEntryError(Exception):
    """external_ref déjà présent — re-import détecté."""


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def entry_exists(external_ref: str) -> bool:
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM journal_entries WHERE external_ref = ?", (external_ref,)
        ).fetchone() is not None


def _insert_entry(conn, date: str, transaction_type: str, external_ref: str | None) -> int:
    try:
        cur = conn.execute(
            "INSERT INTO journal_entries (date, transaction_type, external_ref) VALUES (?,?,?)",
            (date, transaction_type, external_ref),
        )
    except sqlite3.IntegrityError as ex:
        if "external_ref" in str(ex):
            raise DuplicateEntryError(f"external_ref already recorded: {external_ref!r}") from ex
        raise
    return int(cur.lastrowid)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")     # heure locale (Paris)


def _insert_lines(conn, entry_id: int, lines: list[LedgerLine],
                  check_lots: bool = True, created_at: str | None = None) -> None:
    created_at = created_at or _now()
    for ln in lines:
        validate_account(conn, ln.account_id)
        validate_currency(conn, ln.currency)
        if check_lots and ln.lot_id is not None:
            check_lot_open(conn, ln.lot_id)
        conn.execute(
            """
            INSERT INTO journal_lines
                (entry_id, account_id, instrument_conid, lot_id, quantity, cost_basis,
                 currency, amount, line_type, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (entry_id, ln.account_id, ln.instrument_conid, ln.lot_id, ln.quantity, ln.cost_basis,
             ln.currency, ln.amount, ln.line_type, created_at),
        )


def _delete_entry(conn, entry_id: int, keep_lots: bool = False) -> str | None:
    """Supprime l'écriture (lignes en cascade) et ajuste le cycle de vie des lots touchés
    (keep_lots : remplacement en cours, le lot vide est conservé pour la réinsertion).
    Retourne l'heure de saisie d'origine (conservée lors d'un remplacement)."""
    lines = conn.execute(
        "SELECT lot_id, MIN(created_at) AS created_at FROM journal_lines WHERE entry_id = ? GROUP BY lot_id",
        (entry_id,),
    ).fetchall()
    if not lines:
        raise ValueError(f"Unknown journal entry: {entry_id}")
    created_at = min(ln["created_at"] for ln in lines)
    conn.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))
    for lot_id in {ln["lot_id"] for ln in lines if ln["lot_id"]}:
        if conn.execute("SELECT 1 FROM journal_lines WHERE lot_id = ? LIMIT 1", (lot_id,)).fetchone() is None:
            if not keep_lots:
                conn.execute("DELETE FROM lots WHERE id = ?", (lot_id,))
        else:
            _close_lot_if_flat(conn, lot_id, None)
    return created_at


def delete_entry(entry_id: int) -> None:
    with get_conn() as conn:
        _delete_entry(conn, entry_id)
        conn.commit()


def _write(date: str, tx_type: str, external_ref: str | None, lines: list[LedgerLine],
           replace_id: int | None = None) -> int:
    """Une écriture = une transaction SQLite (entry + toutes ses lignes).
    replace_id : écriture remplacée (supprimée dans la même transaction, heure conservée)."""
    with get_conn() as conn:
        created_at = _delete_entry(conn, replace_id) if replace_id else None
        entry_id = _insert_entry(conn, date, tx_type, external_ref)
        _insert_lines(conn, entry_id, lines, created_at=created_at)
        conn.commit()
        return entry_id


def _position(conn, account_id: str, conid: str, lot_id: str) -> tuple[float, float | None]:
    """(qty, avg_cost) courants d'une position — formule WAC invariante."""
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(quantity), 0.0) AS qty,
               CASE WHEN SUM(quantity) = 0 THEN NULL
                    ELSE SUM(quantity * cost_basis) / SUM(quantity) END AS avg_cost
        FROM journal_lines
        WHERE line_type = '{LINE_ASSET_SECURITY}'
          AND account_id = ? AND instrument_conid = ? AND lot_id = ?
        """,
        (account_id, conid, lot_id),
    ).fetchone()
    return float(row["qty"]), (float(row["avg_cost"]) if row["avg_cost"] is not None else None)


def _open_positions_for(conn, conid: str) -> list[sqlite3.Row]:
    """Positions ouvertes (compte × lot) détenant un instrument."""
    return conn.execute(
        f"""
        SELECT account_id, lot_id, SUM(quantity) AS qty,
               SUM(quantity * cost_basis) / SUM(quantity) AS avg_cost, MIN(currency) AS currency
        FROM journal_lines
        WHERE line_type = '{LINE_ASSET_SECURITY}' AND instrument_conid = ?
        GROUP BY account_id, lot_id
        HAVING ROUND(SUM(quantity), 8) != 0
        """,
        (conid,),
    ).fetchall()


def _close_lot_if_flat(conn, lot_id: str, date: str | None) -> None:
    """Toutes les positions du lot à zéro → lot clôturé (à `date`, sinon à la dernière cession) ;
    sinon → lot (r)ouvert."""
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS n FROM (
            SELECT instrument_conid FROM journal_lines
            WHERE line_type = '{LINE_ASSET_SECURITY}' AND lot_id = ?
            GROUP BY instrument_conid, account_id HAVING ROUND(SUM(quantity), 8) != 0)
        """,
        (lot_id,),
    ).fetchone()
    if row["n"] == 0:
        if date is None:
            date = conn.execute(
                f"""SELECT MAX(je.date) FROM journal_lines jl JOIN journal_entries je ON je.id = jl.entry_id
                    WHERE jl.lot_id = ? AND jl.line_type = '{LINE_ASSET_SECURITY}' AND jl.quantity < 0""",
                (lot_id,),
            ).fetchone()[0]
        conn.execute("UPDATE lots SET date_close = ? WHERE id = ?", (date, lot_id))
    else:
        conn.execute("UPDATE lots SET date_close = NULL WHERE id = ?", (lot_id,))


def _instrument_currency(conn, conid: str) -> str:
    row = conn.execute("SELECT currency FROM instruments WHERE conid = ?", (conid,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown instrument: {conid!r} — upsert it first")
    return row["currency"]


# ---------------------------------------------------------------------------
# Flux cash — lignes ASSET_CASH
# ---------------------------------------------------------------------------

def _cash(account_id: str, amount: float, currency: str,
          conid: str | None = None, lot_id: str | None = None) -> LedgerLine:
    return LedgerLine(account_id, conid, lot_id, None, None, currency, amount, LINE_ASSET_CASH)


def add_deposit(date: str, account_id: str, amount: float, currency: str,
                external_ref: str | None = None, replace_id: int | None = None) -> int:
    if amount <= 0:
        raise ValueError("Amount must be > 0")
    return _write(date, "DEPOSIT", external_ref, [_cash(account_id, +amount, currency)], replace_id)


def add_withdrawal(date: str, account_id: str, amount: float, currency: str,
                external_ref: str | None = None, replace_id: int | None = None) -> int:
    if amount <= 0:
        raise ValueError("Amount must be > 0")
    return _write(date, "WITHDRAWAL", external_ref, [_cash(account_id, -amount, currency)], replace_id)


def add_transfer(date: str, from_account: str, to_account: str, amount: float, currency: str,
                 external_ref: str | None = None, replace_id: int | None = None) -> int:
    if amount <= 0:
        raise ValueError("Amount must be > 0")
    if from_account == to_account:
        raise ValueError("From and To accounts must differ")
    return _write(date, "TRANSFER", external_ref, [
        _cash(from_account, -amount, currency), _cash(to_account, +amount, currency),
    ], replace_id)


def add_dividend(date: str, account_id: str, conid: str, lot_id: str, amount: float, currency: str,
                 external_ref: str | None = None) -> int:
    return _write(date, "DIVIDEND", external_ref, [_cash(account_id, +amount, currency, conid, lot_id)])


def add_fee(date: str, account_id: str, amount: float, currency: str,
            lot_id: str | None = None, external_ref: str | None = None) -> int:
    return _write(date, "FEE", external_ref, [_cash(account_id, -amount, currency, None, lot_id)])


def add_tax(date: str, account_id: str, amount: float, currency: str,
            external_ref: str | None = None) -> int:
    return _write(date, "TAX", external_ref, [_cash(account_id, -amount, currency)])


def add_fx_conversion(date: str, account_id: str, sold_amount: float, sold_currency: str,
                      bought_amount: float, bought_currency: str,
                      external_ref: str | None = None) -> int:
    if sold_currency == bought_currency:
        raise ValueError("FX conversion requires two different currencies")
    return _write(date, "FX_CONV", external_ref, [
        _cash(account_id, -sold_amount, sold_currency), _cash(account_id, +bought_amount, bought_currency),
    ])


# ---------------------------------------------------------------------------
# TRADE — ASSET_SECURITY + ASSET_CASH opposée
# ---------------------------------------------------------------------------

def add_trade(
    date: str, account_id: str, conid: str, lot_id: str,
    side: str, quantity: float, amount: float, currency: str,
    cost_basis: float | None = None,     # BUY : prix unitaire fees inclus (requis) ; SELL : WAC courant
    external_ref: str | None = None, replace_id: int | None = None,
) -> int:
    if quantity <= 0:
        raise ValueError("Quantity must be > 0")
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be BUY or SELL, got {side!r}")
    sign = +1 if side == "BUY" else -1
    with get_conn() as conn:
        created_at = _delete_entry(conn, replace_id, keep_lots=True) if replace_id else None
        if side == "BUY" and cost_basis is None:
            raise ValueError("cost_basis is required on BUY (unit price, fees included)")
        if side == "SELL":
            held, wac = _position(conn, account_id, conid, lot_id)
            if wac is None or held < quantity - 1e-9:
                raise ValueError(f"Position {held} of {conid!r} in lot {lot_id!r} — cannot sell {quantity}")
            cost_basis = wac
        entry_id = _insert_entry(conn, date, "TRADE", external_ref)
        _insert_lines(conn, entry_id, [
            LedgerLine(account_id, conid, lot_id, sign * quantity, cost_basis,
                       currency, sign * amount, LINE_ASSET_SECURITY),
            LedgerLine(account_id, None, lot_id, None, None, currency, -sign * amount, LINE_ASSET_CASH),
        ], check_lots=replace_id is None, created_at=created_at)
        _close_lot_if_flat(conn, lot_id, date)
        conn.commit()
        return entry_id


# ---------------------------------------------------------------------------
# Corporate actions
# ---------------------------------------------------------------------------

def apply_split(date: str, conid: str, ratio: float, external_ref: str | None = None) -> int:
    """Par (compte × lot) : -qty @ WAC puis +qty×ratio @ WAC/ratio. Coût total invariant."""
    if ratio <= 0:
        raise ValueError("Split ratio must be > 0")
    with get_conn() as conn:
        positions = _open_positions_for(conn, conid)
        if not positions:
            raise ValueError(f"No open position for instrument {conid!r}")
        lines = []
        for pos in positions:
            qty, avg, ccy = float(pos["qty"]), float(pos["avg_cost"]), pos["currency"]
            lines.append(LedgerLine(pos["account_id"], conid, pos["lot_id"], -qty, avg, ccy, 0.0, LINE_ASSET_SECURITY))
            lines.append(LedgerLine(pos["account_id"], conid, pos["lot_id"], +qty * ratio, avg / ratio, ccy, 0.0, LINE_ASSET_SECURITY))
        entry_id = _insert_entry(conn, date, "SPLIT", external_ref)
        _insert_lines(conn, entry_id, lines)
        conn.commit()
        return entry_id


def apply_spinoff(date: str, account_id: str, lot_id: str, parent_conid: str, child_conid: str,
                  cb_allocated_per_parent_share: float, qty_received: float,
                  external_ref: str | None = None) -> int:
    """Mère : qty 0, cost_basis = -total alloué ; fille : qty reçue @ total / qty. Même lot."""
    if qty_received <= 0 or cb_allocated_per_parent_share <= 0:
        raise ValueError("qty_received and cb_allocated_per_parent_share must be > 0")
    with get_conn() as conn:
        parent_qty, _ = _position(conn, account_id, parent_conid, lot_id)
        if parent_qty <= 0:
            raise ValueError(f"No open parent position for {parent_conid!r} in lot {lot_id!r}")
        parent_ccy, child_ccy = _instrument_currency(conn, parent_conid), _instrument_currency(conn, child_conid)
        total = cb_allocated_per_parent_share * parent_qty
        entry_id = _insert_entry(conn, date, "SPIN-OFF", external_ref)
        _insert_lines(conn, entry_id, [
            LedgerLine(account_id, parent_conid, lot_id, 0.0, -total, parent_ccy, 0.0, LINE_ASSET_SECURITY),
            LedgerLine(account_id, child_conid, lot_id, qty_received, total / qty_received, child_ccy, 0.0, LINE_ASSET_SECURITY),
        ])
        conn.execute("INSERT OR IGNORE INTO lot_instruments (lot_id, instrument_conid) VALUES (?,?)", (lot_id, child_conid))
        conn.commit()
        return entry_id


def apply_merger(date: str, account_id: str, lot_id: str, source_conid: str, mode: str,
                 new_conid: str | None = None, qty_new: float | None = None,
                 cash_received: float = 0.0, cash_currency: str | None = None,
                 cost_alloc_shares: float | None = None, external_ref: str | None = None) -> int:
    """SHARES : le nouveau conid reprend le coût ; CASH : lot clôturé ; MIX : les deux."""
    if mode not in MERGER_MODES:
        raise ValueError(f"mode must be one of {sorted(MERGER_MODES)}, got {mode!r}")
    with get_conn() as conn:
        qty_src, avg_src = _position(conn, account_id, source_conid, lot_id)
        if qty_src == 0 or avg_src is None:
            raise ValueError(f"No open position for {source_conid!r} in lot {lot_id!r}")
        src_ccy = _instrument_currency(conn, source_conid)
        total_cost = qty_src * avg_src
        lines = [LedgerLine(account_id, source_conid, lot_id, -qty_src, avg_src, src_ccy, 0.0, LINE_ASSET_SECURITY)]
        if mode in ("SHARES", "MIX"):
            if not new_conid or not qty_new or qty_new <= 0:
                raise ValueError("SHARES/MIX merger requires new_conid and qty_new > 0")
            carried = total_cost if mode == "SHARES" else cost_alloc_shares
            if carried is None:
                raise ValueError("MIX merger requires cost_alloc_shares")
            lines.append(LedgerLine(account_id, new_conid, lot_id, qty_new, carried / qty_new,
                                    _instrument_currency(conn, new_conid), 0.0, LINE_ASSET_SECURITY))
        if mode in ("CASH", "MIX"):
            if cash_received <= 0 or cash_currency is None:
                raise ValueError("CASH/MIX merger requires cash_received > 0 and cash_currency")
            lines.append(_cash(account_id, +cash_received, cash_currency, None, lot_id))
        entry_id = _insert_entry(conn, date, "MERGER", external_ref)
        _insert_lines(conn, entry_id, lines)
        if new_conid and mode in ("SHARES", "MIX"):
            conn.execute("INSERT OR IGNORE INTO lot_instruments (lot_id, instrument_conid) VALUES (?,?)", (lot_id, new_conid))
        if mode == "CASH":
            conn.execute("UPDATE lots SET date_close = ? WHERE id = ?", (date, lot_id))
        conn.commit()
        return entry_id


def apply_rights(date: str, account_id: str, lot_id: str, rights_conid: str, underlying_conid: str,
                 mode: str, qty_rights: float, proceeds: float = 0.0,
                 qty_shares_received: float = 0.0, subscription_price: float = 0.0,
                 rights_name: str | None = None, external_ref: str | None = None) -> int:
    """Les droits sortent à cost_basis 0. SELL encaisse ; EXERCISE reçoit le sous-jacent et décaisse."""
    if mode not in RIGHTS_MODES:
        raise ValueError(f"mode must be one of {sorted(RIGHTS_MODES)}, got {mode!r}")
    if qty_rights <= 0:
        raise ValueError("qty_rights must be > 0")
    with get_conn() as conn:
        underlying = conn.execute("SELECT name, currency FROM instruments WHERE conid = ?", (underlying_conid,)).fetchone()
        if underlying is None:
            raise ValueError(f"Unknown underlying instrument: {underlying_conid!r}")
        ccy = underlying["currency"]
        conn.execute(
            "INSERT OR IGNORE INTO instruments (conid, name, type, currency) VALUES (?,?,'DELTA_ONE',?)",
            (rights_conid, rights_name or f"{underlying['name']} rights", ccy),
        )
        lines = [LedgerLine(account_id, rights_conid, lot_id, -qty_rights, 0.0, ccy, 0.0, LINE_ASSET_SECURITY)]
        if mode == "SELL":
            if proceeds <= 0:
                raise ValueError("SELL rights requires proceeds > 0")
            lines.append(_cash(account_id, +proceeds, ccy, None, lot_id))
        else:
            if qty_shares_received <= 0 or subscription_price <= 0:
                raise ValueError("EXERCISE requires qty_shares_received > 0 and subscription_price > 0")
            lines.append(LedgerLine(account_id, underlying_conid, lot_id, +qty_shares_received,
                                    subscription_price, ccy, 0.0, LINE_ASSET_SECURITY))
            lines.append(_cash(account_id, -qty_shares_received * subscription_price, ccy, None, lot_id))
        entry_id = _insert_entry(conn, date, "RIGHTS_ISSUE", external_ref)
        _insert_lines(conn, entry_id, lines)
        conn.execute("INSERT OR IGNORE INTO lot_instruments (lot_id, instrument_conid) VALUES (?,?)", (lot_id, rights_conid))
        conn.commit()
        return entry_id


def apply_wash_sale(date: str, account_id: str, conid: str, repurchase_lot_id: str,
                    disallowed_amount: float, source_lot_id: str,
                    external_ref: str | None = None) -> int:
    """La perte refusée majore le coût du lot de rachat (ligne qty 0, cost_basis TOTAL positif)."""
    if disallowed_amount <= 0:
        raise ValueError("disallowed_amount must be > 0")
    if external_ref is None:
        external_ref = f"WASH_SALE:{source_lot_id}:{date}:{repurchase_lot_id}"
    with get_conn() as conn:
        ccy = _instrument_currency(conn, conid)
        entry_id = _insert_entry(conn, date, "WASH_SALE", external_ref)
        _insert_lines(conn, entry_id, [
            LedgerLine(account_id, conid, repurchase_lot_id, 0.0, +disallowed_amount, ccy, 0.0, LINE_ASSET_SECURITY),
        ])
        conn.commit()
        return entry_id


# ---------------------------------------------------------------------------
# Contre-passation — la seule voie de correction du ledger
# ---------------------------------------------------------------------------

def reverse_entry(entry_id: int, date: str | None = None) -> int:
    """Écrit l'entrée opposée ; l'original reste intact. external_ref = 'REV:<ref ou id>'."""
    with get_conn() as conn:
        orig = conn.execute(
            "SELECT date, transaction_type, external_ref FROM journal_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if orig is None:
            raise ValueError(f"Unknown journal entry: {entry_id}")
        lines = conn.execute("SELECT * FROM journal_lines WHERE entry_id = ?", (entry_id,)).fetchall()
        rev_id = _insert_entry(conn, date or orig["date"], orig["transaction_type"],
                               f"REV:{orig['external_ref'] or entry_id}")
        rev_lines = []
        for ln in lines:
            qty, cb = ln["quantity"], ln["cost_basis"]
            if qty:
                qty = -qty                    # position : quantité inversée, coût unitaire conservé
            elif qty == 0 and cb is not None:
                cb = -cb                      # ajustement qty=0 : c'est le coût TOTAL qu'on inverse
            rev_lines.append(LedgerLine(ln["account_id"], ln["instrument_conid"], ln["lot_id"],
                                        qty, cb, ln["currency"], -ln["amount"], ln["line_type"]))
        _insert_lines(conn, rev_id, rev_lines, check_lots=False)
        for lot_id in {ln.lot_id for ln in rev_lines if ln.lot_id}:
            _close_lot_if_flat(conn, lot_id, date or orig["date"])
        conn.commit()
        return rev_id
