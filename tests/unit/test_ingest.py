"""Testes do parser do Planalto, detecção de revogação e registro de normas."""

from __future__ import annotations

from pathlib import Path

from lex_rag.ingest.html_parser import parse_dispositivos, parse_norma, recortar
from lex_rag.ingest.revocation_detector import detectar_revogacao
from lex_rag.ingest.urn_mapper import REGISTRO

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="latin-1")


def test_lcp95_articles_sem_duplicatas():
    ds = parse_dispositivos(_html("lcp_95_1998.html"))
    paths = [d.path for d in ds]
    assert len(paths) == len(set(paths)), "não deve haver dispositivos duplicados"
    assert not any("__" in p for p in paths), "redação superada (tachada) não deve virar artigo"
    for n in range(1, 20):
        assert f"art_{n}" in paths, f"faltou art_{n}"
    assert "art_18_A" in paths


def test_lcp95_caput_inlina_subitens():
    ds = {d.path: d for d in parse_dispositivos(_html("lcp_95_1998.html"))}
    assert "Parágrafo único" in ds["art_1"].texto
    # art 3 traz os incisos I, II, III inlinados no caput
    assert "I -" in ds["art_3"].texto and "III -" in ds["art_3"].texto


def test_lcp95_texto_tachado_removido():
    ds = {d.path: d for d in parse_dispositivos(_html("lcp_95_1998.html"))}
    # art. 9º vigente = redação dada pela LCP 107/2001
    assert "enumerar" in ds["art_9"].texto
    assert "Quando necessária" not in ds["art_9"].texto


def test_lcp95_parent_label_hierarquia():
    ds = {d.path: d for d in parse_dispositivos(_html("lcp_95_1998.html"))}
    assert "CAPÍTULO" in ds["art_1"].parent_label.upper()


def test_cf_art37_administracao():
    ds = {d.path: d for d in parse_dispositivos(_html("cf_1988.html"))}
    assert "art_37" in ds
    assert "administração pública" in ds["art_37"].texto.lower()


def test_lei8666_revogada():
    # Lei 8.666 foi integralmente revogada pela Lei 14.133/2021 (texto tachado).
    ds = {d.path: d for d in parse_dispositivos(_html("lei_8666_1993.html"))}
    assert "art_1" in ds and "art_126" in ds
    assert ds["art_1"].vigente is False


def test_cc_milhar():
    # O Código Civil numera artigos com milhar ("Art. 2.046").
    ds = {d.path: d for d in parse_dispositivos(_html("cc_10406_2002.html"))}
    assert "art_1228" in ds
    assert "art_2046" in ds


def test_art_traco_de_caput_nao_vira_sufixo():
    # Formato antigo (CP, CLT): "Art. N - Texto" — o traço separa o caput.
    ds = {d.path: d for d in parse_dispositivos("<p>Art. 312 - Apropriar-se o funcionário.</p>")}
    assert list(ds) == ["art_312"]
    assert ds["art_312"].label == "Art. 312"
    assert ds["art_312"].texto.startswith("Apropriar-se")


def test_art_caput_iniciando_com_artigo_definido():
    # "A"/"O" maiúsculo após o traço é início de caput, não sufixo ("Art. 100-A").
    ds = {d.path: d for d in parse_dispositivos("<p>Art. 100 - A ação penal é pública.</p>")}
    assert list(ds) == ["art_100"]
    assert ds["art_100"].texto == "A ação penal é pública"


def test_art_sufixo_colado():
    ds = {d.path: d for d in parse_dispositivos("<p>Art. 121-A. Matar mulher por razões.</p>")}
    assert list(ds) == ["art_121_A"]
    assert ds["art_121_A"].label == "Art. 121-A"
    assert ds["art_121_A"].texto.startswith("Matar")


def test_art_sufixo_espacado_vetado():
    # Grafia da LCP 95: "Art. 18 - A (VETADO)" é o art. 18-A, vetado.
    ds = {d.path: d for d in parse_dispositivos("<p>Art. 18 - A (VETADO)</p>")}
    assert list(ds) == ["art_18_A"]
    assert "VETADO" in ds["art_18_A"].texto


