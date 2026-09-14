"""Tool: pesquisa híbrida (denso + esparso + rerank) com grounding."""

from __future__ import annotations

from lex_rag.mcp_server.formatters import formatar_resultados
from lex_rag.retrieve.hybrid_search import HybridSearcher


def pesquisar_norma(
    searcher: HybridSearcher,
    consulta: str,
    limite: int = 5,
    somente_vigente: bool = True,
    tipo_norma: str | None = None,
    urn_lex: str | None = None,
) -> str:
    resultados = searcher.search(
        consulta,
        limit=limite,
        somente_vigente=somente_vigente,
        tipo_norma=tipo_norma,
        urn_lex=urn_lex,
    )
    return formatar_resultados(resultados)
