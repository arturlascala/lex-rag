"""Triagem de leis novas pela ementa e carga do ``registro_novas.json``.

O erro que estes testes existem para impedir é o silencioso nos dois sentidos:
incluir ruído (crédito, denominação, data comemorativa) como se fosse norma de
consulta, ou descartar uma lei autônoma por lê-la como alteração. E, no
catálogo, servir a mesma lei em dobro quando ela é promovida à lista curada.
"""

from __future__ import annotations

import json
from datetime import date

from lex_rag.ingest.descoberta_novas import (
    classificar,
    conferir_nome,
    normas_presentes,
    referencias,
    rotulo,
    ultima_lei,
)
from lex_rag.ingest.urn_mapper import REGISTRO, NormaMeta

PRESENTES = {("lei", "11196"), ("lei", "8112"), ("lei", "9504"), ("decreto.lei", "2848"),
             ("lei.complementar", "101")}


def _meta(urn: str, d: date) -> NormaMeta:
    return NormaMeta(slug="x", urn_lex=urn, tipo="lei", numero="1", data=d,
                     epigrafe="", ementa="", url_canonica="")


# ------------------------------------------------------------- referências

def test_referencias_encadeia_a_especie_citada_por_ultimo():
    ementa = ("Altera as Leis nºs 8.429, de 2 de junho de 1992, e 9.504, de 30 de setembro "
              "de 1997, e o Decreto-Lei nº 2.848, de 7 de dezembro de 1940 (Código Penal).")
    assert referencias(ementa) == [("lei", "8429"), ("lei", "9504"), ("decreto.lei", "2848")]


def test_referencias_nao_confunde_dia_ano_nem_artigo_com_numero_de_lei():
    ementa = ("Altera o art. 1.228 da Lei nº 10.406, de 10 de janeiro de 2002 (Código Civil), "
              "e a Lei Complementar nº 101, de 4 de maio de 2000.")
    assert referencias(ementa) == [("lei", "10406"), ("lei.complementar", "101")]


def test_rotulo_pontua_o_numero():
    assert rotulo(("lei", "15211")) == "Lei 15.211"
    assert rotulo(("lei.complementar", "101")) == "LC 101"


# ---------------------------------------------------------------- triagem

def test_ruido_fica_de_fora():
    casos = {
        "Abre ao Orçamento Fiscal da União crédito especial em favor de X.": "crédito orçamentário",
        "Denomina Rodovia Y o trecho da BR-101.": "denominação de bem público",
        "Institui o Dia Nacional do Z.": "data comemorativa",
        "Inscreve o nome de W no Livro dos Heróis e Heroínas da Pátria.": "Livro dos Heróis",
        "Confere ao Município de K o título de Capital Nacional do Q.": "título honorífico",
        "Dispõe sobre a criação de cargos em comissão no Poder Judiciário.": "quadro de pessoal",
        # Deixadas passar na primeira varredura (15.444, 15.476, 15.491).
        "Cria a Rota Turística das Cidades Coloniais Alagoanas, no Estado de Alagoas.":
            "rota turística",
        "Fica criado o título Cidade Amiga do Idoso, a ser conferido às cidades que se destacarem.":
            "honraria",
        "Institui a campanha de saúde pública Junho Vermelho.": "campanha de conscientização",
    }
    for ementa, motivo in casos.items():
        t = classificar(ementa, PRESENTES)
        assert t.categoria == "ruido" and t.motivo.startswith(motivo), ementa


def test_alteradora_de_norma_do_corpus_e_coberta_pelo_consolidado():
    t = classificar("Altera a Lei nº 8.112, de 11 de dezembro de 1990.", PRESENTES)
    assert t.categoria == "coberta"
    assert "Lei 8.112" in t.motivo