def test_comentario_html_nao_gera_artigo_fantasma():
    html = "<p>Art. 1º Texto real.</p><!-- Art. 99 - Rascunho comentado --><p>Art. 2º Outro.</p>"
    ds = {d.path: d for d in parse_dispositivos(html)}
    assert set(ds) == {"art_1", "art_2"}
    assert ds["art_1"].texto == "Texto real"


def test_detectar_revogacao():
    vig, marca = detectar_revogacao("(Revogado pela Lei nº 14.133, de 2021)")
    assert vig is False and marca is not None and "14.133" in marca

    vig_ok, marca_ok = detectar_revogacao("Texto normal e vigente.")
    assert vig_ok is True and marca_ok is None

    # "Vide" indica remissão, não revogação
    vig_vide, _ = detectar_revogacao("(Vide Decreto nº 1.000, de 2020)")
    assert vig_vide is True

    # Marca no meio do texto = revogação parcial (parágrafo/inciso inlinado);
    # o caput continua vigente.
    vig_parcial, marca_parcial = detectar_revogacao(
        "O regime próprio de previdência. § 4º (Revogado pela EC nº 103, de 2019)"
    )
    assert vig_parcial is True and marca_parcial is None


def test_revogacao_parcial_nao_derruba_caput():
    # § revogado inlinado no chunk do artigo não marca o artigo como revogado.
    html = (
        "<p>Art. 40. O regime próprio de previdência social.</p>"
        "<p>§ 4º (Revogado pela Emenda Constitucional nº 103, de 2019)</p>"
    )
    ds = {d.path: d for d in parse_dispositivos(html)}
    assert ds["art_40"].vigente is True
    assert ds["art_40"].revogado_por is None


def test_cf_art40_vigente_apesar_de_paragrafo_revogado():
    # CF art. 40 tem §§ revogados pela EC 103/2019, mas o caput está vigente.
    ds = {d.path: d for d in parse_dispositivos(_html("cf_1988.html"))}
    assert ds["art_40"].vigente is True


def test_tachado_por_css_inline():
    # O Planalto também tacha por CSS (Lei 8.666 art. 3º), não só por <strike>.
    html = (
        '<p><span style="color: black; text-decoration:line-through">'
        "Art. 3º A licitação destina-se a garantir a isonomia.</span></p>"
    )
    ds = {d.path: d for d in parse_dispositivos(html)}
    assert ds["art_3"].vigente is False


def test_artigo_com_ponto_separado_por_tags():
    # LCP 36/1979 quebra "Art" e ". 1º" em <font> distintos; o achatamento
    # insere espaço entre os nós e o marcador precisa aceitar "Art . 1º".
    html = (
        '<p><span class="T1"><font size="2"><a name="art1"></a>Art</font></span>'
        '<font size="2">. 1º - Ao funcionário público federal poderá ser '
        "concedida aposentadoria com proventos proporcionais.</font></p>"
    )
    ds = {d.path: d for d in parse_dispositivos(html)}
    assert "art_1" in ds
    assert ds["art_1"].label == "Art. 1º"
    assert ds["art_1"].texto.startswith("Ao funcionário público federal")


def test_ordinal_separado_nao_vaza_para_o_caput():
    # A LINDB grafa "Art. 1<sup>o</sup>"; achatado vira "Art. 1 o" e, sem
    # consumir o indicador, o "o" virava a primeira letra do caput.
    html = (
        '<p><a name="art1"></a>Art. 1<sup>o</sup> Salvo disposição contrária, '
        "a lei começa a vigorar em todo o país quarenta e cinco dias depois "
        "de oficialmente publicada.</p>"
    )
    ds = {d.path: d for d in parse_dispositivos(html)}
    assert ds["art_1"].label == "Art. 1º"
    assert ds["art_1"].texto.startswith("Salvo disposição contrária")


