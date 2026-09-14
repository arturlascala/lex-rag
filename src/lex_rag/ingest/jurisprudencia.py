"""Ingestão dos enunciados jurisprudenciais (hoje, as Súmulas Vinculantes do STF).

É o segundo caminho de ingestão do projeto, paralelo ao do Planalto e sem
cruzar com ele. A diferença que justifica o caminho separado não é a fonte, é a
**forma do documento**: ``html_parser`` produz dispositivo a partir de marcador
``Art. N``, e uma súmula é um enunciado único, sem articulação. Rodada pelo
parser de legislação, uma súmula sairia com zero dispositivos — e zero
dispositivo é sucesso silencioso no pipeline (a norma é gravada no estado,
nenhum ponto entra no índice, nada acusa erro).

Aqui o "parse" é trivial por construção: uma súmula é uma ``Norma`` de um único
``Dispositivo`` de path ``enunciado``. O que exige cuidado é o resto —
identidade, vigência e proveniência —, e isso vem do ``sumulas_vinculantes.json``
curado por ``scripts/descobrir_sumulas.py``.

Ao contrário da legislação, cujo texto é rebaixado do Planalto a cada update, o
enunciado é servido do próprio JSON versionado: são 63 textos curtos que o STF
edita uma ou duas vezes por ano, e um scraper vigiando isso em produção custaria
mais manutenção do que a edição que evita. ``conteudo_canonico`` é o que o
pipeline trata como "o documento": o hash dele é o que decide se a súmula
precisa ser reindexada.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache

from lex_rag.ingest.models import Dispositivo, Norma, TipoDispositivo
from lex_rag.ingest.urn_mapper import SUMULAS_VINCULANTES_PATH, NormaMeta

# Tipos do corpus servidos por este módulo, e não pelo caminho do Planalto.
# Espécie jurisprudencial nova (súmula simples do STF/STJ, tese de repercussão
# geral) entra acrescentando o tipo aqui e um builder análogo — sem tocar no
# parser, no chunker nem no schema da coleção.
TIPOS_JURISPRUDENCIA = frozenset({"sumula_vinculante"})

PATH_ENUNCIADO = "enunciado"
LABEL_ENUNCIADO = "Enunciado"


@lru_cache(maxsize=1)
def _sumulas_por_numero() -> dict[int, dict]:
    if not SUMULAS_VINCULANTES_PATH.exists():
        return {}
    entradas = json.loads(SUMULAS_VINCULANTES_PATH.read_text(encoding="utf-8"))
    return {int(e["numero"]): e for e in entradas}


def recarregar() -> int:
    """Relê o JSON, devolvendo quantas súmulas foram carregadas.

    O gêmeo de ``urn_mapper.recarregar_registro`` para este módulo: o daemon lê
    o arquivo uma vez, no import, e sem isto um lote novo descoberto com ele no
    ar não existiria para o ``POST /update``.
    """
    _sumulas_por_numero.cache_clear()
    return len(_sumulas_por_numero())


def entrada_de(meta: NormaMeta) -> dict:
    """A entrada curada correspondente à norma, pelo número da súmula."""
    if meta.tipo not in TIPOS_JURISPRUDENCIA:
        raise ValueError(f"{meta.slug}: tipo {meta.tipo!r} não é jurisprudencial")
    entrada = _sumulas_por_numero().get(int(meta.numero or 0))
    if entrada is None:
        raise KeyError(f"{meta.slug}: súmula ausente de {SUMULAS_VINCULANTES_PATH.name}")
    return entrada


def conteudo_canonico(entrada: dict) -> str:
    """A serialização que o pipeline trata como "o documento" da súmula.

    ``sort_keys`` deixa o hash imune a reordenação de campos e a reformatação do
    arquivo — reindenta o JSON e nada é reindexado; muda o enunciado ou a
    situação de **uma** súmula e só ela é reindexada.
    """
    return json.dumps(entrada, ensure_ascii=False, sort_keys=True)


def _referencia(entrada: dict) -> str:
    """Sessão de aprovação e publicação, no formato que vai ao ``parent_label``.

    Cabe aqui, e não no texto do dispositivo, porque o texto é citado
    literalmente entre aspas: enfiar data nele seria pôr na boca do STF palavra
    que ele não escreveu. O ``parent_label`` já é impresso entre parênteses pelo
    formatador de citação, no lugar onde a legislação mostra a hierarquia.
    """
    partes = [f"Sessão Plenária de {_br(entrada['data_aprovacao'])}"]
    if entrada.get("data_publicacao"):
        partes.append(f"DJe de {_br(entrada['data_publicacao'])}")
    return " — ".join(partes)


def _br(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def montar_norma(meta: NormaMeta, conteudo: str) -> Norma:
    """Uma ``Norma`` de dispositivo único a partir do conteúdo canônico.

    A súmula fora de vigor entra no corpus em vez de ser omitida: o default das
    buscas é ``somente_vigente=True``, então ela não polui o resultado comum, e
    quem procurar por ela recebe o enunciado com a marca de cancelamento — que é
    a resposta certa — em vez de silêncio.
    """
    entrada = json.loads(conteudo)
    vigente = entrada["situacao"] == "vigente"
    return Norma(
        urn_lex=meta.urn_lex,
        tipo=meta.tipo,
        numero=meta.numero,
        data=meta.data,
        epigrafe=meta.epigrafe,
        ementa=meta.ementa,
        url_canonica=meta.url_canonica,
        dispositivos=[
            Dispositivo(
                path=PATH_ENUNCIADO,
                label=LABEL_ENUNCIADO,
                tipo=TipoDispositivo.enunciado,
                texto=entrada["enunciado"],
                parent_label=_referencia(entrada),
                vigente=vigente,
                revogado_por=None if vigente else entrada.get("cancelada_por"),
            )
        ],
    )
