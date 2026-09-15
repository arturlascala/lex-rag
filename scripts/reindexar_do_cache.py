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

``--novos`` é o outro uso: indexa **só** as normas ainda ausentes do
``state.sqlite`` (um lote recém-descoberto, já baixado para o cache pelo
``verificar_parser --novos --baixar``), sem recriar a coleção e sem rede. É o
que o ``POST /update`` faria para elas, menos o download de todo o corpus para
conferir hash — que é o preço do ``update`` quando o lote chega logo depois de
uma reindexação. O ``point_id`` é determinístico, então indexar só as novas
não toca nas demais. ``--slug`` faz o mesmo para normas nomeadas, já indexadas
ou não (apaga os pontos antigos e reinsere) — é o caminho para reprocessar
uma norma depois de um fix de parser que só a ela alcança. Também exigem o
daemon parado.
"""

from __future__ import annotations

import argparse
import sys
import time

from lex_rag.config import settings
from lex_rag.index.collection_schema import ensure_collection
from lex_rag.index.embedder import Embedder
from lex_rag.ingest import raw_cache
from lex_rag.ingest.jurisprudencia import TIPOS_JURISPRUDENCIA
from lex_rag.ingest.source import obter_html
from lex_rag.ingest.urn_mapper import REGISTRO
from lex_rag.storage import state
from lex_rag.update.pipeline import reindex_norma


def main() -> int:
    from qdrant_client import QdrantClient

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--novos", action="store_true",
                    help="só as normas ausentes do state.sqlite, sem recriar a coleção")
    ap.add_argument("--slug", nargs="*",
                    help="só estas normas (apaga e reinsere os pontos), sem recriar a coleção")
    args = ap.parse_args()

    settings.ensure_dirs()

    alvo = dict(REGISTRO)
    parcial = args.novos or bool(args.slug)
    if args.novos:
        alvo = {s: m for s, m in REGISTRO.items() if state.get_indexed(m.urn_lex) is None}
    if args.slug:
        desconhecidos = [s for s in args.slug if s not in REGISTRO]
        if desconhecidos:
            print(f"[reindex] slug fora do catálogo: {', '.join(desconhecidos)}")
            return 1
        alvo = {s: REGISTRO[s] for s in args.slug} if not args.novos else {
            **alvo, **{s: REGISTRO[s] for s in args.slug}
        }
    if not alvo:
        print("[reindex] nenhuma norma nova no catálogo.")
        return 0

    # Súmula não tem HTML a reparsear: o documento é o JSON versionado, e
    # ``obter_html`` o serve local — sem rede, como o resto deste script.
    sem_cache = [
        slug for slug, m in alvo.items()
        if m.tipo not in TIPOS_JURISPRUDENCIA and not raw_cache.get(slug)
    ]
    if sem_cache:
        # Recriar a coleção sem ter o HTML de todas seria trocar o índice
        # completo por um índice furado — melhor parar antes de apagar.
        print(f"[reindex] {len(sem_cache)} normas sem HTML em cache: {', '.join(sem_cache[:8])}")
        print("[reindex] rode 'bootstrap' (ou verificar_parser --baixar) antes.")
        return 1

    print(f"[reindex] Qdrant embedded em {settings.qdrant_path}")
    client = QdrantClient(path=str(settings.qdrant_path))
    ensure_collection(client, settings.collection_name, recreate=not parcial)

    print("[reindex] carregando BGE-M3...")
    t0 = time.time()
    embedder = Embedder()
    print(f"[reindex] modelo carregado em {time.time() - t0:.1f}s (device={embedder.device})")

    print(f"[reindex] reparseando e indexando {len(alvo)} normas do cache...")
    total = 0
    falhas: list[str] = []
    for i, (slug, meta) in enumerate(alvo.items(), 1):
        try:
            # Mesmo caminho do ``update``: apaga os pontos da norma, reparseia,
            # reinsere e registra hash + versão do pipeline.
            conteudo = (
                obter_html(meta) if meta.tipo in TIPOS_JURISPRUDENCIA else raw_cache.get(slug)
            )
            n = reindex_norma(client, embedder, meta, conteudo)
            total += n
            print(f"  [{i:3}/{len(alvo)}] {slug:34} {n:5} chunks", flush=True)
        except Exception as exc:
            falhas.append(f"{slug} ({type(exc).__name__}: {exc})")
            print(f"  [{i:3}/{len(alvo)}] {slug:34} FALHOU: {exc}", flush=True)

    print(f"\n[reindex] {total} pontos indexados em {len(alvo) - len(falhas)} normas")
    if falhas:
        print(f"[reindex] falhas ({len(falhas)}): {'; '.join(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
