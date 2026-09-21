## Schéma comptable et liaisons (vue d’ensemble)

- **Base physique**: fichier SQLite `__datacache__/ledger.db`.
- **Schéma**: défini dans `terminal/database_schema.sql` (tables `accounts`, `journal_entries`, `journal_lines`, etc.).
- **Accès DB**: `terminal/db/ledger_db.py`.
- **Initialisation**: manuelle (appliquer `terminal/database_schema.sql` sur `__datacache__/ledger.db`) ou via un script dédié.
- **UI principale liée au cash**: `terminal/ui/components/dialog/cash_dialog.py`.

---

## 1. `terminal/database_schema.sql`

- Active `PRAGMA foreign_keys = ON`.
- Crée les tables principales (avec `CREATE TABLE IF NOT EXISTS`) :
  - **`accounts`**
    - `id`, `name` uniquement.
  - **`journal_entries`**
    - En-têtes d’écritures: `date`, `description`, `transaction_type` (`DEPOSIT`, `WITHDRAWAL`, `TRANSFER`, …).
  - **`journal_lines`**
    - Lignes d’écritures: `entry_id`, `account_id`, `currency`, montants, `line_type`.
- Le schéma est **idempotent** : le réexécuter ne casse rien.

---

## 2. `terminal/db/ledger_db.py`

### 2.1 Constantes et types

- **`LEDGER_PATH`**: `__datacache__/ledger.db` (chemin du fichier SQLite).
- **`EXTERNAL_FUNDING_NAME`**: `"External Funding"` (compte “monde extérieur”).
- **`LedgerLine`**: dataclass en mémoire avec `account_id`, `amount`, `currency`.

### 2.2 Fonctions techniques

- **`get_conn() -> sqlite3.Connection`**
  - Crée le dossier `__datacache__` si besoin.
  - Ouvre `ledger.db`, active `PRAGMA foreign_keys = ON`, renvoie la connexion.

- **`init_ledger_db(schema_sql: str) -> None`**
  - Ouvre une connexion avec `get_conn()`.
  - Exécute tout le texte SQL reçu (`executescript`).
  - Sert à appliquer `database_schema.sql` à `ledger.db` (création des tables).

- **`get_account_id(conn, name) -> int`**
  - `SELECT id FROM accounts WHERE name = ?`.
  - `ValueError` si le compte est introuvable.

- **`get_accounts() -> list[sqlite3.Row]`**
  - `SELECT id, name FROM accounts ORDER BY name`.
  - Utilisé côté UI (CashDialog) pour remplir les listes déroulantes (comptes From/To).

- **`get_currencies() -> list[str]`**
  - `SELECT DISTINCT currency FROM journal_lines ORDER BY currency`. Liste globale (nouveau compte en Deposit, type vide).
- **`get_currencies_for_account(account_id) -> list[str]`**
  - `SELECT DISTINCT currency FROM journal_lines WHERE account_id = ? ORDER BY currency`. Rafraîchit le menu Currency une fois From (Withdrawal/Transfer) ou To (Deposit) sélectionné : seules les devises déjà utilisées pour ce compte sont proposées.

### 2.3 Insertion d’écritures

- **`_insert_entry_and_lines(conn, date, transaction_type, description, lines)`**
  - Vérifie que la somme des montants (`amount`) est nulle (équilibre des écritures).
  - Insère un en-tête dans `journal_entries`.
  - Insère les lignes correspondantes dans `journal_lines`.

- **`add_deposit(date, to_account_name, amount, currency, description="")`**
  - Vérifie `amount > 0`.
  - Essaie de récupérer l’ID du compte `to_account_name`.
    - Si **inexistant**: crée automatiquement un compte dans `accounts` (`INSERT INTO accounts (name) VALUES (to_account_name)`).
  - Récupère l’ID du compte `External Funding`.
  - Crée 2 lignes équilibrées:
    - `+amount` sur le compte cible,
    - `-amount` sur `External Funding`.

- **`add_withdrawal(date, from_account_name, amount, currency, description="")`**
  - Vérifie `amount > 0`.
  - Lignes:
    - `-amount` sur `from_account_name`,
    - `+amount` sur `External Funding`.

- **`add_transfer(date, from_account_name, to_account_name, amount, currency, description="")`**
  - Vérifie `amount > 0` et `from_account_name != to_account_name`.
  - Lignes:
    - `-amount` sur `from_account_name`,
    - `+amount` sur `to_account_name`.

- **`get_recent_entries(limit=20)`**
  - Lit les dernières lignes de `journal_entries` + leurs `journal_lines` associées.
  - Utilisé par la fenêtre “Check” (historique des opérations).

---

## 3. `terminal/frontend.py`

