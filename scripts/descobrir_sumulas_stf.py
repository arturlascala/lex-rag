"""Gera o registro das súmulas simples do STF (``sumulas_stf.json``) — lote 22-A.

Mesma fonte e mesma mecânica de ``descobrir_sumulas.py`` (as Vinculantes), com a
base 30 do portal em vez da 26, e duas diferenças que dispensam tabela curada:

- **A data vem da própria página.** O bloco "Observação" imprime, conforme a
  súmula, "Data de aprovação do enunciado: Sessão Plenária de 13-12-1963" (157
  páginas, medido) ou "Data de publicação do enunciado: DJ de 12-12-1969" (a
  maioria). A de aprovação entra no URN quando existe; senão, a de publicação
  — as duas são datas que o STF imprime, e ``_referencia`` rotula cada uma
  pelo que é. **Enunciados 1 a 370** são a Súmula original, aprovada na
  Sessão Plenária de 13-12-1963 (Anexo ao Regimento Interno, Imprensa
  Nacional, 1964): é a única data de aprovação que o portal imprime nessa
  faixa (187 páginas, medido), então ela vale para as 162 irmãs cuja página não
  imprime data — com ``observacao`` dizendo isso. Acima de 370, página sem data
  nenhuma é **rejeitada**: sem data não há URN, e inventar uma seria errar a
  chave do corpus (72 enunciados, quase todos entre 371 e 497, ficam de fora
  até a fonte publicar a data).
- **A situação é a que o STF marca**, no índice e no título da página:
  ``(cancelada)``, ``(revogada)``, ``(superada)`` entram como não vigentes, com
  a palavra do Tribunal em ``situacao``; ``(alterada)`` é vigente com o texto
  atual, e a marca fica em ``observacao``. Não há juízo próprio sobre súmula
  materialmente superada mas não cancelada: o STF a mantém, o corpus também.

Como o gate é o do portal (marca conferida na página, não numa tabela), o
script grava só o que baixou e leu com data; ``verificar_sumulas.py --stf``
confere o arquivo depois (numeração 1..736 sem buraco, URN coerente com a
data, enunciado íntegro). As páginas ficam no ``raw_cache`` sob
``pagina_sumula_stf_N`` (prefixo próprio: sob o slug o pipeline grava o
conteúdo canônico da súmula, que é o JSON), e ``--cache`` reprocessa dali.
"""

from __future__ import annotations

import argparse
import json
import re
import time

import httpx
from descobrir_sumulas import (
    _HEADERS,
    BASE,
    _contexto_ssl,
    _fetch,
    extrair_enunciado,
    ids_do_indice,
)

from lex_rag.config import settings
from lex_rag.ingest import raw_cache
from lex_rag.ingest.urn_mapper import SUMULAS_STF_PATH

INDICE = f"{BASE}?base=30"
ROTULO = "Súmula"

# Marca impressa pelo portal -> situação gravada. "alterada" não muda a vigência.
_SITUACAO_DA_MARCA = {"": "vigente", "alterada": "vigente"}
_MARCAS_FORA_DE_VIGOR = {"cancelada", "revogada", "superada"}

# A Súmula original (enunciados 1 a 370) e sua sessão de aprovação.
_ULTIMA_DA_SUMULA_ORIGINAL = 370
_APROVACAO_SUMULA_ORIGINAL = "1963-12-13"
_OBS_SUMULA_ORIGINAL = (
    "Página do STF sem data de aprovação; 13/12/1963 é a Sessão Plenária que aprovou a "
    "Súmula original (enunciados 1 a 370), como o portal registra nos demais enunciados "
    "da faixa."
)

# O rótulo que o portal imprime nem sempre bate com o que segue (a Súmula 359
# diz "Data de publicação do enunciado: Sessão Plenária de ..."): o que define
# a espécie da data é o que vem depois dos dois-pontos, não o rótulo.
# A forma da data varia ("13-12-1963", "13.12.1963", "1º-6-1964"); o rótulo
# também ("Data de aprovação do enunciado:", "Data de aprovação:").
_D = r"(\d{1,2})[ºo]?[-.](\d{1,2})[-.](\d{4})"
_DATA_APROVACAO = re.compile(
    rf"(?:do enunciado:?\s*Sess[ãa]o Plen[áa]ria de|Data de aprova[çc][ãa]o(?: do enunciado)?:)"
    rf"\s*{_D}",
    re.IGNORECASE,
)
_DATA_PUBLICACAO = re.compile(
    rf"(?:do enunciado:?\s*DJ[Ee]?\s*(?:\d+\s+)?de|Data de publica[çc][ãa]o do enunciado:)\s*{_D}",
    re.IGNORECASE,
)


