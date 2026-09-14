"""Detecção de mudança de uma norma (vs. estado indexado)."""

from __future__ import annotations

from lex_rag.config import settings
from lex_rag.storage import state


def norma_mudou(urn_lex: str, content_hash: str) -> bool:
    """True se a norma nunca foi indexada, se o conteúdo mudou ou se ela foi
    indexada por uma versão anterior do pipeline.

    O gatilho de versão existe porque um fix de parser não altera o HTML do
    Planalto: sem ele o delta pularia justamente as normas que precisam ser
    reprocessadas, e a reindexação viraria trabalho manual (apagar linhas do
    ``state.sqlite``). Bump de ``pipeline_version`` em ``config.py`` = o próximo
    ``update --mode delta`` reindexa o corpus inteiro.
    """
    row = state.get_indexed(urn_lex)
    if row is None:
        return True
    return (
        row["content_hash"] != content_hash
        or row["pipeline_version"] != settings.pipeline_version
    )
