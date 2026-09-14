"""Registro das normas do corpus.

``REGISTRO_CURADO`` é o núcleo essencial da legislação federal, mantido à mão:
mapeia cada norma para seu URN-LEX, metadados e URL canônica do Planalto. As 5
primeiras têm ``fixture`` (HTML offline em tests/fixtures/, usado como fallback);
as demais são baixadas ao vivo do Planalto. Todos os itens foram validados
(download + parse com dispositivos plausíveis).

As duas exceções à origem são os **regimentos internos** (``risf_93_1970`` e
``ricd_17_1989``), que o Planalto não publica: vêm do sítio da própria Casa, em
UTF-8 e com mais de um documento por página, e por isso carregam ``recorte``.

``REGISTRO`` (o catálogo efetivo do corpus) é o curado mesclado com três
registros gerados, todos validados por download + parse:

- ``registro_lcp.json`` — todas as Leis Complementares, produzido por
  ``scripts/descobrir_lcps.py`` a partir do quadro oficial do Planalto;
- ``registro_ordinarias.json`` — o lote curado de leis ordinárias de consulta
  frequente, produzido por ``scripts/descobrir_ordinarias.py`` (a lista é
  curada à mão; o script resolve a URL canônica, que o Planalto não deriva do
  número, e confere a data contra a epígrafe da página);
- ``registro_decretos.json`` — o núcleo de decretos regulamentadores e dos
  grandes regulamentos consolidados, produzido por
  ``scripts/descobrir_decretos.py`` pela mesma mecânica;
- ``sumulas_vinculantes.json`` — os enunciados de Súmula Vinculante do STF,
  produzido por ``scripts/descobrir_sumulas.py``. É a única entrada do catálogo
  que **não** aponta para uma página a rebaixar: o texto do enunciado mora no
  próprio JSON (ver ``ingest/jurisprudencia.py``).

Em conflito de URN, a entrada curada vence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class NormaMeta:
    slug: str
    urn_lex: str
    tipo: str  # "constituicao" | "lei_complementar" | "lei" | "codigo" | "decreto"
    #           | "regimento" | "sumula_vinculante"
    numero: str | None
    data: date
    epigrafe: str
    ementa: str
    url_canonica: str
    fixture: str | None = None  # nome do arquivo em tests/fixtures/ (fallback offline)
    # Trecho da página que é o documento, como (marcador de início, marcador de
    # fim); "" de um dos lados = sem corte ali. Só os regimentos usam: cada Casa
    # serve mais de um documento na mesma URL (ver ``html_parser.recortar``).
    recorte: tuple[str, str] | None = None


REGISTRO_CURADO: dict[str, NormaMeta] = {
    "cf_1988": NormaMeta(
        slug="cf_1988",
        urn_lex="urn:lex:br:federal:constituicao:1988-10-05;1988",
        tipo="constituicao",
        numero=None,
        data=date(1988, 10, 5),
        epigrafe="Constituição Federal de 1988",
        ementa="Constituição da República Federativa do Brasil de 1988.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm",
        fixture="cf_1988.html",
    ),
    "lcp_95_1998": NormaMeta(
        slug="lcp_95_1998",
        urn_lex="urn:lex:br:federal:lei.complementar:1998-02-26;95",
        tipo="lei_complementar",
        numero="95",
        data=date(1998, 2, 26),
        epigrafe="Lei Complementar nº 95, de 26 de fevereiro de 1998",
        ementa=(
            "Dispõe sobre a elaboração, a redação, a alteração e a consolidação das "
            "leis, conforme determina o parágrafo único do art. 59 da Constituição "
            "Federal, e estabelece normas para a consolidação dos atos normativos."
        ),
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp95.htm",
        fixture="lcp_95_1998.html",
    ),
    # ---------------------------------------------------------------- regimentos
    # Nenhum dos dois está no Planalto: cada Casa publica o seu, em UTF-8 e com
    # mais de um documento na mesma página — daí o ``recorte`` e o
    # ``ingest/parlamento_fetcher.py``. O URN usa a autoridade da Casa
    # (``senado.federal``, ``camara.deputados``), não ``federal``, que no LexML
    # é a União: resolução de Casa é norma interna dela, não da Federação.
    "risf_93_1970": NormaMeta(
        slug="risf_93_1970",
        urn_lex="urn:lex:br:senado.federal:resolucao:1970-11-27;93",
        tipo="regimento",
        numero="93",
        data=date(1970, 11, 27),
        epigrafe=(
            "Resolução do Senado Federal nº 93, de 27 de novembro de 1970 "
            "(Regimento Interno do Senado Federal)"
        ),
        ementa="Regimento Interno do Senado Federal.",
        url_canonica="https://legis.senado.leg.br/norma/563958/publicacao/16433779",
        # Corta a nota de compilação e o rodapé do portal, que sem isso entram
        # colados ao art. 413 — o papel que nas leis cabe ao corte no fecho.
        recorte=("", "(*) Compilação produzida com base no texto consolidado"),
    ),
    "ricd_17_1989": NormaMeta(
        slug="ricd_17_1989",
        urn_lex="urn:lex:br:camara.deputados:resolucao:1989-09-21;17",
        tipo="regimento",
        numero="17",
        data=date(1989, 9, 21),
        epigrafe=(
            "Resolução da Câmara dos Deputados nº 17, de 21 de setembro de 1989 "
            "(Regimento Interno da Câmara dos Deputados)"
        ),
        ementa="Regimento Interno da Câmara dos Deputados.",
        url_canonica=(
            "https://www2.camara.leg.br/legin/fed/rescad/1989/"
            "resolucaodacamaradosdeputados-17-21-setembro-1989-320110-normaatualizada-pl.html"
        ),
        # A página traz TRÊS documentos: os 8 artigos de promulgação da Resolução
        # 17, o Regimento anexo (que recomeça em "Art. 1º") e a Resolução 25/2001
        # com o Código de Ética. Sem o corte, ``art_1`` seria "O Regimento Interno
        # ... passa a vigorar na conformidade do texto anexo" e o art. 1º do
        # Regimento levaria o sufixo ``__1`` — 31 paths duplicados, medidos.
        recorte=(
            "<b>REGIMENTO INTERNO DA CÂMARA DOS DEPUTADOS</b>",
            "<b>RESOLUÇÃO Nº 25, DE 2001</b>",
        ),
    ),
    "lei_8666_1993": NormaMeta(
        slug="lei_8666_1993",
        urn_lex="urn:lex:br:federal:lei:1993-06-21;8666",
        tipo="lei",
        numero="8666",
        data=date(1993, 6, 21),
        epigrafe="Lei nº 8.666, de 21 de junho de 1993",
        ementa=(
            "Regulamenta o art. 37, inciso XXI, da Constituição Federal, institui "
            "normas para licitações e contratos da Administração Pública."
        ),
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l8666cons.htm",
        fixture="lei_8666_1993.html",
    ),
    "lei_14133_2021": NormaMeta(
        slug="lei_14133_2021",
        urn_lex="urn:lex:br:federal:lei:2021-04-01;14133",
        tipo="lei",
        numero="14133",
        data=date(2021, 4, 1),
        epigrafe="Lei nº 14.133, de 1º de abril de 2021",
        ementa="Lei de Licitações e Contratos Administrativos.",
        url_canonica=(
            "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm"
        ),
        fixture="lei_14133_2021.html",
    ),
    "cc_10406_2002": NormaMeta(
        slug="cc_10406_2002",
        urn_lex="urn:lex:br:federal:lei:2002-01-10;10406",
        tipo="codigo",
        numero="10406",
        data=date(2002, 1, 10),
        epigrafe="Lei nº 10.406, de 10 de janeiro de 2002 (Código Civil)",
        ementa="Institui o Código Civil.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm",
        fixture="cc_10406_2002.html",
    ),
    "cp_2848_1940": NormaMeta(
        slug="cp_2848_1940",
        urn_lex="urn:lex:br:federal:decreto.lei:1940-12-07;2848",
        tipo="codigo",
        numero="2848",
        data=date(1940, 12, 7),
        epigrafe="Decreto-Lei nº 2.848, de 7 de dezembro de 1940 (Código Penal)",
        ementa="Código Penal.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm",
    ),
    "cpp_3689_1941": NormaMeta(
        slug="cpp_3689_1941",
        urn_lex="urn:lex:br:federal:decreto.lei:1941-10-03;3689",
        tipo="codigo",
        numero="3689",
        data=date(1941, 10, 3),
        epigrafe="Decreto-Lei nº 3.689, de 3 de outubro de 1941 (Código de Processo Penal)",
        ementa="Código de Processo Penal.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/decreto-lei/del3689compilado.htm",
    ),
    "cpc_13105_2015": NormaMeta(
        slug="cpc_13105_2015",
        urn_lex="urn:lex:br:federal:lei:2015-03-16;13105",
        tipo="codigo",
        numero="13105",
        data=date(2015, 3, 16),
        epigrafe="Lei nº 13.105, de 16 de março de 2015 (Código de Processo Civil)",
        ementa="Código de Processo Civil.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm",
    ),
    "ctn_5172_1966": NormaMeta(
        slug="ctn_5172_1966",
        urn_lex="urn:lex:br:federal:lei:1966-10-25;5172",
        tipo="codigo",
        numero="5172",
        data=date(1966, 10, 25),
        epigrafe="Lei nº 5.172, de 25 de outubro de 1966 (Código Tributário Nacional)",
        ementa="Dispõe sobre o Sistema Tributário Nacional (Código Tributário Nacional).",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l5172compilado.htm",
    ),
    "clt_5452_1943": NormaMeta(
        slug="clt_5452_1943",
        urn_lex="urn:lex:br:federal:decreto.lei:1943-05-01;5452",
        tipo="codigo",
        numero="5452",
        data=date(1943, 5, 1),
        epigrafe="Decreto-Lei nº 5.452, de 1º de maio de 1943 (CLT)",
        ementa="Consolidação das Leis do Trabalho.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452compilado.htm",
    ),
    "cdc_8078_1990": NormaMeta(
        slug="cdc_8078_1990",
        urn_lex="urn:lex:br:federal:lei:1990-09-11;8078",
        tipo="codigo",
        numero="8078",
        data=date(1990, 9, 11),
        epigrafe="Lei nº 8.078, de 11 de setembro de 1990 (Código de Defesa do Consumidor)",
        ementa="Dispõe sobre a proteção do consumidor.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm",
    ),
    "ctb_9503_1997": NormaMeta(
        slug="ctb_9503_1997",
        urn_lex="urn:lex:br:federal:lei:1997-09-23;9503",
        tipo="codigo",
        numero="9503",
        data=date(1997, 9, 23),
        epigrafe="Lei nº 9.503, de 23 de setembro de 1997 (Código de Trânsito Brasileiro)",
        ementa="Institui o Código de Trânsito Brasileiro.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l9503compilado.htm",
    ),
    "celeitoral_4737_1965": NormaMeta(
        slug="celeitoral_4737_1965",
        urn_lex="urn:lex:br:federal:lei:1965-07-15;4737",
        tipo="codigo",
        numero="4737",
        data=date(1965, 7, 15),
        epigrafe="Lei nº 4.737, de 15 de julho de 1965 (Código Eleitoral)",
        ementa="Institui o Código Eleitoral.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l4737compilado.htm",
    ),
    "cflorestal_12651_2012": NormaMeta(
        slug="cflorestal_12651_2012",
        urn_lex="urn:lex:br:federal:lei:2012-05-25;12651",
        tipo="lei",
        numero="12651",
        data=date(2012, 5, 25),
        epigrafe="Lei nº 12.651, de 25 de maio de 2012 (Código Florestal)",
        ementa="Dispõe sobre a proteção da vegetação nativa (Código Florestal).",
        url_canonica="https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/lei/l12651.htm",
    ),
    "lei_8112_1990": NormaMeta(
        slug="lei_8112_1990",
        urn_lex="urn:lex:br:federal:lei:1990-12-11;8112",
        tipo="lei",
        numero="8112",
        data=date(1990, 12, 11),
        epigrafe="Lei nº 8.112, de 11 de dezembro de 1990",
        ementa="Regime Jurídico dos Servidores Públicos Civis da União.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l8112cons.htm",
    ),
    "lei_9784_1999": NormaMeta(
        slug="lei_9784_1999",
        urn_lex="urn:lex:br:federal:lei:1999-01-29;9784",
        tipo="lei",
        numero="9784",
        data=date(1999, 1, 29),
        epigrafe="Lei nº 9.784, de 29 de janeiro de 1999",
        ementa="Regula o processo administrativo no âmbito da Administração Pública Federal.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l9784.htm",
    ),
    "lcp_101_2000": NormaMeta(
        slug="lcp_101_2000",
        urn_lex="urn:lex:br:federal:lei.complementar:2000-05-04;101",
        tipo="lei_complementar",
        numero="101",
        data=date(2000, 5, 4),
        epigrafe="Lei Complementar nº 101, de 4 de maio de 2000 (Lei de Responsabilidade Fiscal)",
        ementa="Normas de finanças públicas voltadas para a responsabilidade na gestão fiscal.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp101.htm",
    ),
    "lei_4320_1964": NormaMeta(
        slug="lei_4320_1964",
        urn_lex="urn:lex:br:federal:lei:1964-03-17;4320",
        tipo="lei",
        numero="4320",
        data=date(1964, 3, 17),
        epigrafe="Lei nº 4.320, de 17 de março de 1964",
        ementa="Normas gerais de direito financeiro para elaboração e controle dos orçamentos.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l4320compilado.htm",
    ),
    "lei_8429_1992": NormaMeta(
        slug="lei_8429_1992",
        urn_lex="urn:lex:br:federal:lei:1992-06-02;8429",
        tipo="lei",
        numero="8429",
        data=date(1992, 6, 2),
        epigrafe="Lei nº 8.429, de 2 de junho de 1992 (Improbidade Administrativa)",
        ementa="Dispõe sobre as sanções por atos de improbidade administrativa.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l8429.htm",
    ),
    "lei_12846_2013": NormaMeta(
        slug="lei_12846_2013",
        urn_lex="urn:lex:br:federal:lei:2013-08-01;12846",
        tipo="lei",
        numero="12846",
        data=date(2013, 8, 1),
        epigrafe="Lei nº 12.846, de 1º de agosto de 2013 (Lei Anticorrupção)",
        ementa="Responsabilização de pessoas jurídicas por atos contra a administração pública.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/lei/l12846.htm",
    ),
    "lei_12527_2011": NormaMeta(
        slug="lei_12527_2011",
        urn_lex="urn:lex:br:federal:lei:2011-11-18;12527",
        tipo="lei",
        numero="12527",
        data=date(2011, 11, 18),
        epigrafe="Lei nº 12.527, de 18 de novembro de 2011 (Lei de Acesso à Informação)",
        ementa="Regula o acesso a informações previsto na Constituição Federal.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm",
    ),
    "lei_13709_2018": NormaMeta(
        slug="lei_13709_2018",
        urn_lex="urn:lex:br:federal:lei:2018-08-14;13709",
        tipo="lei",
        numero="13709",
        data=date(2018, 8, 14),
        epigrafe="Lei nº 13.709, de 14 de agosto de 2018 (LGPD)",
        ementa="Lei Geral de Proteção de Dados Pessoais.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm",
    ),
    "lei_13303_2016": NormaMeta(
        slug="lei_13303_2016",
        urn_lex="urn:lex:br:federal:lei:2016-06-30;13303",
        tipo="lei",
        numero="13303",
        data=date(2016, 6, 30),
        epigrafe="Lei nº 13.303, de 30 de junho de 2016 (Estatuto das Estatais)",
        ementa="Estatuto jurídico da empresa pública e da sociedade de economia mista.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2016/lei/l13303.htm",
    ),
    "lcp_116_2003": NormaMeta(
        slug="lcp_116_2003",
        urn_lex="urn:lex:br:federal:lei.complementar:2003-07-31;116",
        tipo="lei_complementar",
        numero="116",
        data=date(2003, 7, 31),
        epigrafe="Lei Complementar nº 116, de 31 de julho de 2003",
        ementa="Dispõe sobre o Imposto Sobre Serviços de Qualquer Natureza (ISS).",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp116.htm",
    ),
    "lcp_123_2006": NormaMeta(
        slug="lcp_123_2006",
        urn_lex="urn:lex:br:federal:lei.complementar:2006-12-14;123",
        tipo="lei_complementar",
        numero="123",
        data=date(2006, 12, 14),
        epigrafe="Lei Complementar nº 123, de 14 de dezembro de 2006 (Simples Nacional)",
        ementa="Estatuto Nacional da Microempresa e da Empresa de Pequeno Porte.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm",
    ),
    "lei_9868_1999": NormaMeta(
        slug="lei_9868_1999",
        urn_lex="urn:lex:br:federal:lei:1999-11-10;9868",
        tipo="lei",
        numero="9868",
        data=date(1999, 11, 10),
        epigrafe="Lei nº 9.868, de 10 de novembro de 1999",
        ementa="Processo e julgamento da ADI e da ADC perante o STF.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l9868.htm",
    ),
    "lei_9882_1999": NormaMeta(
        slug="lei_9882_1999",
        urn_lex="urn:lex:br:federal:lei:1999-12-03;9882",
        tipo="lei",
        numero="9882",
        data=date(1999, 12, 3),
        epigrafe="Lei nº 9.882, de 3 de dezembro de 1999",
        ementa="Processo e julgamento da arguição de descumprimento de preceito fundamental.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l9882.htm",
    ),
    "eca_8069_1990": NormaMeta(
        slug="eca_8069_1990",
        urn_lex="urn:lex:br:federal:lei:1990-07-13;8069",
        tipo="lei",
        numero="8069",
        data=date(1990, 7, 13),
        epigrafe="Lei nº 8.069, de 13 de julho de 1990 (Estatuto da Criança e do Adolescente)",
        ementa="Dispõe sobre o Estatuto da Criança e do Adolescente.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l8069.htm",
    ),
    "idoso_10741_2003": NormaMeta(
        slug="idoso_10741_2003",
        urn_lex="urn:lex:br:federal:lei:2003-10-01;10741",
        tipo="lei",
        numero="10741",
        data=date(2003, 10, 1),
        epigrafe="Lei nº 10.741, de 1º de outubro de 2003 (Estatuto da Pessoa Idosa)",
        ementa="Dispõe sobre o Estatuto da Pessoa Idosa.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/2003/l10.741.htm",
    ),
    "pcd_13146_2015": NormaMeta(
        slug="pcd_13146_2015",
        urn_lex="urn:lex:br:federal:lei:2015-07-06;13146",
        tipo="lei",
        numero="13146",
        data=date(2015, 7, 6),
        epigrafe="Lei nº 13.146, de 6 de julho de 2015 (Estatuto da Pessoa com Deficiência)",
        ementa="Lei Brasileira de Inclusão da Pessoa com Deficiência.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13146.htm",
    ),
    "sus_8080_1990": NormaMeta(
        slug="sus_8080_1990",
        urn_lex="urn:lex:br:federal:lei:1990-09-19;8080",
        tipo="lei",
        numero="8080",
        data=date(1990, 9, 19),
        epigrafe="Lei nº 8.080, de 19 de setembro de 1990 (Lei Orgânica da Saúde)",
        ementa="Dispõe sobre as condições para promoção, proteção e recuperação da saúde (SUS).",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l8080.htm",
    ),
    "ldb_9394_1996": NormaMeta(
        slug="ldb_9394_1996",
        urn_lex="urn:lex:br:federal:lei:1996-12-20;9394",
        tipo="lei",
        numero="9394",
        data=date(1996, 12, 20),
        epigrafe="Lei nº 9.394, de 20 de dezembro de 1996 (LDB)",
        ementa="Estabelece as diretrizes e bases da educação nacional.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l9394.htm",
    ),
    "juizados_9099_1995": NormaMeta(
        slug="juizados_9099_1995",
        urn_lex="urn:lex:br:federal:lei:1995-09-26;9099",
        tipo="lei",
        numero="9099",
        data=date(1995, 9, 26),
        epigrafe="Lei nº 9.099, de 26 de setembro de 1995 (Juizados Especiais)",
        ementa="Dispõe sobre os Juizados Especiais Cíveis e Criminais.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l9099.htm",
    ),
    "beneficios_8213_1991": NormaMeta(
        slug="beneficios_8213_1991",
        urn_lex="urn:lex:br:federal:lei:1991-07-24;8213",
        tipo="lei",
        numero="8213",
        data=date(1991, 7, 24),
        epigrafe="Lei nº 8.213, de 24 de julho de 1991 (Planos de Benefícios da Previdência)",
        ementa="Dispõe sobre os Planos de Benefícios da Previdência Social.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/leis/l8213cons.htm",
    ),
    "mariadapenha_11340_2006": NormaMeta(
        slug="mariadapenha_11340_2006",
        urn_lex="urn:lex:br:federal:lei:2006-08-07;11340",
        tipo="lei",
        numero="11340",
        data=date(2006, 8, 7),
        epigrafe="Lei nº 11.340, de 7 de agosto de 2006 (Lei Maria da Penha)",
        ementa="Cria mecanismos para coibir a violência doméstica e familiar contra a mulher.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2006/lei/l11340.htm",
    ),
}

REGISTRO_LCP_PATH = Path(__file__).with_name("registro_lcp.json")
REGISTRO_ORDINARIAS_PATH = Path(__file__).with_name("registro_ordinarias.json")
REGISTRO_DECRETOS_PATH = Path(__file__).with_name("registro_decretos.json")
SUMULAS_VINCULANTES_PATH = Path(__file__).with_name("sumulas_vinculantes.json")


def _carregar_json(caminho: Path, tipo_padrao: str) -> dict[str, NormaMeta]:
    """Lê um registro gerado, descartando o que já está no curado (que vence)."""
    if not caminho.exists():
        return {}
    entradas = json.loads(caminho.read_text(encoding="utf-8"))
    urns_curadas = {m.urn_lex for m in REGISTRO_CURADO.values()}
    return {
        e["slug"]: NormaMeta(
            slug=e["slug"],
            urn_lex=e["urn_lex"],
            tipo=e.get("tipo", tipo_padrao),
            numero=e["numero"],
            data=date.fromisoformat(e["data"]),
            epigrafe=e["epigrafe"],
            ementa=e["ementa"],
            url_canonica=e["url_canonica"],
        )
        for e in entradas
        if e["urn_lex"] not in urns_curadas
    }


def _carregar_sumulas() -> dict[str, NormaMeta]:
    """Metadados das Súmulas Vinculantes a partir do JSON curado.

    O arquivo tem esquema próprio (número, enunciado, situação) em vez do
    ``slug``/``epigrafe``/``ementa`` dos registros de legislação, então não passa
    por ``_carregar_json``: aqui os campos do ``NormaMeta`` são derivados do
    número da súmula. A ementa fica vazia de propósito — o enunciado é curto e
    resumi-lo seria inventar texto que o STF não escreveu.

    ``url_canonica`` aponta para a página da súmula no portal do STF (a mesma de
    onde o enunciado foi colhido), e não para um resolvedor LexML: o LexML não
    indexa súmula vinculante, e citar URL que não resolve seria pior do que
    citar a fonte real.
    """
    if not SUMULAS_VINCULANTES_PATH.exists():
        return {}
    entradas = json.loads(SUMULAS_VINCULANTES_PATH.read_text(encoding="utf-8"))
    return {
        f"sv_{e['numero']}": NormaMeta(
            slug=f"sv_{e['numero']}",
            urn_lex=e["urn_lex"],
            tipo="sumula_vinculante",
            numero=str(e["numero"]),
            data=date.fromisoformat(e["data_aprovacao"]),
            epigrafe=f"Súmula Vinculante {e['numero']} do STF",
            ementa="",
            url_canonica=e["fonte_stf"],
        )
        for e in entradas
    }


REGISTRO: dict[str, NormaMeta] = {
    **REGISTRO_CURADO,
    **_carregar_json(REGISTRO_LCP_PATH, "lei_complementar"),
    **_carregar_json(REGISTRO_ORDINARIAS_PATH, "lei"),
    **_carregar_json(REGISTRO_DECRETOS_PATH, "decreto"),
    **_carregar_sumulas(),
}


def recarregar_registro() -> int:
    """Relê os registros gerados **no mesmo dicionário**, devolvendo o total.

    O daemon monta o ``REGISTRO`` uma vez, no import, e quem consome importa o
    dicionário direto (``from ... import REGISTRO``). Sem isto, um lote novo
    descoberto com o daemon no ar não existe para ele: o ``POST /update`` roda
    sobre o catálogo velho, devolve ``atualizadas: {}`` e o índice fica parado —
    um "não fez nada" que parece sucesso. Aconteceu no lote 5. Mutar o mesmo
    objeto (em vez de reatribuir ou recarregar o módulo) faz o catálogo novo
    valer para todos os importadores, sem mexer no cliente do Qdrant nem nos
    modelos já carregados.
    """
    # Import tardio: jurisprudencia importa este módulo, e o cache de enunciados
    # dele é a outra metade do catálogo de súmulas — recarregar só os metadados
    # deixaria o texto velho sendo servido, com a mesma cara de sucesso do lote 5.
    from lex_rag.ingest import jurisprudencia

    jurisprudencia.recarregar()
    REGISTRO.clear()
    REGISTRO.update(REGISTRO_CURADO)
    REGISTRO.update(_carregar_json(REGISTRO_LCP_PATH, "lei_complementar"))
    REGISTRO.update(_carregar_json(REGISTRO_ORDINARIAS_PATH, "lei"))
    REGISTRO.update(_carregar_json(REGISTRO_DECRETOS_PATH, "decreto"))
    REGISTRO.update(_carregar_sumulas())
    return len(REGISTRO)


def por_urn(urn_lex: str) -> NormaMeta | None:
    for meta in REGISTRO.values():
        if meta.urn_lex == urn_lex:
            return meta
    return None
