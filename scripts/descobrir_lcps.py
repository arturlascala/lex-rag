"""Gera o registro das Leis Complementares (``registro_lcp.json``).

Baixa o quadro oficial do Planalto, extrai número/data/ementa/URL de cada LC,
descarta as que já estão no registro curado e valida cada candidata por
download + parse (dispositivos plausíveis). Só as validadas entram no JSON,
que o ``urn_mapper`` mescla ao ``REGISTRO`` na importação. Falhas são
reportadas no fim, sem abortar a descoberta.
"""

from __future__ import annotations

import json
import time

from lex_rag.config import settings
from lex_rag.ingest.html_parser import parse_norma
from lex_rag.ingest.planalto_fetcher import fetch
from lex_rag.ingest.quadro_lcp import baixar_lcps
from lex_rag.ingest.urn_mapper import REGISTRO_CURADO, REGISTRO_LCP_PATH


def main() -> int:
    lcps = baixar_lcps()
    urns_curadas = {m.urn_lex for m in REGISTRO_CURADO.values()}
    candidatas = [m for m in lcps if m.urn_lex not in urns_curadas]
    print(f"[lcp] quadro oficial: {len(lcps)} LCs ({len(lcps) - len(candidatas)} já curadas)")

    validadas = []
    falhas: list[str] = []
    for i, meta in enumerate(candidatas, 1):
        try:
            norma = parse_norma(meta, fetch(meta.url_canonica))
            if not norma.dispositivos:
                raise ValueError("parse sem dispositivos")
            validadas.append(meta)
            print(f"  [{i:3}/{len(candidatas)}] {meta.slug:14} ok ({len(norma.dispositivos)} disp)")
        except Exception as exc:  # pula a LC e segue
            falhas.append(meta.slug)
            print(f"  [{i:3}/{len(candidatas)}] {meta.slug:14} FALHOU: {type(exc).__name__}: {exc}")
        time.sleep(settings.http_polite_delay)  # coleta educada

    validadas.sort(key=lambda m: (m.data, int(m.numero or 0)))
    payload = [
        {
            "slug": m.slug,
            "urn_lex": m.urn_lex,
            "numero": m.numero,
            "data": m.data.isoformat(),
            "epigrafe": m.epigrafe,
            "ementa": m.ementa,
            "url_canonica": m.url_canonica,
        }
        for m in validadas
    ]
    REGISTRO_LCP_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"[lcp] {len(validadas)} LCs validadas gravadas em {REGISTRO_LCP_PATH}")
    if falhas:
        print(f"[lcp] falhas ({len(falhas)}): {', '.join(falhas)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
