"""Escrita de chunks (denso + esparso) no Qdrant."""

from __future__ import annotations

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, SparseVector

from lex_rag.index.chunker import Chunk


def _sparse_vector(weights: dict) -> SparseVector:
    return SparseVector(
        indices=[int(k) for k in weights],
        values=[float(v) for v in weights.values()],
    )


def to_points(chunks: list[Chunk], dense: np.ndarray, sparse: list[dict]) -> list[PointStruct]:
    points = []
    for i, ch in enumerate(chunks):
        points.append(
            PointStruct(
                id=ch.id,
                vector={"dense": dense[i].tolist(), "sparse": _sparse_vector(sparse[i])},
                payload=ch.payload,
            )
        )
    return points


def upsert_chunks(
    client: QdrantClient,
    name: str,
    chunks: list[Chunk],
    dense: np.ndarray,
    sparse: list[dict],
    batch_size: int = 256,
) -> int:
    points = to_points(chunks, dense, sparse)
    for i in range(0, len(points), batch_size):
        client.upsert(collection_name=name, points=points[i : i + batch_size])
    return len(points)
