import asyncio
from dataclasses import asdict

from engine import performance, portfolio


class EnginePortfolioService:
    """Snapshots calculés par engine/, wrappés async."""

    async def holdings_snapshot(self) -> list[dict]:
        rows = await asyncio.to_thread(portfolio.holdings)
        return [asdict(r) for r in rows]

    async def cash(self) -> list[tuple[str, float, float]]:
        return await asyncio.to_thread(portfolio.cash)

    async def allocation(self) -> list[tuple[str, float, float]]:
        return await asyncio.to_thread(portfolio.allocation)

    async def performance(self) -> list[dict]:
        return await asyncio.to_thread(performance.load)

    async def daily_table(self, start: str, end: str) -> tuple[list[str], list[list]]:
        return await asyncio.to_thread(performance.daily_table, start, end)
