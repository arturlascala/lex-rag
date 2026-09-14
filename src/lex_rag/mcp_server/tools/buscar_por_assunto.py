"""Tool: busca semântica por assunto/tema (busca híbrida com rerank)."""

from __future__ import annotations

from lex_rag.mcp_server.formatters import formatar_resultados
from lex_rag.retrieve.hybrid_search import HybridSearcher


def buscar_por_assunto(
    searcher: HybridSearcher,
    assunto: str,
    limite: int = 5,
    somente_vigente: bool = True,
) -> str:
    resultados = searcher.search(assunto, limit=limite, somente_vigente=somente_vigente)
    return formatar_resultados(resultados)
