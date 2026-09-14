"""Regressão do recreate no Qdrant local persistido.

No qdrant-client 1.18.0 (modo local com path), delete_collection não purga os
pontos do storage em disco: eles "ressuscitam" no create_collection seguinte.
O ensure_collection(recreate=True) precisa entregar uma coleção vazia mesmo
assim — sem isso, todo bootstrap acumula pontos órfãos de cargas anteriores.
"""

from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, SparseVector

from lex_rag.index.collection_schema import DENSE_SIZE, ensure_collection


def _ponto(pid: str) -> PointStruct:
    return PointStruct(
        id=pid,
        vector={"dense": [0.1] * DENSE_SIZE, "sparse": SparseVector(indices=[0], values=[1.0])},
        payload={"k": pid},
    )


def test_recreate_purga_pontos_persistidos(tmp_path):
    # Sessão 1: carga inicial persistida em disco.
    c = QdrantClient(path=str(tmp_path))
    ensure_collection(c, "col", recreate=True)
    c.upsert("col", points=[_ponto("11111111-1111-1111-1111-111111111111")])
    assert c.count("col").count == 1
    c.close()

    # Sessão 2 (novo processo): recreate deve entregar coleção vazia.
    c = QdrantClient(path=str(tmp_path))
    ensure_collection(c, "col", recreate=True)
    assert c.count("col").count == 0, "pontos antigos ressuscitaram após o recreate"
    c.upsert("col", points=[_ponto("22222222-2222-2222-2222-222222222222")])
    assert c.count("col").count == 1
    c.close()


def test_recreate_false_preserva(tmp_path):
    c = QdrantClient(path=str(tmp_path))
    ensure_collection(c, "col", recreate=True)
    c.upsert("col", points=[_ponto("11111111-1111-1111-1111-111111111111")])
    ensure_collection(c, "col", recreate=False)
    assert c.count("col").count == 1
    c.close()
