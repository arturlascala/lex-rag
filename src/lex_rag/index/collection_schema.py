"""Schema da coleção Qdrant: vetores nomeados ``dense`` (1024, cosseno) + ``sparse``."""

from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Filter,
    FilterSelector,
    SparseVectorParams,
    VectorParams,
)

DENSE_SIZE = 1024  # dimensão do BGE-M3


def ensure_collection(client: QdrantClient, name: str, recreate: bool = False) -> None:
    existed = client.collection_exists(name)
    if existed:
        if not recreate:
            return
        client.delete_collection(name)
    client.create_collection(
        collection_name=name,
        vectors_config={"dense": VectorParams(size=DENSE_SIZE, distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams()},
    )
    # qdrant-client em modo local persistido (observado na 1.18.0):
    # delete_collection não purga os pontos do storage em disco e eles
    # "ressuscitam" no create_collection seguinte. Purga explícita para o
    # recreate ser de fato uma carga limpa.
    if existed and recreate and client.count(name).count > 0:
        client.delete(name, points_selector=FilterSelector(filter=Filter()))
