PRAGMA journal_mode = WAL;

-- ============================================================
-- ANALYTICS.DB — performance globale du portefeuille, entièrement
-- recalculée à chaque démarrage (engine.performance.recompute).
-- Une seule série, en USD : NAV et TWR chain-linké.
--   flows_usd    = dépôts − retraits du jour
--   daily_return = (NAV_t − NAV_t−1 − flows_t) / NAV_t−1
--   twr_cumul    = (1 + twr_t−1) × (1 + daily_return) − 1
-- ============================================================

-- Schéma legacy (séries par stratégie, EUR) : supprimé.
DROP TABLE IF EXISTS shareholder_positions;
DROP TABLE IF EXISTS shareholders;
DROP TABLE IF EXISTS ledger_refs;
DROP TABLE IF EXISTS nav_positions_detail;
DROP TABLE IF EXISTS nav_snapshots;
DROP TABLE IF EXISTS twr_snapshots;
DROP TABLE IF EXISTS twr_inception;
DROP TABLE IF EXISTS sync_log;

CREATE TABLE IF NOT EXISTS performance (
    date           TEXT PRIMARY KEY,     -- jour ouvré
    securities_usd REAL NOT NULL,
    cash_usd       REAL NOT NULL,
    nav_usd        REAL NOT NULL,
    flows_usd      REAL NOT NULL,
    daily_return   REAL,
    twr_cumul      REAL NOT NULL
);