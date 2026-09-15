"""Regrava no README a tabela do corpus a partir do catálogo (``REGISTRO``).

O bloco entre ``<!-- corpus:inicio -->`` e ``<!-- corpus:fim -->`` é gerado
inteiro: uma tabela-resumo por espécie e, por espécie, a lista completa das
normas numa seção recolhível (``<details>``), com epígrafe, apelido e ementa.
Rodar depois de cada lote, para a tabela não ficar atrás do catálogo.

As súmulas entram com o enunciado no lugar da ementa (é o que elas têm) e com
a situação quando fora de vigor. Uso::

    python scripts/gerar_tabela_corpus.py          # regrava README.md
    python scripts/gerar_tabela_corpus.py --stdout # só imprime o bloco
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from lex_rag.ingest import jurisprudencia
from lex_rag.ingest.urn_mapper import REGISTRO, NormaMeta

README = Path(__file__).resolve().parent.parent / "README.md"
INICIO, FIM = "<!-- corpus:inicio -->", "<!-- corpus:fim -->"

# Ordem de exibição e rótulo de cada espécie do catálogo.
ESPECIES = [
    ("constituicao", "Constituição e ADCT"),
    ("codigo", "Códigos"),
    ("lei_complementar", "Leis Complementares"),
    ("lei", "Leis ordinárias e decretos-leis"),
    ("decreto", "Decretos"),
    ("regimento", "Regimentos e resoluções de rito das Casas"),
    ("resolucao", "Resoluções do Senado (CF, art. 52)"),
    ("sumula_vinculante", "Súmulas Vinculantes do STF"),
    ("sumula_stf", "Súmulas do STF"),
]
_EMENTA_MAX = 140
_APELIDO = re.compile(r"^(.*?)\s*\((.*)\)$")


def _celula(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ").strip()


def _resumo(texto: str, maximo: int = _EMENTA_MAX) -> str:
    texto = " ".join(texto.split())
    if len(texto) <= maximo:
        return texto
    corte = texto[:maximo].rsplit(" ", 1)[0]
    return corte.rstrip(",;:") + "…"


def _epigrafe_e_apelido(meta: NormaMeta) -> tuple[str, str]:
    m = _APELIDO.match(meta.epigrafe)
    return (m.group(1), m.group(2)) if m else (meta.epigrafe, "")


def _linha_norma(meta: NormaMeta) -> str:
    epigrafe, apelido = _epigrafe_e_apelido(meta)
    return (
        f"| [{_celula(epigrafe)}]({meta.url_canonica}) | {_celula(apelido)} "
        f"| {_celula(_resumo(meta.ementa))} |"
    )


def _linha_sumula(meta: NormaMeta) -> str:
    entrada = jurisprudencia.entrada_de(meta)
    situacao = entrada.get("situacao", "vigente")
    marca = "" if situacao == "vigente" else f" *({situacao})*"
    return (
        f"| [{_celula(meta.epigrafe)}]({meta.url_canonica}){marca} "
        f"| {meta.data.strftime('%d/%m/%Y')} | {_celula(_resumo(entrada['enunciado']))} |"
    )


def _secao(tipo: str, rotulo: str, normas: list[NormaMeta]) -> list[str]:
    jurisprudencial = tipo in jurisprudencia.TIPOS_JURISPRUDENCIA
    if jurisprudencial:
        normas = sorted(normas, key=lambda m: int(m.numero or 0))
        cabecalho = ["| Súmula | Aprovação | Enunciado |", "|---|---|---|"]
        linhas = [_linha_sumula(m) for m in normas]
    else:
        normas = sorted(normas, key=lambda m: (m.data, m.slug))
        cabecalho = ["| Norma | Apelido | Ementa |", "|---|---|---|"]
        linhas = [_linha_norma(m) for m in normas]
    return [
        "<details>",
        f"<summary><b>{rotulo}</b> — {len(normas)}</summary>",
        "",
        *cabecalho,
        *linhas,
        "",
        "</details>",
        "",
    ]


def gerar() -> str:
    por_tipo: dict[str, list[NormaMeta]] = {t: [] for t, _ in ESPECIES}
    for meta in REGISTRO.values():
        por_tipo.setdefault(meta.tipo, []).append(meta)
    desconhecidos = [t for t in por_tipo if t not in dict(ESPECIES)]
    if desconhecidos:
        raise SystemExit(f"espécie sem rótulo em ESPECIES: {desconhecidos}")

    total = len(REGISTRO)
    saida = [
        INICIO,
        "",
        "| Espécie | Documentos |",
        "|---|---:|",
        *[f"| {rotulo} | {len(por_tipo[t])} |" for t, rotulo in ESPECIES],
        f"| **Total** | **{total}** |",
        "",
    ]
    for tipo, rotulo in ESPECIES:
        saida += _secao(tipo, rotulo, por_tipo[tipo])
    saida.append(FIM)
    return "\n".join(saida)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stdout", action="store_true", help="imprime o bloco em vez de gravar")
    args = ap.parse_args()

    bloco = gerar()
    if args.stdout:
        print(bloco)
        return 0
    texto = README.read_text(encoding="utf-8")
    i, j = texto.find(INICIO), texto.find(FIM)
    if i < 0 or j < 0:
        raise SystemExit(f"marcadores {INICIO} / {FIM} ausentes em {README.name}")
    novo = texto[:i] + bloco + texto[j + len(FIM):]
    README.write_text(novo, encoding="utf-8", newline="\n")
    print(f"[corpus] {len(REGISTRO)} documentos -> {README.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
