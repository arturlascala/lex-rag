"""Daemon de inferência do lex-rag (FastAPI).

Processo residente que carrega o BGE-M3 + reranker UMA vez e mantém o Qdrant
embedded aberto (dono único do lock de arquivo). O MCP server fala com este
daemon por HTTP no loopback. Sobe com ``python -m lex_rag.service`` (ou
``.\\tasks.ps1 serve``).

Os endpoints reusam as mesmas funções-tool do MCP (``mcp_server/tools/*``), de
modo que a lógica de busca/grounding/formatação vive num lugar só.
"""

from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

# 1º import de lex_rag: dispara o preload de DLL (pyarrow) antes do qdrant_client.
from lex_rag.config import settings

# Estado residente, preenchido no startup do lifespan.
_client = None
_searcher = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client, _searcher
    from qdrant_client import QdrantClient

    from lex_rag.retrieve.hybrid_search import HybridSearcher

    settings.ensure_dirs()
    print(f"[service] abrindo Qdrant em {settings.qdrant_path}", flush=True)
    _client = QdrantClient(path=str(settings.qdrant_path))

    print("[service] carregando BGE-M3 + reranker (pode levar ~30-60 s)...", flush=True)
    t0 = time.time()
    _searcher = HybridSearcher(client=_client)
    _ = _searcher.reranker  # força o carregamento do reranker já no boot
    print(
        f"[service] modelos carregados em {time.time() - t0:.1f}s "
        f"(device={_searcher.embedder.device})",
        flush=True,
    )

    # Aquecimento: 1 query para compilar os kernels CUDA → a 1ª query real sai rápida.
    try:
        t1 = time.time()
        _searcher.search("aquecimento", limit=1)
        print(f"[service] aquecimento concluído em {time.time() - t1:.1f}s", flush=True)
    except Exception as e:
        print(f"[service] aquecimento falhou (segue mesmo assim): {e}", flush=True)

    print(f"[service] pronto em {settings.service_url}", flush=True)
    try:
        yield
    finally:
        if _client is not None:
            _client.close()
        print("[service] Qdrant fechado.", flush=True)


app = FastAPI(title="lex-rag service", lifespan=lifespan)


class SearchReq(BaseModel):
    consulta: str
    limite: int = 5
    somente_vigente: bool = True
    tipo_norma: str | None = None
    urn_lex: str | None = None


class AssuntoReq(BaseModel):
    assunto: str
    limite: int = 5
    somente_vigente: bool = True


class UpdateReq(BaseModel):
    mode: str = "delta"


@app.get("/health", response_class=PlainTextResponse)
def health_endpoint() -> str:
    from lex_rag.mcp_server.tools.health import health

    return health(_client)


@app.post("/search", response_class=PlainTextResponse)
def search_endpoint(req: SearchReq) -> str:
    from lex_rag.mcp_server.tools.pesquisar_norma import pesquisar_norma

    return pesquisar_norma(
        _searcher, req.consulta, req.limite, req.somente_vigente, req.tipo_norma, req.urn_lex
    )


@app.post("/assunto", response_class=PlainTextResponse)
def assunto_endpoint(req: AssuntoReq) -> str:
    from lex_rag.mcp_server.tools.buscar_por_assunto import buscar_por_assunto

    return buscar_por_assunto(_searcher, req.assunto, req.limite, req.somente_vigente)


@app.get("/dispositivo", response_class=PlainTextResponse)
def dispositivo_endpoint(urn_lex: str, dispositivo_path: str) -> str:
    from lex_rag.mcp_server.tools.obter_dispositivo import obter_dispositivo

    return obter_dispositivo(_client, urn_lex, dispositivo_path)


@app.get("/alteracoes", response_class=PlainTextResponse)
def alteracoes_endpoint(urn_lex: str) -> str:
    from lex_rag.mcp_server.tools.listar_alteracoes import listar_alteracoes

    return listar_alteracoes(_client, urn_lex)


# Serializa o /update: ele compartilha o embedder e o Qdrant com as buscas e
# não deve rodar duas vezes em paralelo (endpoints "def" rodam em threadpool).
_update_lock = threading.Lock()


@app.post("/update")
def update_endpoint(req: UpdateReq) -> dict:
    from lex_rag.ingest.urn_mapper import recarregar_registro
    from lex_rag.update.pipeline import run

    if not _update_lock.acquire(blocking=False):
        return {"erro": "update já em andamento; aguarde a execução atual terminar"}
    try:
        # O catálogo é lido do disco a cada rodada: lote descoberto com o daemon
        # no ar não pode ficar invisível para ele.
        total = recarregar_registro()
        return {"catalogo": total, **run(req.mode, client=_client, embedder=_searcher.embedder)}
    finally:
        _update_lock.release()