Le frontend **ne réapplique pas** le schéma au démarrage.
Si le schéma (tables) ou le compte système `External Funding` sont manquants, les fonctions DB lèvent une erreur explicite (affichée par l’UI).

---

## 4. `terminal/ui/components/dialog/cash_dialog.py` – CashDialog

### 4.1 Rôle

Fenêtre modale pour saisir des mouvements de cash:
- Type: `Deposit`, `Withdrawal`, `Transfer`.
- Date, From Account, To Account, Amount, Currency.
- Confirmation via un dialog “Order Message” avant écriture en DB.

### 4.2 Lien avec `ledger_db`

Imports clés:

- `add_deposit`, `add_withdrawal`, `add_transfer`
  - Fonctions qui écrivent réellement dans `ledger.db`.
- `get_accounts`, `get_currencies`, `EXTERNAL_FUNDING_NAME`
  - Pour remplir et contrôler les combos From/To/Currency.

### 4.3 Chargement des comptes & état local

À l’initialisation:

- Appelle `get_accounts()` et filtre `External Funding`.
- Stocke:
  - `self._accounts`: liste des comptes “normaux”.
  - `self._accounts_by_name`: dictionnaire `name -> row`.
- Connecte les signaux:
  - `typeCombo.currentTextChanged` → `_on_type_changed`.
  - `fromCombo.currentTextChanged` / `toCombo.currentTextChanged` → `_on_account_combo_changed`.

### 4.4 Règles UI par type d’opération

**Deposit**

- `From Account`:
  - Forcé à `External Funding` (non éditable, désactivé) et affiché comme valeur par défaut.
- `To Account`:
  - Liste de tous les comptes existants.
  - Combo éditable: autorise la saisie d’un **nouveau** compte (créé côté DB par `add_deposit`).
- `Currency`:
  - Se rafraîchit **après** sélection du **To Account** : vide au départ ; si To = compte existant → devises du journal pour ce compte (non éditable) ; si To = nouveau nom → toutes les devises du journal (éditable).

**Withdrawal**

- `From Account`:
  - Liste des comptes existants, non éditable (on choisit dans ce qui existe).
- `To Account`:
  - Forcé à `External Funding`, non éditable.
- `Currency`:
  - Se rafraîchit **après** sélection du **From Account** : vide au départ ; si From = compte existant → devises du journal pour ce compte (non éditable).

**Transfer**

- `From` et `To`:
  - Liste des comptes existants (hors `External Funding`), non éditables.
- `Currency`:
  - Alignée sur la devise du compte `From`, non éditable; aucune pré-sélection tant que `From` n’est pas choisi.

### 4.5 Flux “Save” → confirmation → écriture DB

1. `on_save_clicked` lit et valide les champs UI (date, montant, comptes, devise, type).
2. Construit un texte d’ordre lisible (ex: `DEPOSIT 1000 USD to IBK_LONG`).
3. Cache la fenêtre (`self.hide()`) puis ouvre un dialog de confirmation:
   - `OrderDialog(order_message, parent=self)`.
4. Si l’utilisateur clique **Cancel**:
   - Le dialog de confirmation se ferme.
   - `CashDialog` est ré-affiché tel quel (`show()`) → l’utilisateur corrige/changera un champ.
5. Si l’utilisateur clique **OK**:
   - Selon le type: appelle `add_deposit` / `add_withdrawal` / `add_transfer`.
   - Pour `Deposit` + **nouveau To Account**: `add_deposit` crée d’abord le compte dans `accounts`, puis écrit l’écriture.
   - Si tout va bien → `self.accept()` pour fermer définitivement la fenêtre.
   - En cas d’erreur DB → ré-affiche la fenêtre et montre un `QMessageBox` avec l’erreur.

---

## 5. Résumé fonctionnel des liaisons

- **`database_schema.sql`** décrit **quoi** doit exister dans la base.
- **`init_ledger_db(schema_sql)`** applique ce schéma à `ledger.db`.
- **`_init_ledger()` dans `frontend.py`**:
  - exécute le schéma,
  - crée le compte `External Funding` si besoin.
- **`ledger_db.py`** fournit les opérations de plus haut niveau:
  - lire la liste des comptes (`get_accounts`),
  - écrire des dépôts / retraits / transferts (`add_deposit`, `add_withdrawal`, `add_transfer`).
- **`CashDialog`**:
  - utilise `get_accounts` pour piloter les combos et les devises,

---

## 6. Convention de nommage (DB)

- **Écriture**: toutes les fonctions qui écrivent dans la DB commencent par `add_` (ex: `add_deposit`, `add_transfer`).
- **Lecture**: toutes les fonctions qui lisent dans la DB commencent par `get_` (ex: `get_accounts`, `get_recent_entries`).
  - appelle `add_*` uniquement après confirmation explicite de l’utilisateur.

