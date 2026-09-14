"""Empacota e restaura o corpus pré-montado (índice Qdrant + estado + cache HTML).

O git guarda só o código; o corpus (~620 MB) circula como um zip publicado em
Release do GitHub. Quem clona o repositório restaura o snapshot em vez de rodar
``bootstrap`` — o que, sem GPU, levaria horas só de embedding.

Uso:
    python scripts/snapshot.py criar [--saida dist/]      -> dist/lex-rag-snapshot.zip
    python scripts/snapshot.py restaurar <arquivo.zip | URL> [--forcar]

O zip leva os três itens de ``data/`` que constituem o corpus:

- ``qdrant/``        o índice (Qdrant embedded é um diretório; copia e funciona)
- ``state.sqlite``   hashes e versão de pipeline por norma — sem ele o ``update``
                     acha que está tudo por fazer
- ``raw/``           o HTML de cada norma, para ``reindexar_do_cache.py``

e um ``MANIFEST.json`` com a versão do ``qdrant-client`` que gerou o índice: o
formato do Qdrant local muda entre versões, e restaurar com outra é a falha mais
provável — por isso ``restaurar`` confere e avisa.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import date
from importlib.metadata import version
from pathlib import Path

import httpx

from lex_rag.config import settings

ITENS = ("qdrant", "state.sqlite", "raw")


def _daemon_no_ar() -> bool:
    try:
        httpx.get(settings.service_url + "/health", timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


def _commit_atual() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _abortar(msg: str) -> None:
    print(f"[snapshot] {msg}", file=sys.stderr)
    sys.exit(1)


def criar(saida: Path) -> None:
    # O daemon segura o lock do Qdrant e pode ter escrita pendente; copiar o
    # diretório com ele no ar produz snapshot inconsistente.
    if _daemon_no_ar():
        _abortar("o daemon está no ar; pare-o antes (tasks.ps1 daemon-stop / make daemon-stop).")

    faltando = [i for i in ITENS if not (settings.data_dir / i).exists()]
    if faltando:
        _abortar(f"faltam em {settings.data_dir}: {', '.join(faltando)}. Rode o bootstrap antes.")

    saida.mkdir(parents=True, exist_ok=True)
    destino = saida / "lex-rag-snapshot.zip"
    manifesto = {
        "criado_em": date.today().isoformat(),
        "commit": _commit_atual(),
        "qdrant_client": version("qdrant-client"),
        "embedding_model": settings.embedding_model,
        "pipeline_version": settings.pipeline_version,
        "collection_name": settings.collection_name,
    }

    print(f"[snapshot] gravando {destino} ...")
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr("MANIFEST.json", json.dumps(manifesto, indent=2, ensure_ascii=False))
        for item in ITENS:
            origem = settings.data_dir / item
            if origem.is_file():
                arquivos = [origem]
            else:
                arquivos = sorted(p for p in origem.rglob("*") if p.is_file())
            for p in arquivos:
                zf.write(p, p.relative_to(settings.data_dir).as_posix())
    print(f"[snapshot] pronto: {destino} ({destino.stat().st_size / 2**20:.0f} MB)")
    print(json.dumps(manifesto, indent=2, ensure_ascii=False))


def _baixar(url: str, para: Path) -> Path:
    destino = para / url.rsplit("/", 1)[-1]
    print(f"[snapshot] baixando {url} ...")
    with httpx.stream("GET", url, follow_redirects=True, timeout=None) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        lidos = 0
        with destino.open("wb") as f:
            for parte in r.iter_bytes(1 << 20):
                f.write(parte)
                lidos += len(parte)
                if total:
                    print(f"\r[snapshot] {lidos / 2**20:.0f}/{total / 2**20:.0f} MB", end="")
    print()
    return destino


def restaurar(origem: str, forcar: bool) -> None:
    if _daemon_no_ar():
        _abortar("o daemon está no ar; pare-o antes (tasks.ps1 daemon-stop / make daemon-stop).")

    existentes = [i for i in ITENS if (settings.data_dir / i).exists()]
    if existentes and not forcar:
        _abortar(
            f"já existe corpus em {settings.data_dir} ({', '.join(existentes)}). "
            "Use --forcar para substituir."
        )

    with tempfile.TemporaryDirectory() as tmp:
        arquivo = _baixar(origem, Path(tmp)) if origem.startswith("http") else Path(origem)
        if not arquivo.is_file():
            _abortar(f"arquivo não encontrado: {arquivo}")

        with zipfile.ZipFile(arquivo) as zf:
            manifesto = json.loads(zf.read("MANIFEST.json"))
            instalada = version("qdrant-client")
            if manifesto["qdrant_client"] != instalada:
                print(
                    "[snapshot] AVISO: índice gerado com qdrant-client "
                    f"{manifesto['qdrant_client']}, instalado {instalada}. "
                    "Se a busca falhar, alinhe a versão.",
                    file=sys.stderr,
                )
            if existentes:
                for i in existentes:
                    alvo = settings.data_dir / i
                    shutil.rmtree(alvo) if alvo.is_dir() else alvo.unlink()
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            print(f"[snapshot] extraindo em {settings.data_dir} ...")
            zf.extractall(settings.data_dir)

    print("[snapshot] restaurado:")
    print(json.dumps(manifesto, indent=2, ensure_ascii=False))
    print("[snapshot] suba o daemon (tasks.ps1 daemon-start / make serve) e confira o /health.")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("criar", help="empacota data/ num zip em dist/")
    c.add_argument("--saida", type=Path, default=Path("dist"))
    r = sub.add_parser("restaurar", help="extrai um zip (local ou URL) em data/")
    r.add_argument("origem")
    r.add_argument("--forcar", action="store_true", help="substitui o corpus existente")
    args = ap.parse_args()
    if args.cmd == "criar":
        criar(args.saida)
    else:
        restaurar(args.origem, args.forcar)


if __name__ == "__main__":
    main()