def test_ordinal_com_ponto_antes():
    # LCs dos anos 1970 grafam "Art. 2.º - ..."
    html = '<p><a name="art2"></a>Art. 2.º - As empresas produtoras de discos.</p>'
    ds = {d.path: d for d in parse_dispositivos(html)}
    assert ds["art_2"].label == "Art. 2º"
    assert ds["art_2"].texto.startswith("As empresas produtoras")


def test_o_minusculo_de_palavra_nao_e_confundido_com_ordinal():
    # "os prazos": consumir o "o" mutilaria a palavra seguinte.
    ds = {d.path: d for d in parse_dispositivos("<p>Art. 12 os prazos serão contados.</p>")}
    assert ds["art_12"].texto.startswith("os prazos")
    # Lei 8.080 art. 46: a própria fonte grafa o artigo "o" em minúscula depois
    # do ponto — é palavra do texto, não indicador de ordinal, e deve sobreviver.
    ds = {d.path: d for d in parse_dispositivos("<p>Art. 46. o Sistema Único de Saúde.</p>")}
    assert ds["art_46"].texto.startswith("o Sistema Único")


def test_artigo_sem_ponto_no_marcador():
    # As leis dos anos 1940-1980 grafam "Art 1º - ..." sem ponto nenhum; a Lei
    # 6.899/1981 é assim do primeiro ao último artigo e saía com ZERO
    # dispositivos, e a grafia também aparece solta em normas grandes
    # (CLT art. 554, CP art. 187, CC art. 1.636, CTB art. 67-B).
    html = (
        "<p>Art 1º - A correção monetária incide sobre qualquer débito.</p>"
        "<p>Art 554. Destituida a administração na hipótese da alínea c.</p>"
        "<p>Art 1.636. O pai ou a mãe que contrai novas núpcias.</p>"
        "<p>Art 67-B. Trata da jornada do motorista profissional.</p>"
    )
    ds = {d.path: d for d in parse_dispositivos(html)}
    assert ds["art_1"].texto.startswith("A correção monetária")
    assert ds["art_554"].texto.startswith("Destituida a administração")
    assert ds["art_1636"].label == "Art. 1.636" or ds["art_1636"].label == "Art. 1636"
    assert ds["art_67_B"].texto.startswith("Trata da jornada")
    # "Art" grudado no fim de outra palavra não é marcador
    assert not parse_dispositivos("<p>O SmartArt 3 do relatório.</p>")


def test_veto_nao_rouba_o_path_da_redacao_real():
    # O Planalto imprime a marca de veto e, na sequência, a redação de verdade
    # do mesmo artigo (CDC art. 15, PNMA art. 19, PIS art. 33). Sem tratar, o
    # placeholder ficava com "art_19" e o texto real ia para "art_19__1".
    html = (
        "<p>Art 19 - (VETADO).</p>"
        "<p>Art. 19. Ressalvado o disposto nas Leis nºs 5.357 e 6.803.</p>"
    )
    ds = {d.path: d for d in parse_dispositivos(html)}
    assert ds["art_19"].texto.startswith("Ressalvado o disposto")
    assert "art_19__1" not in ds

    # Artigo vetado por inteiro não tem concorrente e permanece no índice
    # (é o caso do art. 18-A da LCP 95, coberto acima).
    so_veto = parse_dispositivos("<p>Art. 7º (VETADO).</p><p>Art. 8º Texto real.</p>")
    assert {d.path for d in so_veto} == {"art_7", "art_8"}

    # Dois placeholders concorrentes: nenhum é descartado (nada a preservar).
    dois = parse_dispositivos("<p>Art. 15 (VETADO)</p><p>Art. 15. ...........</p>")
    assert len(dois) == 2


