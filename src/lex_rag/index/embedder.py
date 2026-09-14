"""Embedding com BGE-M3 (denso + esparso num único pass), acelerado por GPU.

O device e o uso de fp16 são decididos por :mod:`lex_rag.device` (CUDA quando
disponível). A importação do FlagEmbedding é tardia para não carregar o torch
ao importar este módulo.
"""

from __future__ import annotations

import numpy as np

from lex_rag.config import settings
from lex_rag.device import pick_device, prefer_fp16


class Embedder:
    def __init__(
        self,
        model_name: str | None = None,
        batch_size: int = 12,
        max_length: int = 4096,
    ) -> None:
        from FlagEmbedding import BGEM3FlagModel

        self.device = pick_device()
        self.batch_size = batch_size
        self.max_length = max_length
        self.model = BGEM3FlagModel(model_name or settings.embedding_model, use_fp16=prefer_fp16())

    def _encode(self, texts: list[str], batch_size: int) -> tuple[np.ndarray, list[dict]]:
        out = self.model.encode(
            texts,
            batch_size=batch_size,
            max_length=self.max_length,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        return out["dense_vecs"], out["lexical_weights"]

    def encode_passages(self, texts: list[str]) -> tuple[np.ndarray, list[dict]]:
        return self._encode(texts, self.batch_size)

    def encode_query(self, text: str) -> tuple[np.ndarray, dict]:
        dense, sparse = self._encode([text], batch_size=1)
        return dense[0], sparse[0]
