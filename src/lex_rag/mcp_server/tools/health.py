"""Tool: estado do servidor (coleção, nº de pontos, device de inferência)."""

from __future__ import annotations

from qdrant_client import QdrantClient

from lex_rag.config import settings
from lex_rag.device import pick_device


def health(client: QdrantClient) -> str:
    existe = client.collection_exists(settings.collection_name)
    n = client.count(settings.collection_name).count if existe else 0
    return (
        "lex-rag OK\n"
        f"  coleção: {settings.collection_name} ({'presente' if existe else 'ausente'})\n"
        f"  dispositivos indexados: {n}\n"
        f"  device de inferência: {pick_device()}\n"
        f"  embedding: {settings.embedding_model}\n"
        f"  reranker: {settings.reranker_model}"
    )
