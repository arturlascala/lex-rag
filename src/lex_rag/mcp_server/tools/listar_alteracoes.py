"""Tool: lista dispositivos não vigentes (revogados/alterados) de uma norma."""

from __future__ import annotations

import re

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from lex_rag.config import settings


def _num(path: str) -> int:
    m = re.search(r"art_(\d+)", path or "")
    return int(m.group(1)) if m else 0


def listar_alteracoes(client: QdrantClient, urn_lex: str) -> str:
    flt = Filter(
        must=[
            FieldCondition(key="urn_lex", match=MatchValue(value=urn_lex)),
            FieldCondition(key="vigente", match=MatchValue(value=False)),
        ]
    )
    pontos, _ = client.scroll(
        collection_name=settings.collection_name,
        scroll_filter=flt,
        limit=5000,
        with_payload=True,
    )
    if not pontos:
        return f"Nenhum dispositivo não vigente registrado para {urn_lex}."

    pontos.sort(key=lambda p: _num(p.payload.get("dispositivo_path", "")))
    linhas = [f"Dispositivos não vigentes de {urn_lex} ({len(pontos)}):"]
    for p in pontos:
        pl = p.payload
        linhas.append(f"  - {pl.get('dispositivo_label')}: {pl.get('revogado_por') or 'revogado'}")
    return "\n".join(linhas)
