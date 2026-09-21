"""Triagem de leis ordinárias novas para o corpus.

O ``update`` só reprocessa o que já está no catálogo: uma lei sancionada depois
do último lote não entra sozinha. A descoberta (``scripts/descobrir_novas.py``)
fecha essa lacuna varrendo a numeração a partir do maior número conhecido e
decidindo, pela ementa oficial, o que faz sentido para o corpus. Aqui fica a
lógica pura (testável offline) e o cliente da API de metadados do LexML; a
varredura, a resolução da URL e a gravação ficam no script.

As categorias da triagem:

- **ruido** — efeito individual ou simbólico: crédito orçamentário, denominação
  de rodovia, data comemorativa, título honorífico, Livro dos Heróis, pensão
  especial, cargos e subsídios. Nunca é norma de consulta; fica de fora.
- **coberta** — lei que só altera normas já presentes no corpus. O ``update``
  rebaixa o texto **consolidado** de cada norma, então o conteúdo novo chega por
  ele; indexar também a alteradora serviria o mesmo artigo duas vezes, uma delas
  fora de contexto.
- **mae_ausente** — altera norma que o corpus não tem. Não entra: o que vale
  incluir é a norma alterada (na lista curada), não a alteração solta.
- **revisar** — ementa de alteração sem número de norma reconhecível; decisão
  humana.
- **candidata** — lei autônoma (institui, dispõe, regula, define...). Entra,
  desde que a página do Planalto exista, parseie e a data confira com a
  epígrafe — a mesma validação do lote curado.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import date

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from lex_rag.config import settings
from lex_rag.ingest.urn_mapper import NormaMeta

METADADOS_URL = "https://normas.leg.br/api/public/metadados/simples"

# Ementas que nunca rendem norma de consulta. Todas começam pelo verbo, então os
# padrões são ancorados no início; a ordem não importa, o primeiro que casa vale.
_RUIDO: list[tuple[re.Pattern[str], str]] = [
    (re.compile(p, re.IGNORECASE), motivo)
    for p, motivo in [
        (r"^Abre\b", "crédito orçamentário"),
        (r"^(Denomina|Dá o nome|Dá a denominação)\b", "denominação de bem público"),
        (r"^(Institui|Cria|Estabelece|Declara|Consagra|Inclui) [oa]s? "
         r"(Dia|Semana|Mês|Ano|Década|Jornada)\b", "data comemorativa"),
        (r"^Inclui\b.*\bcalend[áa]rio\b", "data comemorativa"),
        (r"^(Institui|Cria|Fica criad[oa]) [oa]s? "
         r"(Selo|Prêmio|Medalha|Comenda|Troféu|Título|Ordem do Mérito)\b", "honraria"),
        (r"^(Institui|Cria) [oa]s? (Rota|Roteiro|Caminho|Circuito|Trilha)s? Tur[íi]stic",
         "rota turística"),
        (r"^Institui [oa]s? campanha\b", "campanha de conscientização"),
        (r"^Confere\b", "título honorífico"),
        (r"^Declara\b.*\b(patrim[ôo]nio|capital nacional|utilidade p[úu]blica)\b",
         "declaração honorífica"),
        (r"^Reconhece\b", "reconhecimento simbólico"),
        (r"^Inscreve\b", "Livro dos Heróis e Heroínas da Pátria"),
        (r"^Concede (pens[ãa]o|indeniza[çc][ãa]o)\b", "benefício individual"),
        (r"^Autoriza\b.*\ba (doar|ceder|alienar|permutar|transferir|reverter)\b",
         "disposição de imóvel"),
        (r"^(Cria|Extingue|Transforma)\b.*\b(cargos?|fun[çc][õo]es)\b", "quadro de pessoal"),
        (r"^Dispõe sobre a (cria[çc][ãa]o|transforma[çc][ãa]o|extin[çc][ãa]o)\b.*"
         r"\b(cargos?|fun[çc][õo]es)\b", "quadro de pessoal"),
        (r"^(Fixa|Reajusta)\b.*\b(subs[íi]dio|remunera[çc][ãa]o|vencimentos?|soldo)\b",
         "remuneração"),
    ]
]

# Ementa de alteração: o conteúdo mora na norma alterada, não aqui.
_ALTERACAO_RE = re.compile(
    r"^(Altera|Modifica|Acrescenta|Acresce|Inclui|Insere|Introduz|D[áa] nova redação|"
    r"Revoga|Prorroga|Suprime)\b",
    re.IGNORECASE,
)

# Espécie citada na ementa → segmento de espécie do URN-LEX. A alternativa longa
# vem antes para "Lei Complementar" não casar como "Lei".
_ESPECIE_RE = re.compile(r"\b(Leis? Complementar(?:es)?|Leis?|Decretos?-Leis?|Decretos?)\b")
# Número de norma: "nº 11.196", "nºs 8.112" ou, nas listas ("as Leis nºs 8.429,
# de ..., e 9.504, de ..."), o número pontuado solto. Dia e ano nunca levam
# ponto, e o ano tem quatro dígitos: não casam. Valor em moeda ("1.000,00")
# tem dígito depois da vírgula e também fica de fora.
_NUMERO_RE = re.compile(
    r"\bn(?:[º°]s?|\.)\s*(\d{1,3}(?:\.\d{3})?)\b|(?<![\d.,])(\d{1,3}\.\d{3})(?![\d.]|,\d)"
)
# "art. 1.228" pontua como número de lei; sai antes da extração.
_ARTIGO_RE = re.compile(r"\barts?\.\s*[\d.]+", re.IGNORECASE)

_URN_FEDERAL_RE = re.compile(r"^urn:lex:br:federal:([a-z.]+):\d{4}-\d{2}-\d{2};(\d+)$")
_ROTULO = {"lei": "Lei", "lei.complementar": "LC", "decreto.lei": "DL", "decreto": "Decreto"}


@dataclass(frozen=True)
class Triagem:
    categoria: str  # "ruido" | "coberta" | "mae_ausente" | "revisar" | "candidata"
    motivo: str


def _especie_urn(rotulo: str) -> str:
    r = rotulo.lower()
    if "complementar" in r:
        return "lei.complementar"
    if r.startswith("decreto"):
        return "decreto.lei" if "lei" in r else "decreto"
    return "lei"


def rotulo(ref: tuple[str, str]) -> str:
    """``("lei", "15211")`` → ``"Lei 15.211"``."""
    especie, numero = ref
    return f"{_ROTULO.get(especie, especie)} {int(numero):,}".replace(",", ".")


def referencias(ementa: str) -> list[tuple[str, str]]:
    """Normas citadas na ementa, como (espécie do URN, número sem pontos).

    Cada número recebe a espécie citada por último antes dele — é assim que a
    ementa encadeia ("as Leis nºs 8.429, de ..., e 9.504, de ..., e o
    Decreto-Lei nº 2.848").
    """
    texto = _ARTIGO_RE.sub(" ", ementa)
    especies = [(m.start(), _especie_urn(m.group(1))) for m in _ESPECIE_RE.finditer(texto)]
    out: list[tuple[str, str]] = []
    for m in _NUMERO_RE.finditer(texto):
        anteriores = [e for pos, e in especies if pos < m.start()]
        if not anteriores:
            continue
        ref = (anteriores[-1], (m.group(1) or m.group(2)).replace(".", ""))
        if ref not in out:
            out.append(ref)
    return out


def classificar(ementa: str, presentes: Collection[tuple[str, str]]) -> Triagem:
    """Decide o destino de uma lei pela ementa; ``presentes`` são as normas do corpus."""
    texto = " ".join(ementa.split())
    for padrao, motivo in _RUIDO:
        if padrao.search(texto):
            return Triagem("ruido", motivo)
    if _ALTERACAO_RE.match(texto):
        refs = referencias(texto)
        if not refs:
            return Triagem("revisar", "altera norma não identificada na ementa")
        ausentes = [r for r in refs if r not in presentes]
        if ausentes:
            return Triagem(
                "mae_ausente",
                "altera norma fora do corpus: " + ", ".join(rotulo(r) for r in ausentes),
            )
        return Triagem("coberta", "altera só normas do corpus: " + ", ".join(map(rotulo, refs)))
    return Triagem("candidata", "lei autônoma")


def normas_presentes(registro: Iterable[NormaMeta]) -> set[tuple[str, str]]:
    """(espécie, número) das normas federais do catálogo, para a triagem."""
    out = set()
    for meta in registro:
        m = _URN_FEDERAL_RE.match(meta.urn_lex)
        if m:
            out.add((m.group(1), m.group(2)))
    return out


def ultima_lei(registro: Iterable[NormaMeta]) -> tuple[int, int]:
    """(número, ano) da lei ordinária mais alta do catálogo — o ponto de partida."""
    leis = [
        (int(m.group(2)), meta.data.year)
        for meta in registro
        if (m := _URN_FEDERAL_RE.match(meta.urn_lex)) and m.group(1) == "lei"
    ]
    return max(leis) if leis else (0, 0)


def conferir_nome(name: str | None, numero: str) -> bool:
    """O ``name`` da resposta ("Lei nº 15.504 de 15/09/2026") confirma o número.

    A API casa o número do URN por **sufixo** — ``lei:1962;118`` devolve a Lei
    4.118 — e a resposta vazia (norma inexistente) vem com 200 e sem ``name``.
    O primeiro número do ``name`` é a única confirmação de que a norma pedida é
    a devolvida.
    """
    m = re.search(r"\d[\d.]*", name or "")
    return bool(m) and m.group(0).replace(".", "") == numero


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def metadados_lexml(especie: str, ano: int, numero: int) -> dict | None:
    """Data e ementa oficiais pela API de metadados do LexML; ``None`` se não existe.

    Aceita a forma curta do URN (``lei:{ano};{numero}``), o que permite varrer a
    numeração sem saber a data. O ano precisa bater: com o ano errado a resposta
    vem vazia, então na virada do ano quem varre tenta também o ano seguinte.
    """
    urn = f"urn:lex:br:federal:{especie}:{ano};{numero}"
    with httpx.Client(timeout=30.0, headers={"User-Agent": settings.http_user_agent}) as client:
        resp = client.get(METADADOS_URL, params={"urn": urn})
        resp.raise_for_status()
    dados = resp.json()
    if not conferir_nome(dados.get("name"), str(numero)):
        return None
    return {
        "numero": str(numero),
        "data": date.fromisoformat(dados["legislationDate"]),
        "ementa": " ".join((dados.get("abstract") or "").split()),
    }
