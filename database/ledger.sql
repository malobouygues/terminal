PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ============================================================
-- LEDGER.DB — source de vérité comptable.
-- Une écriture se corrige depuis Books (suppression / modification de l'entry
-- entière, id AUTOINCREMENT jamais réutilisé) ou par contre-passation (reverse_entry).
-- Idempotence des imports : external_ref UNIQUE.
--
-- Montants : `amount` est dans la devise de la ligne (`currency`).
-- La conversion en USD se fait au jour le jour via market_data.fx_rates.
--
-- PATTERNS DE LIGNES (ledger_ops) :
--   TRADE       ASSET_SECURITY (±qty @ cb achat) + ASSET_CASH miroir
--   DEPOSIT / WITHDRAWAL / FEE / TAX / DIVIDEND  1 ligne ASSET_CASH
--   TRANSFER    2 lignes ASSET_CASH (compte source / compte cible)
--   FX_CONV     2 lignes ASSET_CASH (devise vendue / achetée)
--   SPLIT       par lot : -qty @ WAC  puis  +qty×ratio @ WAC/ratio
--   SPIN-OFF    mère qty=0 cb=-total alloué ; fille +qty @ total/qty
--   MERGER      source -qty @ WAC ; SHARES / CASH / MIX
--   RIGHTS_ISSUE  droits -qty @ 0 ; SELL: +cash ; EXERCISE: +sous-jacent, -cash
--   WASH_SALE   qty=0 cb=+montant disallowed (lot de rachat)
-- Lignes qty=0 : cost_basis porte un ajustement TOTAL, neutre pour le WAC.
-- ============================================================

CREATE TABLE IF NOT EXISTS currencies (
    code TEXT PRIMARY KEY
);

INSERT OR IGNORE INTO currencies(code) VALUES
    ('AUD'), ('CAD'), ('CHF'), ('DKK'), ('EUR'),
    ('GBP'), ('HKD'), ('NOK'), ('SEK'), ('TWD'),
    ('USD');

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY CHECK(id IN ('IBK_LONG', 'IBK_LEV'))
);

INSERT OR IGNORE INTO accounts(id) VALUES ('IBK_LONG'), ('IBK_LEV');

-- Un CONID = un seul instrument. `des` distingue les déclinaisons d'un même Name
-- (Ordinary Shares, ADR, Call 500 Jan29…) : un Des ne se répète pour un Name que
-- dans une autre devise. Symbole unique par CONID (rempli depuis IB).
CREATE TABLE IF NOT EXISTS instruments (
    conid      TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    des        TEXT NOT NULL,
    symbol     TEXT UNIQUE,
    type       TEXT NOT NULL CHECK(type IN ('SECURITY', 'DERIVATIVE')),
    currency   TEXT NOT NULL REFERENCES currencies(code),
    expiry     TEXT,                      -- 'YYYY-MM-DD' (DERIVATIVE)
    strike     REAL,
    "right"    TEXT CHECK("right" IN ('C', 'P') OR "right" IS NULL),
    multiplier REAL NOT NULL DEFAULT 1.0,
    UNIQUE(name, des, currency)
);

-- id = 'tes_01', 'tes_02', … (3 lettres du Name en minuscules + n° de trade idea) ; date_close NULL = lot actif.
CREATE TABLE IF NOT EXISTS lots (
    id         TEXT PRIMARY KEY,
    date_open  TEXT NOT NULL,
    date_close TEXT
);

-- Un lot peut contenir plusieurs CONID ; chaque ligne n'appartient qu'à un lot.
-- Un lot clôturé n'accepte plus d'instrument (validé par ledger_con.link_lot_instrument).
CREATE TABLE IF NOT EXISTS lot_instruments (
    lot_id           TEXT NOT NULL REFERENCES lots(id) ON DELETE CASCADE,
    instrument_conid TEXT NOT NULL REFERENCES instruments(conid),
    PRIMARY KEY (lot_id, instrument_conid)
);

-- id AUTOINCREMENT : strictement unique, jamais réutilisé.
CREATE TABLE IF NOT EXISTS journal_entries (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    date             TEXT NOT NULL,           -- 'YYYY-MM-DD'
    transaction_type TEXT NOT NULL CHECK(transaction_type IN (
                         'DEPOSIT', 'DIVIDEND', 'FEE', 'FX_CONV',
                         'MERGER', 'RIGHTS_ISSUE', 'SPIN-OFF', 'SPLIT',
                         'TAX', 'TRADE', 'TRANSFER', 'WASH_SALE', 'WITHDRAWAL'
                     )),
    external_ref     TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_entries_date ON journal_entries(date);

-- lot_id : TRADE, corporate actions, DIVIDEND, FEE imputable → renseigné ;
--          DEPOSIT / WITHDRAWAL / TRANSFER / FX_CONV / TAX → NULL.
CREATE TABLE IF NOT EXISTS journal_lines (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id         INTEGER NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    account_id       TEXT    NOT NULL REFERENCES accounts(id),
    instrument_conid TEXT             REFERENCES instruments(conid),
    lot_id           TEXT             REFERENCES lots(id),
    quantity         REAL,
    cost_basis       REAL,
    currency         TEXT NOT NULL REFERENCES currencies(code),
    amount           REAL NOT NULL,
    line_type        TEXT NOT NULL CHECK(line_type IN ('ASSET_CASH', 'ASSET_SECURITY')),
    CHECK (line_type != 'ASSET_SECURITY'
           OR (instrument_conid IS NOT NULL AND quantity IS NOT NULL AND cost_basis IS NOT NULL)),
    CHECK (line_type != 'ASSET_CASH'
           OR (quantity IS NULL AND cost_basis IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_lines_entry      ON journal_lines(entry_id);
CREATE INDEX IF NOT EXISTS idx_lines_instrument ON journal_lines(instrument_conid);
CREATE INDEX IF NOT EXISTS idx_lines_lot        ON journal_lines(lot_id);
