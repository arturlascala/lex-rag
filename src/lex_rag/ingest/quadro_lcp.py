"""Descoberta das Leis Complementares no quadro oficial do Planalto.

O quadro (``quadro_lcp.htm``) lista todas as LCs federais com link para a
página de cada uma — é ele que resolve a URL canônica (que não deriva
mecanicamente do URN), além de número, data e ementa. O URN-LEX é derivado de
número + data. ``extrair_lcps`` é puro (testável offline); ``baixar_lcps``
requer rede.
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from lex_rag.ingest import planalto_fetcher
from lex_rag.ingest.urn_mapper import NormaMeta

QUADRO_URL = "https://www.planalto.gov.br/ccivil_03/leis/lcp/quadro_lcp.htm"

_MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

# Cabeçalho de cada linha do quadro: "Lei Complementar nº 233, de 1º.7.2026".
_EPIGRAFE_RE = re.compile(
    r"Lei\s+Complementar\s+n[ºo°]\s*(\d+)\s*,?\s*de\s+(\d{1,2})[ºo°]?\.(\d{1,2})\.(\d{4})",
    re.IGNORECASE,
)


def _epigrafe(numero: int, d: date) -> str:
    dia = "1º" if d.day == 1 else str(d.day)
    return f"Lei Complementar nº {numero}, de {dia} de {_MESES[d.month - 1]} de {d.year}"


def _limpar_ementa(texto: str) -> str:
    texto = " ".join(texto.split())
    return re.sub(r"\s*Mensagem de veto\.?\s*$", "", texto, flags=re.IGNORECASE)


def extrair_lcps(html: str) -> list[NormaMeta]:
    """Extrai as LCs das linhas do quadro (sem duplicar; não requer rede)."""
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, NormaMeta] = {}
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        a = tr.find("a", href=re.compile(r"lcp", re.IGNORECASE))
        if a is None or not a.get("href"):
            continue
        cabecalho = " ".join(tds[0].get_text(" ", strip=True).split())
        m = _EPIGRAFE_RE.search(cabecalho)
        if not m:
            continue
        numero, dia, mes, ano = (int(g) for g in m.groups())
        d = date(ano, mes, dia)
        slug = f"lcp_{numero}_{ano}"
        if slug in out:
            continue
        out[slug] = NormaMeta(
            slug=slug,
            urn_lex=f"urn:lex:br:federal:lei.complementar:{d.isoformat()};{numero}",
            tipo="lei_complementar",
            numero=str(numero),
            data=d,
            epigrafe=_epigrafe(numero, d),
            ementa=_limpar_ementa(tds[1].get_text(" ", strip=True)),
            url_canonica=urljoin(QUADRO_URL, a["href"]),
        )
    return list(out.values())


def baixar_lcps() -> list[NormaMeta]:
    """Baixa o quadro oficial e extrai todas as LCs (requer rede)."""
    return extrair_lcps(planalto_fetcher.fetch(QUADRO_URL))
