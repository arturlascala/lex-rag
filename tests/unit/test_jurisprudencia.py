"""Testes do caminho de ingestão jurisprudencial (Súmulas Vinculantes do STF)."""

from __future__ import annotations

import json
from datetime import date

import pytest

from lex_rag.index.chunker import build_chunks, point_id
from lex_rag.ingest.html_parser import parse_norma
from lex_rag.ingest.jurisprudencia import (
    TIPOS_JURISPRUDENCIA,
    conteudo_canonico,
    entrada_de,
    montar_norma,
)
from lex_rag.ingest.models import TipoDispositivo
from lex_rag.ingest.source import obter_html
from lex_rag.ingest.urn_mapper import REGISTRO, NormaMeta

_ENTRADA = {
    "numero": 13,
    "urn_lex": "urn:lex:br:supremo.tribunal.federal:sumula.vinculante:2008-08-21;13",
    "enunciado": "A nomeação de cônjuge, companheiro ou parente em linha reta (...).",
    "data_aprovacao": "2008-08-21",
    "data_publicacao": "2008-08-29",
    "situacao": "vigente",
    "cancelada_por": None,
    "fonte_stf": "https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=26&sumula=1227",
    "observacao": None,
}

_META = NormaMeta(
    slug="sv_13",
    urn_lex=_ENTRADA["urn_lex"],
    tipo="sumula_vinculante",
    numero="13",
    data=date(2008, 8, 21),
    epigrafe="Súmula Vinculante 13 do STF",
    ementa="",
    url_canonica=_ENTRADA["fonte_stf"],
)


def _com(**alteracoes) -> str:
    return conteudo_canonico({**_ENTRADA, **alteracoes})


def test_sumula_vira_norma_de_dispositivo_unico():
    norma = montar_norma(_META, _com())
    assert len(norma.dispositivos) == 1
    d = norma.dispositivos[0]
    assert (d.path, d.label, d.tipo) == ("enunciado", "Enunciado", TipoDispositivo.enunciado)
    assert d.texto == _ENTRADA["enunciado"]  # citação literal, sem data embutida
    assert d.vigente and d.revogado_por is None


def test_datas_vao_para_o_parent_label_em_formato_brasileiro():
    d = montar_norma(_META, _com()).dispositivos[0]
    assert d.parent_label == "Sessão Plenária de 21/08/2008 — DJe de 29/08/2008"


def test_sumula_sem_publicacao_omite_o_dje_do_rotulo():
    # A SV 30 teve a publicação suspensa e nunca ganhou DJe.
    d = montar_norma(_META, _com(data_publicacao=None)).dispositivos[0]
    assert d.parent_label == "Sessão Plenária de 21/08/2008"


@pytest.mark.parametrize(
    "situacao,motivo",
    [("cancelada", "Cancelada em 26/09/2025 (PSV 60)"),
     ("publicacao_suspensa", "Publicação suspensa em 04/02/2010"),
     # marcas que o STF usa nas súmulas simples (lote 22-A)
     ("revogada", "Marcada pelo STF como revogada"),
     ("superada", "Marcada pelo STF como superada")],
)
def test_sumula_fora_de_vigor_entra_marcada_em_vez_de_sumir(situacao, motivo):
    # Omiti-la devolveria silêncio a quem a procura; entrando como não vigente,
    # o default somente_vigente a esconde da busca comum e a citação a marca.
    d = montar_norma(_META, _com(situacao=situacao, cancelada_por=motivo)).dispositivos[0]
    assert not d.vigente
    assert d.revogado_por == motivo


def test_conteudo_canonico_ignora_reordenacao_de_campos():
    # É o hash disto que decide reindexação: reformatar o arquivo não pode
    # disparar recarga do lote inteiro.
    invertido = dict(reversed(list(_ENTRADA.items())))
    assert conteudo_canonico(invertido) == conteudo_canonico(_ENTRADA)
    assert conteudo_canonico({**_ENTRADA, "situacao": "cancelada"}) != conteudo_canonico(_ENTRADA)


def test_parse_norma_despacha_sem_passar_pelo_parser_de_artigos():
    # O parser de HTML não acharia marcador "Art. N" num enunciado e devolveria
    # lista vazia — zero pontos indexados, sem erro nenhum.
    norma = parse_norma(_META, _com())
    assert [d.path for d in norma.dispositivos] == ["enunciado"]


def test_fonte_local_serve_o_documento_sem_rede():
    meta = REGISTRO["sv_13"]
    conteudo = obter_html(meta, permitir_fixture=False)
    assert json.loads(conteudo)["numero"] == 13


def test_chunk_carrega_a_especie_e_id_estavel():
    chunk = build_chunks(montar_norma(_META, _com()))[0]
    assert chunk.payload["tipo_norma"] == "sumula_vinculante"
    assert chunk.payload["dispositivo_label"] == "Enunciado"
    assert chunk.id == point_id(_META.urn_lex, "enunciado")
    assert _META.epigrafe in chunk.text  # o número da súmula é recuperável na busca


def test_registro_traz_as_sumulas_com_metadados_coerentes():
    sumulas = {s: m for s, m in REGISTRO.items() if m.tipo in TIPOS_JURISPRUDENCIA}
    assert len([m for m in sumulas.values() if m.tipo == "sumula_vinculante"]) >= 63
    assert len([m for m in sumulas.values() if m.tipo == "sumula_stf"]) >= 660  # lote 22-A: 664
    for slug, meta in sumulas.items():
        if meta.tipo == "sumula_vinculante":
            assert slug == f"sv_{meta.numero}"
            assert meta.epigrafe == f"Súmula Vinculante {meta.numero} do STF"
            assert ":sumula.vinculante:" in meta.urn_lex
        else:
            assert slug == f"sumula_stf_{meta.numero}"
            assert meta.epigrafe == f"Súmula {meta.numero} do STF"
            assert ":sumula:" in meta.urn_lex
        assert meta.urn_lex.endswith(f";{meta.numero}")
        # a data de aprovação é parte do URN: divergir é errar a chave do corpus
        assert meta.data.isoformat() in meta.urn_lex
        assert meta.url_canonica.startswith("https://portal.stf.jus.br/")


def test_entrada_de_recusa_norma_que_nao_e_jurisprudencial():
    with pytest.raises(ValueError):
        entrada_de(REGISTRO["cf_1988"])


def test_recarregar_registro_atualiza_tambem_os_enunciados(monkeypatch, tmp_path):
    # O daemon lê o catálogo uma vez, no import. Recarregar só os metadados e
    # deixar o texto no cache serviria enunciado velho com cara de sucesso —
    # a armadilha que custou o lote 5.
    import lex_rag.ingest.urn_mapper as um

    entrada = {**_ENTRADA, "enunciado": "Texto novo, recém-editado."}
    arquivo = tmp_path / "sumulas_vinculantes.json"
    arquivo.write_text(json.dumps([entrada], ensure_ascii=False), encoding="utf-8")

    assert entrada_de(REGISTRO["sv_13"])["enunciado"] != entrada["enunciado"]  # cache quente
    # jurisprudencia resolve o caminho em urn_mapper a cada chamada: um só patch basta.
    monkeypatch.setattr(um, "SUMULAS_VINCULANTES_PATH", arquivo)
    try:
        um.recarregar_registro()
        assert entrada_de(REGISTRO["sv_13"])["enunciado"] == entrada["enunciado"]
    finally:
        monkeypatch.undo()
        um.recarregar_registro()
