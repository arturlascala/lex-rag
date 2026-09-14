"""Entrypoint do daemon: ``python -m lex_rag.service`` ou ``lex-rag-serve``."""

from __future__ import annotations

import lex_rag  # noqa: F401  (dispara o preload de DLL no Windows antes do qdrant_client)
from lex_rag.config import settings


def main() -> None:
    import uvicorn

    uvicorn.run(
        "lex_rag.service.app:app",
        host=settings.service_host,
        port=settings.service_port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
