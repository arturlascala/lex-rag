"""Estado de indexação por norma (SQLite).

Permite ao pipeline de atualização (delta) saber o que já foi indexado e
detectar mudanças por hash de conteúdo.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from lex_rag.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS norma_state (
    urn_lex TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    n_dispositivos INTEGER NOT NULL,
    indexed_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    settings.ensure_dirs()
    con = sqlite3.connect(settings.state_db)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    return con


def get_indexed(urn_lex: str) -> sqlite3.Row | None:
    """Estado indexado da norma (hash + versão do pipeline), ou None se inédita."""
    con = _connect()
    try:
        return con.execute(
            "SELECT content_hash, pipeline_version FROM norma_state WHERE urn_lex=?",
            (urn_lex,),
        ).fetchone()
    finally:
        con.close()


def record(urn_lex: str, content_hash: str, n_dispositivos: int) -> None:
    now = datetime.now(UTC).isoformat()
    con = _connect()
    try:
        con.execute(
            "INSERT INTO norma_state(urn_lex, content_hash, pipeline_version, "
            "n_dispositivos, indexed_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(urn_lex) DO UPDATE SET content_hash=excluded.content_hash, "
            "pipeline_version=excluded.pipeline_version, "
            "n_dispositivos=excluded.n_dispositivos, indexed_at=excluded.indexed_at",
            (urn_lex, content_hash, settings.pipeline_version, n_dispositivos, now),
        )
        con.commit()
    finally:
        con.close()


def all_states() -> list[sqlite3.Row]:
    con = _connect()
    try:
        return con.execute("SELECT * FROM norma_state ORDER BY urn_lex").fetchall()
    finally:
        con.close()
