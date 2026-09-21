"""Registro das normas do corpus.

``REGISTRO_CURADO`` é o núcleo essencial da legislação federal, mantido à mão:
mapeia cada norma para seu URN-LEX, metadados e URL canônica do Planalto. As 5
primeiras têm ``fixture`` (HTML offline em tests/fixtures/, usado como fallback);
as demais são baixadas ao vivo do Planalto. Todos os itens foram validados
(download + parse com dispositivos plausíveis).

As exceções à origem são os **regimentos internos** (``risf_93_1970`` e
``ricd_17_1989``) e as **resoluções das Casas** (lote 21: Regimento Comum,
Códigos de Ética e as resoluções do Senado do art. 52 da CF), que o Planalto não
publica: vêm do sítio da própria Casa, em UTF-8 e com mais de um documento (ou
o rodapé do portal) na mesma página, e por isso carregam ``recorte``.

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
  produzido por ``scripts/descobrir_sumulas.py``, e ``sumulas_stf.json`` — as
  súmulas simples do STF (lote 22-A), por ``scripts/descobrir_sumulas_stf.py``.
  São as únicas entradas do catálogo que **não** apontam para uma página a
  rebaixar: o texto do enunciado mora no próprio JSON (ver
  ``ingest/jurisprudencia.py``);
- ``registro_novas.json`` — as leis ordinárias sancionadas depois do último
  lote que a triagem por ementa julgou de consulta (leis autônomas, não as que
  só alteram norma já presente), produzido por ``scripts/descobrir_novas.py``
  varrendo a numeração na API de metadados do LexML. Perde para qualquer outro
  registro em conflito de URN: promover uma lei daqui para a lista curada não a
  duplica.

Em conflito de URN, a entrada curada vence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from lex_rag.ingest.planalto_urls import MESES


@dataclass(frozen=True)
class NormaMeta:
    slug: str
    urn_lex: str
    tipo: str  # "constituicao" | "lei_complementar" | "lei" | "codigo" | "decreto"
    #           | "regimento" | "resolucao" | "sumula_vinculante" | "sumula_stf"
    numero: str | None
    data: date
    epigrafe: str
    ementa: str
    url_canonica: str
    fixture: str | None = None  # nome do arquivo em tests/fixtures/ (fallback offline)
    # Trecho da página que é o documento, como (marcador de início, marcador de
    # fim); "" de um dos lados = sem corte ali (ver ``html_parser.recortar``).
    # Usam: os regimentos (cada Casa serve mais de um documento na mesma URL);
    # a CF e o ADCT, que dividem a página e recomeçam em "Art. 1º"; e o texto
    # aprovado **apenso** a um ato de aprovação (a CLT no Decreto-Lei 5.452, o
    # Regulamento no decreto que o aprova), em que o apenso é o documento que se
    # cita e tem de ser dono de ``art_N`` — o parser trataria o corpo como a
    # norma e o apenso como anexo (``anexo_art_N``).
    recorte: tuple[str, str] | None = None


# Cabeçalho do ADCT na página da CF (ocorrência única no HTML).
_ADCT_MARCADOR = "ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS"

# Resoluções servidas pelo portal de legislação do Senado (lote 21). Cada norma
# tem um id e várias publicações; a que serve o texto compilado é a
# "Compilação Multivigente" (ou a publicação original, quando é a única), e o
# id dela só se descobre na página da norma — a API de dados abertos
# (``dadosabertos/legislacao/lista?tipo=RSF&numero=&ano=``) dá o id da norma,
# a data de assinatura e a ementa. O HTML do documento vem embutido, como um
# ``<html>`` interno gerado do Word, dentro da página do portal; o fecho da Casa
# ("Senado Federal, em 9 de abril de 2002") não tem o "Nº da Independência" que
# o parser usa para cortar assinaturas e notas, então o ``recorte`` termina
# nele — ou na nota de compilação, quando o fecho não é impresso.
_CASA = {
    "RSF": ("senado.federal", "Resolução do Senado Federal"),
    "RCN": ("congresso.nacional", "Resolução do Congresso Nacional"),
}
_RESOLUCOES_SENADO: list[tuple[str, str, str, date, str, str, str, int, int, str]] = [
    # (slug, sigla, número, data, tipo, apelido, ementa, id da norma, id da publicação, fim)
    ("rcn_1_1970", "RCN", "1", date(1970, 8, 11), "regimento",
     "Regimento Comum do Congresso Nacional", "Regimento Comum do Congresso Nacional.",
     # Corta no traço que separa o articulado da nota de compilação.
     561098, 16433839, "<span>_______________</span>"),
    ("rcn_1_2002", "RCN", "1", date(2002, 5, 8), "regimento",
     "tramitação das medidas provisórias",
     "Dispõe sobre a apreciação, pelo Congresso Nacional, das Medidas Provisórias a que "
     "se refere o art. 62 da Constituição Federal.",
     561120, 27423643, '<span style="font-size:9pt; font-weight:bold">(*)</span>'),
    ("rcn_1_2006", "RCN", "1", date(2006, 12, 22), "regimento",
     "Comissão Mista de Orçamento — CMO",
     "Dispõe sobre a Comissão Mista Permanente a que se refere o § 1º do art. 166 da "
     "Constituição, bem como a tramitação das matérias a que se refere o mesmo artigo.",
     561123, 16433888, "Congresso Nacional, em 22 de dezembro de 2006"),
    ("rsf_20_1993", "RSF", "20", date(1993, 3, 17), "regimento",
     "Código de Ética e Decoro Parlamentar do Senado Federal",
     "Institui o Código de Ética e Decoro Parlamentar.",
     561878, 16433594, "Senado Federal, 17 de março de 1993"),
    ("rsf_40_2001", "RSF", "40", date(2001, 12, 20), "resolucao",
     "limites da dívida consolidada e mobiliária dos Estados, do DF e dos Municípios",
     "Dispõe sobre os limites globais para o montante da dívida pública consolidada e da "
     "dívida pública mobiliária dos Estados, do Distrito Federal e dos Municípios, em "
     "atendimento ao disposto no art. 52, VI e IX, da Constituição Federal.",
     562458, 16433576, "Senado Federal, em 9 de abril de 2002"),
    ("rsf_43_2001", "RSF", "43", date(2001, 12, 21), "resolucao",
     "operações de crédito dos Estados, do DF e dos Municípios",
     "Dispõe sobre as operações de crédito interno e externo dos Estados, do Distrito "
     "Federal e dos Municípios, inclusive concessão de garantias, seus limites e "
     "condições de autorização.",
     582604, 16433616, "Senado Federal, em 9 de abril de 2002"),
    ("rsf_48_2007", "RSF", "48", date(2007, 12, 21), "resolucao",
     "operações de crédito e garantias da União",
     "Dispõe sobre os limites globais para as operações de crédito externo e interno da "
     "União, de suas autarquias e demais entidades controladas pelo Poder Público "
     "federal e estabelece limites e condições para a concessão de garantia da União em "
     "operações de crédito externo e interno.",
     576233, 16433642, "Senado Federal, em 21 de dezembro de 2007"),
    ("rsf_13_2012", "RSF", "13", date(2012, 4, 25), "resolucao",
     "alíquota interestadual do ICMS para bens importados",
     "Estabelece alíquotas do Imposto sobre Operações Relativas à Circulação de "
     "Mercadorias e sobre Prestação de Serviços de Transporte Interestadual e "
     "Intermunicipal e de Comunicação (ICMS), nas operações interestaduais com bens e "
     "mercadorias importados do exterior.",
     586999, 15839317, "Senado Federal, em 25 de abril de 2012"),
    ("rsf_95_1996", "RSF", "95", date(1996, 12, 13), "resolucao",
     "alíquota do ICMS no transporte aéreo interestadual",
     "Fixa alíquota para cobrança do ICMS (transporte aéreo interestadual de passageiro, "
     "carga e mala postal).",
     564024, 15758402, "Senado Federal, em 13 de dezembro de 1996"),
    ("rsf_9_1992", "RSF", "9", date(1992, 5, 5), "resolucao",
     "alíquota máxima do ITCMD",
     "Estabelece alíquota máxima para o Imposto sobre Transmissão Causa Mortis e Doação, "
     "de que trata a alínea a, inciso I, e § 1º, inciso IV do art. 155 da Constituição "
     "Federal.",
     # O fecho impresso grafa "1991" — erro da fonte; a epígrafe e a API dizem 1992.
     590017, 15785996, "Senado Federal, 5 de maio de 1991"),
]


def _resolucoes_senado() -> dict[str, NormaMeta]:
    """Entradas curadas das resoluções servidas pelo portal do Senado."""
    saida: dict[str, NormaMeta] = {}
    for slug, sigla, numero, d, tipo, apelido, ementa, norma_id, pub_id, fim in _RESOLUCOES_SENADO:
        autoridade, rotulo = _CASA[sigla]
        dia = "1º" if d.day == 1 else str(d.day)
        saida[slug] = NormaMeta(
            slug=slug,
            urn_lex=f"urn:lex:br:{autoridade}:resolucao:{d.isoformat()};{numero}",
            tipo=tipo,
            numero=numero,
            data=d,
            epigrafe=f"{rotulo} nº {numero}, de {dia} de {MESES[d.month - 1]} de {d.year} "
                     f"({apelido})",
            ementa=ementa,
            url_canonica=f"https://legis.senado.leg.br/norma/{norma_id}/publicacao/{pub_id}",
            recorte=("", fim),
        )
    return saida

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
        # A mesma página traz o ADCT, que recomeça em "Art. 1º": sem o corte, o
        # art. 1º do ADCT saía como ``art_1__1`` e ``art_97`` (precatórios) só
        # existia como ``art_97__1`` — 128 paths duplicados, medidos no lote 11.
        recorte=("", _ADCT_MARCADOR),
    ),
    "adct_1988": NormaMeta(
        slug="adct_1988",
        # O ``!`` é o componente de fragmento do padrão LexML; o ADCT é parte da
        # mesma Constituição, não norma distinta, e o resolvedor não conhece a
        # forma — registrado como sintético, a exemplo das súmulas.
        urn_lex="urn:lex:br:federal:constituicao:1988-10-05;1988!adct",
        tipo="constituicao",
        numero=None,
        data=date(1988, 10, 5),
        epigrafe="Ato das Disposições Constitucionais Transitórias (ADCT)",
        ementa="Ato das Disposições Constitucionais Transitórias da Constituição de 1988.",
        url_canonica="https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm",
        fixture="cf_1988.html",
        recorte=(_ADCT_MARCADOR, ""),
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
    # O terceiro documento da mesma página: o Código de Ética anexo à Resolução
    # 25/2001. O corte começa no cabeçalho do Código (depois dos 4 artigos de
    # promulgação, que recomeçam em Art. 1º) e vai até o fim da página.
    "rcd_25_2001": NormaMeta(
        slug="rcd_25_2001",
        urn_lex="urn:lex:br:camara.deputados:resolucao:2001-10-10;25",
        tipo="regimento",
        numero="25",
        data=date(2001, 10, 10),
        epigrafe=(
            "Resolução da Câmara dos Deputados nº 25, de 10 de outubro de 2001 "
            "(Código de Ética e Decoro Parlamentar da Câmara dos Deputados)"
        ),
        ementa="Institui o Código de Ética e Decoro Parlamentar da Câmara dos Deputados.",
        url_canonica=(
            "https://www2.camara.leg.br/legin/fed/rescad/1989/"
            "resolucaodacamaradosdeputados-17-21-setembro-1989-320110-normaatualizada-pl.html"
        ),
        recorte=("<b>CÓDIGO DE ÉTICA E DECORO PARLAMENTAR DA CÂMARA DOS DEPUTADOS</b>", ""),
    ),
    **_resolucoes_senado(),
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
        # O Decreto-Lei aprova a Consolidação e a serve apensa: sem o corte,
        # ``art_1`` era "Fica aprovada a Consolidação..." e o art. 1º da CLT
        # saía como ``art_1__1`` (lote 11).
        recorte=("CONSOLIDAÇÃO DAS LEIS DO TRABALHO", ""),
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
SUMULAS_STF_PATH = Path(__file__).with_name("sumulas_stf.json")
REGISTRO_NOVAS_PATH = Path(__file__).with_name("registro_novas.json")


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
            recorte=tuple(e["recorte"]) if e.get("recorte") else None,
        )
        for e in entradas
        if e["urn_lex"] not in urns_curadas
    }


def _carregar_sumulas(
    caminho: Path | None = None,
    tipo: str = "sumula_vinculante",
    prefixo: str = "sv",
    rotulo: str = "Súmula Vinculante",
) -> dict[str, NormaMeta]:
    """Metadados das súmulas a partir do JSON curado (SV por padrão; STF, lote 22-A).

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
    caminho = caminho or SUMULAS_VINCULANTES_PATH  # resolvido na chamada (testes trocam)
    if not caminho.exists():
        return {}
    entradas = json.loads(caminho.read_text(encoding="utf-8"))
    return {
        f"{prefixo}_{e['numero']}": NormaMeta(
            slug=f"{prefixo}_{e['numero']}",
            urn_lex=e["urn_lex"],
            tipo=tipo,
            numero=str(e["numero"]),
            # A data do URN: aprovação, ou publicação quando o STF só imprime esta.
            data=date.fromisoformat(e.get("data_aprovacao") or e["data_publicacao"]),
            epigrafe=f"{rotulo} {e['numero']} do STF",
            ementa="",
            url_canonica=e["fonte_stf"],
        )
        for e in entradas
    }


