"""Reindexa o corpus inteiro a partir do HTML já em ``data/raw/``, sem rede.

Existe por causa de um descompasso do pipeline: o ``update`` incremental decide
o que refazer comparando o **hash do HTML**, então uma correção no *parser* não
dispara reindexação nenhuma — o HTML é o mesmo, e o índice segue com o texto
antigo. A alternativa era o ``bootstrap``, que rebaixa as ~670 normas do
Planalto: lento, e o portal estrangula a conexão bem antes do fim (foi o que
aconteceu no lote 6). Como o HTML cru já está em cache e não é ele que mudou,
reparsear o cache dá o mesmo resultado sem tocar na rede.

Use depois de mexer em ``html_parser``; use ``bootstrap`` quando o que mudou for
o conteúdo no Planalto.

Igual ao bootstrap, recria a coleção — **pare o daemon antes**, que ele segura o
lock do Qdrant.
"""

from __future__ import annotations

import sys
import time

from lex_rag.config import settings
from lex_rag.index.chunker import build_chunks
from lex_rag.index.collection_schema import ensure_collection
from lex_rag.index.embedder import Embedder
from lex_rag.index.qdrant_writer import upsert_chunks
from lex_rag.ingest import raw_cache
from lex_rag.ingest.html_parser import parse_norma
from lex_rag.ingest.urn_mapper import REGISTRO
from lex_rag.storage import raw_db, state


def main() -> int:
    from qdrant_client import QdrantClient

    settings.ensure_dirs()

    sem_cache = [slug for slug in REGISTRO if not raw_cache.get(slug)]
    if sem_cache:
        # Recriar a coleção sem ter o HTML de todas seria trocar o índice
        # completo por um índice furado — melhor parar antes de apagar.
        print(f"[reindex] {len(sem_cache)} normas sem HTML em cache: {', '.join(sem_cache[:8])}")
        print("[reindex] rode 'bootstrap' (ou verificar_parser --baixar) antes.")
        return 1

    print(f"[reindex] Qdrant embedded em {settings.qdrant_path}")
    client = QdrantClient(path=str(settings.qdrant_path))
    ensure_collection(client, settings.collection_name, recreate=True)

    print("[reindex] carregando BGE-M3...")
    t0 = time.time()
    embedder = Embedder()
    print(f"[reindex] modelo carregado em {time.time() - t0:.1f}s (device={embedder.device})")

    print(f"[reindex] reparseando e indexando {len(REGISTRO)} normas do cache...")
    total = 0
    falhas: list[str] = []
    for i, (slug, meta) in enumerate(REGISTRO.items(), 1):
        try:
            html = raw_cache.get(slug)
            norma = parse_norma(meta, html)
            chunks = build_chunks(norma)
            dense, sparse = embedder.encode_passages([c.text for c in chunks])
            n = upsert_chunks(client, settings.collection_name, chunks, dense, sparse)

            h = raw_cache.content_hash(html)
            raw_db.record(norma.urn_lex, slug, meta.url_canonica, h)
            state.record(norma.urn_lex, h, len(norma.dispositivos))
            total += n
            print(f"  [{i:3}/{len(REGISTRO)}] {slug:34} {n:5} chunks", flush=True)
        except Exception as exc:
            falhas.append(f"{slug} ({type(exc).__name__}: {exc})")
            print(f"  [{i:3}/{len(REGISTRO)}] {slug:34} FALHOU: {exc}", flush=True)

    print(f"\n[reindex] {total} pontos indexados em {len(REGISTRO) - len(falhas)} normas")
    if falhas:
        print(f"[reindex] falhas ({len(falhas)}): {'; '.join(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
