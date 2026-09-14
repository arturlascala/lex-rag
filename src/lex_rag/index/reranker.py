"""Reranker BGE-reranker-v2-m3 (Fase 2 da busca), acelerado por GPU.

``compute_score(..., normalize=True)`` aplica sigmoide e devolve scores em 0–1,
comparáveis ao limiar ``reranker_score_min``.
"""

from __future__ import annotations

from lex_rag.config import settings
from lex_rag.device import pick_device, prefer_fp16


class Reranker:
    def __init__(self, model_name: str | None = None) -> None:
        from FlagEmbedding import FlagReranker

        self.device = pick_device()
        self.model = FlagReranker(model_name or settings.reranker_model, use_fp16=prefer_fp16())

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        pairs = [[query, p] for p in passages]
        scores = self.model.compute_score(pairs, normalize=True)
        if isinstance(scores, (int, float)):
            return [float(scores)]
        return [float(s) for s in scores]
