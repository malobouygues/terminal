"""Accès données — ledger.db (source de vérité append-only).

Point d'entrée : database.ledger_db (façade). Les modules internes
ledger_con / ledger_ops / ledger_queries ne sont pas importés directement
par services/ ou engine/.
"""

from . import ledger_db

__all__ = ["ledger_db"]
