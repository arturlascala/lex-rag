"""Gera o registro do lote curado de decretos (``registro_decretos.json``).

Mesma mecânica de ``descobrir_ordinarias.py`` — lista curada à mão, script
resolve a URL canônica e confere a data contra a epígrafe impressa na página —,
com três diferenças que a espécie impõe:

- **A URL muda de convenção por faixa de ano** (``_dirs_decreto`` em
  ``planalto_urls``): ``_ato{faixa}/{ano}/decreto/`` de 2004 em diante,
  ``decreto/{ano}/`` ou ``decreto/`` entre 1999 e 2003, ``decreto/1990-1994/``
  ou ``decreto/`` na primeira metade dos anos 1990, e ``decreto/`` (sufixo
  ``cons``) ou ``decreto/antigos/`` antes disso.
- **A conferência da data é restrita ao rótulo "DECRETO"**: a página de um
  decreto cita, logo abaixo da epígrafe, a lei que ele regulamenta, e um padrão
  frouxo casaria essa referência.
- **O tipo do corpus é ``decreto``**, valor novo no vocabulário do filtro
  ``tipo_norma``.

Recorte do lote: o decreto que **regulamenta** lei já presente no corpus ou que
consolida um regulamento de consulta frequente (RIR, RIPI, Aduaneiro, RPS). Fica
de fora o que só altera outro decreto, a estrutura regimental de órgão e o
decreto de promulgação de tratado — neste último o texto substantivo está em
anexo que o parser ainda não estrutura (medido no Decreto 678/1992: 3
dispositivos, todos do decreto, nenhum da Convenção).

Decreto revogado **entra** quando ainda é invocado em contrato vigente (7.892 e
o SRP da Lei 8.666): o Planalto marca a revogação dispositivo a dispositivo e o
parser a reconhece, então a busca com ``somente_vigente`` não os serve.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date

from lex_rag.config import settings
from lex_rag.ingest.html_parser import parse_dispositivos
from lex_rag.ingest.planalto_fetcher import fetch
from lex_rag.ingest.planalto_urls import BASE, conferir_data, epigrafe, variantes_url
from lex_rag.ingest.urn_mapper import REGISTRO_CURADO, REGISTRO_DECRETOS_PATH

ESPECIE = "decreto"

# (slug, numero, data, apelido, ementa) — a data e a ementa vêm da API de
# metadados do LexML (``normas.leg.br/api/public/metadados/simples``), conferidas
# uma a uma; as ementas antigas, que a base guarda em caixa alta e sem acento,
# foram normalizadas aqui.
CANDIDATAS: list[tuple[str, str, date, str, str]] = [
    # ------------------------------------------- regulamentos consolidados
    ("rir_9580_2018", "9580", date(2018, 11, 22), "RIR",
     "Regulamenta a tributação, a fiscalização, a arrecadação e a administração do "
     "Imposto sobre a Renda e Proventos de Qualquer Natureza."),
    ("ripi_7212_2010", "7212", date(2010, 6, 15), "RIPI",
     "Regulamenta a cobrança, fiscalização, arrecadação e administração do Imposto "
     "sobre Produtos Industrializados - IPI."),
    ("regaduaneiro_6759_2009", "6759", date(2009, 2, 5), "Regulamento Aduaneiro",
     "Regulamenta a administração das atividades aduaneiras, e a fiscalização, o "
     "controle e a tributação das operações de comércio exterior."),
    ("rps_3048_1999", "3048", date(1999, 5, 6), "RPS",
     "Aprova o Regulamento da Previdência Social."),
    ("regiof_6306_2007", "6306", date(2007, 12, 14), "Regulamento do IOF",
     "Regulamenta o Imposto sobre Operações de Crédito, Câmbio e Seguro, ou relativas "
     "a Títulos ou Valores Mobiliários - IOF."),
    ("regitr_4382_2002", "4382", date(2002, 9, 19), "Regulamento do ITR",
     "Regulamenta a tributação, fiscalização, arrecadação e administração do Imposto "
     "sobre a Propriedade Territorial Rural - ITR."),
    ("paf_70235_1972", "70235", date(1972, 3, 6), "Processo administrativo fiscal",
     "Dispõe sobre o processo administrativo fiscal."),
    ("esocial_8373_2014", "8373", date(2014, 12, 11), "eSocial",
     "Institui o Sistema de Escrituração Digital das Obrigações Fiscais, "
     "Previdenciárias e Trabalhistas - eSocial."),
    ("consoltrabalhista_10854_2021", "10854", date(2021, 11, 10),
     "Consolidação trabalhista infralegal",
     "Regulamenta disposições relativas à legislação trabalhista e institui o Programa "
     "Permanente de Consolidação, Simplificação e Desburocratização de Normas "
     "Trabalhistas Infralegais e o Prêmio Nacional Trabalhista."),
    ("convencoesoit_10088_2019", "10088", date(2019, 11, 5), "Convenções da OIT",
     "Consolida atos normativos editados pelo Poder Executivo Federal que dispõem "
     "sobre a promulgação de convenções e recomendações da Organização Internacional "
     "do Trabalho - OIT ratificadas pela República Federativa do Brasil."),

    # ------------------------------------------------ licitações e contratos
    ("srp_11462_2023", "11462", date(2023, 3, 31), "Sistema de registro de preços",
     "Regulamenta os art. 82 a art. 86 da Lei nº 14.133, de 1º de abril de 2021, para "
     "dispor sobre o sistema de registro de preços para a contratação de bens e "
     "serviços, inclusive obras e serviços de engenharia, no âmbito da Administração "
     "Pública federal direta, autárquica e fundacional."),
    ("gestaocontratos_11246_2022", "11246", date(2022, 10, 27),
     "Agente de contratação e fiscais de contrato",
     "Regulamenta o disposto no § 3º do art. 8º da Lei nº 14.133, de 1º de abril de "
     "2021, para dispor sobre as regras para a atuação do agente de contratação e da "
     "equipe de apoio, o funcionamento da comissão de contratação e a atuação dos "
     "gestores e fiscais de contratos."),
    ("pca_10947_2022", "10947", date(2022, 1, 25), "Plano de contratações anual",
     "Regulamenta o inciso VII do caput do art. 12 da Lei nº 14.133, de 1º de abril de "
     "2021, para dispor sobre o plano de contratações anual e instituir o Sistema de "
     "Planejamento e Gerenciamento de Contratações."),
    ("credenciamento_11878_2024", "11878", date(2024, 1, 9), "Credenciamento",
     "Regulamenta o art. 79 da Lei nº 14.133, de 1º de abril de 2021, para dispor "
     "sobre o procedimento auxiliar de credenciamento para a contratação de bens e "
     "serviços."),
    ("margempreferencia_11890_2024", "11890", date(2024, 1, 22), "Margem de preferência",
     "Regulamenta o art. 26 da Lei nº 14.133, de 1º de abril de 2021, para dispor "
     "sobre a aplicação da margem de preferência e institui a Comissão Interministerial "
     "de Contratações Públicas para o Desenvolvimento Sustentável."),
    ("equidadecontratacoes_11430_2023", "11430", date(2023, 3, 8),
     "Mulheres vítimas de violência nas contratações",
     "Regulamenta a Lei nº 14.133, de 1º de abril de 2021, para dispor sobre a "
     "exigência, em contratações públicas, de percentual mínimo de mão de obra "
     "constituída por mulheres vítimas de violência doméstica e sobre ações de "
     "equidade entre mulheres e homens como critério de desempate em licitações."),
    ("execucaoindireta_9507_2018", "9507", date(2018, 9, 21), "Execução indireta de serviços",
     "Dispõe sobre a execução indireta, mediante contratação, de serviços da "
     "administração pública federal direta, autárquica e fundacional e das empresas "
     "públicas e das sociedades de economia mista controladas pela União."),
    ("meepp_8538_2015", "8538", date(2015, 10, 6), "ME e EPP nas contratações",
     "Regulamenta o tratamento favorecido, diferenciado e simplificado para as "
     "microempresas, empresas de pequeno porte, agricultores familiares, produtores "
     "rurais pessoa física, microempreendedores individuais e sociedades cooperativas "
     "de consumo nas contratações públicas."),
    ("srp_7892_2013", "7892", date(2013, 1, 23), "SRP da Lei 8.666",
     "Regulamenta o Sistema de Registro de Preços previsto no art. 15 da Lei nº 8.666, "
     "de 21 de junho de 1993."),
    ("pregaoeletronico_10024_2019", "10024", date(2019, 9, 20), "Pregão eletrônico",
     "Regulamenta a licitação, na modalidade pregão, na forma eletrônica, para a "
     "aquisição de bens e a contratação de serviços comuns, incluídos os serviços "
     "comuns de engenharia, e dispõe sobre o uso da dispensa eletrônica."),

    # ------------------------------------ administração, integridade e acesso
    ("reglai_7724_2012", "7724", date(2012, 5, 16), "Regulamento da LAI",
     "Regulamenta a Lei nº 12.527, de 18 de novembro de 2011, que dispõe sobre o "
     "acesso a informações previsto no inciso XXXIII do caput do art. 5º, no inciso II "
     "do § 3º do art. 37 e no § 2º do art. 216 da Constituição."),
    ("reganticorrupcao_11129_2022", "11129", date(2022, 7, 11), "Regulamento da Lei Anticorrupção",
     "Regulamenta a Lei nº 12.846, de 1º de agosto de 2013, que dispõe sobre a "
     "responsabilização administrativa e civil de pessoas jurídicas pela prática de "
     "atos contra a administração pública, nacional ou estrangeira."),
    ("governanca_9203_2017", "9203", date(2017, 11, 22), "Governança pública",
     "Dispõe sobre a política de governança da administração pública federal direta, "
     "autárquica e fundacional."),
    ("etica_1171_1994", "1171", date(1994, 6, 22), "Código de Ética do servidor",
     "Aprova o Código de Ética Profissional do Servidor Público Civil do Poder "
     "Executivo Federal."),
    ("pndp_9991_2019", "9991", date(2019, 8, 28), "PNDP",
     "Dispõe sobre a Política Nacional de Desenvolvimento de Pessoas da administração "
     "pública federal direta, autárquica e fundacional, e regulamenta dispositivos da "
     "Lei nº 8.112, de 11 de dezembro de 1990, quanto a licenças e afastamentos para "
     "ações de desenvolvimento."),
    ("jornada_1590_1995", "1590", date(1995, 8, 10), "Jornada de trabalho dos servidores",
     "Dispõe sobre a jornada de trabalho dos servidores da administração pública "
     "federal direta, das autarquias e das fundações públicas federais."),
    ("regosc_8726_2016", "8726", date(2016, 4, 27), "Regulamento do MROSC",
     "Regulamenta a Lei nº 13.019, de 31 de julho de 2014, para dispor sobre regras e "
     "procedimentos do regime jurídico das parcerias celebradas entre a administração "
     "pública federal e as organizações da sociedade civil."),

    # ------------------------- direitos, saúde, consumidor e meio ambiente
    ("regsus_7508_2011", "7508", date(2011, 6, 28), "Regulamento da Lei Orgânica da Saúde",
     "Regulamenta a Lei nº 8.080, de 19 de setembro de 1990, para dispor sobre a "
     "organização do Sistema Único de Saúde - SUS, o planejamento da saúde, a "
     "assistência à saúde e a articulação interfederativa."),
    ("bpc_6214_2007", "6214", date(2007, 9, 26), "BPC",
     "Regulamenta o benefício de prestação continuada da assistência social devido à "
     "pessoa com deficiência e ao idoso de que tratam a Lei nº 8.742, de 7 de dezembro "
     "de 1993, e a Lei nº 10.741, de 1º de outubro de 2003."),
    ("integracaopcd_3298_1999", "3298", date(1999, 12, 20),
     "Política Nacional para Integração da Pessoa Portadora de Deficiência",
     "Regulamenta a Lei nº 7.853, de 24 de outubro de 1989, dispõe sobre a Política "
     "Nacional para a Integração da Pessoa Portadora de Deficiência e consolida as "
     "normas de proteção."),
    ("regacessibilidade_5296_2004", "5296", date(2004, 12, 2), "Regulamento da acessibilidade",
     "Regulamenta as Leis nº 10.048, de 8 de novembro de 2000, que dá prioridade de "
     "atendimento às pessoas que especifica, e nº 10.098, de 19 de dezembro de 2000, "
     "que estabelece normas gerais e critérios básicos para a promoção da "
     "acessibilidade das pessoas com deficiência ou com mobilidade reduzida."),
    ("regmigracao_9199_2017", "9199", date(2017, 11, 20), "Regulamento da Lei de Migração",
     "Regulamenta a Lei nº 13.445, de 24 de maio de 2017, que institui a Lei de Migração."),
    ("bolsafamilia_12064_2024", "12064", date(2024, 6, 17), "Regulamento do Bolsa Família",
     "Regulamenta o Programa Bolsa Família, instituído pela Lei nº 14.601, de 19 de "
     "junho de 2023."),
    ("sndc_2181_1997", "2181", date(1997, 3, 20), "SNDC",
     "Dispõe sobre a organização do Sistema Nacional de Defesa do Consumidor - SNDC e "
     "estabelece as normas gerais de aplicação das sanções administrativas previstas "
     "na Lei nº 8.078, de 11 de setembro de 1990."),
    ("comercioeletronico_7962_2013", "7962", date(2013, 3, 15), "Comércio eletrônico",
     "Regulamenta a Lei nº 8.078, de 11 de setembro de 1990, para dispor sobre a "
     "contratação no comércio eletrônico."),
    ("sac_11034_2022", "11034", date(2022, 4, 5), "SAC",
     "Regulamenta a Lei nº 8.078, de 11 de setembro de 1990 - Código de Defesa do "
     "Consumidor, para estabelecer diretrizes e normas sobre o Serviço de Atendimento "
     "ao Consumidor."),
    ("infracoesambientais_6514_2008", "6514", date(2008, 7, 22), "Infrações ambientais",
     "Dispõe sobre as infrações e sanções administrativas ao meio ambiente e estabelece "
     "o processo administrativo federal para apuração destas infrações."),

    # ------------------------------------------------------------ setoriais
    ("comercializacaoenergia_5163_2004", "5163", date(2004, 7, 30),
     "Comercialização de energia elétrica",
     "Regulamenta a comercialização de energia elétrica e o processo de outorga de "
     "concessões e de autorizações de geração de energia elétrica."),
    ("estruturaaneel_2335_1997", "2335", date(1997, 10, 6), "Constituição da ANEEL",
     "Constitui a Agência Nacional de Energia Elétrica - ANEEL, autarquia sob regime "
     "especial, e aprova sua estrutura regimental."),
    ("regdesarmamento_11615_2023", "11615", date(2023, 7, 21),
     "Regulamento do Estatuto do Desarmamento",
     "Regulamenta a Lei nº 10.826, de 22 de dezembro de 2003, para estabelecer regras e "
     "procedimentos relativos à aquisição, ao registro, à posse, ao porte, ao cadastro "
     "e à comercialização nacional de armas de fogo, munições e acessórios."),
    ("florestaspublicas_12046_2024", "12046", date(2024, 6, 5), "Gestão de florestas públicas",
     "Regulamenta, em âmbito federal, a Lei nº 11.284, de 2 de março de 2006, que "
     "dispõe sobre a gestão de florestas públicas para a produção sustentável."),

    # ------------------------------------------------------ defesa comercial
    ("regantidumping_8058_2013", "8058", date(2013, 7, 26), "Regulamento antidumping",
     "Regulamenta os procedimentos administrativos relativos à investigação e à "
     "aplicação de medidas antidumping."),
]


def resolver(numero: str, d: date) -> tuple[str, int, str]:
    """Primeira URL que baixa e parseia com dispositivos plausíveis."""
    erros: list[str] = []
    for url in variantes_url(ESPECIE, numero, d.year):
        try:
            html = fetch(url)
            disp = parse_dispositivos(html)
            if len(disp) < 2:
                erros.append(f"parse magro ({len(disp)} disp) em {url.replace(BASE, '')}")
                continue
            return url, len(disp), conferir_data(html, numero, d, ESPECIE)
        except Exception as exc:
            erros.append(type(exc).__name__)
        finally:
            time.sleep(settings.http_polite_delay)  # coleta educada
    raise RuntimeError("; ".join(dict.fromkeys(erros)) or "sem variante")


def _urls_resolvidas() -> dict[str, str]:
    """URN → URL canônica já resolvida numa rodada anterior."""
    if not REGISTRO_DECRETOS_PATH.exists():
        return {}
    return {
        e["urn_lex"]: e["url_canonica"]
        for e in json.loads(REGISTRO_DECRETOS_PATH.read_text("utf-8"))
    }


def _conferir_unicidade() -> None:
    """Barra decreto repetido na lista curada (ver o gêmeo em descobrir_ordinarias)."""
    urns = [f"urn:lex:br:federal:{ESPECIE}:{d.isoformat()};{num}"
            for _, num, d, _, _ in CANDIDATAS]
    repetidos = {u for u in urns if urns.count(u) > 1}
    if repetidos:
        raise SystemExit(f"URN repetido em CANDIDATAS: {', '.join(sorted(repetidos))}")
    slugs = [c[0] for c in CANDIDATAS]
    if len(slugs) != len(set(slugs)):
        raise SystemExit("slug repetido em CANDIDATAS")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--revalidar",
        action="store_true",
        help="rebaixa tudo do zero, em vez de reaproveitar o que já está no JSON.",
    )
    args = ap.parse_args()

    _conferir_unicidade()
    urns_curadas = {m.urn_lex for m in REGISTRO_CURADO.values()}
    conhecidas = {} if args.revalidar else _urls_resolvidas()
    validadas, falhas, divergentes = [], [], []
    n_reaproveitadas = 0

    for i, (slug, numero, d, apelido, ementa) in enumerate(CANDIDATAS, 1):
        urn = f"urn:lex:br:federal:{ESPECIE}:{d.isoformat()};{numero}"
        if urn in urns_curadas:
            print(f"[{i:3}/{len(CANDIDATAS)}] {slug:34} ja no registro curado")
            continue
        if urn in conhecidas:
            url, n_reaproveitadas = conhecidas[urn], n_reaproveitadas + 1
        else:
            try:
                url, n_disp, confere = resolver(numero, d)
            except Exception as exc:
                falhas.append(slug)
                print(f"[{i:3}/{len(CANDIDATAS)}] {slug:34} FALHOU: {exc}")
                continue
            if confere.startswith("DIVERGE"):
                # data errada = URN errado, e o URN é a chave do corpus: não entra.
                divergentes.append(f"{slug} {confere}")
                print(f"[{i:3}/{len(CANDIDATAS)}] {slug:34} REJEITADA: {confere}")
                continue
            print(f"[{i:3}/{len(CANDIDATAS)}] {slug:34} ok ({n_disp} disp, {confere}) "
                  f"{url.replace(BASE, '')}")
        validadas.append({
            "slug": slug,
            "urn_lex": urn,
            "tipo": "decreto",
            "numero": numero,
            "data": d.isoformat(),
            "epigrafe": epigrafe(ESPECIE, numero, d, apelido),
            "ementa": ementa,
            "url_canonica": url,
        })

    validadas.sort(key=lambda e: (e["data"], int(e["numero"])))
    REGISTRO_DECRETOS_PATH.write_text(
        json.dumps(validadas, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"\n[decretos] {len(validadas)} validadas ({n_reaproveitadas} com URL reaproveitada "
          f"do JSON anterior) -> {REGISTRO_DECRETOS_PATH}")
    if divergentes:
        print(f"[decretos] rejeitadas por data divergente: {'; '.join(divergentes)}")
    if falhas:
        print(f"[decretos] falhas ({len(falhas)}): {', '.join(falhas)}")
    return 1 if falhas or divergentes else 0


if __name__ == "__main__":
    sys.exit(main())