def test_alteradora_de_norma_fora_do_corpus_aponta_a_mae():
    # A Lei 15.504/2026: Redata na Lei 11.196 (presente) e ECA Digital (ausente).
    ementa = ("Altera a Lei nº 11.196, de 21 de novembro de 2005, para instituir o Regime "
              "Especial de Tributação para Serviços de Datacenter (Redata), e a Lei nº 15.211, "
              "de 17 de setembro de 2025 (Estatuto Digital da Criança e do Adolescente).")
    t = classificar(ementa, PRESENTES)
    assert t.categoria == "mae_ausente"
    assert t.motivo.endswith("Lei 15.211")


def test_alteracao_sem_numero_vai_para_revisao_humana():
    assert classificar("Altera a legislação tributária federal.", PRESENTES).categoria == "revisar"


def test_lei_autonoma_e_candidata_mesmo_quando_tambem_altera():
    for ementa in [
        "Institui a Política Nacional de Conscientização sobre a Linfangioleiomiomatose.",
        "Dispõe sobre as diretrizes para a elaboração e a execução da Lei Orçamentária de 2027.",
        "Institui o Marco Legal das Garantias e altera as Leis nºs 8.112 e 9.504.",
    ]:
        assert classificar(ementa, PRESENTES).categoria == "candidata", ementa


# --------------------------------------------------------------- catálogo

def test_normas_presentes_e_ultima_lei_leem_o_urn():
    reg = [
        _meta("urn:lex:br:federal:lei:2026-06-17;15436", date(2026, 6, 17)),
        _meta("urn:lex:br:federal:lei:2025-01-07;15089", date(2025, 1, 7)),
        _meta("urn:lex:br:federal:lei.complementar:2000-05-04;101", date(2000, 5, 4)),
        _meta("urn:lex:br:supremo.tribunal.federal:sumula.vinculante:2007-05-30;1",
              date(2007, 5, 30)),
    ]
    assert normas_presentes(reg) == {("lei", "15436"), ("lei", "15089"),
                                     ("lei.complementar", "101")}
    assert ultima_lei(reg) == (15436, 2026)


def test_conferir_nome_barra_o_casamento_por_sufixo():
    # A API devolve a Lei 4.118 para ``lei:1962;118``, e 200 sem ``name`` para
    # norma inexistente.
    assert conferir_nome("Lei nº 15.504 de 15/09/2026", "15504")
    assert not conferir_nome("Lei nº 4.118 de 27/08/1962", "118")
    assert not conferir_nome(None, "15600")


def test_registro_novas_perde_para_o_urn_ja_catalogado(monkeypatch, tmp_path):
    # Lei promovida daqui para a lista curada ganha slug e apelido à mão; se o
    # JSON das novas ainda a tiver, o índice a serviria em dobro.
    import lex_rag.ingest.urn_mapper as um

    repetida = next(m for m in REGISTRO.values() if m.urn_lex.startswith("urn:lex:br:federal:lei:"))
    entradas = [
        {"slug": "lei_repetida", "urn_lex": repetida.urn_lex, "tipo": "lei", "numero": "1",
         "data": "2026-01-01", "epigrafe": "", "ementa": "", "url_canonica": ""},
        {"slug": "lei_99999_2026", "urn_lex": "urn:lex:br:federal:lei:2026-12-31;99999",
         "tipo": "lei", "numero": "99999", "data": "2026-12-31", "epigrafe": "Lei nº 99.999",
         "ementa": "Institui X.", "url_canonica": "https://www.planalto.gov.br/x.htm"},
    ]
    arquivo = tmp_path / "registro_novas.json"
    arquivo.write_text(json.dumps(entradas, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(um, "REGISTRO_NOVAS_PATH", arquivo)
    try:
        um.recarregar_registro()
        assert "lei_repetida" not in REGISTRO
        assert REGISTRO[repetida.slug] == repetida
        assert REGISTRO["lei_99999_2026"].tipo == "lei"
    finally:
        monkeypatch.undo()
        um.recarregar_registro()
