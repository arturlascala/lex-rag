"""Busca híbrida: prefetch denso + esparso com fusão RRF e rerank (Fase 2).

Fase 1: o BGE-M3 gera vetores denso e esparso da consulta; o Qdrant faz dois
prefetches (um por vetor) e funde por RRF. Fase 2: o BGE-reranker reordena os
candidatos e corta pelo limiar ``reranker_score_min``.
"""

from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.models import Fusion, FusionQuery, Prefetch, SparseVector

from lex_rag.config import settings
from lex_rag.index.embedder import Embedder
from lex_rag.index.reranker import Reranker
from lex_rag.retrieve.filters import build_filter
from lex_rag.retrieve.grounding import Resultado, from_point


def _texto_rerank(c: Resultado) -> str:
    """Mesmo texto contextualizado usado no embedding (chunker._embed_text).

    Sem a epígrafe e a hierarquia, consultas que nomeiam a norma ("o que a
    LGPD diz sobre...") perderiam esse sinal justamente na fase que corta por
    limiar.
    """
    ctx = f"[{c.epigrafe}]"
    if c.parent_label:
        ctx += f" [{c.parent_label}]"
    return f"{ctx} {c.dispositivo_label}: {c.texto}"


class HybridSearcher:
    def __init__(
        self,
        client: QdrantClient | None = None,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self.client = client or QdrantClient(path=str(settings.qdrant_path))
        self.embedder = embedder or Embedder()
        self._reranker = reranker

    @property
    def reranker(self) -> Reranker:
        if self._reranker is None:
            self._reranker = Reranker()
        return self._reranker

    def search(
        self,
        query: str,
        limit: int = 5,
        somente_vigente: bool = True,
        urn_lex: str | None = None,
        tipo_norma: str | None = None,
        rerank: bool = True,
    ) -> list[Resultado]:
        q_dense, q_sparse = self.embedder.encode_query(query)
        flt = build_filter(somente_vigente, urn_lex, tipo_norma)
        sparse_vec = SparseVector(
            indices=[int(k) for k in q_sparse],
            values=[float(v) for v in q_sparse.values()],
        )
        fused = self.client.query_points(
            collection_name=settings.collection_name,
            prefetch=[
                Prefetch(
                    query=q_dense.tolist(),
                    using="dense",
                    limit=settings.dense_prefetch_limit,
                    filter=flt,
                ),
                Prefetch(
                    query=sparse_vec,
                    using="sparse",
                    limit=settings.sparse_prefetch_limit,
                    filter=flt,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            with_payload=True,
            limit=settings.dense_prefetch_limit if rerank else limit,
        )
        candidates = [from_point(p.payload, p.score) for p in fused.points]
        if not rerank or not candidates:
            return candidates[:limit]

        scores = self.reranker.score(query, [_texto_rerank(c) for c in candidates])
        for c, s in zip(candidates, scores, strict=False):
            c.score = s
        candidates.sort(key=lambda c: c.score, reverse=True)
        aprovados = [c for c in candidates if c.score >= settings.reranker_score_min]
        if aprovados:
            return aprovados[:limit]
        melhores = candidates[:limit]
        for c in melhores:
            c.confiavel = False
        return melhores

    def close(self) -> None:
        self.client.close()
