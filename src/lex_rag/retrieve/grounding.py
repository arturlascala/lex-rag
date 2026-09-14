"""Resultado de busca com grounding (anti-alucinação).

Cada resultado carrega o TEXTO LITERAL do dispositivo + URN-LEX + URL canônica,
nunca paráfrase. ``is_grounded`` confirma que o resultado referencia um
dispositivo real e completo do índice.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Resultado:
    urn_lex: str
    epigrafe: str
    dispositivo_label: str
    dispositivo_path: str
    parent_label: str
    texto: str
    url_canonica: str
    vigente: bool
    revogado_por: str | None
    score: float
    # False quando nenhum candidato atingiu o limiar do reranker e a busca
    # devolveu os melhores disponíveis mesmo assim (sinalizado na formatação).
    confiavel: bool = True


def from_point(payload: dict, score: float) -> Resultado:
    return Resultado(
        urn_lex=payload.get("urn_lex", ""),
        epigrafe=payload.get("epigrafe", ""),
        dispositivo_label=payload.get("dispositivo_label", ""),
        dispositivo_path=payload.get("dispositivo_path", ""),
        parent_label=payload.get("parent_label", ""),
        texto=payload.get("texto", ""),
        url_canonica=payload.get("url_canonica", ""),
        vigente=payload.get("vigente", True),
        revogado_por=payload.get("revogado_por"),
        score=float(score),
    )


def is_grounded(r: Resultado) -> bool:
    return bool(r.texto and r.urn_lex and r.dispositivo_label)
