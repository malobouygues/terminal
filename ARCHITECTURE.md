# ARCHITECTURE DU PROJET TERMINAL — Document de référence

## 1. Vue d'ensemble

Projet **Investments Terminal (Ailefroide)** :
- **Frontend** : application desktop PySide6 (style Bloomberg), boucle asyncio via qasync
- **Market data** : IB Gateway (API TWS, `ib_async`) → cache SQLite
- **Ledger** : comptabilité en partie double, append-only (SQLite)
- **Performance** : NAV / TWR quotidiens du portefeuille global, en USD

Règle de dépendance : `ui/ → services/ → database/ + engine/`. L'UI n'importe jamais
`database.*` ni `engine.*` ; les services sont injectés par constructeur (`services=` / `ledger=`).

## 2. Structure

```
terminal/
├── main.py                  # Point d'entrée : IB Gateway → login → sync → performance → frontend
├── frontend.py              # MainWindow (Home ↔ Liquid)
├── market_data.py           # IB Gateway → market_data.db (clôtures, FX, cash IB, prix live)
│
├── database/
│   ├── ledger.sql / market_data.sql / analytics.sql   # schémas (idempotents)
│   ├── ledger_con.py        # chemins, connexion, migration, référentiels, instruments, lots
│   ├── ledger_ops.py        # écritures append-only (deposit, trade, corporate actions, reverse)
│   ├── ledger_queries.py    # positions, cash, journal
│   └── ledger_db.py         # façade (point d'entrée unique)
│
├── engine/
│   ├── db.py                # connexions, ensure_schemas, séries de marché (dernier cours ≤ date)
│   ├── performance.py       # recompute() → analytics.performance (NAV / TWR), load()
│   └── portfolio.py         # holdings() / allocation() pour l'UI (USD)
│
├── services/
│   ├── ports.py             # Protocols LedgerService / PortfolioService / MarketService
│   ├── ledger_service.py    # SqliteLedgerService (asyncio.to_thread ; recompute après écriture)
│   ├── portfolio_service.py # EnginePortfolioService
│   ├── market_service.py    # IbMarketService (prix live, cash IB, détails de contrat)
│   └── container.py         # ServiceContainer.from_defaults(ib=…)
│
└── ui/
    ├── styles/              # palette, dimensions, police Bloomberg, builders QSS
    ├── models/              # HoldingsModel (+build_holdings_rows), AllocationModel, BooksModel
    ├── components/
    │   ├── widgets.py       # BloombergTableView, RatioHeaderView, TableBorderDelegate, TabButton, …
    │   ├── charts/          # PieChartWidget, LineChartWidget
    │   └── dialog/          # FramelessDialog, TradeTicketDialog (Delta-One / Derivatives),
    │                        # CashDialog, CheckDialog, OrderDialog, dialog_components
    └── pages/               # home, liquid (function bar), holdings, books, performance
```

## 3. Démarrage (`main.py`)

1. `ensure_schemas()` — applique les schémas, migre une base à l'ancien format.
2. Lance IB Gateway (`IB_GATEWAY_APP`) si aucun port API (`IB_PORTS`) ne répond ; auto-login par
   System Events si `IB_USERNAME` / `IB_PASSWORD` sont renseignés (autorisation Accessibilité
   requise) ; attend l'API (`LOGIN_TIMEOUT`, laisse le temps au 2FA).
3. `market_data.sync_history` (clôtures manquantes + FX), `sync_cash` (`IB_ACCOUNTS` : id IB →
   compte ledger), `refresh_live`.
4. `performance.recompute()` puis ouverture du frontend. La connexion IB reste ouverte : la page
   Holdings rafraîchit les prix live toutes les 5 minutes.
5. Fermeture de la fenêtre → déconnexion IB, arrêt d'IB Gateway ; le raccourci `.command` du
   Bureau ferme ensuite sa fenêtre Terminal.

Le terminal s'ouvre même sans IB Gateway (cache market_data.db).

## 4. Bases de données (`__datacache__/`)

| Base | Tables | Rôle |
|------|--------|------|
| `ledger.db` | currencies, accounts (IBK_LONG / IBK_LEV), instruments (conid, name UNIQUE, symbol UNIQUE), lots (`Tes_01` = 3 lettres du Name, 3e lettre décalée si le préfixe est pris par une autre security, + n° de trade idea ; date_close), lot_instruments, journal_entries, journal_lines (created_at = heure locale) | source de vérité |
| `market_data.db` | close_prices, fx_rates (rate_usd), live_prices, cash_balances | cache refetchable |
| `analytics.db` | performance (date, securities_usd, cash_usd, nav_usd, flows_usd, daily_return, twr_cumul) | recalculée au démarrage |

Cotation manquante → dernier cours disponible avant la date. Un lot clôturé n'accepte plus
d'écriture. Une écriture se corrige entière depuis Books (✕ supprime, ✎ rouvre le dialog et
remplace ; l'heure de saisie d'origine est conservée) ; un lot vidé est supprimé, un lot dont
la cession est retirée est rouvert.

## 5. Écrans

- **Holdings / Main View** : table LIVE (lots actifs par valeur de marché, puis une ligne par
  devise de cash convertie en USD) + HISTORIQUE (lots clôturés par date : bandeau "Last Sell",
  Rlzd PnL sous la colonne Last, rien au-delà) ; `last update` en haut à droite.
  Lot multi-instruments = ligne agrégée + sous-lignes.
- **Holdings / Allocation** : % du portefeuille par Name (+ Cash), camembert horaire depuis le haut.
- **Books** : journal_entries (date desc, heure sous la date) et leurs journal_lines (écriture à
  une ligne = une seule ligne) ; ✕ / ✎ par écriture ; `<cash>` → CashDialog ; Add Delta-One /
  Derivatives → TradeTicketDialog ; Check → données brutes journalières (clôtures, cash, FX) sur
  une plage de dates.
- **Performance** : Value (NAV USD) / Performance (TWR), périodes All-time … 1M (YTD + Performance
  par défaut), échelle adaptative.

## 6. Conventions

- Pages : `QWidget` direct, UI construite dans `__init__`, layouts QVBox / QHBox.
- Dialogs : `FramelessDialog` + `DialogSection` / `GridRow` / `create_*`.
- Écritures DB : préfixe `add_` / `apply_` ; lectures : `get_`.
- Pas de nouvelle abstraction sans nécessité fonctionnelle.
