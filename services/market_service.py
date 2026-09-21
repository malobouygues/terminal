import asyncio
from datetime import datetime

import market_data
from engine.db import load_live, market_conn


class IbMarketService:
    """Accès IB Gateway pour l'UI. ``ib`` peut être None (Gateway indisponible) :
    les méthodes retournent alors des valeurs vides."""

    def __init__(self, ib=None):
        self._ib = ib

    @property
    def connected(self) -> bool:
        return self._ib is not None and self._ib.isConnected()

    async def refresh_live(self) -> datetime | None:
        if not self.connected:
            return await self.last_update()
        return await market_data.refresh_live(self._ib)

    async def last_update(self) -> datetime | None:
        def _read():
            market = market_conn()
            try:
                return load_live(market)[1]
            finally:
                market.close()
        stamp = await asyncio.to_thread(_read)
        return datetime.fromisoformat(stamp) if stamp else None

    async def ib_cash(self, account_id: str) -> dict[str, float]:
        return await asyncio.to_thread(market_data.cash_balances, account_id)

    async def contract_details(self, conid: str) -> dict | None:
        if not self.connected:
            return None
        return await market_data.contract_details(self._ib, conid)

    def close(self) -> None:
        if self.connected:
            self._ib.disconnect()
