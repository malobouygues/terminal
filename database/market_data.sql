PRAGMA journal_mode = WAL;

-- ============================================================
-- MARKET_DATA.DB — cache refetchable, source IB Gateway (market_data.py).
-- Base USD : fx_rates.rate_usd = valeur en USD d'une unité de `currency`.
-- USD n'a pas de ligne (taux 1 implicite). Cotation manquante → dernier
-- cours disponible avant la date (engine.db.price_at / fx_at).
-- ============================================================

CREATE TABLE IF NOT EXISTS close_prices (
    date  TEXT NOT NULL,                 -- 'YYYY-MM-DD'
    conid TEXT NOT NULL,                 -- → ledger.instruments.conid
    close REAL NOT NULL,                 -- devise du contrat
    PRIMARY KEY (date, conid)
);

CREATE TABLE IF NOT EXISTS fx_rates (
    date     TEXT NOT NULL,
    currency TEXT NOT NULL,              -- → ledger.currencies.code (≠ USD)
    rate_usd REAL NOT NULL,
    PRIMARY KEY (date, currency)
);

-- Derniers prix intraday : key = conid, ou 'FX:<currency>' (rate_usd).
CREATE TABLE IF NOT EXISTS live_prices (
    key        TEXT PRIMARY KEY,
    price      REAL NOT NULL,
    updated_at TEXT NOT NULL             -- ISO UTC
);

-- Cash IB par compte ledger et devise (snapshot du dernier sync).
CREATE TABLE IF NOT EXISTS cash_balances (
    account_id TEXT NOT NULL,
    currency   TEXT NOT NULL,
    amount     REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account_id, currency)
);
