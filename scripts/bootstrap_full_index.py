"""Carga do corpus: baixa cada norma do registro (Planalto) e indexa no Qdrant.

Percorre o REGISTRO (núcleo essencial da legislação federal), baixa o HTML ao
vivo do Planalto (com fallback para fixture offline quando houver) e transforma
cada dispositivo num ponto com vetor denso + esparso. Normas que falharem no
download/parse são puladas e reportadas no fim, sem abortar a carga.

Obs.: o qdrant_client é importado dentro de main(), depois dos módulos lex_rag,
para garantir que o pré-carregamento de DLL (pyarrow) ocorra antes — ver
lex_rag/__init__.py.
"""

from __future__ import annotations

import time

from lex_rag.config import settings
from lex_rag.index.chunker import build_chunks
from lex_rag.index.collection_schema import ensure_collection
from lex_rag.index.embedder import Embedder
from lex_rag.index.qdrant_writer import upsert_chunks
from lex_rag.ingest import raw_cache
from lex_rag.ingest.html_parser import parse_norma
from lex_rag.ingest.source import obter_html
from lex_rag.ingest.urn_mapper import REGISTRO
from lex_rag.storage import raw_db, state


def main() -> int:
    from qdrant_client import QdrantClient

    settings.ensure_dirs()
    print(f"[bootstrap] Qdrant embedded em {settings.qdrant_path}")
    client = QdrantClient(path=str(settings.qdrant_path))
    ensure_collection(client, settings.collection_name, recreate=True)

    print("[bootstrap] Carregando BGE-M3 (primeira vez baixa ~2.3GB)...")
    t0 = time.time()
    embedder = Embedder()
    print(f"[bootstrap] modelo carregado em {time.time() - t0:.1f}s (device={embedder.device})")

    print(f"[bootstrap] indexando {len(REGISTRO)} normas do Planalto...")
    total = 0
    falhas: list[str] = []
    for slug, meta in REGISTRO.items():
        try:
            html = obter_html(meta)
            norma = parse_norma(meta, html)
            chunks = build_chunks(norma)
            t0 = time.time()
            dense, sparse = embedder.encode_passages([c.text for c in chunks])
            n = upsert_chunks(client, settings.collection_name, chunks, dense, sparse)

            h = raw_cache.content_hash(html)
            raw_cache.put(slug, html)
            raw_db.record(norma.urn_lex, slug, meta.url_canonica, h)
            state.record(norma.urn_lex, h, len(norma.dispositivos))
            total += n
            print(
                f"  {slug:24} {n:5} chunks / {len(norma.dispositivos):4} disp "
                f"em {time.time() - t0:6.1f}s"
            )
        except Exception as exc:  # pula a norma e segue
            falhas.append(slug)
            print(f"  {slug:24} FALHOU: {type(exc).__name__}: {exc}")
        time.sleep(settings.http_polite_delay)  # coleta educada

    count = client.count(settings.collection_name).count
    client.close()
    ok = len(REGISTRO) - len(falhas)
    print(
        f"[bootstrap] OK: {ok}/{len(REGISTRO)} normas | {total} chunks indexados | "
        f"coleção '{settings.collection_name}' = {count} pontos"
    )
    if falhas:
        print(f"[bootstrap] falhas ({len(falhas)}): {', '.join(falhas)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
