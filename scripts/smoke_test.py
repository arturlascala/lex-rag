"""Smoke test da Fase 0.

Indexa 3 artigos hard-coded da CF/1988 num Qdrant embedded local usando BGE-M3
(denso + esparso) e roda uma busca híbrida (RRF) para validar a stack ponta-a-ponta.

Uso:
    python scripts/smoke_test.py
"""

from __future__ import annotations

import shutil
import time
from uuid import NAMESPACE_URL, uuid5

from lex_rag.config import settings

SMOKE_COLLECTION = "smoke_legislacao_federal"

CHUNKS = [
    {
        "urn_lex": "urn:lex:br:federal:constituicao:1988-10-05;1988",
        "dispositivo_path": "art_1",
        "dispositivo_label": "Art. 1º",
        "texto": (
            "A República Federativa do Brasil, formada pela união indissolúvel dos "
            "Estados e Municípios e do Distrito Federal, constitui-se em Estado "
            "Democrático de Direito e tem como fundamentos: I - a soberania; "
            "II - a cidadania; III - a dignidade da pessoa humana; IV - os valores "
            "sociais do trabalho e da livre iniciativa; V - o pluralismo político. "
            "Parágrafo único. Todo o poder emana do povo, que o exerce por meio de "
            "representantes eleitos ou diretamente, nos termos desta Constituição."
        ),
        "parent_label": "Título I - Dos Princípios Fundamentais",
    },
    {
        "urn_lex": "urn:lex:br:federal:constituicao:1988-10-05;1988",
        "dispositivo_path": "art_5",
        "dispositivo_label": "Art. 5º",
        "texto": (
            "Todos são iguais perante a lei, sem distinção de qualquer natureza, "
            "garantindo-se aos brasileiros e aos estrangeiros residentes no País a "
            "inviolabilidade do direito à vida, à liberdade, à igualdade, à segurança "
            "e à propriedade, nos termos seguintes: I - homens e mulheres são iguais "
            "em direitos e obrigações, nos termos desta Constituição; II - ninguém "
            "será obrigado a fazer ou deixar de fazer alguma coisa senão em virtude "
            "de lei."
        ),
        "parent_label": "Título II - Dos Direitos e Garantias Fundamentais",
    },
    {
        "urn_lex": "urn:lex:br:federal:constituicao:1988-10-05;1988",
        "dispositivo_path": "art_37",
        "dispositivo_label": "Art. 37",
        "texto": (
            "A administração pública direta e indireta de qualquer dos Poderes da "
            "União, dos Estados, do Distrito Federal e dos Municípios obedecerá aos "
            "princípios de legalidade, impessoalidade, moralidade, publicidade e "
            "eficiência."
        ),
        "parent_label": "Título III - Capítulo VII - Da Administração Pública",
    },
]

QUERY = "princípio da impessoalidade na administração pública"


def build_text_com_contexto(chunk: dict) -> str:
    epigrafe = "Constituição Federal de 1988"
    return f"[{epigrafe}] [{chunk['parent_label']}] {chunk['dispositivo_label']}: {chunk['texto']}"


def main() -> int:
    print(f"[smoke] Python OK, settings.qdrant_path = {settings.qdrant_path}")
    settings.ensure_dirs()

    smoke_qdrant_path = settings.data_dir / "qdrant_smoke"
    if smoke_qdrant_path.exists():
        shutil.rmtree(smoke_qdrant_path)
    smoke_qdrant_path.mkdir(parents=True, exist_ok=True)
    print(f"[smoke] Qdrant embedded em {smoke_qdrant_path}")

    print("[smoke] Carregando BGE-M3 (primeira vez baixa ~2.3GB da HF)...")
    t0 = time.time()
    from FlagEmbedding import BGEM3FlagModel

    from lex_rag.device import pick_device, prefer_fp16

    print(f"[smoke] device detectado = {pick_device()} (fp16={prefer_fp16()})")
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=prefer_fp16())
    print(f"[smoke] BGE-M3 carregado em {time.time() - t0:.1f}s")

    textos = [build_text_com_contexto(c) for c in CHUNKS]
    print("[smoke] Encodando 3 chunks (denso + esparso)...")
    t0 = time.time()
    out = model.encode(
        textos,
        batch_size=2,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )
    dense = out["dense_vecs"]
    sparse = out["lexical_weights"]
    print(
        f"[smoke] Encode em {time.time() - t0:.1f}s | "
        f"dense.shape={dense.shape} sparse[0]_tokens={len(sparse[0])}"
    )

    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        Fusion,
        FusionQuery,
        PointStruct,
        Prefetch,
        SparseVector,
        SparseVectorParams,
        VectorParams,
    )

    client = QdrantClient(path=str(smoke_qdrant_path))

    if client.collection_exists(SMOKE_COLLECTION):
        client.delete_collection(SMOKE_COLLECTION)

    dense_size = int(dense.shape[1])
    print(f"[smoke] Criando coleção '{SMOKE_COLLECTION}' (dense_size={dense_size})...")
    client.create_collection(
        collection_name=SMOKE_COLLECTION,
        vectors_config={"dense": VectorParams(size=dense_size, distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams()},
    )

    points = []
    for i, chunk in enumerate(CHUNKS):
        sparse_dict = sparse[i]
        sparse_vec = SparseVector(
            indices=[int(k) for k in sparse_dict],
            values=[float(v) for v in sparse_dict.values()],
        )
        point_id = str(uuid5(NAMESPACE_URL, chunk["urn_lex"] + "#" + chunk["dispositivo_path"]))
        points.append(
            PointStruct(
                id=point_id,
                vector={"dense": dense[i].tolist(), "sparse": sparse_vec},
                payload={
                    "urn_lex": chunk["urn_lex"],
                    "dispositivo_label": chunk["dispositivo_label"],
                    "dispositivo_path": chunk["dispositivo_path"],
                    "parent_label": chunk["parent_label"],
                    "texto": chunk["texto"],
                },
            )
        )
    client.upsert(collection_name=SMOKE_COLLECTION, points=points)
    print(f"[smoke] Upserted {len(points)} pontos.")

    print(f"[smoke] Encodando query: {QUERY!r}")
    q_out = model.encode(
        [QUERY],
        batch_size=1,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )
    q_dense = q_out["dense_vecs"][0].tolist()
    q_sparse_dict = q_out["lexical_weights"][0]
    q_sparse = SparseVector(
        indices=[int(k) for k in q_sparse_dict],
        values=[float(v) for v in q_sparse_dict.values()],
    )

    print("[smoke] Rodando busca híbrida (RRF de denso+esparso)...")
    res = client.query_points(
        collection_name=SMOKE_COLLECTION,
        prefetch=[
            Prefetch(query=q_dense, using="dense", limit=10),
            Prefetch(query=q_sparse, using="sparse", limit=10),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        with_payload=True,
        limit=5,
    )

    print("\n=== Resultados ===")
    for rank, point in enumerate(res.points, start=1):
        print(
            f"#{rank}  score={point.score:.4f}  "
            f"{point.payload['dispositivo_label']}  "
            f"({point.payload['urn_lex']})"
        )
        print(f"   texto: {point.payload['texto'][:140]}...")
    print()

    top = res.points[0]
    expected = "art_37"
    ok = top.payload["dispositivo_path"] == expected
    print(
        f"[smoke] {'OK' if ok else 'FALHA'}: top-1 esperado={expected!r}, "
        f"obtido={top.payload['dispositivo_path']!r}"
    )

    client.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
