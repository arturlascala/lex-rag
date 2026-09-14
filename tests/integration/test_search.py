"""Teste de integração da busca híbrida (requer índice populado via bootstrap).

Auto-skip se a coleção não existir. Carrega BGE-M3 + reranker (usa GPU se houver).
"""

from __future__ import annotations

import pytest
from qdrant_client import QdrantClient

from lex_rag.config import settings


def _has_index() -> bool:
    try:
        c = QdrantClient(path=str(settings.qdrant_path))
        ok = c.collection_exists(settings.collection_name) and (
            c.count(settings.collection_name).count > 0
        )
        c.close()
        return ok
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _has_index(), reason="índice vazio — rode .\\tasks.ps1 bootstrap"
)


@pytest.fixture(scope="module")
def searcher():
    from lex_rag.retrieve.hybrid_search import HybridSearcher

    s = HybridSearcher()
    yield s
    s.close()


def test_impessoalidade_retorna_cf_art37(searcher):
    res = searcher.search("princípio da impessoalidade na administração pública", limit=5)
    assert res, "deveria retornar resultados"
    top = res[0]
    assert "37" in top.dispositivo_label
    assert top.urn_lex.startswith("urn:lex:br:federal:constituicao")
    assert top.texto  # grounding: texto literal presente


def test_licitacao_usa_lei_vigente_nao_revogada(searcher):
    # Com somente_vigente=True não deve trazer a Lei 8.666 (revogada).
    res = searcher.search("modalidades de licitação", limit=5)
    assert res
    assert all("8.666" not in r.epigrafe for r in res)


def test_filtro_por_norma(searcher):
    urn_cf = "urn:lex:br:federal:constituicao:1988-10-05;1988"
    res = searcher.search("direitos fundamentais", limit=5, urn_lex=urn_cf)
    assert res
    assert all(r.urn_lex == urn_cf for r in res)


def test_nepotismo_traz_a_sumula_vinculante_13(searcher):
    # O caso que motivou o lote: sem jurisprudência, a consulta era respondida
    # pela metade — o art. 37 da CF sem o enunciado que o concretiza.
    res = searcher.search("nomeação de parentes para cargo em comissão, nepotismo", limit=5)
    assert res
    sumulas = [r for r in res if "sumula.vinculante" in r.urn_lex]
    assert sumulas, "a SV 13 deveria estar entre os resultados"
    sv13 = sumulas[0]
    assert "13" in sv13.epigrafe
    assert sv13.dispositivo_label == "Enunciado"
    assert "cônjuge, companheiro ou parente" in sv13.texto  # texto literal, não paráfrase


def test_filtro_por_especie_isola_a_jurisprudencia(searcher):
    res = searcher.search("prisão civil de depositário infiel", limit=5,
                          tipo_norma="sumula_vinculante")
    assert res
    assert all(r.urn_lex.startswith("urn:lex:br:supremo.tribunal.federal") for r in res)


def test_sumula_cancelada_fica_fora_da_busca_vigente(searcher):
    # A SV 9 foi cancelada em 2025; com o default somente_vigente ela não pode
    # aparecer, ou o corpus estaria servindo entendimento morto como vivo.
    res = searcher.search("remição de pena por falta grave, perda dos dias remidos", limit=10)
    assert all(";9" not in r.urn_lex for r in res if "sumula.vinculante" in r.urn_lex)