def extrair_datas(html: str) -> tuple[str | None, str | None]:
    """(data de aprovação, data de publicação) em ISO; None para a que a página omite."""
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).replace("&nbsp;", " ")

    def iso(m: re.Match | None) -> str | None:
        if not m:
            return None
        dia, mes, ano = (int(g) for g in m.groups())
        return f"{ano:04d}-{mes:02d}-{dia:02d}"

    return iso(_DATA_APROVACAO.search(flat)), iso(_DATA_PUBLICACAO.search(flat))


def _entrada(
    numero: int, sid: int, enunciado: str, marca: str, aprovacao: str | None, publicacao: str | None
) -> dict:
    if marca in _MARCAS_FORA_DE_VIGOR:
        situacao, motivo = marca, f"Marcada pelo STF como {marca}"
    elif marca in _SITUACAO_DA_MARCA:
        situacao, motivo = "vigente", None
    else:
        raise ValueError(f"Súmula {numero}: marca desconhecida no portal: {marca!r}")
    observacao = "Enunciado alterado (marca do STF)" if marca == "alterada" else None
    if aprovacao is None and numero <= _ULTIMA_DA_SUMULA_ORIGINAL:
        aprovacao = _APROVACAO_SUMULA_ORIGINAL
        observacao = " ".join(filter(None, [observacao, _OBS_SUMULA_ORIGINAL]))
    data = aprovacao or publicacao
    return {
        "numero": numero,
        "urn_lex": f"urn:lex:br:supremo.tribunal.federal:sumula:{data};{numero}",
        "enunciado": enunciado,
        "data_aprovacao": aprovacao,
        "data_publicacao": publicacao,
        "situacao": situacao,
        "cancelada_por": motivo,
        "fonte_stf": f"{BASE}?base=30&sumula={sid}",
        "observacao": observacao,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--limite", type=int, default=0,
        help="baixa só as N primeiras súmulas (para teste rápido do coletor).",
    )
    ap.add_argument(
        "--cache", action="store_true",
        help="reprocessa as páginas já gravadas em data/raw, baixando só as ausentes.",
    )
    args = ap.parse_args()

    with httpx.Client(
        timeout=60.0, headers={**_HEADERS, "Referer": INDICE}, follow_redirects=True,
        verify=_contexto_ssl(),
    ) as client:
        ids = ids_do_indice(_fetch(INDICE, client), ROTULO)
        if not ids:
            raise SystemExit("nenhuma súmula no índice do portal — o HTML mudou de forma?")
        print(f"[súmulas STF] índice: {len(ids)} súmulas (1..{max(ids)})")

        numeros = sorted(ids)[: args.limite or None]
        validadas, falhas, sem_data = [], [], []
        for i, numero in enumerate(numeros, 1):
            sid, slug = ids[numero], f"pagina_sumula_stf_{numero}"
            try:
                pagina = raw_cache.get(slug) if args.cache else None
                if pagina is None:
                    pagina = _fetch(f"{BASE}?base=30&sumula={sid}", client)
                    raw_cache.put(slug, pagina)
                    time.sleep(settings.http_polite_delay)  # coleta educada
                enunciado, marca = extrair_enunciado(pagina, numero, ROTULO)
                aprovacao, publicacao = extrair_datas(pagina)
            except Exception as exc:
                falhas.append(f"Súmula {numero}: {type(exc).__name__}: {exc}")
                print(f"[{i:3}/{len(numeros)}] Súmula {numero:<3} FALHOU: {exc}")
                continue
            if aprovacao is None and publicacao is None and numero > _ULTIMA_DA_SUMULA_ORIGINAL:
                sem_data.append(numero)
                print(f"[{i:3}/{len(numeros)}] Súmula {numero:<3} REJEITADA: página sem data")
                continue
            validadas.append(_entrada(numero, sid, enunciado, marca, aprovacao, publicacao))
            rotulo = f", {marca}" if marca else ""
            print(f"[{i:3}/{len(numeros)}] Súmula {numero:<3} ok ({len(enunciado)} chars{rotulo})")

    validadas.sort(key=lambda e: e["numero"])
    SUMULAS_STF_PATH.write_text(
        json.dumps(validadas, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"\n[súmulas STF] {len(validadas)} validadas -> {SUMULAS_STF_PATH}")
    if sem_data:
        print(f"[súmulas STF] rejeitadas por falta de data ({len(sem_data)}): {sem_data}")
    if falhas:
        print(f"[súmulas STF] falhas ({len(falhas)}): {'; '.join(falhas)}")
    return 1 if (falhas or sem_data) else 0


if __name__ == "__main__":
    raise SystemExit(main())
