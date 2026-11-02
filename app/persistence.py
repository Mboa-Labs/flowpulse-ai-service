"""Persistance des objets des agents dans PostgreSQL (schéma mobility).

Chaque objet (trace, recommandation, manque, simulation, état) est rangé en JSON dans une seule
table : le format suit les classes de app/agents/store.py sans migration à chaque évolution.
Sans FLOWPULSE_DATABASE_URL (tests, console), le service reste en mémoire.
"""

from __future__ import annotations

import json
import logging
from typing import Iterable, Protocol

log = logging.getLogger(__name__)

DDL = """
CREATE SCHEMA IF NOT EXISTS mobility;
CREATE TABLE IF NOT EXISTS mobility.objet_agent (
    type TEXT NOT NULL,
    id TEXT NOT NULL,
    donnees JSONB NOT NULL,
    mis_a_jour TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (type, id)
);
"""

Row = tuple[str, str, dict]


class Backend(Protocol):
    def load(self) -> list[Row]: ...

    def save(self, rows: Iterable[Row]) -> None: ...


class PostgresBackend:
    def __init__(self, url: str) -> None:
        import psycopg

        self._psycopg = psycopg
        self.url = url
        with self._connect(autocommit=True) as conn:
            conn.execute(DDL)

    def _connect(self, **kw):
        return self._psycopg.connect(self.url, connect_timeout=5, **kw)

    def load(self) -> list[Row]:
        with self._connect() as conn:
            return [(t, i, d) for t, i, d in conn.execute("SELECT type, id, donnees FROM mobility.objet_agent ORDER BY mis_a_jour")]

    def save(self, rows: Iterable[Row]) -> None:
        with self._connect() as conn:
            conn.cursor().executemany(
                "INSERT INTO mobility.objet_agent (type, id, donnees) VALUES (%s, %s, %s) "
                "ON CONFLICT (type, id) DO UPDATE SET donnees = EXCLUDED.donnees, mis_a_jour = now()",
                [(t, i, json.dumps(d, ensure_ascii=False, default=str)) for t, i, d in rows],
            )


_backend: Backend | None = None


def connect(url: str) -> Backend | None:
    """Stockage PostgreSQL, ou None (mémoire seule) si l'URL est vide ou la base injoignable."""
    if not url:
        return None
    try:
        return PostgresBackend(url)
    except Exception as e:
        log.error("Persistance désactivée, base injoignable (%s) : les objets seront perdus au redémarrage", e)
        return None


def init(backend: Backend | None) -> None:
    """Branche un stockage et recharge les objets déjà enregistrés."""
    from app.agents import store

    global _backend
    _backend = backend
    if backend is not None:
        rows = backend.load()
        store.restore(rows)
        log.info("Persistance : %d objets rechargés", len(rows))


def flush() -> None:
    """Enregistre les objets créés ou modifiés depuis le dernier appel."""
    from app.agents import store

    rows = store.pending()
    if _backend is None or not rows:
        return
    try:
        _backend.save(rows)
    except Exception:
        log.exception("Persistance : échec de l'enregistrement de %d objets", len(rows))
        store.requeue(rows)
