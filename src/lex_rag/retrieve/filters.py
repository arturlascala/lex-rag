"""Filtros de payload para a busca no Qdrant."""

from __future__ import annotations

from qdrant_client.models import FieldCondition, Filter, MatchValue


def build_filter(
    somente_vigente: bool = True,
    urn_lex: str | None = None,
    tipo_norma: str | None = None,
) -> Filter | None:
    must: list[FieldCondition] = []
    if somente_vigente:
        must.append(FieldCondition(key="vigente", match=MatchValue(value=True)))
    if urn_lex:
        must.append(FieldCondition(key="urn_lex", match=MatchValue(value=urn_lex)))
    if tipo_norma:
        must.append(FieldCondition(key="tipo_norma", match=MatchValue(value=tipo_norma)))
    return Filter(must=must) if must else None
