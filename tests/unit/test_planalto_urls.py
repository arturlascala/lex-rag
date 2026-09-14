"""Resolução de URL do Planalto e conferência de data pela epígrafe.

Os dois erros que estes testes existem para impedir são silenciosos: pegar a
página do texto *original* em vez do consolidado (serviria texto revogado como
vigente) e aceitar uma data errada (o URN-LEX carrega a data de promulgação,
então data errada = norma indexada sob identificador errado).
"""

from __future__ import annotations

from datetime import date

from lex_rag.ingest.planalto_urls import (
    conferir_data,
    epigrafe,
    numero_pontuado,
    variantes_url,
)
from lex_rag.ingest.urn_mapper import REGISTRO, REGISTRO_CURADO


def test_consolidado_vem_antes_do_texto_simples():
    # Na Lei das S.A. o l6404.htm é o texto de 1976; o vigente está em
    # l6404compilada.htm — o consolidado precisa ser tentado primeiro.
    urls = variantes_url("lei", "6404", 1976)
    compilada = next(i for i, u in enumerate(urls) if u.endswith("l6404compilada.htm"))
    simples = next(i for i, u in enumerate(urls) if u.endswith("l6404.htm"))
    assert compilada < simples


def test_diretorios_por_ano():
    # 1999-2003 se espalham por leis/{ano}/, leis/leis_{ano}/ e leis/
    urls_2001 = variantes_url("lei", "10257", 2001)
    assert any("leis/leis_2001/l10257.htm" in u for u in urls_2001)
    assert any("leis/2001/" in u for u in urls_2001)
    # de 2004 em diante, os diretórios _ato{inicio}-{fim}
    assert all("_ato2004-2006/2004/lei/" in u for u in variantes_url("lei", "10973", 2004))
    # decreto-lei tem diretório próprio
    assert all("decreto-lei/del4657" in u for u in variantes_url("decreto.lei", "4657", 1942))


def test_numero_com_e_sem_ponto():
    # O Planalto usa as duas grafias: l10973.htm e l10.973.htm
    urls = variantes_url("lei", "10973", 2004)
    assert any(u.endswith("l10973.htm") for u in urls)
    assert any(u.endswith("l10.973.htm") for u in urls)
    assert numero_pontuado("10973") == "10.973"


def test_numero_curto_ganha_variante_zerada():
    # Normas antigas de numeração baixa ficam em arquivo zerado à esquerda:
    # l0605.htm (Lei 605/1949) e del0037.htm (DL 37/1966).
    urls_605 = variantes_url("lei", "605", 1949)
    assert any(u.endswith("l0605.htm") for u in urls_605)
    assert any(u.endswith("l605.htm") for u in urls_605)
    assert any(u.endswith("del0037.htm") for u in variantes_url("decreto.lei", "37", 1966))
    # sem duplicatas: "605" pontuado é ele mesmo, e nº de 4+ dígitos não zera
    assert len(urls_605) == len(set(urls_605))
    assert not any("l09504" in u for u in variantes_url("lei", "9504", 1997))


def test_diretorios_dos_decretos_mudam_por_faixa_de_ano():
    # De 2004 em diante valem os mesmos _ato das leis.
    assert all("_ato2023-2026/2023/decreto/" in u for u in variantes_url("decreto", "11462", 2023))
    # 1999-2003 se dividem entre decreto/{ano}/ (Dec. 4.382/2002) e decreto/
    urls_2002 = variantes_url("decreto", "4382", 2002)
    assert any(u.endswith("decreto/2002/d4382.htm") for u in urls_2002)
    assert any(u.endswith("decreto/d4382.htm") for u in urls_2002)
    # 1990-1994 entre decreto/1990-1994/ (Dec. 592/1992) e decreto/ (Dec. 678/1992),
    # com o zero à esquerda dos números curtos
    urls_1992 = variantes_url("decreto", "592", 1992)
    assert any(u.endswith("decreto/1990-1994/d0592.htm") for u in urls_1992)
    assert any(u.endswith("decreto/d0592.htm") for u in urls_1992)
    # antes de 1990, o consolidado fica em decreto/ (o Dec. 70.235/1972 resolve
    # em d70235compilado.htm) ou em decreto/antigos/
    urls_1972 = variantes_url("decreto", "70235", 1972)
    assert any(u.endswith("decreto/d70235compilado.htm") for u in urls_1972)
    assert any("decreto/antigos/" in u for u in urls_1972)
    # só minúsculas: a grafia maiúscula só gera um 301 para a mesma página
    assert not any("/D" in u.replace("ccivil_03/D", "") for u in urls_1992)


