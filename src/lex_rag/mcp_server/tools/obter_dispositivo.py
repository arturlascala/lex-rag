"""Tool: obtém um dispositivo específico pelo URN-LEX + path (ex.: 'art_37')."""

from __future__ import annotations

from qdrant_client import QdrantClient

from lex_rag.config import settings
from lex_rag.index.chunker import point_id
from lex_rag.mcp_server.formatters import formatar_dispositivo
from lex_rag.retrieve.grounding import from_point


def obter_dispositivo(client: QdrantClient, urn_lex: str, dispositivo_path: str) -> str:
    pid = point_id(urn_lex, dispositivo_path)
    recs = client.retrieve(
        collection_name=settings.collection_name, ids=[pid], with_payload=True
    )
    if not recs:
        return f"Dispositivo não encontrado: '{dispositivo_path}' em {urn_lex}."
    return formatar_dispositivo(from_point(recs[0].payload, 1.0))
