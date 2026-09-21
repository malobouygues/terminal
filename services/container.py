from dataclasses import dataclass

from .ledger_service import SqliteLedgerService
from .market_service import IbMarketService
from .portfolio_service import EnginePortfolioService
from .ports import LedgerService, MarketService, PortfolioService


@dataclass(frozen=True)
class ServiceContainer:
    """Services concrets exposés à l'UI. Construit une fois au démarrage et injecté."""

    ledger: LedgerService
    portfolio: PortfolioService
    market: MarketService

    @classmethod
    def from_defaults(cls, ib=None) -> "ServiceContainer":
        return cls(ledger=SqliteLedgerService(), portfolio=EnginePortfolioService(),
                   market=IbMarketService(ib))
