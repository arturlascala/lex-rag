"""Seleção de device para os modelos (BGE-M3 / reranker).

Detecta CUDA automaticamente; permite override via ``LEX_RAG_DEVICE=cuda|cpu``.
"""

from __future__ import annotations

import torch

from lex_rag.config import settings


def pick_device() -> str:
    pref = (settings.device or "auto").lower()
    if pref in ("cuda", "cpu"):
        return pref
    return "cuda" if torch.cuda.is_available() else "cpu"


def prefer_fp16() -> bool:
    """fp16 só vale a pena (e é estável) em GPU."""
    return pick_device() == "cuda"
