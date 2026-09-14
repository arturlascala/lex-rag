"""Gera o registro do lote curado de leis ordinárias (``registro_ordinarias.json``).

Diferente das Leis Complementares, as ordinárias **não** têm quadro oficial
utilizável: são milhares, a maioria de artigo único (denominação de rodovia,
crédito orçamentário), então varrer o quadro traria muito mais ruído que sinal.
Aqui a lista é curada à mão — normas de consulta frequente — e o script resolve
a parte mecânica que não dá para adivinhar: a **URL canônica**.

A resolução da URL e a conferência da data ficam em
``lex_rag.ingest.planalto_urls`` (puras, testáveis offline); aqui fica a lista e
a orquestração. Cada candidata é validada por download + parse; entram no JSON
só as que parseiam com dispositivos plausíveis **e** cuja data declarada bate
com a epígrafe impressa na página — data errada é URN errado, e o URN é a chave
do corpus.

A lista cresce por lotes, então o script reaproveita do JSON anterior a URL já
resolvida de cada norma e só vai à rede pelas novas; ``--revalidar`` força a
resolução do zero (útil quando o Planalto pode ter publicado um consolidado
novo). Os demais metadados são sempre reconstruídos a partir de ``CANDIDATAS``.
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
from lex_rag.ingest.urn_mapper import REGISTRO_CURADO, REGISTRO_ORDINARIAS_PATH

# (slug, especie, numero, data, apelido, ementa) — ``especie`` é o segmento do
# URN-LEX ("lei" | "decreto.lei"), que não se confunde com o ``tipo`` gravado no
# corpus: este alimenta o filtro ``tipo_norma`` da busca e tem vocabulário
# próprio ("lei" | "codigo" | "lei_complementar" | "constituicao").
CANDIDATAS: list[tuple[str, str, str, date, str, str]] = [
    # ------------------------------------------------ fundamentos e processo
    ("lindb_4657_1942", "decreto.lei", "4657", date(1942, 9, 4), "LINDB",
     "Lei de Introdução às Normas do Direito Brasileiro."),
    ("crimesresp_1079_1950", "lei", "1079", date(1950, 4, 10), "Crimes de responsabilidade",
     "Define os crimes de responsabilidade e regula o respectivo processo de julgamento."),
    ("acaopopular_4717_1965", "lei", "4717", date(1965, 6, 29), "Ação popular",
     "Regula a ação popular."),
    ("acp_7347_1985", "lei", "7347", date(1985, 7, 24), "Ação civil pública",
     "Disciplina a ação civil pública de responsabilidade por danos causados ao meio "
     "ambiente, ao consumidor e a bens e direitos de valor artístico, estético, "
     "histórico, turístico e paisagístico."),
    ("habeasdata_9507_1997", "lei", "9507", date(1997, 11, 12), "Habeas data",
     "Regula o direito de acesso a informações e disciplina o rito processual do habeas data."),
    ("consultapop_9709_1998", "lei", "9709", date(1998, 11, 18), "Plebiscito e referendo",
     "Regulamenta a execução do disposto nos incisos I, II e III do art. 14 da "
     "Constituição Federal (plebiscito, referendo e iniciativa popular)."),
    ("ms_12016_2009", "lei", "12016", date(2009, 8, 7), "Mandado de segurança",
     "Disciplina o mandado de segurança individual e coletivo."),
    ("mi_13300_2016", "lei", "13300", date(2016, 6, 23), "Mandado de injunção",
     "Disciplina o processo e o julgamento dos mandados de injunção individual e coletivo."),

    # ------------------------------------------ controle e finanças públicas
    ("lotcu_8443_1992", "lei", "8443", date(1992, 7, 16), "Lei Orgânica do TCU",
     "Dispõe sobre a Lei Orgânica do Tribunal de Contas da União."),
    ("execfiscal_6830_1980", "lei", "6830", date(1980, 9, 22), "Execução fiscal",
     "Dispõe sobre a cobrança judicial da Dívida Ativa da Fazenda Pública."),
    ("lei_9430_1996", "lei", "9430", date(1996, 12, 27), "Legislação tributária federal",
     "Dispõe sobre a legislação tributária federal, as contribuições para a seguridade "
     "social e o processo administrativo de consulta."),
    ("transacao_13988_2020", "lei", "13988", date(2020, 4, 14), "Transação tributária",
     "Dispõe sobre a transação nas hipóteses que especifica e sobre o contencioso "
     "administrativo fiscal de baixa complexidade."),
    ("custeio_8212_1991", "lei", "8212", date(1991, 7, 24), "Custeio da seguridade social",
     "Dispõe sobre a organização da Seguridade Social e institui Plano de Custeio."),
    ("rpps_9717_1998", "lei", "9717", date(1998, 11, 27), "Regras gerais dos RPPS",
     "Dispõe sobre regras gerais para a organização e o funcionamento dos regimes "
     "próprios de previdência social dos servidores públicos."),
    ("fgts_8036_1990", "lei", "8036", date(1990, 5, 11), "FGTS",
     "Dispõe sobre o Fundo de Garantia do Tempo de Serviço."),

    # ------------------------------------------------- administração pública
    ("temporarios_8745_1993", "lei", "8745", date(1993, 12, 9), "Contratação temporária",
     "Dispõe sobre a contratação por tempo determinado para atender a necessidade "
     "temporária de excepcional interesse público."),
    ("concessoes_8987_1995", "lei", "8987", date(1995, 2, 13), "Concessões e permissões",
     "Dispõe sobre o regime de concessão e permissão da prestação de serviços públicos "
     "previsto no art. 175 da Constituição Federal."),
    ("ppp_11079_2004", "lei", "11079", date(2004, 12, 30), "Parcerias público-privadas",
     "Institui normas gerais para licitação e contratação de parceria público-privada "
     "no âmbito da administração pública."),
    ("mrosc_13019_2014", "lei", "13019", date(2014, 7, 31), "Parcerias com OSC (MROSC)",
     "Estabelece o regime jurídico das parcerias entre a administração pública e as "
     "organizações da sociedade civil."),
    ("os_9637_1998", "lei", "9637", date(1998, 5, 15), "Organizações sociais",
     "Dispõe sobre a qualificação de entidades como organizações sociais e a criação do "
     "Programa Nacional de Publicização."),
    ("govdigital_14129_2021", "lei", "14129", date(2021, 3, 29), "Governo digital",
     "Dispõe sobre princípios, regras e instrumentos para o Governo Digital e para o "
     "aumento da eficiência pública."),
    ("abusoautoridade_13869_2019", "lei", "13869", date(2019, 9, 5), "Abuso de autoridade",
     "Dispõe sobre os crimes de abuso de autoridade."),

    # -------------------------------------------------- eleitoral e partidário
    ("eleicoes_9504_1997", "lei", "9504", date(1997, 9, 30), "Lei das Eleições",
     "Estabelece normas para as eleições."),
    ("partidos_9096_1995", "lei", "9096", date(1995, 9, 19), "Partidos políticos",
     "Dispõe sobre partidos políticos e regulamenta os arts. 17 e 14, § 3º, inciso V, "
     "da Constituição Federal."),

    # ------------------------------------------------------ penal extravagante
    ("lep_7210_1984", "lei", "7210", date(1984, 7, 11), "Lei de Execução Penal",
     "Institui a Lei de Execução Penal."),
    ("hediondos_8072_1990", "lei", "8072", date(1990, 7, 25), "Crimes hediondos",
     "Dispõe sobre os crimes hediondos, nos termos do art. 5º, inciso XLIII, da "
     "Constituição Federal."),
    ("interceptacao_9296_1996", "lei", "9296", date(1996, 7, 24), "Interceptação telefônica",
     "Regulamenta o inciso XII, parte final, do art. 5º da Constituição Federal."),
    ("lavagem_9613_1998", "lei", "9613", date(1998, 3, 3), "Lavagem de dinheiro",
     "Dispõe sobre os crimes de lavagem ou ocultação de bens, direitos e valores e cria "
     "o Conselho de Controle de Atividades Financeiras (COAF)."),
    ("crimesambientais_9605_1998", "lei", "9605", date(1998, 2, 12), "Crimes ambientais",
     "Dispõe sobre as sanções penais e administrativas derivadas de condutas e atividades "
     "lesivas ao meio ambiente."),
    ("desarmamento_10826_2003", "lei", "10826", date(2003, 12, 22), "Estatuto do Desarmamento",
     "Dispõe sobre registro, posse e comercialização de armas de fogo e munição e sobre o "
     "Sistema Nacional de Armas (Sinarm)."),
    ("drogas_11343_2006", "lei", "11343", date(2006, 8, 23), "Lei de Drogas",
     "Institui o Sistema Nacional de Políticas Públicas sobre Drogas (Sisnad) e define "
     "crimes relativos ao tráfico."),
    ("orgcriminosa_12850_2013", "lei", "12850", date(2013, 8, 2), "Organização criminosa",
     "Define organização criminosa e dispõe sobre a investigação criminal e os meios de "
     "obtenção da prova."),

    # ------------------------------------------------------ civil e empresarial
    ("registrospublicos_6015_1973", "lei", "6015", date(1973, 12, 31), "Registros públicos",
     "Dispõe sobre os registros públicos."),
    ("sa_6404_1976", "lei", "6404", date(1976, 12, 15), "Sociedades por ações",
     "Dispõe sobre as Sociedades por Ações."),
    ("parcelamentosolo_6766_1979", "lei", "6766", date(1979, 12, 19), "Parcelamento do solo urbano",
     "Dispõe sobre o parcelamento do solo urbano."),
    ("locacoes_8245_1991", "lei", "8245", date(1991, 10, 18), "Lei do Inquilinato",
     "Dispõe sobre as locações dos imóveis urbanos e os procedimentos a elas pertinentes."),
    ("propind_9279_1996", "lei", "9279", date(1996, 5, 14), "Propriedade industrial",
     "Regula direitos e obrigações relativos à propriedade industrial."),
    ("arbitragem_9307_1996", "lei", "9307", date(1996, 9, 23), "Arbitragem",
     "Dispõe sobre a arbitragem."),
    ("direitosautorais_9610_1998", "lei", "9610", date(1998, 2, 19), "Direitos autorais",
     "Altera, atualiza e consolida a legislação sobre direitos autorais."),
    ("falencias_11101_2005", "lei", "11101", date(2005, 2, 9), "Recuperação e falência",
     "Regula a recuperação judicial, a extrajudicial e a falência do empresário e da "
     "sociedade empresária."),
    ("cade_12529_2011", "lei", "12529", date(2011, 11, 30), "Defesa da concorrência",
     "Estrutura o Sistema Brasileiro de Defesa da Concorrência e dispõe sobre a prevenção "
     "e repressão às infrações contra a ordem econômica."),
    ("liberdadeeconomica_13874_2019", "lei", "13874", date(2019, 9, 20), "Liberdade econômica",
     "Institui a Declaração de Direitos de Liberdade Econômica e estabelece garantias de "
     "livre mercado."),

    # ---------------------------------------------------------- urbano e ambiental
    ("pnma_6938_1981", "lei", "6938", date(1981, 8, 31), "Política Nacional do Meio Ambiente",
     "Dispõe sobre a Política Nacional do Meio Ambiente, seus fins e mecanismos de "
     "formulação e aplicação."),
    ("recursoshidricos_9433_1997", "lei", "9433", date(1997, 1, 8), "Recursos hídricos",
     "Institui a Política Nacional de Recursos Hídricos e cria o Sistema Nacional de "
     "Gerenciamento de Recursos Hídricos."),
    ("snuc_9985_2000", "lei", "9985", date(2000, 7, 18), "SNUC",
     "Institui o Sistema Nacional de Unidades de Conservação da Natureza."),
    ("estatutocidade_10257_2001", "lei", "10257", date(2001, 7, 10), "Estatuto da Cidade",
     "Regulamenta os arts. 182 e 183 da Constituição Federal e estabelece diretrizes "
     "gerais da política urbana."),
    ("saneamento_11445_2007", "lei", "11445", date(2007, 1, 5), "Saneamento básico",
     "Estabelece as diretrizes nacionais para o saneamento básico."),
    ("residuos_12305_2010", "lei", "12305", date(2010, 8, 2), "Resíduos sólidos",
     "Institui a Política Nacional de Resíduos Sólidos."),

    # ------------------------------------------------------ digital e comunicações
    ("lgt_9472_1997", "lei", "9472", date(1997, 7, 16), "Lei Geral de Telecomunicações",
     "Dispõe sobre a organização dos serviços de telecomunicações e a criação e "
     "funcionamento de um órgão regulador (Anatel)."),
    ("marcocivil_12965_2014", "lei", "12965", date(2014, 4, 23), "Marco Civil da Internet",
     "Estabelece princípios, garantias, direitos e deveres para o uso da internet no Brasil."),

    # ------------------------------------------------------------ social e direitos
    ("greve_7783_1989", "lei", "7783", date(1989, 6, 28), "Direito de greve",
     "Dispõe sobre o exercício do direito de greve e define as atividades essenciais."),
    ("loas_8742_1993", "lei", "8742", date(1993, 12, 7), "LOAS",
     "Dispõe sobre a organização da Assistência Social."),
    ("estatutoindio_6001_1973", "lei", "6001", date(1973, 12, 19), "Estatuto do Índio",
     "Dispõe sobre o Estatuto do Índio."),
    ("igualdaderacial_12288_2010", "lei", "12288", date(2010, 7, 20),
     "Estatuto da Igualdade Racial", "Institui o Estatuto da Igualdade Racial."),
    ("migracao_13445_2017", "lei", "13445", date(2017, 5, 24), "Lei de Migração",
     "Institui a Lei de Migração."),
    ("bolsafamilia_14601_2023", "lei", "14601", date(2023, 6, 19), "Bolsa Família",
     "Institui o Programa Bolsa Família e o benefício de que trata a Lei nº 10.836."),

    # ------------------------------- sistema financeiro, capitais e pagamentos
    ("sfn_4595_1964", "lei", "4595", date(1964, 12, 31), "Sistema Financeiro Nacional",
     "Dispõe sobre a Política e as Instituições Monetárias, Bancárias e Creditícias e "
     "cria o Conselho Monetário Nacional."),
    ("cvm_6385_1976", "lei", "6385", date(1976, 12, 7), "CVM e mercado de valores mobiliários",
     "Dispõe sobre o mercado de valores mobiliários e cria a Comissão de Valores Mobiliários."),
    ("sfi_9514_1997", "lei", "9514", date(1997, 11, 20), "SFI e alienação fiduciária de imóvel",
     "Dispõe sobre o Sistema de Financiamento Imobiliário e institui a alienação "
     "fiduciária de coisa imóvel."),
    ("cambio_14286_2021", "lei", "14286", date(2021, 12, 29), "Mercado de câmbio",
     "Dispõe sobre o mercado de câmbio brasileiro, o capital brasileiro no exterior e o "
     "capital estrangeiro no País."),
    ("pagamentos_12865_2013", "lei", "12865", date(2013, 10, 9), "Arranjos de pagamento",
     "Dispõe sobre os arranjos de pagamento e as instituições de pagamento integrantes do "
     "Sistema de Pagamentos Brasileiro."),
    ("ativosvirtuais_14478_2022", "lei", "14478", date(2022, 12, 21), "Ativos virtuais",
     "Dispõe sobre diretrizes para a prestação de serviços de ativos virtuais e sobre as "
     "prestadoras de serviços de ativos virtuais."),
    ("crimesfinanceiros_7492_1986", "lei", "7492", date(1986, 6, 16), "Crimes contra o SFN",
     "Define os crimes contra o sistema financeiro nacional."),

    # ------------------------------- regulação, infraestrutura e desestatização
    ("agenciasreg_13848_2019", "lei", "13848", date(2019, 6, 25), "Lei Geral das Agências",
     "Dispõe sobre a gestão, a organização, o processo decisório e o controle social das "
     "agências reguladoras."),
    ("petroleo_9478_1997", "lei", "9478", date(1997, 8, 6), "Política Energética / ANP",
     "Dispõe sobre a política energética nacional e institui a Agência Nacional do Petróleo."),
    ("aneel_9427_1996", "lei", "9427", date(1996, 12, 26), "ANEEL e serviços de energia",
     "Institui a Agência Nacional de Energia Elétrica e disciplina o regime das concessões "
     "de serviços públicos de energia elétrica."),
    ("transportes_10233_2001", "lei", "10233", date(2001, 6, 5), "ANTT e ANTAQ",
     "Dispõe sobre a reestruturação dos transportes aquaviário e terrestre e cria a ANTT, "
     "a ANTAQ e o DNIT."),
    ("desestatizacao_9491_1997", "lei", "9491", date(1997, 9, 9), "Desestatização (PND)",
     "Altera procedimentos relativos ao Programa Nacional de Desestatização."),
    ("ppi_13334_2016", "lei", "13334", date(2016, 9, 13), "Parcerias de Investimentos (PPI)",
     "Cria o Programa de Parcerias de Investimentos (PPI)."),

    # --------------------------- ambiente de negócios e organização empresarial
    ("ambientenegocios_14195_2021", "lei", "14195", date(2021, 8, 26), "Ambiente de negócios",
     "Dispõe sobre a facilitação para abertura de empresas, a proteção de acionistas "
     "minoritários e a racionalização de atos societários."),
    ("redesim_11598_2007", "lei", "11598", date(2007, 12, 3), "Redesim",
     "Estabelece diretrizes e procedimentos para a simplificação do registro e da "
     "legalização de empresários e pessoas jurídicas."),
    ("cooperativas_5764_1971", "lei", "5764", date(1971, 12, 16), "Cooperativismo",
     "Define a Política Nacional de Cooperativismo e institui o regime jurídico das "
     "sociedades cooperativas."),
    ("franquia_13966_2019", "lei", "13966", date(2019, 12, 26), "Franquia empresarial",
     "Dispõe sobre o sistema de franquia empresarial."),
    ("protesto_9492_1997", "lei", "9492", date(1997, 9, 10), "Protesto de títulos",
     "Define competência, regulamenta os serviços concernentes ao protesto de títulos e "
     "outros documentos de dívida."),
    ("duplicatas_5474_1968", "lei", "5474", date(1968, 7, 18), "Duplicatas",
     "Dispõe sobre as duplicatas."),

    # ------------------------ inovação, ordem econômica e tributação da atividade
    ("inovacao_10973_2004", "lei", "10973", date(2004, 12, 2), "Marco Legal da Inovação",
     "Dispõe sobre incentivos à inovação e à pesquisa científica e tecnológica no ambiente "
     "produtivo."),
    ("leidobem_11196_2005", "lei", "11196", date(2005, 11, 21), "Lei do Bem",
     "Institui o Regime Especial de Tributação para a Plataforma de Exportação de Serviços "
     "de Tecnologia da Informação e incentivos à inovação tecnológica."),
    ("ordemtributaria_8137_1990", "lei", "8137", date(1990, 12, 27),
     "Crimes contra a ordem econômica",
     "Define crimes contra a ordem tributária, econômica e contra as relações de consumo."),
    ("irpj_9249_1995", "lei", "9249", date(1995, 12, 26), "IRPJ e CSLL",
     "Altera a legislação do imposto de renda das pessoas jurídicas e da contribuição "
     "social sobre o lucro líquido."),
    ("pis_10637_2002", "lei", "10637", date(2002, 12, 30), "PIS/Pasep não cumulativo",
     "Dispõe sobre a não cumulatividade na cobrança da contribuição para o PIS/Pasep."),
    ("cofins_10833_2003", "lei", "10833", date(2003, 12, 29), "Cofins não cumulativa",
     "Altera a legislação tributária federal e dispõe sobre a não cumulatividade da Cofins."),

    # =====================================================================
    # Lote 2 (2026-08-07): cobertura setorial — processo e carreiras
    # jurídicas, militar e segurança pública, trabalho, saúde, educação e
    # cultura, agrário, urbano e transportes, energia e mineração, tributário
    # complementar, organização do Estado, comunicações e direitos sociais.
    # =====================================================================

    # ------------------------------------- processo e carreiras jurídicas
    ("procstf_8038_1990", "lei", "8038", date(1990, 5, 28), "Processos no STF e no STJ",
     "Institui normas procedimentais para os processos que especifica, perante o Superior "
     "Tribunal de Justiça e o Supremo Tribunal Federal."),
    ("assistjud_1060_1950", "lei", "1060", date(1950, 2, 5), "Assistência judiciária",
     "Estabelece normas para a concessão de assistência judiciária aos necessitados."),
    ("correcaojud_6899_1981", "lei", "6899", date(1981, 4, 8), "Correção monetária judicial",
     "Determina a aplicação da correção monetária nos débitos oriundos de decisão judicial."),
    ("procjudeletronico_11419_2006", "lei", "11419", date(2006, 12, 19),
     "Processo judicial eletrônico",
     "Dispõe sobre a informatização do processo judicial."),
    ("sumulavinculante_11417_2006", "lei", "11417", date(2006, 12, 19), "Súmula vinculante",
     "Disciplina a edição, a revisão e o cancelamento de enunciado de súmula vinculante "
     "pelo Supremo Tribunal Federal."),
    ("mediacao_13140_2015", "lei", "13140", date(2015, 6, 26), "Mediação",
     "Dispõe sobre a mediação entre particulares e sobre a autocomposição de conflitos no "
     "âmbito da administração pública."),
    ("jefederais_10259_2001", "lei", "10259", date(2001, 7, 12), "Juizados Especiais Federais",
     "Dispõe sobre a instituição dos Juizados Especiais Cíveis e Criminais no âmbito da "
     "Justiça Federal."),
    ("jefazenda_12153_2009", "lei", "12153", date(2009, 12, 22),
     "Juizados da Fazenda Pública",
     "Dispõe sobre os Juizados Especiais da Fazenda Pública no âmbito dos Estados, do "
     "Distrito Federal, dos Territórios e dos Municípios."),
    ("agu_9028_1995", "lei", "9028", date(1995, 4, 12), "Advocacia-Geral da União",
     "Dispõe sobre o exercício das atribuições institucionais da Advocacia-Geral da União."),
    ("acordosuniao_9469_1997", "lei", "9469", date(1997, 7, 10), "Intervenção da União e acordos",
     "Dispõe sobre a intervenção da União nas causas em que figurarem como autores ou réus "
     "entes da administração indireta e sobre a celebração de acordos judiciais."),
    ("oab_8906_1994", "lei", "8906", date(1994, 7, 4), "Estatuto da Advocacia e da OAB",
     "Dispõe sobre o Estatuto da Advocacia e a Ordem dos Advogados do Brasil (OAB)."),
    ("lonmp_8625_1993", "lei", "8625", date(1993, 2, 12), "Lei Orgânica Nacional do MP",
     "Institui a Lei Orgânica Nacional do Ministério Público e dispõe sobre normas gerais "
     "para a organização do Ministério Público dos Estados."),

    # ------------------------------------- militar, defesa e segurança pública
    ("cpm_1001_1969", "decreto.lei", "1001", date(1969, 10, 21), "Código Penal Militar",
     "Código Penal Militar."),
    ("cppm_1002_1969", "decreto.lei", "1002", date(1969, 10, 21),
     "Código de Processo Penal Militar", "Código de Processo Penal Militar."),
    ("estatutomilitares_6880_1980", "lei", "6880", date(1980, 12, 9), "Estatuto dos Militares",
     "Dispõe sobre o Estatuto dos Militares."),
    ("carreiramilitar_13954_2019", "lei", "13954", date(2019, 12, 16),
     "Proteção social e carreira dos militares",
     "Dispõe sobre a reestruturação da carreira militar e sobre o Sistema de Proteção "
     "Social dos Militares das Forças Armadas."),
    ("defesa_12598_2012", "lei", "12598", date(2012, 3, 21), "Produtos de defesa",
     "Estabelece normas especiais para as compras, as contratações e o desenvolvimento de "
     "produtos e sistemas de defesa."),
    ("faixafronteira_6634_1979", "lei", "6634", date(1979, 5, 2), "Faixa de fronteira",
     "Dispõe sobre a Faixa de Fronteira."),
    ("terrorismo_13260_2016", "lei", "13260", date(2016, 3, 16), "Terrorismo",
     "Regulamenta o disposto no inciso XLIII do art. 5º da Constituição Federal, "
     "disciplinando o terrorismo e tratando de disposições investigatórias e processuais."),
    ("susp_13675_2018", "lei", "13675", date(2018, 6, 11), "SUSP e política de segurança",
     "Institui o Sistema Único de Segurança Pública (Susp) e cria a Política Nacional de "
     "Segurança Pública e Defesa Social."),
    ("protecaotestemunha_9807_1999", "lei", "9807", date(1999, 7, 13),
     "Proteção a vítimas e testemunhas",
     "Estabelece normas para a organização e a manutenção de programas especiais de "
     "proteção a vítimas e a testemunhas ameaçadas."),
    ("presidiosfederais_11671_2008", "lei", "11671", date(2008, 5, 8),
     "Presos em estabelecimentos federais",
     "Dispõe sobre a transferência e a inclusão de presos em estabelecimentos penais "
     "federais de segurança máxima."),
    ("colegiado_12694_2012", "lei", "12694", date(2012, 7, 24), "Julgamento colegiado",
     "Dispõe sobre o processo e o julgamento colegiado em primeiro grau de crimes "
     "praticados por organizações criminosas."),
    ("fnsp_13756_2018", "lei", "13756", date(2018, 12, 12), "Fundo Nacional de Segurança Pública",
     "Dispõe sobre o Fundo Nacional de Segurança Pública (FNSP) e sobre as loterias."),
    ("atribuicaopf_10446_2002", "lei", "10446", date(2002, 5, 8), "Atribuições da Polícia Federal",
     "Dispõe sobre infrações penais de repercussão interestadual ou internacional que "
     "exigem repressão uniforme pela Polícia Federal."),
    ("sinesp_12681_2012", "lei", "12681", date(2012, 7, 4), "Sinesp",
     "Institui o Sistema Nacional de Informações de Segurança Pública, Prisionais e sobre "
     "Drogas (Sinesp)."),
    ("racismo_7716_1989", "lei", "7716", date(1989, 1, 5), "Crimes de preconceito e racismo",
     "Define os crimes resultantes de preconceito de raça ou de cor."),
    ("tortura_9455_1997", "lei", "9455", date(1997, 4, 7), "Crime de tortura",
     "Define os crimes de tortura."),
    ("identcriminal_12037_2009", "lei", "12037", date(2009, 10, 1), "Identificação criminal",
     "Dispõe sobre a identificação criminal do civilmente identificado."),
    ("invpolicial_12830_2013", "lei", "12830", date(2013, 6, 20), "Investigação criminal",
     "Dispõe sobre a investigação criminal conduzida pelo delegado de polícia."),

    # ------------------------------------------------- trabalho e emprego
    ("repousosemanal_605_1949", "lei", "605", date(1949, 1, 5), "Repouso semanal remunerado",
     "Dispõe sobre o repouso semanal remunerado e o pagamento de salário nos dias feriados."),
    ("trabalhorural_5889_1973", "lei", "5889", date(1973, 6, 8), "Trabalho rural",
     "Estatui normas reguladoras do trabalho rural."),
    ("trabalhotemporario_6019_1974", "lei", "6019", date(1974, 1, 3), "Trabalho temporário",
     "Dispõe sobre o trabalho temporário nas empresas urbanas e sobre as relações de "
     "trabalho na empresa de prestação de serviços a terceiros."),
    ("segurodesemprego_7998_1990", "lei", "7998", date(1990, 1, 11), "Seguro-desemprego e FAT",
     "Regula o Programa do Seguro-Desemprego e o abono salarial e institui o Fundo de "
     "Amparo ao Trabalhador (FAT)."),
    ("plr_10101_2000", "lei", "10101", date(2000, 12, 19), "Participação nos lucros",
     "Dispõe sobre a participação dos trabalhadores nos lucros ou resultados da empresa."),
    ("funpresp_12618_2012", "lei", "12618", date(2012, 4, 30),
     "Previdência complementar do servidor",
     "Institui o regime de previdência complementar para os servidores públicos federais "
     "titulares de cargo efetivo."),
    ("prazodeterminado_9601_1998", "lei", "9601", date(1998, 1, 21),
     "Contrato de trabalho por prazo determinado",
     "Dispõe sobre o contrato de trabalho por prazo determinado."),
    ("consignado_10820_2003", "lei", "10820", date(2003, 12, 17), "Empréstimo consignado",
     "Dispõe sobre a autorização para desconto de prestações em folha de pagamento."),
    ("avisoprevio_12506_2011", "lei", "12506", date(2011, 10, 11), "Aviso prévio proporcional",
     "Dispõe sobre o aviso prévio."),
    ("igualdadesalarial_14611_2023", "lei", "14611", date(2023, 7, 3),
     "Igualdade salarial entre mulheres e homens",
     "Dispõe sobre a igualdade salarial e de critérios remuneratórios entre mulheres e "
     "homens."),
    ("estagio_11788_2008", "lei", "11788", date(2008, 9, 25), "Estágio",
     "Dispõe sobre o estágio de estudantes."),

    # ------------------------------------------------------------- saúde
    ("planosdesaude_9656_1998", "lei", "9656", date(1998, 6, 3), "Planos de saúde",
     "Dispõe sobre os planos e seguros privados de assistência à saúde."),
    ("vigilanciasanitaria_6360_1976", "lei", "6360", date(1976, 9, 23),
     "Vigilância sanitária de medicamentos",
     "Dispõe sobre a vigilância sanitária a que ficam sujeitos os medicamentos, as drogas, "
     "os insumos farmacêuticos e correlatos, cosméticos e saneantes."),
    ("infracoessanitarias_6437_1977", "lei", "6437", date(1977, 8, 20), "Infrações sanitárias",
     "Configura infrações à legislação sanitária federal e estabelece as sanções "
     "respectivas."),
    ("anvisa_9782_1999", "lei", "9782", date(1999, 1, 26), "Anvisa",
     "Define o Sistema Nacional de Vigilância Sanitária e cria a Agência Nacional de "
     "Vigilância Sanitária."),
    ("ans_9961_2000", "lei", "9961", date(2000, 1, 28), "ANS",
     "Cria a Agência Nacional de Saúde Suplementar (ANS)."),
    ("participacaosus_8142_1990", "lei", "8142", date(1990, 12, 28),
     "Participação da comunidade no SUS",
     "Dispõe sobre a participação da comunidade na gestão do Sistema Único de Saúde e "
     "sobre as transferências intergovernamentais de recursos financeiros da saúde."),
    ("genericos_9787_1999", "lei", "9787", date(1999, 2, 10), "Medicamentos genéricos",
     "Estabelece o medicamento genérico e dispõe sobre a utilização de nomes genéricos em "
     "produtos farmacêuticos."),
    ("saudemental_10216_2001", "lei", "10216", date(2001, 4, 6), "Saúde mental",
     "Dispõe sobre a proteção e os direitos das pessoas portadoras de transtornos mentais "
     "e redireciona o modelo assistencial em saúde mental."),
    ("biosseguranca_11105_2005", "lei", "11105", date(2005, 3, 24), "Biossegurança",
     "Estabelece normas de segurança e mecanismos de fiscalização de atividades que "
     "envolvam organismos geneticamente modificados (OGM)."),
    ("pesquisaclinica_14874_2024", "lei", "14874", date(2024, 5, 28),
     "Pesquisa com seres humanos",
     "Dispõe sobre a proteção dos participantes de pesquisa com seres humanos."),

    # ------------------------------------------ educação, cultura e esporte
    ("pne_13005_2014", "lei", "13005", date(2014, 6, 25), "Plano Nacional de Educação",
     "Aprova o Plano Nacional de Educação (PNE)."),
    ("cotas_12711_2012", "lei", "12711", date(2012, 8, 29), "Cotas no ensino federal",
     "Dispõe sobre o ingresso nas universidades federais e nas instituições federais de "
     "ensino técnico de nível médio."),
    ("fundeb_14113_2020", "lei", "14113", date(2020, 12, 25), "Fundeb",
     "Regulamenta o Fundo de Manutenção e Desenvolvimento da Educação Básica e de "
     "Valorização dos Profissionais da Educação (Fundeb)."),
    ("fies_10260_2001", "lei", "10260", date(2001, 7, 12), "Fies",
     "Dispõe sobre o Fundo de Financiamento ao Estudante do Ensino Superior (Fies)."),
    ("prouni_11096_2005", "lei", "11096", date(2005, 1, 13), "ProUni",
     "Institui o Programa Universidade para Todos (ProUni) e regula a atuação de entidades "
     "beneficentes de assistência social no ensino superior."),
    ("pele_9615_1998", "lei", "9615", date(1998, 3, 24), "Lei Pelé (desporto)",
     "Institui normas gerais sobre desporto."),
    ("torcedor_10671_2003", "lei", "10671", date(2003, 5, 15), "Estatuto de Defesa do Torcedor",
     "Dispõe sobre o Estatuto de Defesa do Torcedor."),
    ("leigeraldoesporte_14597_2023", "lei", "14597", date(2023, 6, 14), "Lei Geral do Esporte",
     "Institui a Lei Geral do Esporte."),
    ("rouanet_8313_1991", "lei", "8313", date(1991, 12, 23), "Lei Rouanet",
     "Restabelece princípios da Lei nº 7.505 e institui o Programa Nacional de Apoio à "
     "Cultura (Pronac)."),
    ("pnc_12343_2010", "lei", "12343", date(2010, 12, 2), "Plano Nacional de Cultura",
     "Institui o Plano Nacional de Cultura (PNC) e cria o Sistema Nacional de Informações "
     "e Indicadores Culturais."),
    ("arquivos_8159_1991", "lei", "8159", date(1991, 1, 8), "Política Nacional de Arquivos",
     "Dispõe sobre a política nacional de arquivos públicos e privados."),

    # ------------------------------------------- agrário, rural e ambiental
    ("estatutodaterra_4504_1964", "lei", "4504", date(1964, 11, 30), "Estatuto da Terra",
     "Dispõe sobre o Estatuto da Terra."),
    ("reformaagraria_8629_1993", "lei", "8629", date(1993, 2, 25), "Reforma agrária",
     "Dispõe sobre a regulamentação dos dispositivos constitucionais relativos à reforma "
     "agrária."),
    ("agriculturafamiliar_11326_2006", "lei", "11326", date(2006, 7, 24),
     "Agricultura familiar",
     "Estabelece as diretrizes para a formulação da Política Nacional da Agricultura "
     "Familiar e Empreendimentos Familiares Rurais."),
    ("politicaagricola_8171_1991", "lei", "8171", date(1991, 1, 17), "Política agrícola",
     "Dispõe sobre a política agrícola."),
    ("agrotoxicos_14785_2023", "lei", "14785", date(2023, 12, 27), "Agrotóxicos (pesticidas)",
     "Dispõe sobre a pesquisa, a produção, o registro, o comércio e a fiscalização de "
     "agrotóxicos e produtos de controle ambiental."),
    ("itr_9393_1996", "lei", "9393", date(1996, 12, 19), "ITR",
     "Dispõe sobre o Imposto sobre a Propriedade Territorial Rural (ITR)."),
    ("patrimoniogenetico_13123_2015", "lei", "13123", date(2015, 5, 20), "Patrimônio genético",
     "Dispõe sobre o acesso ao patrimônio genético, sobre a proteção do conhecimento "
     "tradicional associado e sobre a repartição de benefícios."),
    ("mataatlantica_11428_2006", "lei", "11428", date(2006, 12, 22), "Mata Atlântica",
     "Dispõe sobre a utilização e a proteção da vegetação nativa do Bioma Mata Atlântica."),
    ("clima_12187_2009", "lei", "12187", date(2009, 12, 29), "Mudança do clima",
     "Institui a Política Nacional sobre Mudança do Clima (PNMC)."),
    ("psa_14119_2021", "lei", "14119", date(2021, 1, 13), "Pagamento por serviços ambientais",
     "Institui a Política Nacional de Pagamento por Serviços Ambientais."),
    ("poluicaooleo_9966_2000", "lei", "9966", date(2000, 4, 28), "Poluição por óleo",
     "Dispõe sobre a prevenção, o controle e a fiscalização da poluição causada por "
     "lançamento de óleo em águas sob jurisdição nacional."),
    ("barragens_12334_2010", "lei", "12334", date(2010, 9, 20), "Segurança de barragens",
     "Estabelece a Política Nacional de Segurança de Barragens (PNSB)."),
    ("estacoesecologicas_6902_1981", "lei", "6902", date(1981, 4, 27),
     "Estações ecológicas e APAs",
     "Dispõe sobre a criação de Estações Ecológicas e Áreas de Proteção Ambiental."),

    # ------------------------------- urbano, habitação, transporte e logística
    ("mobilidade_12587_2012", "lei", "12587", date(2012, 1, 3), "Mobilidade urbana",
     "Institui as diretrizes da Política Nacional de Mobilidade Urbana."),
    ("mcmv_11977_2009", "lei", "11977", date(2009, 7, 7),
     "Programa Minha Casa, Minha Vida",
     "Dispõe sobre o Programa Minha Casa, Minha Vida e a regularização fundiária de "
     "assentamentos em áreas urbanas."),
    ("regfundiaria_13465_2017", "lei", "13465", date(2017, 7, 11), "Regularização fundiária",
     "Dispõe sobre a regularização fundiária rural e urbana e sobre a liquidação de "
     "créditos concedidos aos assentados da reforma agrária."),
    ("condominio_4591_1964", "lei", "4591", date(1964, 12, 16), "Condomínio e incorporações",
     "Dispõe sobre o condomínio em edificações e as incorporações imobiliárias."),
    ("sfh_4380_1964", "lei", "4380", date(1964, 8, 21), "Sistema Financeiro da Habitação",
     "Institui a correção monetária nos contratos imobiliários de interesse social e o "
     "Sistema Financeiro da Habitação."),
    ("tac_11442_2007", "lei", "11442", date(2007, 1, 5), "Transporte rodoviário de cargas",
     "Dispõe sobre o transporte rodoviário de cargas por conta de terceiros e mediante "
     "remuneração."),
    ("cba_7565_1986", "lei", "7565", date(1986, 12, 19), "Código Brasileiro de Aeronáutica",
     "Dispõe sobre o Código Brasileiro de Aeronáutica."),
    ("trafegoaquaviario_9537_1997", "lei", "9537", date(1997, 12, 11),
     "Segurança do tráfego aquaviário",
     "Dispõe sobre a segurança do tráfego aquaviário em águas sob jurisdição nacional."),
    ("marinhamercante_9432_1997", "lei", "9432", date(1997, 1, 8),
     "Ordenação do transporte aquaviário",
     "Dispõe sobre a ordenação do transporte aquaviário."),
    ("snv_12379_2011", "lei", "12379", date(2011, 1, 6), "Sistema Nacional de Viação",
     "Dispõe sobre o Sistema Nacional de Viação (SNV)."),
    ("ferrovias_14273_2021", "lei", "14273", date(2021, 12, 23), "Lei das Ferrovias",
     "Institui o marco legal das ferrovias e dispõe sobre o transporte ferroviário."),
    ("anac_11182_2005", "lei", "11182", date(2005, 9, 27), "ANAC",
     "Cria a Agência Nacional de Aviação Civil (ANAC)."),

    # ---------------------------------------------- energia e mineração
    ("codigomineracao_227_1967", "decreto.lei", "227", date(1967, 2, 28), "Código de Mineração",
     "Dá nova redação ao Decreto-Lei nº 1.985 (Código de Minas)."),
    ("anm_13575_2017", "lei", "13575", date(2017, 12, 26), "ANM",
     "Cria a Agência Nacional de Mineração (ANM)."),
    ("royalties_7990_1989", "lei", "7990", date(1989, 12, 28), "Compensação financeira (CFEM)",
     "Institui, para os Estados, o Distrito Federal e os Municípios, compensação financeira "
     "pelo resultado da exploração de recursos hídricos e minerais."),
    ("presal_12351_2010", "lei", "12351", date(2010, 12, 22), "Partilha de produção (pré-sal)",
     "Dispõe sobre a exploração e a produção de petróleo sob o regime de partilha de "
     "produção e cria o Fundo Social."),
    ("concessoesenergia_9074_1995", "lei", "9074", date(1995, 7, 7),
     "Concessões de serviços de energia",
     "Estabelece normas para outorga e prorrogação das concessões e permissões de serviços "
     "públicos."),
    ("comercenergia_10848_2004", "lei", "10848", date(2004, 3, 15),
     "Comercialização de energia elétrica",
     "Dispõe sobre a comercialização de energia elétrica."),
    ("gd_14300_2022", "lei", "14300", date(2022, 1, 6), "Geração distribuída",
     "Institui o marco legal da microgeração e minigeração distribuída e o Sistema de "
     "Compensação de Energia Elétrica."),
    ("leidogas_14134_2021", "lei", "14134", date(2021, 4, 8), "Lei do Gás",
     "Dispõe sobre as atividades relativas ao transporte de gás natural e sobre as "
     "atividades de escoamento, tratamento, processamento, estocagem e comercialização."),

    # ------------------------------------------- tributário complementar
    ("irpf_7713_1988", "lei", "7713", date(1988, 12, 22), "Imposto de renda das pessoas físicas",
     "Altera a legislação do imposto de renda e dá outras providências."),
    ("irpf_9250_1995", "lei", "9250", date(1995, 12, 26), "IRPF (declaração e deduções)",
     "Altera a legislação do imposto de renda das pessoas físicas."),
    ("pispasep_9718_1998", "lei", "9718", date(1998, 11, 27), "PIS/Cofins cumulativo",
     "Altera a legislação tributária federal (regime cumulativo do PIS/Pasep e da Cofins)."),
    ("pisimportacao_10865_2004", "lei", "10865", date(2004, 4, 30), "PIS/Cofins-Importação",
     "Dispõe sobre a contribuição para o PIS/Pasep e a Cofins incidentes na importação de "
     "bens e serviços."),
    ("legtrib_8981_1995", "lei", "8981", date(1995, 1, 20), "Legislação tributária federal",
     "Altera a legislação tributária federal."),
    ("legtrib_9532_1997", "lei", "9532", date(1997, 12, 10),
     "Legislação tributária federal (1997)",
     "Altera a legislação tributária federal (imunidades, isenções e imposto de renda)."),
    ("rfb_11457_2007", "lei", "11457", date(2007, 3, 16), "Receita Federal do Brasil",
     "Dispõe sobre a Administração Tributária Federal e cria a Secretaria da Receita "
     "Federal do Brasil."),
    ("cadin_10522_2002", "lei", "10522", date(2002, 7, 19), "Cadin e parcelamentos",
     "Dispõe sobre o Cadastro Informativo dos créditos não quitados de órgãos e entidades "
     "federais (Cadin)."),
    ("ipi_4502_1964", "lei", "4502", date(1964, 11, 30), "Imposto sobre Produtos Industrializados",
     "Dispõe sobre o Imposto de Consumo (atual Imposto sobre Produtos Industrializados)."),
    ("precostransferencia_14596_2023", "lei", "14596", date(2023, 6, 14),
     "Preços de transferência",
     "Dispõe sobre as regras de preços de transferência relativas ao IRPJ e à CSLL."),
    ("subvencoes_14789_2023", "lei", "14789", date(2023, 12, 29),
     "Crédito fiscal de subvenção para investimento",
     "Dispõe sobre o crédito fiscal decorrente de subvenção para a implantação ou expansão "
     "de empreendimento econômico."),
    ("desoneracao_12546_2011", "lei", "12546", date(2011, 12, 14),
     "Contribuição sobre a receita bruta e Reintegra",
     "Institui o Regime Especial de Reintegração de Valores Tributários (Reintegra) e a "
     "contribuição previdenciária sobre a receita bruta."),
    ("aduaneiro_37_1966", "decreto.lei", "37", date(1966, 11, 18), "Imposto de importação",
     "Dispõe sobre o imposto de importação e reorganiza os serviços aduaneiros."),

    # ---------------------------- organização do Estado e controle interno
    ("presidencia_14600_2023", "lei", "14600", date(2023, 6, 19),
     "Organização básica da Presidência e dos Ministérios",
     "Estabelece a organização básica dos órgãos da Presidência da República e dos "
     "Ministérios."),
    ("presidencia_9649_1998", "lei", "9649", date(1998, 5, 27),
     "Organização da Presidência (1998)",
     "Dispõe sobre a organização da Presidência da República e dos Ministérios."),
    ("sistemasfederais_10180_2001", "lei", "10180", date(2001, 2, 6),
     "Planejamento, orçamento e controle interno",
     "Organiza e disciplina os Sistemas de Planejamento e de Orçamento Federal, de "
     "Administração Financeira Federal, de Contabilidade Federal e de Controle Interno."),
    ("declaracaobens_8730_1993", "lei", "8730", date(1993, 11, 10), "Declaração de bens",
     "Estabelece a obrigatoriedade da declaração de bens e rendas para o exercício de "
     "cargos, empregos e funções nos Poderes da União."),
    ("conflitointeresses_12813_2013", "lei", "12813", date(2013, 5, 16),
     "Conflito de interesses",
     "Dispõe sobre o conflito de interesses no exercício de cargo ou emprego do Poder "
     "Executivo federal."),
    ("usuarioservicos_13460_2017", "lei", "13460", date(2017, 6, 26),
     "Defesa do usuário de serviços públicos",
     "Dispõe sobre participação, proteção e defesa dos direitos do usuário dos serviços "
     "públicos da administração pública."),
    ("contaspublicas_9755_1998", "lei", "9755", date(1998, 12, 16), "Publicidade das contas",
     "Dispõe sobre a criação de homepage na internet pelo Tribunal de Contas da União para "
     "divulgação de dados e informações das contas públicas."),
    ("consorcios_11107_2005", "lei", "11107", date(2005, 4, 6), "Consórcios públicos",
     "Dispõe sobre normas gerais de contratação de consórcios públicos."),
    ("fundacoesapoio_8958_1994", "lei", "8958", date(1994, 12, 20), "Fundações de apoio",
     "Dispõe sobre as relações entre as instituições federais de ensino superior e de "
     "pesquisa científica e tecnológica e as fundações de apoio."),
    ("oscip_9790_1999", "lei", "9790", date(1999, 3, 23), "OSCIP",
     "Dispõe sobre a qualificação de pessoas jurídicas de direito privado sem fins "
     "lucrativos como Organizações da Sociedade Civil de Interesse Público."),
    ("nacionalidade_818_1949", "lei", "818", date(1949, 9, 18), "Nacionalidade brasileira",
     "Regula a aquisição, a perda e a reaquisição da nacionalidade e a perda dos direitos "
     "políticos."),

    # --------------------------------- comunicações, digital e crédito
    ("seac_12485_2011", "lei", "12485", date(2011, 9, 12), "Comunicação audiovisual por assinatura",
     "Dispõe sobre a comunicação audiovisual de acesso condicionado."),
    ("cbt_4117_1962", "lei", "4117", date(1962, 8, 27),
     "Código Brasileiro de Telecomunicações",
     "Institui o Código Brasileiro de Telecomunicações."),
    ("cadastropositivo_12414_2011", "lei", "12414", date(2011, 6, 9), "Cadastro positivo",
     "Disciplina a formação e a consulta a bancos de dados com informações de adimplemento "
     "de pessoas naturais e jurídicas."),
    ("assinaturaeletronica_14063_2020", "lei", "14063", date(2020, 9, 23),
     "Assinaturas eletrônicas",
     "Dispõe sobre o uso de assinaturas eletrônicas em interações com entes públicos."),
    ("software_9609_1998", "lei", "9609", date(1998, 2, 19), "Programa de computador",
     "Dispõe sobre a proteção da propriedade intelectual de programa de computador e sua "
     "comercialização no País."),
    ("seguros_73_1966", "decreto.lei", "73", date(1966, 11, 21), "Sistema Nacional de Seguros",
     "Dispõe sobre o Sistema Nacional de Seguros Privados e regula as operações de seguros "
     "e resseguros."),
    ("securitizacao_14430_2022", "lei", "14430", date(2022, 8, 3), "Securitização",
     "Dispõe sobre as Letras de Riscos de Seguros e sobre a securitização de direitos "
     "creditórios."),

    # ----------------------------------------------- direitos e proteção social
    ("sisan_11346_2006", "lei", "11346", date(2006, 9, 15), "Segurança alimentar (Sisan)",
     "Cria o Sistema Nacional de Segurança Alimentar e Nutricional (Sisan)."),
    ("atendimentoprioritario_10048_2000", "lei", "10048", date(2000, 11, 8),
     "Atendimento prioritário",
     "Dá prioridade de atendimento às pessoas que especifica."),
    ("acessibilidade_10098_2000", "lei", "10098", date(2000, 12, 19), "Acessibilidade",
     "Estabelece normas gerais e critérios básicos para a promoção da acessibilidade das "
     "pessoas com deficiência ou com mobilidade reduzida."),
    ("tea_12764_2012", "lei", "12764", date(2012, 12, 27),
     "Proteção da pessoa com transtorno do espectro autista",
     "Institui a Política Nacional de Proteção dos Direitos da Pessoa com Transtorno do "
     "Espectro Autista."),
    ("planejamentofamiliar_9263_1996", "lei", "9263", date(1996, 1, 12), "Planejamento familiar",
     "Regula o § 7º do art. 226 da Constituição Federal, que trata do planejamento familiar."),
    ("juventude_12852_2013", "lei", "12852", date(2013, 8, 5), "Estatuto da Juventude",
     "Institui o Estatuto da Juventude e dispõe sobre os direitos dos jovens."),

    # =====================================================================
    # Lote 3 (2026-08-07): leis que regem **fundos**. Recorte pedido: a norma
    # que institui ou disciplina o fundo, não a que apenas o menciona. Vários
    # fundos já estavam cobertos por leis do corpus (FGTS 8.036, FAT 7.998,
    # Fundeb 14.113, Fies 10.260, FNS 8.142, FNSP 13.756, Fundo Social 12.351,
    # Funpresp 12.618, FNC 8.313, FGP 11.079) ou por LCs (Funpen LC 79,
    # FPE/FPM LC 62 e 143, Combate à Pobreza LC 111, PIS/Pasep LC 7/8/26,
    # FDA/FDNE LC 124 e 125, Fundo de Terras LC 93) — esses não se repetem aqui.
    # =====================================================================

    # ------------------------ fundos constitucionais e garantidores de crédito
    ("fundosconst_7827_1989", "lei", "7827", date(1989, 9, 27),
     "Fundos Constitucionais de Financiamento (FNO, FNE e FCO)",
     "Regulamenta o art. 159, inciso I, alínea c, da Constituição Federal, e institui o Fundo "
     "Constitucional de Financiamento do Norte (FNO), o do Nordeste (FNE) e o do Centro-Oeste "
     "(FCO)."),
    ("fundosconst_10177_2001", "lei", "10177", date(2001, 1, 12),
     "Operações dos Fundos Constitucionais",
     "Dispõe sobre as operações com recursos dos Fundos Constitucionais de Financiamento do "
     "Norte, do Nordeste e do Centro-Oeste."),
    ("fgo_fgi_12087_2009", "lei", "12087", date(2009, 11, 11),
     "Fundos garantidores de crédito (FGO e FGI)",
     "Autoriza a União a participar de fundos garantidores de risco de crédito para micro, "
     "pequenas e médias empresas, base do Fundo Garantidor de Operações (FGO) e do Fundo "
     "Garantidor para Investimentos (FGI)."),
    ("fgie_12712_2012", "lei", "12712", date(2012, 8, 30),
     "ABGF e fundos garantidores de infraestrutura",
     "Autoriza a criação da Agência Brasileira Gestora de Fundos Garantidores e Garantias S.A. "
     "(ABGF) e dispõe sobre fundos garantidores de infraestrutura e de crédito."),
    ("fge_9818_1999", "lei", "9818", date(1999, 8, 23), "Fundo de Garantia à Exportação (FGE)",
     "Cria o Fundo de Garantia à Exportação (FGE)."),
    ("fgpc_9531_1997", "lei", "9531", date(1997, 12, 10),
     "Fundo de Garantia para Promoção da Competitividade (FGPC)",
     "Cria o Fundo de Garantia para Promoção da Competitividade (FGPC), conhecido como Fundo "
     "de Aval."),

    # ------------------------------- fundos de investimento e patrimoniais
    ("fii_8668_1993", "lei", "8668", date(1993, 6, 25), "Fundos de Investimento Imobiliário",
     "Dispõe sobre a constituição e o regime tributário dos Fundos de Investimento "
     "Imobiliário."),
    ("tribfii_9779_1999", "lei", "9779", date(1999, 1, 19),
     "Tributação dos Fundos de Investimento Imobiliário",
     "Altera a legislação do imposto sobre a renda, inclusive quanto ao regime dos Fundos de "
     "Investimento Imobiliário, e das contribuições."),
    ("fipie_11478_2007", "lei", "11478", date(2007, 5, 29), "FIP-IE e FIP-PD&I",
     "Institui o Fundo de Investimento em Participações em Infraestrutura (FIP-IE) e o Fundo "
     "de Investimento em Participação na Produção Econômica Intensiva em Pesquisa, "
     "Desenvolvimento e Inovação (FIP-PD&I)."),
    ("mercfin_11033_2004", "lei", "11033", date(2004, 12, 21),
     "Tributação do mercado financeiro e de capitais",
     "Altera a tributação do mercado financeiro e de capitais, inclusive de cotas de fundos "
     "de investimento, e institui o Reporto."),
    ("incentivados_12431_2011", "lei", "12431", date(2011, 6, 24),
     "Debêntures incentivadas e fundos de investimento",
     "Dispõe sobre a incidência do imposto sobre a renda nas operações que especifica, "
     "inclusive em fundos de investimento em direitos creditórios e fundos de índice."),
    ("fundospatrim_13800_2019", "lei", "13800", date(2019, 1, 4),
     "Fundos patrimoniais (endowments)",
     "Autoriza a administração pública a firmar instrumentos de parceria com organizações "
     "gestoras de fundos patrimoniais e dispõe sobre esses fundos."),
    ("tribfundos_14754_2023", "lei", "14754", date(2023, 12, 12),
     "Tributação de fundos de investimento e offshore",
     "Dispõe sobre a tributação de aplicações em fundos de investimento no País e da renda "
     "auferida por pessoas físicas residentes no País em aplicações financeiras, entidades "
     "controladas e trusts no exterior."),

    # ------------------------------------ fundos socioambientais e de direitos
    ("fnma_7797_1989", "lei", "7797", date(1989, 7, 10), "Fundo Nacional do Meio Ambiente",
     "Cria o Fundo Nacional de Meio Ambiente (FNMA)."),
    ("fundoclima_12114_2009", "lei", "12114", date(2009, 12, 9),
     "Fundo Nacional sobre Mudança do Clima",
     "Cria o Fundo Nacional sobre Mudança do Clima (Fundo Clima)."),
    ("florestas_11284_2006", "lei", "11284", date(2006, 3, 2),
     "Florestas públicas e Fundo Nacional de Desenvolvimento Florestal",
     "Dispõe sobre a gestão de florestas públicas para produção sustentável, institui o "
     "Serviço Florestal Brasileiro e cria o Fundo Nacional de Desenvolvimento Florestal "
     "(FNDF)."),
    ("fdd_9008_1995", "lei", "9008", date(1995, 3, 21),
     "CFDD e Fundo de Defesa de Direitos Difusos",
     "Cria, na estrutura do Ministério da Justiça, o Conselho Federal de que trata o art. 13 "
     "da Lei nº 7.347, de 1985, gestor do Fundo de Defesa de Direitos Difusos."),
    ("fnca_8242_1991", "lei", "8242", date(1991, 10, 12),
     "Conanda e Fundo dos Direitos da Criança e do Adolescente",
     "Cria o Conselho Nacional dos Direitos da Criança e do Adolescente (Conanda), a quem "
     "compete gerir o fundo nacional a que se refere o Estatuto da Criança e do Adolescente."),
    ("fundoidoso_12213_2010", "lei", "12213", date(2010, 1, 20), "Fundo Nacional do Idoso",
     "Institui o Fundo Nacional do Idoso e autoriza deduzir do imposto de renda devido pelas "
     "pessoas físicas e jurídicas as doações efetuadas aos Fundos Municipais, Estaduais e "
     "Nacional do Idoso."),
    ("funad_7560_1986", "lei", "7560", date(1986, 12, 19), "Fundo Nacional Antidrogas (Funad)",
     "Cria o Fundo de Prevenção, Recuperação e de Combate às Drogas de Abuso e dispõe sobre "
     "os bens apreendidos e adquiridos com o produto do tráfico."),

    # -------------- fundos de infraestrutura, comunicações, habitação e educação
    ("fndct_11540_2007", "lei", "11540", date(2007, 11, 12),
     "Fundo Nacional de Desenvolvimento Científico e Tecnológico (FNDCT)",
     "Dispõe sobre o Fundo Nacional de Desenvolvimento Científico e Tecnológico (FNDCT) e "
     "sobre o incentivo à inovação e à pesquisa científica e tecnológica."),
    ("fndct_719_1969", "decreto.lei", "719", date(1969, 7, 31), "Criação do FNDCT",
     "Cria o Fundo Nacional de Desenvolvimento Científico e Tecnológico (FNDCT). Os arts. 2º "
     "e 3º foram revogados pela Lei nº 11.540, de 2007, que reorganizou o Fundo."),
    ("fnde_5537_1968", "lei", "5537", date(1968, 11, 21),
     "Fundo Nacional de Desenvolvimento da Educação (FNDE)",
     "Cria o Fundo Nacional de Desenvolvimento da Educação (FNDE)."),
    ("fust_9998_2000", "lei", "9998", date(2000, 8, 17),
     "Fust — universalização das telecomunicações",
     "Institui o Fundo de Universalização dos Serviços de Telecomunicações (Fust)."),
    ("funttel_10052_2000", "lei", "10052", date(2000, 11, 28),
     "Funttel — desenvolvimento tecnológico das telecomunicações",
     "Institui o Fundo para o Desenvolvimento Tecnológico das Telecomunicações (Funttel)."),
    ("fistel_5070_1966", "lei", "5070", date(1966, 7, 7),
     "Fistel — fiscalização das telecomunicações",
     "Cria o Fundo de Fiscalização das Telecomunicações (Fistel)."),
    ("fmm_10893_2004", "lei", "10893", date(2004, 7, 13),
     "AFRMM e Fundo da Marinha Mercante",
     "Dispõe sobre o Adicional ao Frete para a Renovação da Marinha Mercante (AFRMM) e o "
     "Fundo da Marinha Mercante (FMM)."),
    ("fnhis_11124_2005", "lei", "11124", date(2005, 6, 16),
     "SNHIS e Fundo Nacional de Habitação de Interesse Social",
     "Dispõe sobre o Sistema Nacional de Habitação de Interesse Social (SNHIS) e cria o Fundo "
     "Nacional de Habitação de Interesse Social (FNHIS)."),
    ("cde_10438_2002", "lei", "10438", date(2002, 4, 26),
     "CDE e universalização da energia elétrica",
     "Dispõe sobre a expansão da oferta de energia elétrica emergencial, cria o Programa de "
     "Incentivo às Fontes Alternativas de Energia Elétrica (Proinfa) e a Conta de "
     "Desenvolvimento Energético (CDE)."),
    ("fcvs_10150_2000", "lei", "10150", date(2000, 12, 21),
     "FCVS — Fundo de Compensação de Variações Salariais",
     "Dispõe sobre a novação de dívidas e responsabilidades do Fundo de Compensação de "
     "Variações Salariais (FCVS)."),
    ("fcdf_10633_2002", "lei", "10633", date(2002, 12, 27), "Fundo Constitucional do DF",
     "Institui o Fundo Constitucional do Distrito Federal (FCDF)."),

    # --------------------- fundos setoriais de C&T (as fontes que abastecem o FNDCT)
    ("ctenerg_9991_2000", "lei", "9991", date(2000, 7, 24), "CT-Energ — P&D do setor elétrico",
     "Dispõe sobre a realização de investimentos em pesquisa e desenvolvimento e em "
     "eficiência energética por parte das empresas concessionárias, permissionárias e "
     "autorizadas do setor de energia elétrica."),
    ("cttransp_9992_2000", "lei", "9992", date(2000, 7, 24), "CT-Transporte",
     "Dispõe sobre investimentos em pesquisa científica e desenvolvimento tecnológico no "
     "setor de transportes, custeados pelas concessionárias de rodovias federais."),
    ("cthidro_9993_2000", "lei", "9993", date(2000, 7, 24), "CT-Hidro e CT-Mineral",
     "Destina ao setor de ciência e tecnologia parcela da compensação financeira pela "
     "utilização de recursos hídricos para fins de geração de energia elétrica e pela "
     "exploração de recursos minerais."),
    ("ctespacial_9994_2000", "lei", "9994", date(2000, 7, 24), "CT-Espacial",
     "Institui o Programa de Desenvolvimento Científico e Tecnológico do Setor Espacial."),
    ("ctverdeamarelo_10168_2000", "lei", "10168", date(2000, 12, 29),
     "CT-Verde-Amarelo (Cide-royalties)",
     "Institui contribuição de intervenção no domínio econômico destinada a financiar o "
     "Programa de Estímulo à Interação Universidade-Empresa para o Apoio à Inovação."),
    ("ctsetoriais_10332_2001", "lei", "10332", date(2001, 12, 19),
     "CT-Agro, Saúde, Biotecnologia e Aeronáutico",
     "Institui mecanismo de financiamento para os Programas de Ciência e Tecnologia para o "
     "Agronegócio, de Fomento à Pesquisa em Saúde, de Biotecnologia e Recursos Genéticos, de "
     "Ciência e Tecnologia para o Setor Aeronáutico e de Inovação para Competitividade."),
    ("informatica_8248_1991", "lei", "8248", date(1991, 10, 23),
     "Lei de Informática (contrapartida em P&D)",
     "Dispõe sobre a capacitação e competitividade do setor de informática e automação, com "
     "contrapartida de investimento em pesquisa e desenvolvimento."),
    ("zfm_8387_1991", "lei", "8387", date(1991, 12, 30),
     "Zona Franca de Manaus e P&D na Amazônia Ocidental",
     "Dá nova redação a dispositivos do Decreto-Lei nº 288, de 1967 (Zona Franca de Manaus), "
     "e vincula parte do faturamento das empresas incentivadas a pesquisa e desenvolvimento, "
     "com recolhimento ao FNDCT."),

    # --------------------------------------------------------- audiovisual
    ("audiovisual_8685_1993", "lei", "8685", date(1993, 7, 20),
     "Lei do Audiovisual (Funcines)",
     "Cria mecanismos de fomento à atividade audiovisual, entre eles os Fundos de "
     "Financiamento da Indústria Cinematográfica Nacional (Funcines)."),
    ("fsa_11437_2006", "lei", "11437", date(2006, 12, 28),
     "Condecine e Fundo Setorial do Audiovisual",
     "Altera a destinação de receitas decorrentes da Contribuição para o Desenvolvimento da "
     "Indústria Cinematográfica Nacional (Condecine) para apoio a programas e projetos do "
     "setor audiovisual."),

    # ------------------------------------------------- demais fundos públicos
    ("fundaf_1437_1975", "decreto.lei", "1437", date(1975, 12, 17),
     "Fundaf — fundo da fiscalização aduaneira",
     "Dispõe sobre a base de cálculo do imposto sobre produtos industrializados relativo aos "
     "produtos de procedência estrangeira e institui, no art. 6º, o Fundo Especial de "
     "Desenvolvimento e Aperfeiçoamento das Atividades de Fiscalização (Fundaf)."),
    ("funcafe_2295_1986", "decreto.lei", "2295", date(1986, 11, 21),
     "Funcafé — Fundo de Defesa da Economia Cafeeira",
     "Isenta do imposto de exportação as vendas de café para o exterior e dispõe sobre a "
     "quota de contribuição destinada ao Fundo de Defesa da Economia Cafeeira (Funcafé)."),

    # =====================================================================
    # Lote 4 (2026-08-10): leis de **política nacional** e correlatas
    # estruturantes (Sistema/Plano Nacional). Recorte: a norma que **institui
    # ou define** a política, não a que a altera. A lista saiu de varredura
    # exaustiva — quadros oficiais do Planalto (1988-2000) e API de metadados
    # do LexML, ``normas.leg.br/api/public/metadados/simples`` (1934-2026,
    # 15.396 leis) — filtrando a ementa por "Política Nacional". Ficaram de
    # fora, por revogação ou superação: Lei 2.004/1953 (petróleo, revogada
    # pela 9.478/1997), Lei 5.318/1967 (saneamento, pela 11.445/2007),
    # Lei 6.662/1979 (irrigação, pela 12.787/2013, que entra) e as cinco leis
    # de política nacional de salários (8.073, 8.222, 8.419, 8.542 e 8.700),
    # superadas pela desindexação da Lei 10.192/2001.
    # =====================================================================

    ("energianuclear_4118_1962", "lei", "4118", date(1962, 8, 27),
     "Política Nacional de Energia Nuclear",
     "Dispõe sobre a política nacional de energia nuclear, cria a Comissão Nacional de Energia "
     "Nuclear."),
    ("informatica_7232_1984", "lei", "7232", date(1984, 10, 29),
     "Política Nacional de Informática",
     "Dispõe sobre a Política Nacional de Informática."),
    ("gerenciamentocosteiro_7661_1988", "lei", "7661", date(1988, 5, 16),
     "Plano Nacional de Gerenciamento Costeiro",
     "Institui o Plano Nacional de Gerenciamento Costeiro."),
    ("idoso_8842_1994", "lei", "8842", date(1994, 1, 4),
     "Política Nacional do Idoso",
     "Dispõe sobre a política nacional do idoso, cria o Conselho Nacional do Idoso."),
    ("educacaoambiental_9795_1999", "lei", "9795", date(1999, 4, 27),
     "Política Nacional de Educação Ambiental",
     "Dispõe sobre a educação ambiental, institui a Política Nacional de Educação Ambiental."),
    ("ana_9984_2000", "lei", "9984", date(2000, 7, 17),
     "Agência Nacional de Águas (ANA)",
     "Dispõe sobre a criação da Agência Nacional de Águas e Saneamento Básico (ANA), entidade "
     "federal de implementação da Política Nacional de Recursos Hídricos, integrante do "
     "Sistema Nacional de Gerenciamento de Recursos Hídricos (Singreh) e responsável pela "
     "instituição de normas de referência para a regulação dos serviços públicos de saneamento "
     "básico."),
    ("eficienciaenergetica_10295_2001", "lei", "10295", date(2001, 10, 17),
     "Política Nacional de Conservação e Uso Racional de Energia",
     "Dispõe sobre a Política Nacional de Conservação e Uso Racional de Energia."),
    ("sementesmudas_10711_2003", "lei", "10711", date(2003, 8, 5),
     "Sistema Nacional de Sementes e Mudas",
     "Dispõe sobre o Sistema Nacional de Sementes e Mudas."),
    ("livro_10753_2003", "lei", "10753", date(2003, 10, 30),
     "Política Nacional do Livro",
     "Institui a Política Nacional do Livro."),
    ("sinaes_10861_2004", "lei", "10861", date(2004, 4, 14),
     "Sinaes — avaliação da educação superior",
     "Institui o Sistema Nacional de Avaliação da Educação Superior - SINAES."),
    ("sinamob_11631_2007", "lei", "11631", date(2007, 12, 27),
     "Mobilização Nacional (Sinamob)",
     "Dispõe sobre a Mobilização Nacional e cria o Sistema Nacional de Mobilização - SINAMOB."),
    ("turismo_11771_2008", "lei", "11771", date(2008, 9, 17),
     "Política Nacional de Turismo",
     "Dispõe sobre a Política Nacional de Turismo, define as atribuições do Governo Federal no "
     "planejamento, desenvolvimento e estímulo ao setor turístico."),
    ("aquiculturapesca_11959_2009", "lei", "11959", date(2009, 6, 29),
     "Política Nacional de Desenvolvimento da Aquicultura e da Pesca",
     "Dispõe sobre a Política Nacional de Desenvolvimento Sustentável da Aquicultura e da "
     "Pesca, regula as atividades pesqueiras."),
    ("pnater_12188_2010", "lei", "12188", date(2010, 1, 11),
     "Pnater — assistência técnica e extensão rural",
     "Institui a Política Nacional de Assistência Técnica e Extensão Rural para a Agricultura "
     "Familiar e Reforma Agrária - PNATER e o Programa Nacional de Assistência Técnica e "
     "Extensão Rural na Agricultura Familiar e na Reforma Agrária - PRONATER."),
    ("bambu_12484_2011", "lei", "12484", date(2011, 9, 8),
     "Política Nacional do Bambu",
     "Dispõe sobre a Política Nacional de Incentivo ao Manejo Sustentado e ao Cultivo do "
     "Bambu."),
    ("sinase_12594_2012", "lei", "12594", date(2012, 1, 18),
     "Sinase — atendimento socioeducativo",
     "Institui o Sistema Nacional de Atendimento Socioeducativo (Sinase), regulamenta a "
     "execução das medidas socioeducativas destinadas a adolescente que pratique ato "
     "infracional."),
    ("defesacivil_12608_2012", "lei", "12608", date(2012, 4, 10),
     "Política Nacional de Proteção e Defesa Civil (PNPDEC)",
     "Institui a Política Nacional de Proteção e Defesa Civil - PNPDEC; dispõe sobre o Sistema "
     "Nacional de Proteção e Defesa Civil - SINPDEC e o Conselho Nacional de Proteção e Defesa "
     "Civil - CONPDEC; autoriza a criação de sistema de informações e monitoramento de "
     "desastres."),
    ("irrigacao_12787_2013", "lei", "12787", date(2013, 1, 11),
     "Política Nacional de Irrigação",
     "Dispõe sobre a Política Nacional de Irrigação."),
    ("ilpf_12805_2013", "lei", "12805", date(2013, 4, 29),
     "Política Nacional de Integração Lavoura-Pecuária-Floresta",
     "Institui a Política Nacional de Integração Lavoura-Pecuária-Floresta."),
    ("prevencaotortura_12847_2013", "lei", "12847", date(2013, 8, 2),
     "Sistema Nacional de Prevenção e Combate à Tortura",
     "Institui o Sistema Nacional de Prevenção e Combate à Tortura; cria o Comitê Nacional de "
     "Prevenção e Combate à Tortura e o Mecanismo Nacional de Prevenção e Combate à Tortura."),
    ("culturaviva_13018_2014", "lei", "13018", date(2014, 7, 22),
     "Política Nacional de Cultura Viva",
     "Institui a Política Nacional de Cultura Viva."),
    ("desertificacao_13153_2015", "lei", "13153", date(2015, 7, 30),
     "Política Nacional de Combate à Desertificação",
     "Institui a Política Nacional de Combate à Desertificação e Mitigação dos Efeitos da Seca "
     "e seus instrumentos; prevê a criação da Comissão Nacional de Combate à Desertificação."),
    ("renovabio_13576_2017", "lei", "13576", date(2017, 12, 26),
     "RenovaBio — Política Nacional de Biocombustíveis",
     "Dispõe sobre a Política Nacional de Biocombustíveis (RenovaBio)."),
    ("pnatrans_13614_2018", "lei", "13614", date(2018, 1, 11),
     "Pnatrans — redução de mortes no trânsito",
     "Cria o Plano Nacional de Redução de Mortes e Lesões no Trânsito (Pnatrans)."),
    ("sine_13667_2018", "lei", "13667", date(2018, 5, 17),
     "Sistema Nacional de Emprego (Sine)",
     "Dispõe sobre o Sistema Nacional de Emprego (Sine), criado pelo Decreto nº 76.403, de 8 "
     "de outubro de 1975."),
    ("leituraescrita_13696_2018", "lei", "13696", date(2018, 7, 12),
     "Política Nacional de Leitura e Escrita",
     "Institui a Política Nacional de Leitura e Escrita."),
    ("pisosminimos_13703_2018", "lei", "13703", date(2018, 8, 8),
     "Política Nacional de Pisos Mínimos do Transporte Rodoviário de Cargas",
     "Institui a Política Nacional de Pisos Mínimos do Transporte Rodoviário de Cargas."),
    ("cacau_13710_2018", "lei", "13710", date(2018, 8, 24),
     "Política Nacional do Cacau",
     "Institui a Política Nacional de Incentivo à Produção de Cacau de Qualidade."),
    ("ervamate_13791_2019", "lei", "13791", date(2019, 1, 3),
     "Política Nacional da Erva-Mate",
     "Dispõe sobre a Política Nacional da Erva-Mate."),
    ("desaparecidos_13812_2019", "lei", "13812", date(2019, 3, 16),
     "Política Nacional de Busca de Pessoas Desaparecidas",
     "Institui a Política Nacional de Busca de Pessoas Desaparecidas, cria o Cadastro Nacional "
     "de Pessoas Desaparecidas."),
    ("automutilacao_13819_2019", "lei", "13819", date(2019, 4, 26),
     "Política Nacional de Prevenção da Automutilação e do Suicídio",
     "Institui a Política Nacional de Prevenção da Automutilação e do Suicídio, a ser "
     "implementada pela União, em cooperação com os Estados, o Distrito Federal e os "
     "Municípios."),
    ("ovinocaprinocultura_13854_2019", "lei", "13854", date(2019, 7, 8),
     "Política Nacional de Ovinocaprinocultura",
     "Institui a Política Nacional de Incentivo à Ovinocaprinocultura."),
    ("diabetes_13895_2019", "lei", "13895", date(2019, 10, 30),
     "Política Nacional de Prevenção do Diabetes",
     "Institui a Política Nacional de Prevenção do Diabetes e de Assistência Integral à Pessoa "
     "Diabética."),
    ("pnainfo_14232_2021", "lei", "14232", date(2021, 10, 28),
     "PNAINFO — dados sobre violência contra as mulheres",
     "Institui a Política Nacional de Dados e Informações relacionadas à Violência contra as "
     "Mulheres (PNAINFO)."),
    ("oncologiapediatrica_14308_2022", "lei", "14308", date(2022, 3, 8),
     "Política Nacional de Oncologia Pediátrica",
     "Institui a Política Nacional de Atenção à Oncologia Pediátrica."),
    ("aldirblanc_14399_2022", "lei", "14399", date(2022, 7, 8),
     "Política Nacional Aldir Blanc de Fomento à Cultura",
     "Institui a Política Nacional Aldir Blanc de Fomento à Cultura."),
    ("agriculturaprecisao_14475_2022", "lei", "14475", date(2022, 12, 13),
     "Política Nacional de Agricultura e Pecuária de Precisão",
     "Institui a Política Nacional de Incentivo à Agricultura e Pecuária de Precisão para "
     "ampliação da eficiência na aplicação de recursos e insumos de produção, de forma a "
     "diminuir o desperdício, reduzir os custos de produção e aumentar a produtividade e a "
     "lucratividade, bem como garantir a sustentabilidade ambiental, social e econômica."),
    ("eletroeletronicos_14479_2022", "lei", "14479", date(2022, 12, 21),
     "Política Nacional de Desfazimento e Recondicionamento de Eletroeletrônicos",
     "Institui a Política Nacional de Desfazimento e Recondicionamento de Equipamentos "
     "Eletroeletrônicos e dispõe sobre o Programa Computadores para Inclusão."),
    ("educacaodigital_14533_2023", "lei", "14533", date(2023, 1, 11),
     "Política Nacional de Educação Digital (PNED)",
     "Institui a Política Nacional de Educação Digital."),
    ("saudebucal_14572_2023", "lei", "14572", date(2023, 5, 8),
     "Política Nacional de Saúde Bucal",
     "Institui a Política Nacional de Saúde Bucal no âmbito do Sistema Único de Saúde (SUS)."),
    ("flores_14637_2023", "lei", "14637", date(2023, 7, 25),
     "Política Nacional de Flores e Plantas Ornamentais",
     "Institui a Política Nacional de Incentivo à Cultura de Flores e de Plantas Ornamentais "
     "de Qualidade."),
    ("apicultura_14639_2023", "lei", "14639", date(2023, 7, 25),
     "Política Nacional de Produção Melífera",
     "Institui a Política Nacional de Incentivo à Produção Melífera e ao Desenvolvimento de "
     "Produtos e Serviços Apícolas e Meliponícolas de Qualidade."),
    ("jovemdocampo_14666_2023", "lei", "14666", date(2023, 9, 4),
     "Política Nacional de Empreendedorismo do Jovem do Campo",
     "Institui a Política Nacional de Estímulo ao Empreendedorismo do Jovem do Campo (PNEEJC) "
     "e define seus princípios, objetivos e ações."),
    ("transplantes_14722_2023", "lei", "14722", date(2023, 11, 8),
     "Política Nacional de Doação e Transplante de Órgãos",
     "Institui a Política Nacional de Conscientização e Incentivo à Doação e ao Transplante de "
     "Órgãos e Tecidos."),
    ("atingidosbarragens_14755_2023", "lei", "14755", date(2023, 12, 15),
     "Política Nacional de Direitos das Populações Atingidas por Barragens (PNAB)",
     "Institui a Política Nacional de Direitos das Populações Atingidas por Barragens (PNAB); "
     "discrimina os direitos das Populações Atingidas por Barragens (PAB); prevê o Programa de "
     "Direitos das Populações Atingidas por Barragens (PDPAB); estabelece regras de "
     "responsabilidade social do empreendedor."),
    ("cancer_14758_2023", "lei", "14758", date(2023, 12, 19),
     "Política Nacional de Prevenção e Controle do Câncer",
     "Institui a Política Nacional de Prevenção e Controle do Câncer no âmbito do Sistema "
     "Único de Saúde (SUS) e o Programa Nacional de Navegação da Pessoa com Diagnóstico de "
     "Câncer."),
    ("protecaoescolar_14811_2024", "lei", "14811", date(2024, 1, 12),
     "Proteção da criança nas escolas e combate ao abuso sexual",
     "Institui medidas de proteção à criança e ao adolescente contra a violência nos "
     "estabelecimentos educacionais ou similares, prevê a Política Nacional de Prevenção e "
     "Combate ao Abuso e Exploração Sexual da Criança e do Adolescente."),
    ("atencaopsicossocial_14819_2024", "lei", "14819", date(2024, 1, 16),
     "Política Nacional de Atenção Psicossocial nas Comunidades Escolares",
     "Institui a Política Nacional de Atenção Psicossocial nas Comunidades Escolares."),
    ("poprua_14821_2024", "lei", "14821", date(2024, 1, 16),
     "PNTC PopRua — trabalho digno para população em situação de rua",
     "Institui a Política Nacional de Trabalho Digno e Cidadania para a População em Situação "
     "de Rua (PNTC PopRua)."),
    ("snc_14835_2024", "lei", "14835", date(2024, 4, 4),
     "Marco regulatório do Sistema Nacional de Cultura",
     "Institui o marco regulatório do Sistema Nacional de Cultura (SNC), para garantia dos "
     "direitos culturais, organizado em regime de colaboração entre os entes federativos para "
     "gestão conjunta das políticas públicas de cultura."),
    ("qualidadedoar_14850_2024", "lei", "14850", date(2024, 5, 2),
     "Política Nacional de Qualidade do Ar",
     "Institui a Política Nacional de Qualidade do Ar."),
    ("alzheimer_14878_2024", "lei", "14878", date(2024, 6, 4),
     "Política Nacional de Cuidado às Pessoas com Alzheimer",
     "Institui a Política Nacional de Cuidado Integral às Pessoas com Doença de Alzheimer e "
     "Outras Demências."),
    ("pnaes_14914_2024", "lei", "14914", date(2024, 7, 3),
     "Política Nacional de Assistência Estudantil (PNAES)",
     "Institui a Política Nacional de Assistência Estudantil (PNAES)."),
    ("agriculturaurbana_14935_2024", "lei", "14935", date(2024, 7, 26),
     "Política Nacional de Agricultura Urbana",
     "Institui a Política Nacional de Agricultura Urbana e Periurbana."),
    ("manejofogo_14944_2024", "lei", "14944", date(2024, 7, 31),
     "Política Nacional de Manejo Integrado do Fogo",
     "Institui a Política Nacional de Manejo Integrado do Fogo."),
    ("hidrogenio_14948_2024", "lei", "14948", date(2024, 8, 2),
     "Hidrogênio de baixa emissão de carbono",
     "Institui o marco legal do hidrogênio de baixa emissão de carbono; dispõe sobre a "
     "Política Nacional do Hidrogênio de Baixa Emissão de Carbono; institui incentivos para a "
     "indústria do hidrogênio de baixa emissão de carbono; institui o Regime Especial de "
     "Incentivos para a Produção de Hidrogênio de Baixa Emissão de Carbono (Rehidro); cria o "
     "Programa de Desenvolvimento do Hidrogênio de Baixa Emissão de Carbono (PHBC)."),
    ("cocoicultura_14975_2024", "lei", "14975", date(2024, 9, 18),
     "Política Nacional de Cocoicultura",
     "Institui a Política Nacional de Incentivo à Cocoicultura de Qualidade."),
    ("economiasolidaria_15068_2024", "lei", "15068", date(2024, 12, 23),
     "Política Nacional de Economia Solidária",
     "Dispõe sobre os empreendimentos de economia solidária e a Política Nacional de Economia "
     "Solidária; cria o Sistema Nacional de Economia Solidária (Sinaes)."),
    ("cuidados_15069_2024", "lei", "15069", date(2024, 12, 23),
     "Política Nacional de Cuidados",
     "Institui a Política Nacional de Cuidados."),
    ("pequi_15089_2025", "lei", "15089", date(2025, 1, 7),
     "Política Nacional do Pequi e dos frutos do Cerrado",
     "Institui a Política Nacional para o Manejo Sustentável, Plantio, Extração, Consumo, "
     "Comercialização e Transformação do Pequi (Caryocar brasiliense) e demais Frutos e "
     "Produtos Nativos do Cerrado."),
    ("doencasintestinais_15138_2025", "lei", "15138", date(2025, 5, 21),
     "Política Nacional sobre Doenças Inflamatórias Intestinais",
     "Institui a Política Nacional de Assistência, Conscientização e Orientação sobre as "
     "Doenças Inflamatórias Intestinais - Doença de Crohn e Retocolite Ulcerativa."),
    ("lutomaterno_15139_2025", "lei", "15139", date(2025, 5, 23),
     "Política Nacional de Humanização do Luto Materno",
     "Institui a Política Nacional de Humanização do Luto Materno e Parental."),
    ("albinismo_15140_2025", "lei", "15140", date(2025, 5, 28),
     "Política Nacional de Proteção da Pessoa com Albinismo",
     "Institui a Política Nacional de Proteção dos Direitos da Pessoa com Albinismo."),
    ("hpv_15174_2025", "lei", "15174", date(2025, 7, 22),
     "Política Nacional de Enfrentamento ao HPV",
     "Institui a Política Nacional de Enfrentamento da Infecção por Papilomavírus Humano."),
    ("juventuderural_15178_2025", "lei", "15178", date(2025, 7, 23),
     "Política Nacional de Juventude e Sucessão Rural",
     "Institui a Política Nacional de Juventude e Sucessão Rural e o Plano Nacional de "
     "Juventude e Sucessão Rural."),
    ("visitacaouc_15180_2025", "lei", "15180", date(2025, 7, 25),
     "Política Nacional de Visitação a Unidades de Conservação",
     "Institui a Política Nacional de Incentivo à Visitação a Unidades de Conservação e "
     "autoriza o Instituto Chico Mendes de Conservação da Biodiversidade (ICMBio) e os órgãos "
     "estaduais e municipais executores do Sistema Nacional de Unidades de Conservação da "
     "Natureza (SNUC) a contratar instituição financeira oficial para criar e gerir fundo "
     "privado com os objetivos de financiar e de apoiar a visitação a unidades de conservação."),
    ("desperdicioalimentos_15224_2025", "lei", "15224", date(2025, 9, 30),
     "Política Nacional de Combate ao Desperdício de Alimentos",
     "Institui a Política Nacional de Combate à Perda e ao Desperdício de Alimentos (PNCPDA); "
     "cria o Selo Doador de Alimentos."),
    ("linguagemsimples_15263_2025", "lei", "15263", date(2025, 11, 14),
     "Política Nacional de Linguagem Simples",
     "Institui a Política Nacional de Linguagem Simples nos órgãos e entidades da "
     "administração pública direta e indireta de todos os Poderes da União, dos Estados, do "
     "Distrito Federal e dos Municípios."),
    ("maisprofessores_15344_2026", "lei", "15344", date(2026, 1, 12),
     "Política Nacional de Indução à Docência",
     "Institui a Política Nacional de Indução à Docência na Educação Básica - Mais Professores "
     "para o Brasil."),
    ("pne_15388_2026", "lei", "15388", date(2026, 4, 14),
     "Plano Nacional de Educação (PNE)",
     "Aprova o Plano Nacional de Educação (PNE)."),
    ("caatinga_15430_2026", "lei", "15430", date(2026, 6, 10),
     "Política Nacional de Recuperação da Vegetação da Caatinga",
     "Institui a Política Nacional para Recuperação da Vegetação da Caatinga e cria o Programa "
     "Nacional para a Recuperação da Vegetação da Caatinga."),
    ("altashabilidades_15436_2026", "lei", "15436", date(2026, 6, 17),
     "Política Nacional para Estudantes com Altas Habilidades ou Superdotação",
     "Institui a Política Nacional para Estudantes com Altas Habilidades ou Superdotação; cria "
     "o Cadastro Nacional de Estudantes com Altas Habilidades ou Superdotação."),

    # ------------------------------------------------- buracos do lote 5
    # Achados por varredura do registro contra uma lista de leis de consulta
    # pesada: eram o que faltava fora do recorte dos lotes anteriores. As duas
    # revogadas entram porque o Planalto marca a revogação dispositivo a
    # dispositivo (a Lei 10.520 volta 13 dispositivos, nenhum vigente), então a
    # busca padrão não as serve — mas a consulta a contrato antigo as alcança.
    ("genocidio_2889_1956", "lei", "2889", date(1956, 10, 1), "Crime de genocídio",
     "Define e pune o crime de genocídio."),
    ("pregao_10520_2002", "lei", "10520", date(2002, 7, 17), "Pregão",
     "Institui, no âmbito da União, Estados, Distrito Federal e Municípios, nos termos do "
     "art. 37, inciso XXI, da Constituição Federal, modalidade de licitação denominada "
     "pregão, para aquisição de bens e serviços comuns."),
    ("acs_11350_2006", "lei", "11350", date(2006, 10, 5),
     "Agentes comunitários de saúde e de combate às endemias",
     "Regulamenta o § 5º do art. 198 da Constituição Federal e dispõe sobre o "
     "aproveitamento de pessoal amparado pelo parágrafo único do art. 2º da Emenda "
     "Constitucional nº 51, de 14 de fevereiro de 2006."),
    ("magisteriofederal_12772_2012", "lei", "12772", date(2012, 12, 28),
     "Plano de Carreiras do Magistério Federal",
     "Dispõe sobre a estruturação do Plano de Carreiras e Cargos de Magistério Federal, "
     "sobre a Carreira do Magistério Superior, de que trata a Lei nº 7.596, de 10 de abril "
     "de 1987, e sobre o Plano de Carreira e Cargos de Magistério do Ensino Básico, Técnico "
     "e Tecnológico."),
    ("orgpresidencia_13844_2019", "lei", "13844", date(2019, 6, 18),
     "Organização da Presidência e dos Ministérios até 2023",
     "Estabelece a organização básica dos órgãos da Presidência da República e dos "
     "Ministérios."),

    # =====================================================================
    # Lote 6 (2026-08-12): a **parte textual** das leis orçamentárias anuais
    # — LDO e LOA — dos exercícios de 2012 a 2026 (15 pares). Recorte: só a
    # lei que fixa as diretrizes (LDO) ou estima receita e fixa despesa (LOA)
    # do exercício; as que apenas as alteram e as de crédito suplementar,
    # especial ou extraordinário ficam de fora — são dezenas por ano e não
    # carregam norma consultável.
    #
    # "Parte textual" sai de graça da arquitetura: o pipeline indexa
    # dispositivos parseados, e os anexos da LOA e da LDO são tabelas, que o
    # parser não produz como dispositivo. A LOA de 2024, por exemplo, tem 309
    # KB de HTML e rende 10 artigos.
    #
    # Série levantada por varredura na API de metadados do LexML (faixa
    # 12.100-15.800, filtrando a ementa oficial), não de memória: nenhum
    # exercício ficou sem par. O corte em 2012 acompanha os ciclos de PPA
    # (2012-2015, 2016-2019, 2020-2023, 2024-2027). Não há LDO de 2027 até
    # esta data.
    #
    # O apelido carrega o exercício ("LDO 2024"), e como a epígrafe entra no
    # texto embedado, o ano distingue artigos quase idênticos que se repetem
    # de um exercício para o outro — sem isso a busca por "meta fiscal"
    # devolveria 15 vizinhos indistinguíveis.
    # =====================================================================

    ("ldo2012_12465_2011", "lei", "12465", date(2011, 8, 12), "LDO 2012",
     "Dispõe sobre as diretrizes para a elaboração e execução da Lei Orçamentária de 2012 "
     "e dá outras providências."),
    ("loa2012_12595_2012", "lei", "12595", date(2012, 1, 19), "LOA 2012",
     "Estima a receita e fixa a despesa da União para o exercício financeiro de 2012."),
    ("ldo2013_12708_2012", "lei", "12708", date(2012, 8, 17), "LDO 2013",
     "Dispõe sobre as diretrizes para a elaboração e execução da Lei Orçamentária de 2013 "
     "e dá outras providências."),
    ("loa2013_12798_2013", "lei", "12798", date(2013, 4, 4), "LOA 2013",
     "Estima a receita e fixa a despesa da União para o exercício financeiro de 2013."),
    ("ldo2014_12919_2013", "lei", "12919", date(2013, 12, 24), "LDO 2014",
     "Dispõe sobre as diretrizes para a elaboração e execução da Lei Orçamentária de 2014 "
     "e dá outras providências."),
    ("loa2014_12952_2014", "lei", "12952", date(2014, 1, 20), "LOA 2014",
     "Estima a receita e fixa a despesa da União para o exercício financeiro de 2014."),
    ("ldo2015_13080_2015", "lei", "13080", date(2015, 1, 2), "LDO 2015",
     "Dispõe sobre as diretrizes para a elaboração e execução da Lei Orçamentária de 2015 "
     "e dá outras providências."),
    ("loa2015_13115_2015", "lei", "13115", date(2015, 4, 20), "LOA 2015",
     "Estima a receita e fixa a despesa da União para o exercício financeiro de 2015."),
    ("ldo2016_13242_2015", "lei", "13242", date(2015, 12, 30), "LDO 2016",
     "Dispõe sobre as diretrizes para a elaboração e execução da Lei Orçamentária de 2016 "
     "e dá outras providências."),
    ("loa2016_13255_2016", "lei", "13255", date(2016, 1, 14), "LOA 2016",
     "Estima a receita e fixa a despesa da União para o exercício financeiro de 2016."),
    ("ldo2017_13408_2016", "lei", "13408", date(2016, 12, 26), "LDO 2017",
     "Dispõe sobre as diretrizes para a elaboração e execução da Lei Orçamentária de 2017 "
     "e dá outras providências."),
    ("loa2017_13414_2017", "lei", "13414", date(2017, 1, 10), "LOA 2017",
     "Estima a receita e fixa a despesa da União para o exercício financeiro de 2017."),
    ("ldo2018_13473_2017", "lei", "13473", date(2017, 8, 8), "LDO 2018",
     "Dispõe sobre as diretrizes para a elaboração e execução da Lei Orçamentária de 2018 "
     "e dá outras providências."),
    ("loa2018_13587_2018", "lei", "13587", date(2018, 1, 2), "LOA 2018",
     "Estima a receita e fixa a despesa da União para o exercício financeiro de 2018."),
    ("ldo2019_13707_2018", "lei", "13707", date(2018, 8, 14), "LDO 2019",
     "Dispõe sobre as diretrizes para a elaboração e execução da Lei Orçamentária de 2019 "
     "e dá outras providências."),
    ("loa2019_13808_2019", "lei", "13808", date(2019, 1, 15), "LOA 2019",
     "Estima a receita e fixa a despesa da União para o exercício financeiro de 2019."),
    ("ldo2020_13898_2019", "lei", "13898", date(2019, 11, 11), "LDO 2020",
     "Dispõe sobre as diretrizes para a elaboração e a execução da Lei Orçamentária de "
     "2020 e dá outras providências."),
    ("loa2020_13978_2020", "lei", "13978", date(2020, 1, 17), "LOA 2020",
     "Estima a receita e fixa a despesa da União para o exercício financeiro de 2020."),
    ("ldo2021_14116_2020", "lei", "14116", date(2020, 12, 31), "LDO 2021",
     "Dispõe sobre as diretrizes para a elaboração e a execução da Lei Orçamentária de "
     "2021 e dá outras providências."),
    ("loa2021_14144_2021", "lei", "14144", date(2021, 4, 22), "LOA 2021",
     "Estima a receita e fixa a despesa da União para o exercício financeiro de 2021."),
    ("ldo2022_14194_2021", "lei", "14194", date(2021, 8, 20), "LDO 2022",
     "Dispõe sobre as diretrizes para a elaboração e a execução da Lei Orçamentária de "
     "2022 e dá outras providências."),
    ("loa2022_14303_2022", "lei", "14303", date(2022, 1, 21), "LOA 2022",
     "Estima a receita e fixa a despesa da União para o exercício financeiro de 2022."),
    ("ldo2023_14436_2022", "lei", "14436", date(2022, 8, 9), "LDO 2023",
     "Dispõe sobre as diretrizes para a elaboração e a execução da Lei Orçamentária de "
     "2023 e dá outras providências."),
    ("loa2023_14535_2023", "lei", "14535", date(2023, 1, 17), "LOA 2023",
     "Estima a receita e fixa a despesa da União para o exercício financeiro de 2023."),
    ("ldo2024_14791_2023", "lei", "14791", date(2023, 12, 29), "LDO 2024",
     "Dispõe sobre as diretrizes para a elaboração e a execução da Lei Orçamentária de "
     "2024 e dá outras providências."),
    ("loa2024_14822_2024", "lei", "14822", date(2024, 1, 22), "LOA 2024",
     "Estima a receita e fixa a despesa da União para o exercício financeiro de 2024."),
    ("ldo2025_15080_2024", "lei", "15080", date(2024, 12, 30), "LDO 2025",
     "Dispõe sobre as diretrizes para a elaboração e a execução da Lei Orçamentária de "
     "2025 e dá outras providências."),
    ("loa2025_15121_2025", "lei", "15121", date(2025, 4, 10), "LOA 2025",
     "Estima a receita e fixa a despesa da União para o exercício financeiro de 2025."),
    ("ldo2026_15321_2025", "lei", "15321", date(2025, 12, 31), "LDO 2026",
     "Dispõe sobre as diretrizes para a elaboração e a execução da Lei Orçamentária de "
     "2026 e dá outras providências."),
    ("loa2026_15346_2026", "lei", "15346", date(2026, 1, 14), "LOA 2026",
     "Estima a receita e fixa a despesa da União para o exercício financeiro de 2026."),

    # =====================================================================
    # Lote 8 (2026-08-18): regimes de incentivo setorial — automotivo e
    # infraestrutura. São leis de política industrial que concedem crédito
    # financeiro ou suspensão tributária mediante contrapartida (P&D,
    # eficiência energética, obra de infraestrutura), e o corpus tinha o
    # incentivo genérico (Lei do Bem, Marco da Inovação) sem os regimes
    # setoriais que respondem pela maior parte da renúncia. A Rota 2030 e o
    # Mover entram como par: o Mover sucede a Rota 2030 e revoga dispositivos
    # dela, então quem consulta um precisa do outro para saber o que sobrou.
    # =====================================================================

    ("reidi_11488_2007", "lei", "11488", date(2007, 6, 15), "REIDI",
     "Cria o Regime Especial de Incentivos para o Desenvolvimento da Infraestrutura "
     "(Reidi) e reduz o prazo mínimo para utilização dos créditos da Contribuição para o "
     "PIS/Pasep e da Cofins decorrentes da aquisição de edificações."),
    ("rota2030_13755_2018", "lei", "13755", date(2018, 12, 10), "Rota 2030",
     "Estabelece requisitos obrigatórios para a comercialização de veículos no Brasil, "
     "institui o Programa Rota 2030 - Mobilidade e Logística e dispõe sobre o regime "
     "tributário de autopeças não produzidas."),
    ("mover_14902_2024", "lei", "14902", date(2024, 6, 27), "Programa Mover",
     "Institui o Programa Mobilidade Verde e Inovação (Programa Mover) e revoga "
     "dispositivos da Lei nº 13.755, de 10 de dezembro de 2018 (Rota 2030)."),

    # =====================================================================
    # Lote 9 (2026-08-21): direito econômico — o que faltava para além da
    # ordem econômica constitucional. O corpus já tinha a espinha dorsal
    # (Lei 12.529/2011, Lei 13.874/2019, CDC, as oito agências e a Lei
    # 13.848/2019, concessões, PPP, estatais, PND, 6.385, 6.404, 4.595,
    # 7.492, 9.279, 11.101); faltavam quatro flancos inteiros: defesa
    # comercial, resolução bancária, infraestrutura de mercado e os títulos
    # que financiam a atividade produtiva.
    # =====================================================================

    # ---------------------------------- defesa comercial e regime regional
    ("defesacomercial_9019_1995", "lei", "9019", date(1995, 3, 30), "Antidumping e compensatórios",
     "Dispõe sobre a aplicação dos direitos previstos no Acordo Antidumping e no Acordo "
     "de Subsídios e Direitos Compensatórios."),
    ("zfm_288_1967", "decreto.lei", "288", date(1967, 2, 28), "Zona Franca de Manaus",
     "Altera as disposições da Lei nº 3.173, de 6 de junho de 1957, e regula a Zona "
     "Franca de Manaus."),

    # --------------------- sistema financeiro: resolução, mercado e sanção
    ("liquidacaoif_6024_1974", "lei", "6024", date(1974, 3, 13), "Intervenção e liquidação de instituições financeiras",
     "Dispõe sobre a intervenção e a liquidação extrajudicial de instituições financeiras."),
    ("respcontroladores_9447_1997", "lei", "9447", date(1997, 3, 14), "Responsabilidade de controladores de instituição financeira",
     "Dispõe sobre a responsabilidade solidária de controladores de instituições "
     "submetidas aos regimes da Lei nº 6.024, de 13 de março de 1974, e do Decreto-Lei "
     "nº 2.321, de 25 de fevereiro de 1987, sobre a indisponibilidade de seus bens e "
     "sobre a responsabilização das empresas de auditoria contábil."),
    ("spb_10214_2001", "lei", "10214", date(2001, 3, 27), "Sistema de Pagamentos Brasileiro",
     "Dispõe sobre a atuação das câmaras e dos prestadores de serviços de compensação e "
     "de liquidação, no âmbito do sistema de pagamentos brasileiro."),
    ("sancionadorbcbcvm_13506_2017", "lei", "13506", date(2017, 11, 13), "Processo sancionador do BCB e da CVM",
     "Dispõe sobre o processo administrativo sancionador na esfera de atuação do Banco "
     "Central do Brasil e da Comissão de Valores Mobiliários."),
    ("mercadocapitais_4728_1965", "lei", "4728", date(1965, 7, 14), "Mercado de capitais",
     "Disciplina o mercado de capitais e estabelece medidas para o seu desenvolvimento."),

    # ------------------------- organização empresarial e canais de venda
    ("registroempresas_8934_1994", "lei", "8934", date(1994, 11, 18), "Registro Público de Empresas Mercantis",
     "Dispõe sobre o Registro Público de Empresas Mercantis e Atividades Afins."),
    ("repcomercial_4886_1965", "lei", "4886", date(1965, 12, 9), "Representação comercial",
     "Regula as atividades dos representantes comerciais autônomos."),
    ("leiferrari_6729_1979", "lei", "6729", date(1979, 11, 28), "Lei Ferrari",
     "Dispõe sobre a concessão comercial entre produtores e distribuidores de veículos "
     "automotores de via terrestre."),
    ("crimesordemecon_8176_1991", "lei", "8176", date(1991, 2, 8), "Crimes contra a ordem econômica",
     "Define crimes contra a ordem econômica e cria o Sistema de Estoques de Combustíveis."),

    # ------------------------------- infraestrutura: portos e parcerias
    ("portos_12815_2013", "lei", "12815", date(2013, 6, 5), "Lei dos Portos",
     "Dispõe sobre a exploração direta e indireta pela União de portos e instalações "
     "portuárias e sobre as atividades desempenhadas pelos operadores portuários."),
    ("relicitacao_13448_2017", "lei", "13448", date(2017, 6, 5), "Prorrogação e relicitação de contratos de parceria",
     "Estabelece diretrizes gerais para prorrogação e relicitação dos contratos de "
     "parceria definidos nos termos da Lei nº 13.334, de 13 de setembro de 2016, nos "
     "setores rodoviário, ferroviário e aeroportuário da administração pública federal."),
    ("debentinfra_14801_2024", "lei", "14801", date(2024, 1, 9), "Debêntures de infraestrutura",
     "Dispõe sobre as debêntures de infraestrutura e altera as Leis nº 11.478, de 29 de "
     "maio de 2007 (FIP-IE), e nº 12.431, de 24 de junho de 2011."),

    # ------------------------- títulos de crédito e financiamento privado
    ("cpr_8929_1994", "lei", "8929", date(1994, 8, 22), "Cédula de Produto Rural",
     "Institui a Cédula de Produto Rural (CPR)."),
    ("titulosagro_11076_2004", "lei", "11076", date(2004, 12, 30), "Títulos do agronegócio",
     "Dispõe sobre o Certificado de Depósito Agropecuário (CDA), o Warrant Agropecuário "
     "(WA), o Certificado de Direitos Creditórios do Agronegócio (CDCA), a Letra de "
     "Crédito do Agronegócio (LCA) e o Certificado de Recebíveis do Agronegócio (CRA)."),
    ("leidoagro_13986_2020", "lei", "13986", date(2020, 4, 7), "Lei do Agro",
     "Institui o Fundo Garantidor Solidário (FGS) e dispõe sobre o patrimônio rural em "
     "afetação, a Cédula Imobiliária Rural (CIR) e a escrituração de títulos de crédito."),
    ("titulosimob_10931_2004", "lei", "10931", date(2004, 8, 2), "Patrimônio de afetação, LCI, CCI e CCB",
     "Dispõe sobre o patrimônio de afetação de incorporações imobiliárias, a Letra de "
     "Crédito Imobiliário (LCI), a Cédula de Crédito Imobiliário (CCI) e a Cédula de "
     "Crédito Bancário (CCB)."),
    ("leasing_6099_1974", "lei", "6099", date(1974, 9, 12), "Arrendamento mercantil",
     "Dispõe sobre o tratamento tributário das operações de arrendamento mercantil."),
    ("consorcios_11795_2008", "lei", "11795", date(2008, 10, 8), "Sistema de consórcio",
     "Dispõe sobre o Sistema de Consórcio."),
    ("pnmpo_13636_2018", "lei", "13636", date(2018, 3, 20), "PNMPO",
     "Dispõe sobre o Programa Nacional de Microcrédito Produtivo Orientado (PNMPO)."),
    ("pronampe_13999_2020", "lei", "13999", date(2020, 5, 18), "Pronampe",
     "Institui o Programa Nacional de Apoio às Microempresas e Empresas de Pequeno Porte "
     "(Pronampe), para o desenvolvimento e o fortalecimento dos pequenos negócios."),

    # =================================================================
    # Lote 13 (onda de expansão) — direito público de base. Datas e ementas
    # da API de metadados do LexML, conferidas contra o número pedido.
    # =================================================================
    # ------------------------------------ organização administrativa
    ("dl200_1967", "decreto.lei", "200", date(1967, 2, 25),
     "Organização da Administração Federal",
     "Dispõe sobre a organização da Administração Federal, estabelece diretrizes para "
     "a Reforma Administrativa."),
    ("empregopublico_9962_2000", "lei", "9962", date(2000, 2, 22), "Emprego público",
     "Disciplina o regime de emprego público do pessoal da Administração federal direta, "
     "autárquica e fundacional."),
    ("carreirasjudiciario_11416_2006", "lei", "11416", date(2006, 12, 15),
     "Carreiras do Poder Judiciário da União",
     "Dispõe sobre as Carreiras dos Servidores do Poder Judiciário da União."),
    ("pgf_10480_2002", "lei", "10480", date(2002, 7, 2), "Procuradoria-Geral Federal",
     "Dispõe sobre o Quadro de Pessoal da Advocacia-Geral da União e cria a "
     "Procuradoria-Geral Federal."),
    ("honorariosadvpublica_13327_2016", "lei", "13327", date(2016, 7, 29),
     "Honorários da advocacia pública",
     "Altera a remuneração de servidores públicos; dispõe sobre os honorários advocatícios "
     "de sucumbência das causas em que forem parte a União, suas autarquias e fundações "
     "(arts. 27 a 36); reestrutura cargos e carreiras."),
    # ------------------------------------ patrimônio e desapropriação
    ("desapropriacao_3365_1941", "decreto.lei", "3365", date(1941, 6, 21),
     "Desapropriação por utilidade pública",
     "Dispõe sobre desapropriações por utilidade pública."),
    ("desapropriacaosocial_4132_1962", "lei", "4132", date(1962, 9, 10),
     "Desapropriação por interesse social",
     "Define os casos de desapropriação por interesse social e dispõe sobre sua aplicação."),
    ("imoveisuniao_9760_1946", "decreto.lei", "9760", date(1946, 9, 5),
     "Bens imóveis da União",
     "Dispõe sobre os bens imóveis da União."),
    ("gestaoimoveisuniao_9636_1998", "lei", "9636", date(1998, 5, 15),
     "Regularização e alienação de imóveis da União",
     "Dispõe sobre a regularização, administração, aforamento e alienação de bens imóveis "
     "de domínio da União."),
    ("forolaudemio_2398_1987", "decreto.lei", "2398", date(1987, 12, 21),
     "Foros, laudêmios e taxas de ocupação",
     "Dispõe sobre foros, laudêmios e taxas de ocupação relativas a imóveis de "
     "propriedade da União."),
    ("alienacaoimoveisuniao_13240_2015", "lei", "13240", date(2015, 12, 30),
     "Administração e alienação de imóveis da União",
     "Dispõe sobre a administração, a alienação, a transferência de gestão de imóveis da "
     "União e seu uso para a constituição de fundos."),
    # ------------------------------------ processo contra a Fazenda
    ("cautelarespoderpublico_8437_1992", "lei", "8437", date(1992, 6, 30),
     "Medidas cautelares contra o Poder Público",
     "Dispõe sobre a concessão de medidas cautelares contra atos do Poder Público."),
    ("tutelafazenda_9494_1997", "lei", "9494", date(1997, 9, 10),
     "Tutela antecipada contra a Fazenda Pública",
     "Disciplina a aplicação da tutela antecipada contra a Fazenda Pública."),
    ("prescricaoadm_9873_1999", "lei", "9873", date(1999, 11, 23),
     "Prescrição da ação punitiva da Administração",
     "Estabelece prazo de prescrição para o exercício de ação punitiva pela Administração "
     "Pública Federal, direta e indireta."),
    ("justicafederal_5010_1966", "lei", "5010", date(1966, 5, 30),
     "Organização da Justiça Federal",
     "Organiza a Justiça Federal de primeira instância."),
    ("representacaointerventiva_12562_2011", "lei", "12562", date(2011, 12, 23),
     "Representação interventiva",
     "Regulamenta o inciso III do art. 36 da Constituição Federal, para dispor sobre o "
     "processo e julgamento da representação interventiva perante o Supremo Tribunal "
     "Federal."),
    # ------------------------------------ segurança e defesa
    ("servicomilitar_4375_1964", "lei", "4375", date(1964, 8, 17), "Lei do Serviço Militar",
     "Lei do Serviço Militar."),
    ("abin_9883_1999", "lei", "9883", date(1999, 12, 7), "Sisbin e ABIN",
     "Institui o Sistema Brasileiro de Inteligência, cria a Agência Brasileira de "
     "Inteligência - ABIN."),
    ("lopmbombeiros_14751_2023", "lei", "14751", date(2023, 12, 12),
     "Lei Orgânica das Polícias Militares e Bombeiros",
     "Institui a Lei Orgânica Nacional das Polícias Militares e dos Corpos de Bombeiros "
     "Militares dos Estados, do Distrito Federal e dos Territórios."),
    ("forcanacional_11473_2007", "lei", "11473", date(2007, 5, 10),
     "Força Nacional de Segurança Pública",
     "Dispõe sobre cooperação federativa no âmbito da segurança pública."),
    # ------------------------------------ urbano, comunicação e cartórios
    ("metropole_13089_2015", "lei", "13089", date(2015, 1, 12), "Estatuto da Metrópole",
     "Institui o Estatuto da Metrópole."),
    ("publicidade_12232_2010", "lei", "12232", date(2010, 4, 29),
     "Licitação de serviços de publicidade",
     "Dispõe sobre as normas gerais para licitação e contratação pela administração "
     "pública de serviços de publicidade prestados por intermédio de agências de "
     "propaganda."),
    ("desburocratizacao_13726_2018", "lei", "13726", date(2018, 10, 8),
     "Desburocratização",
     "Racionaliza atos e procedimentos administrativos dos Poderes da União, dos Estados, "
     "do Distrito Federal e dos Municípios e institui o Selo de Desburocratização e "
     "Simplificação."),
    ("notarios_8935_1994", "lei", "8935", date(1994, 11, 18),
     "Serviços notariais e de registro",
     "Regulamenta o art. 236 da Constituição Federal, dispondo sobre serviços notariais "
     "e de registro."),

    # =================================================================
    # Lote 14 (onda de expansão) — direito privado, família e penal especial.
    # =================================================================
    # ------------------------------------ decretos-lei de base
    ("contravencoes_3688_1941", "decreto.lei", "3688", date(1941, 10, 3),
     "Lei das Contravenções Penais", "Lei das Contravenções Penais."),
    ("tombamento_25_1937", "decreto.lei", "25", date(1937, 11, 30), "Tombamento",
     "Organiza a proteção do patrimônio histórico e artístico nacional."),
    ("alienacaofiduciaria_911_1969", "decreto.lei", "911", date(1969, 10, 1),
     "Alienação fiduciária de bens móveis",
     "Altera a redação do art. 66 da Lei nº 4.728, de 14 de julho de 1965, e estabelece "
     "normas de processo sobre alienação fiduciária."),
    ("cedulahipotecaria_70_1966", "decreto.lei", "70", date(1966, 11, 21),
     "Cédula hipotecária e execução extrajudicial",
     "Autoriza o funcionamento de associações de poupança e empréstimo e institui a "
     "cédula hipotecária."),
    ("creditorural_167_1967", "decreto.lei", "167", date(1967, 2, 14),
     "Títulos de crédito rural", "Dispõe sobre títulos de crédito rural."),
    ("alimentos_986_1969", "decreto.lei", "986", date(1969, 10, 21),
     "Normas básicas sobre alimentos", "Institui normas básicas sobre alimentos."),
    # ------------------------------------ civil, família e imobiliário
    ("bemdefamilia_8009_1990", "lei", "8009", date(1990, 3, 29), "Bem de família",
     "Dispõe sobre a impenhorabilidade do bem de família."),
    ("cheque_7357_1985", "lei", "7357", date(1985, 9, 2), "Lei do Cheque",
     "Dispõe sobre o cheque."),
    ("acaoalimentos_5478_1968", "lei", "5478", date(1968, 7, 25), "Ação de alimentos",
     "Dispõe sobre ação de alimentos."),
    ("paternidade_8560_1992", "lei", "8560", date(1992, 12, 29),
     "Investigação de paternidade",
     "Regula a investigação de paternidade dos filhos havidos fora do casamento."),
    ("divorcio_6515_1977", "lei", "6515", date(1977, 12, 26), "Lei do Divórcio",
     "Regula os casos de dissolução da sociedade conjugal e do casamento, seus efeitos "
     "e respectivos processos."),
    ("alimentosgravidicos_11804_2008", "lei", "11804", date(2008, 11, 5),
     "Alimentos gravídicos",
     "Disciplina o direito a alimentos gravídicos e a forma como ele será exercido."),
    ("alienacaoparental_12318_2010", "lei", "12318", date(2010, 8, 26),
     "Alienação parental", "Dispõe sobre a alienação parental."),
    ("distrato_13786_2018", "lei", "13786", date(2018, 12, 27),
     "Distrato imobiliário",
     "Disciplina a resolução do contrato por inadimplemento do adquirente de unidade "
     "imobiliária em incorporação imobiliária e em parcelamento de solo urbano."),
    ("marcogarantias_14711_2023", "lei", "14711", date(2023, 10, 30),
     "Marco Legal das Garantias",
     "Dispõe sobre o aprimoramento das regras de garantia, a execução extrajudicial de "
     "créditos garantidos por hipoteca, a execução extrajudicial de garantia imobiliária "
     "em concurso de credores e o procedimento de busca e apreensão extrajudicial de "
     "bens móveis."),
    ("saf_14193_2021", "lei", "14193", date(2021, 8, 6), "Sociedade Anônima do Futebol",
     "Institui a Sociedade Anônima do Futebol e dispõe sobre normas de constituição, "
     "governança, controle e transparência, meios de financiamento da atividade "
     "futebolística e tratamento dos passivos das entidades de práticas desportivas."),
    # ------------------------------------ penal e processo penal especial
    ("prisaotemporaria_7960_1989", "lei", "7960", date(1989, 12, 21), "Prisão temporária",
     "Dispõe sobre prisão temporária."),
    ("traficopessoas_13344_2016", "lei", "13344", date(2016, 10, 6),
     "Tráfico de pessoas",
     "Dispõe sobre prevenção e repressão ao tráfico interno e internacional de pessoas "
     "e sobre medidas de atenção às vítimas."),
    ("escutaprotegida_13431_2017", "lei", "13431", date(2017, 4, 4),
     "Criança vítima ou testemunha de violência",
     "Estabelece o sistema de garantia de direitos da criança e do adolescente vítima "
     "ou testemunha de violência."),
    ("primeirainfancia_13257_2016", "lei", "13257", date(2016, 3, 8),
     "Marco Legal da Primeira Infância",
     "Dispõe sobre as políticas públicas para a primeira infância."),
    ("bullying_13185_2015", "lei", "13185", date(2015, 11, 6), "Combate ao bullying",
     "Institui o Programa de Combate à Intimidação Sistemática (Bullying)."),
    ("violenciasexual_12845_2013", "lei", "12845", date(2013, 8, 1),
     "Atendimento a vítimas de violência sexual",
     "Dispõe sobre o atendimento obrigatório e integral de pessoas em situação de "
     "violência sexual."),
    ("naoenao_14786_2023", "lei", "14786", date(2023, 12, 28), "Protocolo Não é Não",
     "Cria o protocolo 'Não é Não', para prevenção ao constrangimento e à violência "
     "contra a mulher e para proteção à vítima."),
    ("violenciapolitica_14192_2021", "lei", "14192", date(2021, 8, 4),
     "Violência política contra a mulher",
     "Estabelece normas para prevenir, reprimir e combater a violência política contra "
     "a mulher."),
    # ------------------------------------ direitos de grupos
    ("apoiopcd_7853_1989", "lei", "7853", date(1989, 10, 24),
     "Apoio às pessoas com deficiência",
     "Dispõe sobre o apoio às pessoas portadoras de deficiência, sua integração social "
     "e a tutela jurisdicional de interesses coletivos ou difusos dessas pessoas."),
    ("passelivre_8899_1994", "lei", "8899", date(1994, 6, 29), "Passe livre interestadual",
     "Concede passe livre às pessoas portadoras de deficiência no sistema de transporte "
     "coletivo interestadual."),
    ("libras_10436_2002", "lei", "10436", date(2002, 4, 24), "Libras",
     "Dispõe sobre a Língua Brasileira de Sinais - Libras."),
    ("refugiados_9474_1997", "lei", "9474", date(1997, 7, 22), "Estatuto dos Refugiados",
     "Define mecanismos para a implementação do Estatuto dos Refugiados de 1951."),
    ("terrasindigenas_14701_2023", "lei", "14701", date(2023, 10, 20),
     "Demarcação de terras indígenas",
     "Regulamenta o art. 231 da Constituição Federal, para dispor sobre o "
     "reconhecimento, a demarcação, o uso e a gestão de terras indígenas."),
    ("cotasconcursos_15142_2025", "lei", "15142", date(2025, 6, 3),
     "Cotas raciais em concursos públicos",
     "Reserva às pessoas pretas e pardas, indígenas e quilombolas o percentual de 30% "
     "das vagas oferecidas nos concursos públicos para provimento de cargos efetivos e "
     "empregos públicos no âmbito da administração pública federal."),
    ("transporteeleitores_6091_1974", "lei", "6091", date(1974, 8, 15),
     "Transporte de eleitores",
     "Dispõe sobre o fornecimento gratuito de transporte, em dias de eleição, a "
     "eleitores residentes nas zonas rurais."),

    # =================================================================
    # Lote 15 (onda de expansão) — trabalho, profissões regulamentadas e
    # previdência. A Lei 14.434/2022 (piso da enfermagem) fica de fora: só
    # altera a Lei 7.498, que entra compilada.
    # =================================================================
    # ------------------------------------ trabalho
    ("decimoterceiro_4090_1962", "lei", "4090", date(1962, 7, 13), "13º salário",
     "Institui a gratificação de Natal para os trabalhadores."),
    ("decimoterceiropag_4749_1965", "lei", "4749", date(1965, 8, 12),
     "Pagamento do 13º salário",
     "Dispõe sobre o pagamento da gratificação prevista na Lei nº 4.090, de 13 de julho "
     "de 1962."),
    ("valetransporte_7418_1985", "lei", "7418", date(1985, 12, 16), "Vale-Transporte",
     "Institui o Vale-Transporte."),
    ("pat_6321_1976", "lei", "6321", date(1976, 4, 14),
     "PAT — Programa de Alimentação do Trabalhador",
     "Dispõe sobre a dedução, do lucro tributável para fins de imposto sobre a renda das "
     "pessoas jurídicas, do dobro das despesas realizadas em programas de alimentação do "
     "trabalhador."),
    ("discriminacaotrabalho_9029_1995", "lei", "9029", date(1995, 4, 13),
     "Práticas discriminatórias no trabalho",
     "Proíbe a exigência de atestados de gravidez e esterilização, e outras práticas "
     "discriminatórias, para efeitos admissionais ou de permanência da relação jurídica "
     "de trabalho."),
    ("motorista_13103_2015", "lei", "13103", date(2015, 3, 2), "Motorista profissional",
     "Dispõe sobre o exercício da profissão de motorista."),
    ("trabalhoavulso_12023_2009", "lei", "12023", date(2009, 8, 27), "Trabalho avulso",
     "Dispõe sobre as atividades de movimentação de mercadorias em geral e sobre o "
     "trabalho avulso."),
    ("cooperativastrabalho_12690_2012", "lei", "12690", date(2012, 7, 19),
     "Cooperativas de trabalho",
     "Dispõe sobre a organização e o funcionamento das Cooperativas de Trabalho e "
     "institui o Programa Nacional de Fomento às Cooperativas de Trabalho - PRONACOOP."),
    ("segurancaprivada_14967_2024", "lei", "14967", date(2024, 9, 9),
     "Estatuto da Segurança Privada",
     "Institui o Estatuto da Segurança Privada e da Segurança das Instituições "
     "Financeiras."),
    # ------------------------------------ previdência
    ("rppsuniao_10887_2004", "lei", "10887", date(2004, 6, 18),
     "Contribuição e cálculo dos benefícios do RPPS",
     "Dispõe sobre a aplicação de disposições da Emenda Constitucional nº 41, de 19 de "
     "dezembro de 2003 (cálculo dos proventos e contribuição previdenciária do servidor)."),
    ("aposentadoriaespecial_10666_2003", "lei", "10666", date(2003, 5, 8),
     "Aposentadoria especial do cooperado e regras de custeio",
     "Dispõe sobre a concessão da aposentadoria especial ao cooperado de cooperativa de "
     "trabalho ou de produção."),
    ("revisaobeneficios_13846_2019", "lei", "13846", date(2019, 6, 18),
     "Revisão de benefícios previdenciários",
     "Institui o Programa Especial para Análise de Benefícios com Indícios de "
     "Irregularidade e o Programa de Revisão de Benefícios por Incapacidade."),
    # ------------------------------------ profissões regulamentadas
    ("medicina_12842_2013", "lei", "12842", date(2013, 7, 10), "Lei do Ato Médico",
     "Dispõe sobre o exercício da Medicina."),
    ("enfermagem_7498_1986", "lei", "7498", date(1986, 6, 25), "Exercício da enfermagem",
     "Dispõe sobre a regulamentação do exercício da enfermagem."),
    ("engenharia_5194_1966", "lei", "5194", date(1966, 12, 24),
     "Profissões de Engenharia e Agronomia",
     "Regula o exercício das profissões de Engenharia, Arquiteto e Engenheiro-Agrônomo."),
    ("arquitetura_12378_2010", "lei", "12378", date(2010, 12, 31),
     "Arquitetura e Urbanismo — CAU",
     "Regulamenta o exercício da Arquitetura e Urbanismo; cria o Conselho de Arquitetura "
     "e Urbanismo do Brasil - CAU/BR."),
    ("contabilidade_9295_1946", "decreto.lei", "9295", date(1946, 5, 27),
     "Profissão contábil — CFC",
     "Cria o Conselho Federal de Contabilidade e define as atribuições do Contador e do "
     "Guarda-livros."),
    ("farmacia_13021_2014", "lei", "13021", date(2014, 8, 8), "Atividades farmacêuticas",
     "Dispõe sobre o exercício e a fiscalização das atividades farmacêuticas."),
    ("psicologia_4119_1962", "lei", "4119", date(1962, 8, 27), "Profissão de psicólogo",
     "Dispõe sobre os cursos de formação em psicologia e regulamenta a profissão de "
     "psicólogo."),
    ("servicosocial_8662_1993", "lei", "8662", date(1993, 6, 7),
     "Profissão de Assistente Social",
     "Dispõe sobre a profissão de Assistente Social."),
    ("educacaofisica_9696_1998", "lei", "9696", date(1998, 9, 1),
     "Profissão de Educação Física",
     "Dispõe sobre a regulamentação da Profissão de Educação Física e cria os "
     "respectivos Conselho Federal e Conselhos Regionais de Educação Física."),
    ("nutricao_8234_1991", "lei", "8234", date(1991, 9, 17), "Profissão de Nutricionista",
     "Regulamenta a profissão de Nutricionista."),
    ("veterinaria_5517_1968", "lei", "5517", date(1968, 10, 23),
     "Profissão de médico-veterinário",
     "Dispõe sobre o exercício da profissão de médico-veterinário e cria os Conselhos "
     "Federal e Regionais de Medicina Veterinária."),
    ("odontologia_5081_1966", "lei", "5081", date(1966, 8, 24), "Exercício da Odontologia",
     "Regula o exercício da Odontologia."),
    ("corretorimoveis_6530_1978", "lei", "6530", date(1978, 5, 12),
     "Profissão de Corretor de Imóveis",
     "Dá nova regulamentação à profissão de Corretor de Imóveis e disciplina o "
     "funcionamento de seus órgãos de fiscalização."),
    ("corretorseguros_4594_1964", "lei", "4594", date(1964, 12, 29),
     "Profissão de corretor de seguros",
     "Regula a profissão de corretor de seguros."),
    ("taxista_12468_2011", "lei", "12468", date(2011, 8, 26), "Profissão de taxista",
     "Regulamenta a profissão de taxista."),
    ("artistas_6533_1978", "lei", "6533", date(1978, 5, 24),
     "Profissões de Artista e Técnico em Espetáculos",
     "Dispõe sobre a regulamentação das profissões de Artista e de Técnico em "
     "Espetáculos de Diversões."),
    ("radialista_6615_1978", "lei", "6615", date(1978, 12, 16), "Profissão de Radialista",
     "Dispõe sobre a regulamentação da profissão de Radialista."),
    ("jornalista_972_1969", "decreto.lei", "972", date(1969, 10, 17),
     "Profissão de jornalista",
     "Dispõe sobre o exercício da profissão de jornalista."),
    ("jornadamedicos_3999_1961", "lei", "3999", date(1961, 12, 15),
     "Salário-mínimo e jornada de médicos e cirurgiões-dentistas",
     "Altera o salário-mínimo dos médicos e cirurgiões dentistas."),
    ("petroleiros_5811_1972", "lei", "5811", date(1972, 10, 11),
     "Regime de trabalho dos petroleiros",
     "Dispõe sobre o regime de trabalho dos empregados nas atividades de exploração, "
     "perfuração, produção e refinação de petróleo, industrialização do xisto, indústria "
     "petroquímica e transporte de petróleo e seus derivados por meio de dutos."),
    ("bombeirocivil_11901_2009", "lei", "11901", date(2009, 1, 12),
     "Profissão de Bombeiro Civil",
     "Dispõe sobre a profissão de Bombeiro Civil."),
    ("guiaturismo_8623_1993", "lei", "8623", date(1993, 1, 28), "Profissão de Guia de Turismo",
     "Dispõe sobre a profissão de Guia de Turismo."),
    ("administracao_4769_1965", "lei", "4769", date(1965, 9, 9),
     "Profissão de Administrador",
     "Dispõe sobre o exercício da profissão de Técnico de Administração (Administrador)."),
    ("economista_1411_1951", "lei", "1411", date(1951, 8, 13), "Profissão de Economista",
     "Dispõe sobre a profissão de Economista."),
    ("fisioterapia_938_1969", "decreto.lei", "938", date(1969, 10, 13),
     "Profissões de fisioterapeuta e terapeuta ocupacional",
     "Provê sobre as profissões de fisioterapeuta e terapeuta ocupacional."),
    ("biologia_6684_1979", "lei", "6684", date(1979, 9, 3),
     "Profissões de Biólogo e Biomédico",
     "Regulamenta as profissões de Biólogo e Biomédico e cria o Conselho Federal e os "
     "Conselhos Regionais de Biologia e Biomedicina."),
    ("radiologia_7394_1985", "lei", "7394", date(1985, 10, 29),
     "Profissão de Técnico em Radiologia",
     "Regula o exercício da Profissão de Técnico em Radiologia."),

    # =================================================================
    # Lote 16 (onda de expansão) — tributário e financeiro estrutural. Ficam
    # de fora as que só alteram outra lei (13.476, 13.540, 13.259) e o Desenrola
    # (14.690, programa temporário).
    # =================================================================
    ("csll_7689_1988", "lei", "7689", date(1988, 12, 15), "CSLL",
     "Institui contribuição social sobre o lucro das pessoas jurídicas."),
    ("lucroreal_1598_1977", "decreto.lei", "1598", date(1977, 12, 26),
     "Lucro real — IRPJ das pessoas jurídicas",
     "Altera a legislação do imposto sobre a renda (apuração do lucro real, "
     "escrituração e lucro da exploração)."),
    ("ufir_8383_1991", "lei", "8383", date(1991, 12, 30), "UFIR e imposto de renda",
     "Institui a Unidade Fiscal de Referência e altera a legislação do imposto de renda."),
    ("irpjifrs_12973_2014", "lei", "12973", date(2014, 5, 13),
     "IRPJ e CSLL após os padrões contábeis internacionais",
     "Altera a legislação tributária federal relativa ao IRPJ, à CSLL, ao PIS/Pasep e à "
     "Cofins, adequando-a aos padrões contábeis internacionais e extinguindo o Regime "
     "Tributário de Transição."),
    ("parcelamento_11941_2009", "lei", "11941", date(2009, 5, 27),
     "Parcelamento de débitos e Regime Tributário de Transição",
     "Altera a legislação tributária federal relativa ao parcelamento ordinário de "
     "débitos tributários, concede remissão e institui regime tributário de transição."),
    ("compensacaoprejuizos_9065_1995", "lei", "9065", date(1995, 6, 20),
     "Compensação de prejuízos fiscais e juros Selic",
     "Dá nova redação a dispositivos da Lei nº 8.981, de 20 de janeiro de 1995 (limite "
     "de 30% na compensação de prejuízos e juros equivalentes à taxa Selic)."),
    ("iof_8894_1994", "lei", "8894", date(1994, 6, 21), "IOF",
     "Dispõe sobre o Imposto sobre Operações de Crédito, Câmbio e Seguro, ou relativas a "
     "Títulos e Valores Mobiliários."),
    ("cidecombustiveis_10336_2001", "lei", "10336", date(2001, 12, 19),
     "Cide-Combustíveis",
     "Institui Contribuição de Intervenção no Domínio Econômico incidente sobre a "
     "importação e a comercialização de petróleo e seus derivados, gás natural e seus "
     "derivados, e álcool etílico combustível (Cide)."),
    ("piscofinsagro_10925_2004", "lei", "10925", date(2004, 7, 23),
     "PIS/Cofins no agronegócio e na cesta básica",
     "Reduz as alíquotas do PIS/Pasep e da Cofins incidentes na importação e na "
     "comercialização do mercado interno de fertilizantes e defensivos agropecuários."),
    ("zpe_11508_2007", "lei", "11508", date(2007, 7, 20),
     "Zonas de Processamento de Exportação",
     "Dispõe sobre o regime tributário, cambial e administrativo das Zonas de "
     "Processamento de Exportação."),
    ("padis_11484_2007", "lei", "11484", date(2007, 5, 31), "Padis e PATVD",
     "Dispõe sobre os incentivos às indústrias de equipamentos para TV Digital e de "
     "componentes eletrônicos semicondutores e sobre a proteção à propriedade "
     "intelectual das topografias de circuitos integrados."),
    ("perdimento_1455_1976", "decreto.lei", "1455", date(1976, 4, 7),
     "Bagagem, entreposto aduaneiro e perdimento",
     "Dispõe sobre bagagem de passageiro procedente do exterior, disciplina o regime de "
     "entreposto aduaneiro e estabelece normas sobre mercadorias estrangeiras "
     "apreendidas."),
    ("encargolegal_1025_1969", "decreto.lei", "1025", date(1969, 10, 21),
     "Encargo legal da Dívida Ativa da União",
     "Declara extinta a participação de servidores públicos na cobrança da Dívida Ativa "
     "da União (encargo legal de 20%)."),
    ("prr_13606_2018", "lei", "13606", date(2018, 1, 9),
     "Regularização Tributária Rural e averbação pré-executória",
     "Institui o Programa de Regularização Tributária Rural (PRR) na Secretaria da "
     "Receita Federal do Brasil e na Procuradoria-Geral da Fazenda Nacional."),
    ("desoneracaofolha_14973_2024", "lei", "14973", date(2024, 9, 16),
     "Transição da desoneração da folha",
     "Estabelece regime de transição para a contribuição substitutiva prevista nos arts. "
     "7º e 8º da Lei nº 12.546, de 14 de dezembro de 2011, e para o adicional sobre a "
     "Cofins-Importação."),
    ("autorregularizacao_14740_2023", "lei", "14740", date(2023, 11, 29),
     "Autorregularização incentivada",
     "Dispõe sobre a autorregularização incentivada de tributos administrados pela "
     "Secretaria Especial da Receita Federal do Brasil."),
    ("carf_14689_2023", "lei", "14689", date(2023, 9, 20),
     "Voto de qualidade no Carf e conformidade tributária",
     "Disciplina a proclamação de resultados de julgamentos na hipótese de empate na "
     "votação no âmbito do Conselho Administrativo de Recursos Fiscais (Carf); dispõe "
     "sobre a autorregularização de débitos e a conformidade tributária."),
    ("perse_14148_2021", "lei", "14148", date(2021, 5, 3), "Perse",
     "Dispõe sobre ações emergenciais e temporárias destinadas ao setor de eventos e "
     "institui o Programa Emergencial de Retomada do Setor de Eventos (Perse)."),
    ("transparenciatributaria_12741_2012", "lei", "12741", date(2012, 12, 8),
     "Transparência tributária ao consumidor",
     "Dispõe sobre as medidas de esclarecimento ao consumidor, de que trata o § 5º do "
     "artigo 150 da Constituição Federal (informação dos tributos incidentes no preço)."),
    ("cfem_8001_1990", "lei", "8001", date(1990, 3, 13),
     "Distribuição da CFEM e da compensação hídrica",
     "Define os percentuais da distribuição da compensação financeira de que trata a Lei "
     "nº 7.990, de 28 de dezembro de 1989."),
    ("cmed_10742_2003", "lei", "10742", date(2003, 10, 6), "CMED — regulação de medicamentos",
     "Define normas de regulação para o setor farmacêutico e cria a Câmara de Regulação "
     "do Mercado de Medicamentos - CMED."),
    ("parcelamentoentes_12810_2013", "lei", "12810", date(2013, 5, 15),
     "Parcelamento previdenciário dos entes e registro de ativos financeiros",
     "Dispõe sobre o parcelamento de débitos com a Fazenda Nacional relativos às "
     "contribuições previdenciárias de responsabilidade dos Estados, do Distrito Federal "
     "e dos Municípios, e sobre o registro e o depósito centralizado de ativos "
     "financeiros."),

    # =================================================================
    # Lote 17 (onda de expansão) — saúde, educação, ambiente, energia, agrário
    # e comunicação. Ficam de fora as que só alteram (14.454, 9.131, 10.267).
    # =================================================================
    # ------------------------------------ saúde
    ("transplantes_9434_1997", "lei", "9434", date(1997, 2, 4), "Lei de Transplantes",
     "Dispõe sobre a remoção de órgãos, tecidos e partes do corpo humano para fins de "
     "transplante e tratamento."),
    ("propagandafumo_9294_1996", "lei", "9294", date(1996, 7, 15),
     "Propaganda de fumo, bebidas e medicamentos",
     "Dispõe sobre as restrições ao uso e à propaganda de produtos fumígeros, bebidas "
     "alcoólicas, medicamentos, terapias e defensivos agrícolas."),
    ("comerciofarmaceutico_5991_1973", "lei", "5991", date(1973, 12, 17),
     "Comércio farmacêutico",
     "Dispõe sobre o controle sanitário do comércio de drogas, medicamentos, insumos "
     "farmacêuticos e correlatos."),
    ("sangue_10205_2001", "lei", "10205", date(2001, 3, 21), "Política Nacional de Sangue",
     "Regulamenta o § 4º do art. 199 da Constituição Federal, relativo à coleta, "
     "processamento, estocagem, distribuição e aplicação do sangue, seus componentes e "
     "derivados."),
    ("vigilanciaepidemiologica_6259_1975", "lei", "6259", date(1975, 10, 30),
     "Vigilância epidemiológica e PNI",
     "Dispõe sobre a organização das ações de Vigilância Epidemiológica, sobre o "
     "Programa Nacional de Imunizações e sobre a notificação compulsória de doenças."),
    # ------------------------------------ educação
    ("institutosfederais_11892_2008", "lei", "11892", date(2008, 12, 29),
     "Rede Federal e Institutos Federais",
     "Institui a Rede Federal de Educação Profissional, Científica e Tecnológica e cria "
     "os Institutos Federais de Educação, Ciência e Tecnologia."),
    ("pisomagisterio_11738_2008", "lei", "11738", date(2008, 7, 16),
     "Piso salarial do magistério",
     "Institui o piso salarial profissional nacional para os profissionais do magistério "
     "público da educação básica."),
    ("pnae_11947_2009", "lei", "11947", date(2009, 6, 16), "PNAE e PDDE",
     "Dispõe sobre o atendimento da alimentação escolar e do Programa Dinheiro Direto na "
     "Escola aos alunos da educação básica."),
    ("salarioeducacao_9766_1998", "lei", "9766", date(1998, 12, 18), "Salário-educação",
     "Altera a legislação que rege o salário-educação."),
    ("pnate_10880_2004", "lei", "10880", date(2004, 6, 9), "PNATE",
     "Institui o Programa Nacional de Apoio ao Transporte do Escolar - PNATE e o Programa "
     "de Apoio aos Sistemas de Ensino para Atendimento à Educação de Jovens e Adultos."),
    ("psicologiaescolas_13935_2019", "lei", "13935", date(2019, 12, 11),
     "Psicologia e serviço social nas escolas",
     "Dispõe sobre a prestação de serviços de psicologia e de serviço social nas redes "
     "públicas de educação básica."),
    ("royaltieseducacao_12858_2013", "lei", "12858", date(2013, 9, 9),
     "Royalties do petróleo para educação e saúde",
     "Dispõe sobre a destinação para as áreas de educação e saúde de parcela da "
     "participação no resultado ou da compensação financeira pela exploração de petróleo "
     "e gás natural."),
    # ------------------------------------ ambiente
    ("fauna_5197_1967", "lei", "5197", date(1967, 1, 3), "Proteção à fauna",
     "Dispõe sobre a proteção à fauna."),
    ("ibama_7735_1989", "lei", "7735", date(1989, 2, 22), "Ibama",
     "Cria o Instituto Brasileiro do Meio Ambiente e dos Recursos Naturais Renováveis."),
    ("icmbio_11516_2007", "lei", "11516", date(2007, 8, 28), "ICMBio",
     "Dispõe sobre a criação do Instituto Chico Mendes de Conservação da Biodiversidade."),
    ("infoambiental_10650_2003", "lei", "10650", date(2003, 4, 16),
     "Acesso à informação ambiental",
     "Dispõe sobre o acesso público aos dados e informações existentes nos órgãos e "
     "entidades integrantes do Sisnama."),
    ("zoneamentoindustrial_6803_1980", "lei", "6803", date(1980, 7, 2),
     "Zoneamento industrial",
     "Dispõe sobre as diretrizes básicas para o zoneamento industrial nas áreas críticas "
     "de poluição."),
    ("cetaceos_7643_1987", "lei", "7643", date(1987, 12, 18), "Proteção aos cetáceos",
     "Proíbe a pesca de cetáceo nas águas jurisdicionais brasileiras."),
    ("bolsaverde_12512_2011", "lei", "12512", date(2011, 10, 14),
     "Bolsa Verde e Fomento Rural",
     "Institui o Programa de Apoio à Conservação Ambiental e o Programa de Fomento às "
     "Atividades Produtivas Rurais."),
    # ------------------------------------ energia e clima
    ("mercadocarbono_15042_2024", "lei", "15042", date(2024, 12, 11),
     "Mercado de carbono — SBCE",
     "Institui o Sistema Brasileiro de Comércio de Emissões de Gases de Efeito Estufa "
     "(SBCE)."),
    ("combustiveldofuturo_14993_2024", "lei", "14993", date(2024, 10, 8),
     "Combustível do Futuro",
     "Dispõe sobre a promoção da mobilidade sustentável de baixo carbono e a captura e a "
     "estocagem geológica de dióxido de carbono; institui o ProBioQAV, o PNDBio e o "
     "Programa Nacional de Descarbonização do Produtor e Importador de Gás Natural."),
    ("offshore_15097_2025", "lei", "15097", date(2025, 1, 10),
     "Energia offshore",
     "Disciplina o aproveitamento de potencial energético offshore."),
    ("eletrobras_14182_2021", "lei", "14182", date(2021, 7, 12),
     "Desestatização da Eletrobras",
     "Dispõe sobre a desestatização da empresa Centrais Elétricas Brasileiras S.A. "
     "(Eletrobras)."),
    ("epe_10847_2004", "lei", "10847", date(2004, 3, 15), "EPE",
     "Autoriza a criação da Empresa de Pesquisa Energética - EPE."),
    ("concessoeseletricas_12783_2013", "lei", "12783", date(2013, 1, 11),
     "Renovação das concessões de energia elétrica",
     "Dispõe sobre as concessões de geração, transmissão e distribuição de energia "
     "elétrica, sobre a redução dos encargos setoriais e sobre a modicidade tarifária."),
    # ------------------------------------ agrário
    ("terrasestrangeiros_5709_1971", "lei", "5709", date(1971, 10, 7),
     "Aquisição de imóvel rural por estrangeiro",
     "Regula a aquisição de imóvel rural por estrangeiro residente no País ou pessoa "
     "jurídica estrangeira autorizada a funcionar no Brasil."),
    ("terralegal_11952_2009", "lei", "11952", date(2009, 6, 25),
     "Regularização fundiária na Amazônia Legal",
     "Dispõe sobre a regularização fundiária das ocupações incidentes em terras situadas "
     "em áreas da União, no âmbito da Amazônia Legal."),
    ("creditoruralinst_4829_1965", "lei", "4829", date(1965, 11, 5),
     "Institucionalização do crédito rural",
     "Institucionaliza o crédito rural."),
    ("subvencaorural_8427_1992", "lei", "8427", date(1992, 5, 27),
     "Subvenção econômica no crédito rural",
     "Dispõe sobre a concessão de subvenção econômica nas operações de crédito rural."),
    ("cultivares_9456_1997", "lei", "9456", date(1997, 4, 25), "Proteção de Cultivares",
     "Institui a Lei de Proteção de Cultivares."),
    ("organicos_10831_2003", "lei", "10831", date(2003, 12, 23), "Agricultura orgânica",
     "Dispõe sobre a agricultura orgânica."),
    ("armazenagem_9973_2000", "lei", "9973", date(2000, 5, 29),
     "Armazenagem de produtos agropecuários",
     "Dispõe sobre o sistema de armazenagem dos produtos agropecuários."),
    ("dividasrurais_10696_2003", "lei", "10696", date(2003, 7, 2),
     "Repactuação de dívidas rurais",
     "Dispõe sobre a repactuação e o alongamento de dívidas oriundas de operações de "
     "crédito rural (o art. 19, que instituía o PAA, foi revogado pela Lei nº 14.628, "
     "de 2023)."),
    ("paa_14628_2023", "lei", "14628", date(2023, 7, 20),
     "PAA — Programa de Aquisição de Alimentos",
     "Institui o Programa de Aquisição de Alimentos (PAA) e o Programa Cozinha "
     "Solidária."),
    # ------------------------------------ comunicação e apostas
    ("radiocomunitaria_9612_1998", "lei", "9612", date(1998, 2, 19),
     "Radiodifusão comunitária",
     "Institui o Serviço de Radiodifusão Comunitária."),
    ("ebc_11652_2008", "lei", "11652", date(2008, 4, 7), "Radiodifusão pública e EBC",
     "Institui os princípios e objetivos dos serviços de radiodifusão pública e autoriza "
     "o Poder Executivo a constituir a Empresa Brasil de Comunicação - EBC."),
    ("direitoderesposta_13188_2015", "lei", "13188", date(2015, 11, 11),
     "Direito de resposta",
     "Dispõe sobre o direito de resposta ou retificação do ofendido em matéria "
     "divulgada, publicada ou transmitida por veículo de comunicação social."),
    ("apostas_14790_2023", "lei", "14790", date(2023, 12, 29), "Apostas de quota fixa",
     "Dispõe sobre a modalidade lotérica denominada apostas de quota fixa."),
]

# Espécie do URN → tipo do corpus (vocabulário próprio, que alimenta o filtro
# ``tipo_norma`` da busca): "decreto.lei" é espécie, não tipo.
_TIPO_CORPUS = {"lei": "lei", "decreto.lei": "lei"}

# Códigos que entram pelo lote 2 — quem filtra por ``tipo_norma="codigo"``
# espera encontrá-los junto com o Penal e o Civil, que vêm do registro curado.
_CODIGOS = {
    "cpm_1001_1969", "cppm_1002_1969", "cba_7565_1986", "cbt_4117_1962",
    "codigomineracao_227_1967",
}


def tipo_corpus(slug: str, especie: str) -> str:
    return "codigo" if slug in _CODIGOS else _TIPO_CORPUS[especie]


def resolver(especie: str, numero: str, d: date) -> tuple[str, int, str]:
    """Primeira URL que baixa e parseia com dispositivos plausíveis."""
    # Todos os motivos, não só o da última variante: a lista termina em 404
    # (variantes que não existem), e guardar só o último mascarava o diagnóstico
    # de verdade — foi o que escondeu o "parse magro" da Lei 6.899, que na
    # realidade baixava bem e caía no parser.
    erros: list[str] = []
    for url in variantes_url(especie, numero, d.year):
        try:
            html = fetch(url)
            disp = parse_dispositivos(html)
            # Piso em 2: página errada (404, índice) parseia com 0 ou 1, mas há
            # lei legítima de dois artigos — o de conteúdo e o de vigência
            # (Lei 12.506/2011, aviso prévio; Lei 10.446/2002, atribuição da PF).
            if len(disp) < 2:
                erros.append(f"parse magro ({len(disp)} disp) em {url.replace(BASE, '')}")
                continue
            return url, len(disp), conferir_data(html, numero, d)
        except Exception as exc:
            erros.append(type(exc).__name__)
        finally:
            time.sleep(settings.http_polite_delay)  # coleta educada
    raise RuntimeError("; ".join(dict.fromkeys(erros)) or "sem variante")


def _urls_resolvidas() -> dict[str, str]:
    """URN → URL canônica já resolvida numa rodada anterior.

    Só a URL é reaproveitada: o resto dos metadados é sempre reconstruído a
    partir de ``CANDIDATAS``, para que corrigir uma ementa ou um apelido não
    exija rebaixar o corpus. A data não precisa de nova conferência porque ela
    compõe o URN — mudou a data, mudou a chave, e a norma volta para a fila.
    """
    if not REGISTRO_ORDINARIAS_PATH.exists():
        return {}
    return {
        e["urn_lex"]: e["url_canonica"]
        for e in json.loads(REGISTRO_ORDINARIAS_PATH.read_text("utf-8"))
    }


def _conferir_unicidade() -> None:
    """Barra norma repetida na lista curada, sob slug diferente.

    A lista cresce por lotes e passa de trezentas entradas: no lote 5 a Lei
    14.600/2023 foi reincluída como ``orgpresidencia_...`` sem que ninguém
    notasse que ela já estava como ``presidencia_...``. O JSON aceitou as duas —
    mesmo URN, slugs distintos —, e o índice teria a mesma lei duas vezes,
    dobrando os pontos e as ocorrências na busca. O URN é a chave do corpus, e
    é por ele que a repetição se detecta.
    """
    urns = [f"urn:lex:br:federal:{esp}:{d.isoformat()};{num}"
            for _, esp, num, d, _, _ in CANDIDATAS]
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
        help="rebaixa tudo do zero, em vez de reaproveitar o que já está no JSON "
             "(use quando o Planalto puder ter publicado um consolidado novo).",
    )
    args = ap.parse_args()

    _conferir_unicidade()
    urns_curadas = {m.urn_lex for m in REGISTRO_CURADO.values()}
    conhecidas = {} if args.revalidar else _urls_resolvidas()
    validadas, falhas, divergentes = [], [], []
    n_reaproveitadas = 0

    for i, (slug, especie, numero, d, apelido, ementa) in enumerate(CANDIDATAS, 1):
        urn = f"urn:lex:br:federal:{especie}:{d.isoformat()};{numero}"
        if urn in urns_curadas:
            print(f"[{i:3}/{len(CANDIDATAS)}] {slug:32} ja no registro curado")
            continue
        if urn in conhecidas:
            # URL já resolvida numa rodada anterior: sai da fila de download,
            # para que um lote novo custe só as normas novas.
            url, n_reaproveitadas = conhecidas[urn], n_reaproveitadas + 1
        else:
            try:
                url, n_disp, confere = resolver(especie, numero, d)
            except Exception as exc:
                falhas.append(slug)
                print(f"[{i:3}/{len(CANDIDATAS)}] {slug:32} FALHOU: {exc}")
                continue
            if confere.startswith("DIVERGE"):
                # data errada = URN errado, e o URN é a chave do corpus: não entra.
                divergentes.append(f"{slug} {confere}")
                print(f"[{i:3}/{len(CANDIDATAS)}] {slug:32} REJEITADA: {confere}")
                continue
            print(f"[{i:3}/{len(CANDIDATAS)}] {slug:32} ok ({n_disp} disp, {confere}) "
                  f"{url.replace(BASE, '')}")
        validadas.append({
            "slug": slug,
            "urn_lex": urn,
            "tipo": tipo_corpus(slug, especie),
            "numero": numero,
            "data": d.isoformat(),
            "epigrafe": epigrafe(especie, numero, d, apelido),
            "ementa": ementa,
            "url_canonica": url,
        })

    validadas.sort(key=lambda e: (e["data"], int(e["numero"])))
    REGISTRO_ORDINARIAS_PATH.write_text(
        json.dumps(validadas, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"\n[ordinarias] {len(validadas)} validadas ({n_reaproveitadas} com URL reaproveitada "
          f"do JSON anterior) -> {REGISTRO_ORDINARIAS_PATH}")
    if divergentes:
        print(f"[ordinarias] rejeitadas por data divergente: {'; '.join(divergentes)}")
    if falhas:
        print(f"[ordinarias] falhas ({len(falhas)}): {', '.join(falhas)}")
    return 1 if falhas or divergentes else 0


if __name__ == "__main__":
    sys.exit(main())
