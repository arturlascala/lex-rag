"""Detecção de revogação a partir do texto do dispositivo.

O Planalto marca dispositivos revogados com expressões entre parênteses, ex.:
"(Revogado pela Lei nº 14.133, de 2021)". Não confundir com "(Vide ...)" ou
"(Redação dada pela ...)", que indicam alteração mas não revogação.
"""

from __future__ import annotations

import re

_REVOG_RE = re.compile(r"\(\s*Revogad[oa]s?\b[^)]*\)", re.IGNORECASE)
_WS = re.compile(r"\s+")


def detectar_revogacao(texto: str) -> tuple[bool, str | None]:
    """Retorna (vigente, revogado_por).

    vigente=False apenas quando a marca abre o texto do dispositivo. Marca no
    meio do texto é revogação parcial (parágrafo/inciso inlinado no chunk do
    artigo) e não derruba a vigência do caput — ex.: CF art. 40, § 4º.
    """
    m = _REVOG_RE.match(texto.lstrip())
    if not m:
        return True, None
    return False, _limpar_marca(m)


def extrair_marca_revogacao(texto: str) -> str | None:
    """Marca de revogação em qualquer posição do texto (uso: dispositivo já
    identificado como revogado por outro sinal, ex. texto tachado)."""
    m = _REVOG_RE.search(texto)
    return _limpar_marca(m) if m else None


def _limpar_marca(m: re.Match[str]) -> str:
    return _WS.sub(" ", m.group(0)).strip("() ").strip()