def test_artigo_citado_em_bloco_alterador_nao_entra_no_corpus():
    # "A Lei X passa a vigorar com a seguinte redação: “Art. 14. ...”" — o art. 14
    # é de OUTRA lei. Indexá-lo aqui atribuiria à norma um dispositivo que não é
    # dela; o texto citado continua no caput do artigo alterador.
    html = (
        "<p>Art. 91. A Lei nº 6.015, de 1973, passa a vigorar com a seguinte "
        "redação: &ldquo;Art. 14. O oficial cobrará os emolumentos devidos.&rdquo; (NR)</p>"
        "<p>Art. 92. Esta Lei entra em vigor na data de sua publicação.</p>"
    )
    ds = {d.path: d for d in parse_dispositivos(html)}
    assert set(ds) == {"art_91", "art_92"}
    assert "Art. 14" in ds["art_91"].texto  # o texto citado não se perde

    # Aspa ASCII: só conta como abertura depois de ":" ou do ")" do "(NR)".
    ascii_ = parse_dispositivos(
        '<p>Art. 3º A Lei nº 8.137 passa a ter a seguinte redação: "Art. 316. Exigir '
        'vantagem indevida." (NR)</p>'
    )
    assert {d.path for d in ascii_} == {"art_3"}

    # Depois da aspa de FECHAMENTO vem artigo de verdade — não pode sumir.
    fecha = parse_dispositivos(
        "<p>Art. 78. A Lei nº 10.257 passa a vigorar acrescida do seguinte artigo: "
        "&ldquo;Art. 34-A. Nas regiões metropolitanas.&rdquo; Art. 79. Fica revogado o "
        "art. 5º da Lei nº 6.766.</p>"
    )
    assert {d.path for d in fecha} == {"art_78", "art_79"}


def test_lexml_extrair_urns():
    from lex_rag.ingest.lexml_sru import extrair_urns

    xml = (
        "<resp><rec><urn>urn:lex:br:federal:lei:2021-04-01;14133</urn></rec>"
        " texto urn:lex:br:federal:lei:1993-06-21;8666. "
        " dup urn:lex:br:federal:lei:2021-04-01;14133 </resp>"
    )
    urns = extrair_urns(xml)
    assert "urn:lex:br:federal:lei:2021-04-01;14133" in urns
    assert "urn:lex:br:federal:lei:1993-06-21;8666" in urns
    assert len(urns) == len(set(urns))  # sem duplicatas


def test_parse_norma_metadados():
    meta = REGISTRO["lcp_95_1998"]
    norma = parse_norma(meta, _html("lcp_95_1998.html"))
    assert norma.urn_lex == meta.urn_lex
    assert norma.epigrafe == meta.epigrafe
    assert norma.tipo == "lei_complementar"
    assert len(norma.dispositivos) >= 19


def test_referencia_a_artigo_nao_abre_dispositivo():
    """Citação de artigo no meio do texto não pode virar dispositivo (lote 6).

    Nos anexos da LDO o título cita a LRF — "(Art. 4º, § 1º, da Lei Complementar
    nº 101...)" — e o Anexo de Riscos Fiscais cita processos. Cada citação abria
    um falso "Art. 4º" que engolia o anexo seguinte e o servia como texto DA LDO.
    """
    d = parse_dispositivos(
        "<p>Art. 4º Para efeito desta Lei, entende-se por subtítulo o menor nível.</p>"
        "<p>ANEXO IV - METAS FISCAIS (Art. 4º, § 1º, da Lei Complementar nº 101, de 4 de "
        "maio de 2000) A Lei Complementar estabelece que integrará o projeto.</p>"
    )
    # O anexo entra como dispositivo próprio (lote 11), sem roubar o art. 4º.
    assert [x.path for x in d] == ["art_4", "anexo_iv"]
    assert d[0].texto.startswith("Para efeito desta Lei")
    assert d[1].texto.startswith("METAS FISCAIS")

    # "art. 3º da Portaria AGU nº 40/2015" — preposição também denuncia citação.
    prep = parse_dispositivos(
        "<p>Art. 3º São riscos fiscais os passivos contingentes.</p>"
        "<p>Ação ajuizada na forma do art. 3º da Portaria AGU nº 40/2015, em razão dos "
        "valores envolvidos.</p>"
    )
    assert [x.path for x in prep] == ["art_3"]

    # O trecho descartado como fronteira fica colado ao dispositivo anterior, e
    # não se perde: era assim que o art. 72 do ADCT saía truncado em "art. 22".
    inteiro = parse_dispositivos(
        "<p>Art. 72. Integram o Fundo Social de Emergência: I - o produto da arrecadação "
        "prevista no art. 22 da Lei nº 8.212, a qual será recolhida ao Tesouro.</p>"
    )
    assert [x.path for x in inteiro] == ["art_72"]
    assert "recolhida ao Tesouro" in inteiro[0].texto

    # Conjunção: "art. 35 e seu parágrafo único" — sem o guarda a Lei 6.360
    # servia o art. 35 truncado em "dispostos no", sem o objeto da frase.
    conj = parse_dispositivos(
        "<p>Art. 34. As associações de inseticidas deverão satisfazer aos requisitos "
        "dispostos no Art. 35 e seu parágrafo único, quanto à toxicidade.</p>"
    )
    assert [x.path for x in conj] == ["art_34"]
    assert conj[0].texto.endswith("quanto à toxicidade")

    # Pronome demonstrativo (lote 15): "art. 1º desta Lei" abria falso art. 1º.
    dem = parse_dispositivos(
        "<p>Art. 1º O adiantamento será pago entre fevereiro e novembro.</p>"
        "<p>Art. 2º Na hipótese do Art. 1º desta Lei, o empregador poderá compensar o "
        "adiantamento; aplica-se o art. 3º deste Decreto e o disposto no art. 4º nesta "
        "Lei.</p>"
    )
    assert [x.path for x in dem] == ["art_1", "art_2"]
    assert dem[1].texto.endswith("nesta Lei")


