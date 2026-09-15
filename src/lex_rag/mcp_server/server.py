"""Servidor MCP (stdio) do lex-rag — cliente fino do daemon de inferência.

Expõe a base normativa federal (Constituição, leis complementares e ordinárias,
decretos) e os enunciados de Súmula Vinculante do STF, com busca
anti-alucinação: as respostas trazem sempre o texto literal do dispositivo +
URN-LEX + URL canônica da fonte oficial, nunca paráfrase.

Este processo é leve: NÃO carrega torch/qdrant nem os modelos. Cada tool
encaminha por HTTP para o daemon residente (``lex_rag.service``), que segura os
modelos quentes. Suba o daemon antes com ``.\\tasks.ps1 serve``.

Entrypoint: ``lex-rag-mcp`` ou ``python -m lex_rag.mcp_server.server``.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from lex_rag.service import client

mcp = FastMCP("lex-rag")


@mcp.tool()
def pesquisar_norma(
    consulta: str,
    limite: int = 5,
    somente_vigente: bool = True,
    tipo_norma: str | None = None,
    urn_lex: str | None = None,
) -> str:
    """Pesquisa a base jurídica federal por busca semântica + reranking.

    Devolve o texto literal de cada dispositivo com URN-LEX e URL da fonte
    oficial. Use para perguntas jurídicas sobre a Constituição, leis
    complementares, leis ordinárias e decretos federais — e sobre as Súmulas
    Vinculantes do STF, que entram no mesmo resultado que a legislação (uma
    consulta sobre nepotismo traz o art. 37 da CF e a Súmula Vinculante 13).
    As 736 súmulas simples do STF (não vinculantes) também estão no corpus,
    com a situação que o próprio STF publica (cancelada, revogada, superada).

    Para perguntas de processo legislativo e de rito das Casas, o corpus tem os
    regimentos internos (RISF, RICD e Regimento Comum), os Códigos de Ética
    parlamentar, a resolução de tramitação de MPs e a da CMO (tipo "regimento"),
    além das resoluções do Senado do art. 52 da CF — limites de dívida e de
    crédito dos entes, alíquotas de ICMS e ITCMD (tipo "resolucao").

    Filtros opcionais: ``tipo_norma`` restringe por espécie ("constituicao",
    "lei_complementar", "lei", "codigo", "decreto", "regimento", "resolucao",
    "sumula_vinculante", "sumula_stf");
    ``urn_lex`` restringe a um documento específico (ex.:
    'urn:lex:br:federal:lei:2018-08-14;13709' para buscar só na LGPD).

    Súmula cancelada ou de publicação suspensa fica fora do resultado enquanto
    ``somente_vigente`` for verdadeiro, e vem marcada como não vigente quando
    ele é desligado.
    """
    return client.search(consulta, limite, somente_vigente, tipo_norma, urn_lex)


@mcp.tool()
def buscar_por_assunto(assunto: str, limite: int = 5) -> str:
    """Busca dispositivos por tema/assunto (busca semântica com reranking).

    Equivalente à pesquisa, otimizada para descrições de tema (ex.: "proteção
    de dados", "improbidade administrativa").
    """
    return client.assunto(assunto, limite)


@mcp.tool()
def obter_dispositivo(urn_lex: str, dispositivo_path: str) -> str:
    """Obtém o texto literal de um dispositivo específico.

    ``urn_lex`` é o identificador do documento (ex.:
    'urn:lex:br:federal:constituicao:1988-10-05;1988') e ``dispositivo_path`` o
    caminho do artigo (ex.: 'art_37', 'art_5_A'). Artigo de anexo leva o prefixo
    do anexo ('anexo_art_1', 'anexo_ii_art_3'); anexo sem articulação (tabela,
    quadro) é dispositivo de texto ('anexo_i', 'anexo_i_p2'...). O ADCT é
    documento próprio ('urn:lex:br:federal:constituicao:1988-10-05;1988!adct').
    Súmula (vinculante ou não) tem dispositivo único, de path 'enunciado'
    ('urn:lex:br:supremo.tribunal.federal:sumula:1963-12-13;1' é a Súmula 1).
    """
    return client.dispositivo(urn_lex, dispositivo_path)


@mcp.tool()
def listar_alteracoes(urn_lex: str) -> str:
    """Lista os dispositivos não vigentes (revogados/alterados) de uma norma, pelo URN-LEX."""
    return client.alteracoes(urn_lex)


@mcp.tool()
def health() -> str:
    """Estado do servidor: coleção, nº de dispositivos indexados e device de inferência."""
    return client.health()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