def test_conferir_data_do_decreto_ignora_a_lei_regulamentada():
    # A página de um decreto traz a lei regulamentada logo abaixo da epígrafe.
    # Sem o rótulo restrito à espécie, a conferência casaria a *referência* e
    # rejeitaria a norma por "data divergente".
    pagina = (
        "<p>DECRETO Nº 11.462, DE 31 DE MARÇO DE 2023.</p>"
        "<p>Regulamenta os art. 82 a art. 86 da Lei nº 14.133, de 1º de abril de 2021.</p>"
    )
    assert conferir_data(pagina, "11462", date(2023, 3, 31), "decreto") == "ok"
    # e o rótulo do decreto não é confundido com o do decreto-lei
    dl = "<p>DECRETO-LEI Nº 4.657, DE 4 DE SETEMBRO DE 1942.</p>"
    assert conferir_data(dl, "4657", date(1942, 9, 4), "decreto") == "epigrafe nao localizada"
    assert conferir_data(dl, "4657", date(1942, 9, 4), "decreto.lei") == "ok"


def test_conferir_data_aceita_grafias_do_planalto():
    # "N o" com o "o" em <sup>, que o achatamento separa por espaço
    pagina = "<p>LEI N<sup>o</sup> 6.830, DE 22 DE SETEMBRO DE 1980.</p>"
    assert conferir_data(pagina, "6830", date(1980, 9, 22)) == "ok"
    # &nbsp; entre os termos e "DE" não repetido antes do ano
    nbsp = "<p>LEI Nº 9.433, DE 8 DE&nbsp;JANEIRO&nbsp;DE 1997.</p>"
    assert conferir_data(nbsp, "9433", date(1997, 1, 8)) == "ok"
    # entidade no lugar do caractere literal
    assert conferir_data("<p>LEI N&ordm; 9.433, DE 8 DE JANEIRO DE 1997.</p>",
                         "9433", date(1997, 1, 8)) == "ok"


def test_conferir_data_detecta_divergencia():
    pagina = "<p>LEI Nº 9.433, DE 8 DE JANEIRO DE 1997.</p>"
    assert conferir_data(pagina, "9433", date(1997, 1, 9)).startswith("DIVERGE")
    assert conferir_data("<p>sem epigrafe</p>", "9433", date(1997, 1, 8)) == (
        "epigrafe nao localizada"
    )


def test_epigrafe_canonica():
    assert epigrafe("lei", "9279", date(1996, 5, 14)) == "Lei nº 9.279, de 14 de maio de 1996"
    assert epigrafe("decreto.lei", "4657", date(1942, 9, 4), "LINDB") == (
        "Decreto-Lei nº 4.657, de 4 de setembro de 1942 (LINDB)"
    )
    assert epigrafe("decreto", "9580", date(2018, 11, 22), "RIR") == (
        "Decreto nº 9.580, de 22 de novembro de 2018 (RIR)"
    )
    assert "de 1º de janeiro" in epigrafe("lei", "1", date(2020, 1, 1))


def test_registro_ordinarias_entra_no_corpus_sem_poluir_o_tipo():
    vocabulario = {
        "lei", "codigo", "lei_complementar", "constituicao", "decreto", "regimento",
        "sumula_vinculante",
    }
    assert {m.tipo for m in REGISTRO.values()} <= vocabulario  # nunca "decreto.lei"
    # o curado continua vencendo em conflito de URN
    for slug, meta in REGISTRO_CURADO.items():
        assert REGISTRO[slug] is meta
    # e o lote de ordinárias está de fato mesclado
    assert "lindb_4657_1942" in REGISTRO
    assert REGISTRO["lindb_4657_1942"].urn_lex == (
        "urn:lex:br:federal:decreto.lei:1942-09-04;4657"
    )


def test_nenhuma_norma_entra_duas_vezes_no_corpus():
    # O REGISTRO é a mescla de quatro fontes (curado + três JSON gerados) e é
    # indexado por slug, então norma repetida sob slugs diferentes passaria: a
    # mesma lei entraria duas vezes no índice, dobrando pontos e ocorrências na
    # busca. Aconteceu no lote 5 com a Lei 14.600/2023. A chave real é o URN.
    urns = [m.urn_lex for m in REGISTRO.values()]
    repetidos = sorted({u for u in urns if urns.count(u) > 1})
    assert not repetidos, f"URN repetido no corpus: {repetidos}"