def test_fecho_encerra_o_texto_articulado():
    """Depois do fecho vêm assinaturas e anexos — não são texto do artigo (lote 6)."""
    d = parse_dispositivos(
        "<p>Art. 10. Esta Lei entra em vigor na data de sua publicação. Brasília, 21 de "
        "janeiro de 2022; 201º da Independência e 134º da República. JAIR MESSIAS "
        "BOLSONARO Paulo Guedes Este texto não substitui o publicado no DOU de 24.1.2022 "
        "ANEXO V AUTORIZAÇÕES ESPECÍFICAS 27 812 5026 00SL 0001 Apoio à Implantação.</p>"
    )
    assert [x.path for x in d] == ["art_10", "anexo_v"]  # o anexo é dispositivo próprio
    assert d[0].texto == (
        "Esta Lei entra em vigor na data de sua publicação. Brasília, 21 de janeiro de "
        "2022; 201º da Independência"
    )
    assert d[1].texto.startswith("AUTORIZAÇÕES ESPECÍFICAS")

    # Sem fecho, nada é truncado.
    sem = parse_dispositivos("<p>Art. 1º Esta Lei dispõe sobre o que especifica.</p>")
    assert sem[0].texto == "Esta Lei dispõe sobre o que especifica"


def test_recorte_isola_o_documento_na_pagina_com_varios():
    """A página da Câmara traz três documentos; o recorte fica só com o Regimento."""
    html = (
        "<p>Art. 1º O Regimento Interno passa a vigorar na conformidade do texto anexo.</p>"
        "<p><b>REGIMENTO INTERNO DA CÂMARA DOS DEPUTADOS</b></p>"
        "<p>Art. 1º A Câmara dos Deputados funciona no Palácio do Congresso Nacional.</p>"
        "<p><b>RESOLUÇÃO Nº 25, DE 2001</b></p>"
        "<p>Art. 1º O Código de Ética é instituído na conformidade do texto anexo.</p>"
    )
    recorte = (
        "<b>REGIMENTO INTERNO DA CÂMARA DOS DEPUTADOS</b>",
        "<b>RESOLUÇÃO Nº 25, DE 2001</b>",
    )
    ds = parse_dispositivos(recortar(html, recorte))
    assert [d.path for d in ds] == ["art_1"], "só o artigo do Regimento deve sobrar"
    assert ds[0].texto.startswith("A Câmara dos Deputados funciona")


def test_recorte_tolera_quebra_de_linha_no_marcador():
    """O HTML da Câmara quebra a linha no meio do título; o marcador segue casando."""
    html = "<p>Art. 1º Vale.</p><p><b>RESOLUÇÃO\nNº 25, DE 2001</b></p><p>Art. 1º Não vale.</p>"
    recortado = recortar(html, ("", "<b>RESOLUÇÃO Nº 25, DE 2001</b>"))
    assert "Não vale" not in recortado
    assert [d.texto for d in parse_dispositivos(recortado)] == ["Vale"]


