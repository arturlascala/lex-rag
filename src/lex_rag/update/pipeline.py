"""Pipeline de atualização incremental do índice.

Para cada norma do registro baixa o HTML ao vivo do Planalto (com fallback para
fixture offline), e reindexa apenas as que mudaram (modo ``delta``) ou todas
(modo ``full``). A reindexação substitui os pontos da norma no Qdrant e atualiza
o estado. Normas que falharem no download/parse são puladas e reportadas.
"""

from __future__ import annotations

import logging
import time

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from lex_rag.config import settings
from lex_rag.index.chunker import build_chunks
from lex_rag.index.collection_schema import ensure_collection
from lex_rag.index.qdrant_writer import upsert_chunks
from lex_rag.ingest import raw_cache
from lex_rag.ingest.html_parser import parse_norma
from lex_rag.ingest.source import obter_html
from lex_rag.ingest.urn_mapper import REGISTRO, NormaMeta
from lex_rag.storage import raw_db, state
from lex_rag.update.diff import norma_mudou

logger = logging.getLogger(__name__)


def fonte_html(meta: NormaMeta) -> str:
    """HTML cru da norma (download ao vivo do Planalto, sem fallback fixture).

    No update, falha de download deve pular a norma (preservando o índice
    atual), nunca regredir para o fixture antigo — esse fallback é só do
    bootstrap inicial.
    """
    return obter_html(meta, permitir_fixture=False)


def _pontos_da_norma(client: QdrantClient, urn_lex: str) -> int:
    """Quantos pontos a norma tem hoje no Qdrant (0 = índice ausente/recriado)."""
    return client.count(
        collection_name=settings.collection_name,
        count_filter=Filter(
            must=[FieldCondition(key="urn_lex", match=MatchValue(value=urn_lex))]
        ),
    ).count


def reindex_norma(client: QdrantClient, embedder, meta: NormaMeta, html: str) -> int:
    norma = parse_norma(meta, html)
    client.delete(
        collection_name=settings.collection_name,
        points_selector=Filter(
            must=[FieldCondition(key="urn_lex", match=MatchValue(value=meta.urn_lex))]
        ),
    )
    chunks = build_chunks(norma)
    dense, sparse = embedder.encode_passages([c.text for c in chunks])
    n = upsert_chunks(client, settings.collection_name, chunks, dense, sparse)

    h = raw_cache.content_hash(html)
    raw_cache.put(meta.slug, html)
    raw_db.record(meta.urn_lex, meta.slug, meta.url_canonica, h)
    state.record(meta.urn_lex, h, len(norma.dispositivos))
    return n


def run(mode: str = "delta", client: QdrantClient | None = None, embedder=None) -> dict:
    """Reindexa o que mudou (``delta``) ou tudo (``full``).

    ``client`` e ``embedder`` podem ser injetados pelo daemon (instâncias já
    quentes, dono único do Qdrant); nesse caso não são criados nem fechados aqui.
    Sem injeção, a CLI ``lex-rag-update`` cria e fecha o próprio client.
    """
    settings.ensure_dirs()
    own_client = client is None
    if client is None:
        client = QdrantClient(path=str(settings.qdrant_path))
    ensure_collection(client, settings.collection_name, recreate=False)

    # embedder injetado já está quente; senão, carrega só se houver algo a reindexar.
    atualizadas: dict[str, int] = {}
    inalteradas: list[str] = []
    falhas: list[str] = []

    for meta in REGISTRO.values():
        try:
            html = fonte_html(meta)
            h = raw_cache.content_hash(html)
            # Além do hash, confere o Qdrant: se a coleção foi recriada sem
            # zerar o state.sqlite, o delta reindexará mesmo com hash igual.
            if (
                mode == "delta"
                and not norma_mudou(meta.urn_lex, h)
                and _pontos_da_norma(client, meta.urn_lex) > 0
            ):
                inalteradas.append(meta.slug)
                continue
            if embedder is None:
                from lex_rag.index.embedder import Embedder

                embedder = Embedder()
            atualizadas[meta.slug] = reindex_norma(client, embedder, meta, html)
        except Exception as exc:  # pula a norma e segue
            falhas.append(meta.slug)
            logger.warning("update falhou para %s: %s", meta.slug, exc)
        finally:
            time.sleep(settings.http_polite_delay)  # coleta educada

    count = client.count(settings.collection_name).count
    if own_client:
        client.close()
    return {
        "mode": mode,
        "atualizadas": atualizadas,
        "inalteradas": inalteradas,
        "falhas": falhas,
        "total_pontos": count,
    }
