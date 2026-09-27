# PROMPT — Backend Terminal de Trading

> Continuité de la conversation « Investment terminal UI architecture review (fork) ».
> Spec complémentaire : `spec_terminal.md`.

---

## Goal

Inspecter `terminal/database/`, analyser la refonte (fenêtres/fichiers Python), puis concevoir et générer le backend en s'appuyant sur `spec_terminal.md`.

Implémenter de manière robuste et élégante les cas particuliers financiers ci-dessous.

---

## 1. Invariants de la Base & Traitement de la donnée

### SQLite Multi-db isolées

- `ledger.db` — append-only strict, `external_ref UNIQUE`
- `market_data.db` — cache
- `analytics.db` — dérivée

**Interdiction absolue** d'utiliser `ATTACH DATABASE`.

### Règle Miroir & Lignes à Quantité Nulle

- Un **TRADE** génère 2 lignes : `ASSET_SECURITY` + `ASSET_CASH`
- Les **Corporate Actions** génèrent des lignes `ASSET_SECURITY` avec `quantity = 0`

### Formule Invariante du Coût Moyen Pondéré

Utiliser dans `ledger_queries`, `nav_engine`, `twr_engine` :

```sql
CASE WHEN SUM(quantity) = 0 THEN NULL
     ELSE SUM(quantity * cost_basis) / SUM(quantity)
END AS avg_cost
```

---

## 2. Cas particuliers des Corporate Actions (Gestion des pattes)

### SPLIT

Clôture comptable par lot détenant le titre :

- 1 ligne annulation à `-qty`
- 1 ligne recréation à `+qty × ratio` et `cost_basis / ratio`

### SPIN-OFF

Même lot :

- **Mère** : `qty = 0`, `cost_basis` négatif via `cb_alloué_par_action_mère` (manuel)
- **Fille** : `qty_reçue`, `cost_basis = total alloué / qty_reçue`

### MERGER

Clôture du lot source. Trois modes via paramètre :

| Mode | Comportement |
|------|--------------|
| `SHARES` | Échange de titres ; lier via `lot_instruments` |
| `CASH` | Liquidation cash |
| `MIX` | Titres + cash |

### RIGHTS

Création inline de l'instrument `DELTA_ONE` s'il est absent.

| Mode | Lignes |
|------|--------|
| `SELL` | `qty = -N`, `cb = 0` + `ASSET_CASH` |
| `EXERCISE` | `qty = -N`, `cb = 0` + `ASSET_SECURITY` sous-jacent + `ASSET_CASH` négatif |

### WASH_SALE

- Ligne `ASSET_SECURITY` : `qty = 0`, `cost_basis = +montant_disallowed` sur le lot de rachat
- `external_ref = lot_id_source` pour audit

---

## 3. Logique Quantitative & Chronologie EOD

### Enchaînement cron immuable

```
sync_inception_dates() → compute_nav(date) → compute_all_twr(date)
```

### TWR Daily Chain-linked

```
daily_return = (V(t) - V(t-1) - F(t)) / V(t-1)
```

### Règle Anti-Dilution

Émission/rachat de parts calculé sur la NAV mathématique **juste AVANT** l'impact du flux de trésorerie entrant.

---

## 4. Comptes & périmètres

```python
NAV_ACCOUNTS = {"IBK_LONG", "IBK_LEV"}
SXO_ACCOUNTS = {"SXO_LARGE", "SXO_SMID"}
```

---

## 5. Architecture attendue

```
ui/  →  services/  →  database/  →  SQLite
                  →  engine/     →  NAV / TWR
```

Refonte backend cible :

| Fichier | Rôle |
|---------|------|
| `ledger_con.py` | Connexion, constantes, référentiels |
| `ledger_ops.py` | Écritures append-only |
| `ledger_queries.py` | Lectures |
| `ledger_db.py` | Façade pour `services/` |