def test_recorte_com_marcador_ausente_falha_em_vez_de_parsear_tudo():
    """Página que mudou de forma tem de abortar, não voltar a misturar documentos."""
    import pytest

    with pytest.raises(ValueError):
        recortar("<p>Art. 1º Texto.</p>", ("<b>MARCADOR QUE NÃO EXISTE</b>", ""))


def test_registro_tem_os_dois_regimentos_internos():
    for slug in ("risf_93_1970", "ricd_17_1989"):
        meta = REGISTRO[slug]
        assert meta.tipo == "regimento"
        assert meta.recorte is not None
        assert meta.urn_lex.startswith("urn:lex:br:")
        assert "planalto.gov.br" not in meta.url_canonica


def test_resolucoes_das_casas_vem_do_parlamento_com_recorte():
    """Lote 21: fonte da Casa, URN pela autoridade da Casa e recorte obrigatório."""
    from lex_rag.ingest.parlamento_fetcher import TIPOS_PARLAMENTO

    das_casas = {s: m for s, m in REGISTRO.items() if m.tipo in ("regimento", "resolucao")}
    assert {"rcn_1_1970", "rsf_40_2001", "rcd_25_2001", "rsf_20_1993"} <= das_casas.keys()
    for meta in das_casas.values():
        assert meta.tipo in TIPOS_PARLAMENTO
        assert meta.recorte is not None and any(meta.recorte)
        assert "planalto.gov.br" not in meta.url_canonica
    assert REGISTRO["rsf_40_2001"].urn_lex == "urn:lex:br:senado.federal:resolucao:2001-12-20;40"
    assert REGISTRO["rcn_1_1970"].urn_lex == "urn:lex:br:congresso.nacional:resolucao:1970-08-11;1"
    assert REGISTRO["rsf_40_2001"].epigrafe.startswith(
        "Resolução do Senado Federal nº 40, de 20 de dezembro de 2001"
    )
    # O Código de Ética da Câmara é o terceiro documento da página do RICD.
    assert REGISTRO["rcd_25_2001"].url_canonica == REGISTRO["ricd_17_1989"].url_canonica


# ------------------------------------------------------------------ anexos (lote 11)


def test_anexo_articulado_ganha_prefixo_e_nao_colide_com_o_corpo():
    """Decreto que aprova o Regulamento anexo: os dois recomeçam em Art. 1º."""
    d = parse_dispositivos(
        "<p>Art. 1º Fica aprovado o Regulamento anexo a este Decreto.</p>"
        "<p>Art. 2º Este Decreto entra em vigor na data de sua publicação.</p>"
        "<p>Brasília, 26 de setembro de 2007; 186º da Independência e 119º da República.</p>"
        "<p>ANEXO</p><p>REGULAMENTO DO BENEFÍCIO</p>"
        "<p>CAPÍTULO I</p><p>DO BENEFÍCIO</p>"
        "<p>Art. 1º O Benefício de Prestação Continuada é a garantia de um salário mínimo.</p>"
        "<p>Art. 2º Compete ao Ministério a gestão do benefício.</p>"
    )
    paths = [x.path for x in d]
    assert paths == ["art_1", "art_2", "anexo_art_1", "anexo_art_2"]
    assert not any("__" in p for p in paths)
    ds = {x.path: x for x in d}
    assert ds["art_1"].texto.startswith("Fica aprovado")
    assert ds["anexo_art_1"].texto.startswith("O Benefício de Prestação Continuada")
    assert ds["anexo_art_1"].label == "Art. 1º"
    assert ds["anexo_art_1"].parent_label.startswith("ANEXO - REGULAMENTO DO BENEFÍCIO")
    assert "CAPÍTULO I" in ds["anexo_art_1"].parent_label
    # o fecho já não engole o anexo: o art. 2º do decreto termina no fecho
    assert ds["art_2"].texto.endswith("da Independência")


