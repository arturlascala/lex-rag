"""Descoberta de normas via API SRU do LexML.

Consulta o serviço SRU e extrai os URN-LEX retornados. ``buscar_urns`` requer
rede; ``extrair_urns`` é puro (testável offline).
"""

from __future__ import annotations

import re

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from lex_rag.config import settings

SRU_URL = "https://www.lexml.gov.br/busca/SRU"
_URN_RE = re.compile(r"urn:lex:[a-z0-9:.;_-]+", re.IGNORECASE)


def extrair_urns(xml_text: str) -> list[str]:
    """Extrai URN-LEX (sem duplicar) de uma resposta SRU, sem depender do schema XML."""
    out: list[str] = []
    for urn in _URN_RE.findall(xml_text):
        urn = urn.rstrip(".,;")
        if urn not in out:
            out.append(urn)
    return out


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def buscar_urns(consulta: str, max_registros: int = 20) -> list[str]:
    params = {
        "operation": "searchRetrieve",
        "version": "1.1",
        "query": consulta,
        "maximumRecords": str(max_registros),
    }
    with httpx.Client(timeout=30.0, headers={"User-Agent": settings.http_user_agent}) as client:
        resp = client.get(SRU_URL, params=params)
        resp.raise_for_status()
        return extrair_urns(resp.text)
