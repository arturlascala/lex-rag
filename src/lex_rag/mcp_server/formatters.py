"""Formatação dos resultados como citação jurídica (texto literal + fonte).

Nunca parafraseia: expõe o texto literal do dispositivo, o URN-LEX e a URL
canônica do Planalto, sinalizando dispositivos não vigentes.
"""

from __future__ import annotations

from lex_rag.retrieve.grounding import Resultado, is_grounded


def citar(r: Resultado, n: int | None = None) -> str:
    cabecalho = f"{n}. " if n is not None else ""
    linhas = [f"{cabecalho}{r.epigrafe} — {r.dispositivo_label}"]
    if r.parent_label:
        linhas.append(f"   ({r.parent_label})")
    if not r.vigente:
        linhas.append(f"   [NÃO VIGENTE — {r.revogado_por or 'revogado'}]")
    linhas.append(f'   "{r.texto}"')
    linhas.append(f"   URN-LEX: {r.urn_lex}")
    if r.url_canonica:
        linhas.append(f"   Fonte: {r.url_canonica}")
    return "\n".join(linhas)


def formatar_resultados(resultados: list[Resultado]) -> str:
    resultados = [r for r in resultados if is_grounded(r)]
    if not resultados:
        return "Nenhum dispositivo pertinente foi encontrado na base."
    aviso = ""
    if any(not r.confiavel for r in resultados):
        # "[AVISO]" em vez de emoji: o transporte MCP stdio no Windows pode
        # usar cp1252, que não representa caracteres fora do Latin-1.
        aviso = (
            "[AVISO] Nenhum resultado atingiu o limiar de confiança do reranker; "
            "os itens abaixo são os melhores candidatos disponíveis e podem "
            "não responder à consulta.\n\n"
        )
    return aviso + "\n\n".join(citar(r, i) for i, r in enumerate(resultados, 1))


def formatar_dispositivo(r: Resultado) -> str:
    return citar(r)