def test_anexo_sem_artigo_vira_dispositivo_de_texto():
    d = parse_dispositivos(
        "<p>Art. 89. Esta Lei entra em vigor na data de sua publicação.</p>"
        "<p>Brasília, 14 de dezembro de 2006; 185º da Independência e 118º da República.</p>"
        "<p>ANEXO I DA LEI COMPLEMENTAR Nº 123</p>"
        "<p>Alíquotas e Partilha do Simples Nacional - Comércio</p>"
        "<p>Receita Bruta em 12 Meses Alíquota IRPJ CSLL Cofins</p>"
        "<p>ANEXO II DA LEI COMPLEMENTAR Nº 123</p>"
        "<p>Alíquotas e Partilha do Simples Nacional - Indústria</p>"
    )
    assert [x.path for x in d] == ["art_89", "anexo_i", "anexo_ii"]
    assert d[0].texto.endswith("185º da Independência")
    assert d[1].label == "Anexo I" and d[1].tipo == "anexo"
    assert d[1].texto.startswith("DA LEI COMPLEMENTAR Nº 123 Alíquotas")
    assert "Indústria" not in d[1].texto and "Indústria" in d[2].texto


def test_anexo_grande_sai_em_partes():
    from lex_rag.ingest import html_parser

    texto = " ".join(f"linha {i} da tabela" for i in range(600))  # ~11 KB
    d = parse_dispositivos(f"<p>Art. 1º Vale.</p><p>ANEXO ÚNICO</p><p>{texto}</p>")
    paths = [x.path for x in d]
    assert paths[:2] == ["art_1", "anexo_unico"]
    assert paths[2].startswith("anexo_unico_p2")
    assert all(len(x.texto) <= html_parser._ANEXO_PARTE for x in d[1:])
    assert d[2].label == "Anexo ÚNICO (parte 2)"
    assert "".join(x.texto.replace(" ", "") for x in d[1:]) == texto.replace(" ", "")


def test_tratado_em_anexo_usa_artigo_por_extenso():
    """Decreto promulgador: o texto da Convenção grafa "Artigo N", não "Art."."""
    d = parse_dispositivos(
        "<p>Art. 1º A Convenção apensa por cópia ao presente decreto deverá ser cumprida.</p>"
        "<p>Brasília, 6 de novembro de 1992; 171º da Independência e 104º da República.</p>"
        "<p>ANEXO</p><p>CONVENÇÃO AMERICANA SOBRE DIREITOS HUMANOS</p>"
        "<p>Artigo 1º - Obrigação de respeitar os direitos. Os Estados Partes comprometem-se "
        "a respeitar os direitos, nos termos do artigo 2 e do Artigo 3, § 1º.</p>"
        "<p>ARTIGO 8 Garantias judiciais. Toda pessoa tem direito a ser ouvida.</p>"
        "<p>Artigo XII 1. A presente Convenção será ratificada.</p>"
    )
    paths = [x.path for x in d]
    assert paths == ["art_1", "anexo_art_1", "anexo_art_8", "anexo_art_12"]
    ds = {x.path: x for x in d}
    assert "nos termos do artigo 2 e do Artigo 3" in ds["anexo_art_1"].texto
    assert ds["anexo_art_8"].label == "Art. 8º"
    assert ds["anexo_art_12"].label == "Art. 12"  # romano normalizado


def test_artigo_por_extenso_fora_do_anexo_nao_abre_dispositivo():
    d = parse_dispositivos(
        "<p>Art. 1º Aplica-se o disposto no Artigo 5 da Convenção às partes.</p>"
    )
    assert [x.path for x in d] == ["art_1"]
    assert d[0].texto.endswith("às partes")


def test_anexo_citado_entre_aspas_e_referencia_nao_abrem_anexo():
    d = parse_dispositivos(
        "<p>Art. 1º A Lei passa a vigorar com a seguinte redação: “ANEXO VII Alimentos "
        "destinados ao consumo humano”.</p>"
        "<p>Art. 2º Os produtos relacionados no ANEXO XV ficam isentos.</p>"
    )
    assert [x.path for x in d] == ["art_1", "art_2"]


