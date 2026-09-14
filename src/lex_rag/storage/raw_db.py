"""Índice SQLite dos HTML crus baixados (metadados de fetch).

Compartilha o arquivo ``settings.state_db`` com :mod:`lex_rag.storage.state`.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from lex_rag.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_fetch (
    urn_lex TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    url TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    settings.ensure_dirs()
    con = sqlite3.connect(settings.state_db)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return con


def record(urn_lex: str, slug: str, url: str, content_hash: str) -> None:
    now = datetime.now(UTC).isoformat()
    con = _connect()
    try:
        con.execute(
            "INSERT INTO raw_fetch(urn_lex, slug, url, content_hash, fetched_at) "
            "VALUES(?,?,?,?,?) ON CONFLICT(urn_lex) DO UPDATE SET "
            "slug=excluded.slug, url=excluded.url, content_hash=excluded.content_hash, "
            "fetched_at=excluded.fetched_at",
            (urn_lex, slug, url, content_hash, now),
        )
        con.commit()
    finally:
        con.close()


def get(urn_lex: str) -> sqlite3.Row | None:
    con = _connect()
    try:
        return con.execute("SELECT * FROM raw_fetch WHERE urn_lex=?", (urn_lex,)).fetchone()
    finally:
        con.close()