def _montar_registro() -> dict[str, NormaMeta]:
    registro = {
        **REGISTRO_CURADO,
        **_carregar_json(REGISTRO_LCP_PATH, "lei_complementar"),
        **_carregar_json(REGISTRO_ORDINARIAS_PATH, "lei"),
        **_carregar_json(REGISTRO_DECRETOS_PATH, "decreto"),
        **_carregar_sumulas(),
        **_carregar_sumulas(SUMULAS_STF_PATH, "sumula_stf", "sumula_stf", "Súmula"),
    }
    # As leis descobertas entram por último e só onde o URN ainda não existe:
    # uma lei promovida daqui para a lista curada (slug e apelido à mão) teria
    # dois slugs para o mesmo URN, e o índice a serviria em dobro.
    urns = {m.urn_lex for m in registro.values()}
    registro.update({
        slug: meta
        for slug, meta in _carregar_json(REGISTRO_NOVAS_PATH, "lei").items()
        if meta.urn_lex not in urns
    })
    return registro


REGISTRO: dict[str, NormaMeta] = _montar_registro()


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
    REGISTRO.update(_montar_registro())
    return len(REGISTRO)


def por_urn(urn_lex: str) -> NormaMeta | None:
    for meta in REGISTRO.values():
        if meta.urn_lex == urn_lex:
            return meta
    return None