def test_cf_fixture_recorte_separa_adct_do_corpo():
    """A página da CF traz o ADCT recomeçando em Art. 1º: 128 paths __N medidos."""
    from lex_rag.ingest.urn_mapper import REGISTRO

    html = _html("cf_1988.html")
    corpo = {x.path: x for x in parse_dispositivos(recortar(html, REGISTRO["cf_1988"].recorte))}
    adct = {x.path: x for x in parse_dispositivos(recortar(html, REGISTRO["adct_1988"].recorte))}
    assert not any("__" in p for p in corpo), "o ADCT não pode mais colidir com o corpo"
    assert "maioria absoluta" in corpo["art_97"].texto  # reserva de plenário
    assert "precatório" in adct["art_97"].texto.lower()  # regime especial de pagamento
    assert adct["art_1"].texto.startswith("O Presidente da República, o Presidente do Supremo")
    assert "art_250" in corpo and "art_250" not in adct


def test_sufixo_com_ordinal_em_sup_nao_se_perde():
    """Bug nº 11 (lote 13): "Art. 1<sup>o</sup>-A" achatado vira "Art. 1 o -A"."""
    d = parse_dispositivos(
        "<p>Art. 1<sup>o</sup> Aplica-se à tutela antecipada o disposto nesta Lei.</p>"
        "<p>Art. 1<sup>o</sup>-A. Estão dispensadas de depósito prévio as pessoas "
        "jurídicas de direito público.</p>"
        "<p>Art. 1<sup>o</sup>-F. Nas condenações impostas à Fazenda Pública incidirão "
        "juros de mora.</p>"
        "<p>Art. 100 - A ação penal é pública.</p>"
        "<p>Art. 312 - Apropriar-se o funcionário público de dinheiro.</p>"
    )
    assert [x.path for x in d] == ["art_1", "art_1_A", "art_1_F", "art_100", "art_312"]
    ds = {x.path: x for x in d}
    assert ds["art_1_A"].texto.startswith("Estão dispensadas")
    assert ds["art_1_A"].label == "Art. 1º-A"
    assert ds["art_100"].texto.startswith("A ação penal")  # letra solta não é sufixo


def test_tratado_colado_ao_fecho_abre_anexo_implicito():
    """Metade dos decretos de promulgação serve a Convenção sem cabeçalho ANEXO."""
    d = parse_dispositivos(
        "<p>Art. 1º A Convenção apensa por cópia ao presente Decreto será executada.</p>"
        "<p>Art. 2º Este Decreto entra em vigor na data de sua publicação.</p>"
        "<p>Brasília, 15 de fevereiro de 1991; 170º da Independência e 103º da "
        "República.</p><p>FERNANDO COLLOR</p>"
        "<p>Este texto não substitui o publicado no D.O.U. de 18.2.1991</p>"
        "<p>CONVENÇÃO CONTRA A TORTURA</p><p>PARTE I</p>"
        "<p>Artigo 1º 1. Para os fins da presente Convenção, o termo tortura designa "
        "qualquer ato pelo qual dores são infligidas.</p>"
        "<p>Artigo 2º 1. Cada Estado Parte tomará medidas eficazes, em conformidade com o "
        "Artigo 8º e com o disposto no Artigo 4(1) para todos os direitos.</p>"
    )
    paths = [x.path for x in d]
    assert paths == ["art_1", "art_2", "anexo_art_1", "anexo_art_2"]
    ds = {x.path: x for x in d}
    assert ds["anexo_art_1"].texto.startswith("1. Para os fins")
    assert ds["anexo_art_2"].texto.endswith("para todos os direitos")  # referências coladas
    assert ds["anexo_art_1"].parent_label == "ANEXO"  # o anexo implícito não tem título
    # sem fecho, "Artigo" por extenso segue sendo referência, não marcador
    sem = parse_dispositivos("<p>Art. 1º Vale o Artigo 5 da Convenção.</p>")
    assert [x.path for x in sem] == ["art_1"]

