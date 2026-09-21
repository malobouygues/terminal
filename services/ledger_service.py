import asyncio

from database import ledger_db
from engine import performance


class SqliteLedgerService:
    """Wrappe l'API synchrone database.ledger_db avec asyncio.to_thread
    pour ne jamais bloquer la boucle Qt."""

    async def list_accounts(self) -> list[str]:
        return await asyncio.to_thread(ledger_db.get_accounts)

    async def list_currencies(self) -> list[str]:
        return await asyncio.to_thread(ledger_db.get_currencies)

    async def list_currencies_for_account(self, account_id: str) -> list[str]:
        return await asyncio.to_thread(ledger_db.get_currencies_for_account, account_id)

    async def cash_balances(self, account_id: str) -> dict[str, float]:
        rows = await asyncio.to_thread(ledger_db.get_cash_balances, account_id)
        return {r["currency"]: r["balance"] for r in rows}

    async def add_deposit(self, date, to_account, amount, currency, replace_id=None) -> None:
        await self._write(ledger_db.add_deposit, date, to_account, amount, currency, None, replace_id)

    async def add_withdrawal(self, date, from_account, amount, currency, replace_id=None) -> None:
        await self._write(ledger_db.add_withdrawal, date, from_account, amount, currency, None, replace_id)

    async def add_transfer(self, date, from_account, to_account, amount, currency, replace_id=None) -> None:
        await self._write(ledger_db.add_transfer, date, from_account, to_account, amount, currency, None, replace_id)

    async def delete_entry(self, entry_id: int) -> None:
        await self._write(ledger_db.delete_entry, entry_id)

    async def list_entries(self, limit: int | None = None) -> list[dict]:
        return await asyncio.to_thread(ledger_db.get_entries, limit)

    async def list_instruments(self) -> list[dict]:
        """Instruments du ledger ; ``active`` = détenu dans un lot actif."""
        def _list():
            active = {p["conid"] for p in ledger_db.get_positions()}
            return [{**i, "active": i["conid"] in active} for i in ledger_db.get_instruments()]
        return await asyncio.to_thread(_list)

    async def instrument_context(self, conid: str) -> dict:
        """{'position': qty ouverte totale, 'lot_id': lot actif contenant l'instrument ou None}."""
        def _ctx():
            qty = sum(p["qty"] for p in ledger_db.get_positions() if p["conid"] == conid)
            return {"position": qty, "lot_id": ledger_db.open_lot_for(conid)}
        return await asyncio.to_thread(_ctx)

    async def next_lot_id(self, name: str, conid: str | None = None) -> str:
        return await asyncio.to_thread(ledger_db.next_lot_id, name, conid)

    async def add_trade(self, *, date, account, conid, name, type, currency, side, quantity,
                        price, cost_basis, lot_id, expiry=None, strike=None, right=None,
                        multiplier=1.0, symbol=None, replace_id=None) -> None:
        def _do():
            ledger_db.upsert_instrument(conid, name, type, currency, expiry, strike, right, multiplier, symbol)
            if ledger_db.get_lot(lot_id) is None:
                ledger_db.create_lot(lot_id, date)
            if replace_id is None:
                ledger_db.link_lot_instrument(lot_id, conid)
            ledger_db.add_trade(date, account, conid, lot_id, side, quantity,
                                quantity * price * multiplier, currency, cost_basis, replace_id=replace_id)
            performance.recompute()
        await asyncio.to_thread(_do)

    @staticmethod
    async def _write(fn, *args) -> None:
        def _do():
            fn(*args)
            performance.recompute()
        await asyncio.to_thread(_do)
