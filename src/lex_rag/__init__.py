import contextlib as _contextlib
import sys as _sys

# Windows: o pyarrow (puxado por FlagEmbedding/datasets) sofre access violation se
# carregado DEPOIS das libs nativas do qdrant_client. Pré-carregá-lo aqui, ao
# importar o pacote, garante a ordem correta de DLLs. No-op fora do Windows.
if _sys.platform == "win32":
    with _contextlib.suppress(Exception):
        import pyarrow.dataset  # noqa: F401

del _sys, _contextlib

__version__ = "0.1.0"
