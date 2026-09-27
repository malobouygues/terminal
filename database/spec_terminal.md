# Récap Projet — Terminal de Trading Personnel

## Vision globale
Terminal Python (desktop) pour tracker un portefeuille IBKR personnel, pensé pour évoluer vers une structure hedge fund. Source de données : IBKR Flex Query (cron 22h05 Paris). Pas d'ORM, pas de framework. Code linéaire, explicite, trader tool mindset.

---

## Architecture 3 bases SQLite

### 1. ledger.db — Source de vérité, jamais recalculée, jamais supprimée
* **Append-only strict :** Une erreur → contre-passation, jamais de `UPDATE` ou `DELETE` sur une ligne existante.
* **Idempotence :** Via `external_ref UNIQUE` sur `journal_entries` (= execId IBKR, protège contre les re-imports Flex Query).

#### Tables clés :
* **accounts** — `id TEXT PRIMARY KEY` uniquement. Ex: `'IBK_LONG'`, `'IBK_LEV'`. Pas de colonne name.
* **instruments** — PK = `conid` (Contract ID IBKR). `ticker`, `name`, `type` (`DELTA_ONE` | `DERIVATIVES`), `currency`, `underlying_conid`, `expiry`, `strike`, `right`, `multiplier`. Les droits (rights) sont `DELTA_ONE` avec `underlying_conid` renseigné.
* **lots** — `id TEXT`, `strategy` (Resilient | Tactical | Strategic), `date_open`, `date_close`. Jamais de strategy `GLOBAL` dans un lot — GLOBAL est un scope de calcul, pas une stratégie assignable.
* **lot_instruments** — liaison many-to-many lot ↔ instrument. Pas de colonne `role`.
* **journal_entries** — `date`, `transaction_type`, `external_ref`. 
  * *Types :* `DEPOSIT`, `DIVIDEND`, `FEE`, `FX_CONV`, `MERGER`, `RIGHTS`, `SPIN-OFF`, `SPLIT`, `TAX`, `TRADE`, `TRANSFER`, `WASH_SALE`, `WITHDRAWAL`.
* **journal_lines** — `entry_id`, `account_id`, `instrument_conid`, `lot_id`, `quantity`, `cost_basis`, `currency`, `amount_txn`, `amount_account`, `line_type` (`ASSET_CASH` | `ASSET_SECURITY`).

#### Règles de gestion Ledger :
* **Règle miroir :** Les `TRADE` génèrent toujours deux lignes — `ASSET_SECURITY` (position) + `ASSET_CASH` (flux cash opposé). Pas de contrainte SUM=0 globale. Les flux externes (`DEPOSIT`, `DIVIDEND`, `FEE`) génèrent une seule ligne `ASSET_CASH`.
* **Montants :** `amount_txn` = montant en devise du contrat. `amount_account` = montant converti en devise du compte, snapshot IBKR Flex Query immuable.
* **Cost Basis :** `cost_basis` = prix unitaire en devise contrat, fees inclus, toujours celui de l'achat (invariant). Peut être négatif sur les lignes de correction (SPLIT annulation, SPIN-OFF réduction mère).
* **Quantité :** `quantity` peut être `0` (pas NULL) sur les lignes `ASSET_SECURITY` sans mouvement de qty : SPLIT annulation/recréation, WASH_SALE, SPIN-OFF mère.

### 2. market_data.db — Cache refetchable, peut être wipée et reconstruite
* **close_prices** — `date`, `symbol` (ticker IBKR), `conid`, `close`, `currency`. `UNIQUE(date, symbol)`.
* **fx_rates** — `date`, `quote` (USD/AUD/CAD/CHF/DKK/GBP/HKD/NOK/SEK), `rate` (1 EUR = rate quote). Base toujours EUR.

### 3. analytics.db — Dérivée, entièrement recalculable depuis les deux autres
* **shareholders** — `id`, `name`, `entity` (`NATURAL` | `LEGAL`).
* **shareholder_positions** — historique émissions/rachats de parts. `shares_delta`, `nav_per_share`, `shares_cumul`. Lecture : `SUM(shares_delta)`, pas de running total.
* **nav_snapshots** — NAV consolidée IBK_LONG + IBK_LEV par jour. `aum_equity`, `cash_net`, `nav_total`, `shares_outstanding`, `nav_per_share`. Périmètre : `NAV_ACCOUNTS = {"IBK_LONG", "IBK_LEV"}` uniquement.
* **nav_positions_detail** — détail par instrument à chaque snapshot (qty × close / fx).
* **twr_snapshots** — 4 séries : `RESILIENT`, `TACTICAL`, `STRATEGIC`, `GLOBAL`. Chain-linking quotidien. `daily_return = (V(t) - V(t-1) - F(t)) / V(t-1)`.
* **twr_inception** — date de départ de chaque série = `MIN(lot.date_open)` de la strategy. GLOBAL = min absolu.

---

## Comptes et périmètres

```python
NAV_ACCOUNTS = {"IBK_LONG", "IBK_LEV"}   # périmètre NAV + TWR
SXO_ACCOUNTS = {"SXO_LARGE", "SXO_SMID"} # hors NAV, hors TWR
```
