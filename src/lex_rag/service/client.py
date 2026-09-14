"""Cliente HTTP fino do daemon de inferência.

Consumido pelo MCP server (``mcp_server/server.py``), que assim sobe em
milissegundos sem importar torch/qdrant. Se o daemon não estiver no ar, devolve
uma mensagem amigável em vez de um traceback.
"""

from __future__ import annotations

import httpx

from lex_rag.config import settings

# Timeout generoso no total para cobrir o 1º aquecimento; connect curto para
# detectar rápido que o daemon está fora do ar.
_TIMEOUT = httpx.Timeout(60.0, connect=5.0)

_OFFLINE = (
    "Serviço lex-rag não está no ar. Inicie o daemon com `.\\tasks.ps1 serve` "
    "(ou `.\\tasks.ps1 daemon-start`) e tente novamente."
)


def _request_text(method: str, path: str, **kw) -> str:
    try:
        with httpx.Client(base_url=settings.service_url, timeout=_TIMEOUT) as c:
            r = c.request(method, path, **kw)
            r.raise_for_status()
            return r.text
    except httpx.ConnectError:
        return _OFFLINE
    except httpx.HTTPError as e:
        return f"Erro ao consultar o serviço lex-rag: {e}"


def search(
    consulta: str,
    limite: int = 5,
    somente_vigente: bool = True,
    tipo_norma: str | None = None,
    urn_lex: str | None = None,
) -> str:
    return _request_text(
        "POST",
        "/search",
        json={
            "consulta": consulta,
            "limite": limite,
            "somente_vigente": somente_vigente,
            "tipo_norma": tipo_norma,
            "urn_lex": urn_lex,
        },
    )


def assunto(assunto: str, limite: int = 5, somente_vigente: bool = True) -> str:
    return _request_text(
        "POST",
        "/assunto",
        json={"assunto": assunto, "limite": limite, "somente_vigente": somente_vigente},
    )


def dispositivo(urn_lex: str, dispositivo_path: str) -> str:
    return _request_text(
        "GET",
        "/dispositivo",
        params={"urn_lex": urn_lex, "dispositivo_path": dispositivo_path},
    )


def alteracoes(urn_lex: str) -> str:
    return _request_text("GET", "/alteracoes", params={"urn_lex": urn_lex})


def health() -> str:
    return _request_text("GET", "/health")


def update(mode: str = "delta") -> str:
    # Um update completo (download + embedding de 35 normas) leva vários
    # minutos; não usar o timeout padrão de busca.
    return _request_text(
        "POST", "/update", json={"mode": mode}, timeout=httpx.Timeout(1800.0, connect=5.0)
    )
