"""Cache local do HTML cru das normas (arquivos em data/raw/, já em UTF-8)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from lex_rag.config import settings

# O WAF do Planalto (F5/BIG-IP) injeta um <script id="f5_cspm"> com token
# aleatório em cada resposta; hashear o HTML cru faria o delta reindexar tudo
# a cada update. Scripts nunca carregam texto de norma, então saem do hash.
# O espaço em branco também é colapsado: a tradução de quebras de linha do
# modo texto do Windows (cache ida-e-volta) não pode mudar o hash.
_SCRIPT_RE = re.compile(r"<script\b.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_WS_RE = re.compile(r"\s+")


def content_hash(html: str) -> str:
    canonico = _WS_RE.sub(" ", _SCRIPT_RE.sub("", html))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def path_for(slug: str) -> Path:
    return settings.raw_cache_path / f"{slug}.html"


def get(slug: str) -> str | None:
    p = path_for(slug)
    return p.read_text(encoding="utf-8") if p.exists() else None


def put(slug: str, html: str) -> Path:
    settings.ensure_dirs()
    p = path_for(slug)
    # newline="": sem tradução de quebras no Windows ("\r\n" viraria "\r\r\n").
    p.write_text(html, encoding="utf-8", newline="")
    return p
