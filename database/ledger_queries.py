"""Lectures du ledger (positions, cash, journal)."""

from .ledger_con import LINE_ASSET_CASH, LINE_ASSET_SECURITY, get_conn


def get_positions(open_only: bool = True) -> list[dict]:
    """Par (instrument × lot × compte) : qty, basis (Σ q·cb + ajustements), first_buy, last_sell."""
    sql = f"""
        SELECT jl.instrument_conid AS conid, jl.lot_id, jl.account_id,
               i.name, i.type, i.currency, i.multiplier, i.expiry, i.strike, i."right",
               l.date_open, l.date_close,
               SUM(jl.quantity) AS qty,
               SUM(CASE WHEN jl.quantity = 0 THEN jl.cost_basis ELSE jl.quantity * jl.cost_basis END) AS basis,
               MIN(CASE WHEN jl.quantity > 0 THEN je.date END) AS first_buy,
               MAX(CASE WHEN jl.quantity < 0 THEN je.date END) AS last_sell
        FROM journal_lines jl
        JOIN journal_entries je ON je.id = jl.entry_id
        JOIN instruments i      ON i.conid = jl.instrument_conid
        LEFT JOIN lots l        ON l.id = jl.lot_id
        WHERE jl.line_type = '{LINE_ASSET_SECURITY}'
        GROUP BY jl.instrument_conid, jl.lot_id, jl.account_id
    """
    if open_only:
        sql += " HAVING ROUND(SUM(jl.quantity), 8) != 0"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql + " ORDER BY i.name")]


def get_cash_balances(account_id: str | None = None) -> list[dict]:
    sql = f"""
        SELECT account_id, currency, SUM(amount) AS balance
        FROM journal_lines WHERE line_type = '{LINE_ASSET_CASH}'
    """
    params: list = []
    if account_id:
        sql += " AND account_id = ?"
        params.append(account_id)
    sql += " GROUP BY account_id, currency HAVING ROUND(SUM(amount), 6) != 0 ORDER BY account_id, currency"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def get_currencies_for_account(account_id: str) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT currency FROM journal_lines WHERE account_id = ? ORDER BY currency",
            (account_id,),
        ).fetchall()
        return [r["currency"] for r in rows]


def get_entries(limit: int | None = None) -> list[dict]:
    """Écritures avec leurs lignes. Tri : date desc, puis heure de la première ligne desc ;
    lignes par heure croissante."""
    sql = """
        SELECT je.id, je.date, je.transaction_type, je.external_ref, MIN(jl.created_at) AS first_time
        FROM journal_entries je JOIN journal_lines jl ON jl.entry_id = je.id
        GROUP BY je.id ORDER BY je.date DESC, first_time DESC, je.id DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    with get_conn() as conn:
        entries = {r["id"]: {**dict(r), "lines": []} for r in conn.execute(sql)}
        if not entries:
            return []
        ids = ",".join("?" * len(entries))
        lines = conn.execute(
            f"""
            SELECT jl.*, i.name AS instrument_name, i.type AS instrument_type
            FROM journal_lines jl LEFT JOIN instruments i ON i.conid = jl.instrument_conid
            WHERE jl.entry_id IN ({ids}) ORDER BY jl.created_at, jl.id
            """,
            list(entries),
        )
        for ln in lines:
            entries[ln["entry_id"]]["lines"].append(dict(ln))
        return list(entries.values())
