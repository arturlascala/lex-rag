"""Parser do HTML do Planalto.

As páginas do Planalto têm estruturas heterogêneas: as antigas usam ``<p>``
(FrontPage), as compiladas mais novas espalham o texto em ``<span>``/``<td>``.
Para ser robusto a todos os formatos, o parser trabalha sobre o **fluxo de texto
achatado**: localiza marcadores de artigo (``Art. N``) e de cabeçalho
(LIVRO/TÍTULO/CAPÍTULO/SEÇÃO) por regex e fatia o conteúdo entre marcadores.

Texto tachado (``<strike>``) tem dois significados no Planalto:
  - redação **anterior** de um artigo que segue vigente (há versão não-tachada);
  - artigo **revogado** por inteiro (só existe a versão tachada).
Por isso o parser rastreia quais trechos são tachados: se um número de artigo tem
versão tachada e não-tachada, fica a não-tachada (redação atual); se só há a
tachada, o artigo é mantido e marcado ``vigente=False``.

Os **anexos** que o Planalto serve na mesma página, depois do fecho, têm espaço
de path próprio: a partir do cabeçalho ``ANEXO`` (``_ANEXO_MARK``) o artigo sai
com prefixo (``anexo_art_1``, ``anexo_ii_art_3``) e o anexo sem artigo — tabela,
quadro, código por incisos — vira dispositivo de texto (``anexo_i``, em partes
se for grande). Quando o anexo **é** o documento que se cita (a CLT apensa ao
Decreto-Lei 5.452, o Regulamento apenso ao decreto que o aprova), o certo é o
``recorte`` do ``NormaMeta``, que descarta o ato de aprovação e deixa o texto
apenso dono de ``art_N`` — o parser não adivinha qual dos dois o leitor quer.
"""

from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup, Comment, Doctype, NavigableString, Tag

from lex_rag.ingest import jurisprudencia
from lex_rag.ingest.models import Dispositivo, Norma, TipoDispositivo
from lex_rag.ingest.revocation_detector import detectar_revogacao, extrair_marca_revogacao
from lex_rag.ingest.urn_mapper import NormaMeta

_WS = re.compile(r"\s+")

# Marcador de artigo: "Art. 1º", "Art. 37.", "Art. 5º-A", "Art. 1o",
# "Art. 2.028" (milhar com ponto, como no Código Civil). O ponto pode vir
# separado ("Art . 1º"): a LCP 36 quebra "Art" e ". 1º" em <font> distintos e
# o achatamento insere espaço entre eles. E pode **não vir**: as leis dos anos
# 1940-1980 grafam "Art 1º - ..." sem ponto nenhum (a Lei 6.899/1981 é assim do
# primeiro ao último artigo, e saía com zero dispositivos), e o mesmo aparece
# solto no meio de normas grandes (CLT arts. 554/555/571/572/575, CP arts.
# 187/188, CC art. 1.636, CTB art. 67-B). Daí o ponto ser opcional; o \b evita
# casar "Art" no fim de outra palavra.
# O indicador de ordinal também pode vir separado: o Planalto grafa
# "Art. 1<sup>o</sup>", que achatado vira "Art. 1 o" — sem consumi-lo, o "o"
# sobra e vira a primeira letra do caput ("o Salvo disposição contrária...",
# na LINDB). O símbolo aceita ponto antes ("Art. 2.º - ...", nas LCs dos anos
# 1970); o "o" solto NÃO aceita, senão "Art. 46. o Sistema Único de Saúde"
# (Lei 8.080, minúscula da própria fonte) perderia o artigo "o". O "o" solto
# exige ainda não-letra em seguida, senão "Art. 12 os prazos" perderia o "o"
# de "os"; o "O" maiúsculo que abre caput fica de fora por não estar na classe.
# Sufixo de artigo vale com a letra COLADA ao hífen ("Art. 121-A.") e seguida
# de não-letra; o traço espaçado dos códigos antigos ("Art. 312 - Apropriar-se
# ...") separa o caput e não pode virar sufixo, e "Art. 100 - A ação penal"
# tampouco (a letra não está colada ao hífen). Antes do hífen o espaço é
# aceito, porque o ordinal em <sup> deixa um ao ser achatado: "Art. 1<sup>o
# </sup>-A" vira "Art. 1 o -A." — e sem isso o sufixo se perdia e o artigo saía
# como "art_1__1" com o texto "A. Estão dispensadas..." (bug nº 11, achado no
# lote 13: 148 artigos em 58 normas, LCP 123 art. 3º-A, CTB art. 7º-A, Lei
# 9.494 arts. 1º-A a 1º-F). Exceção única no corpus: a LCP 95 grafa o sufixo
# espaçado dos dois lados em "Art. 18 - A (VETADO)" — aceito apenas com
# "(VETADO" logo depois.
_ART_MARK = re.compile(
    r"\bArt\s*\.?\s*(\d{1,3}(?:\.\d{3})*)(?:\s*\.?\s*[º°ª]|\s*o(?![A-Za-zÀ-ÿ]))?"
    r"(?:\s*-([A-Z])(?![A-Za-zÀ-ÿ])|\s+-\s+([A-Z])(?=\s*\(\s*VETADO))?"
)

# Caput que não carrega norma: o Planalto imprime a marca de veto e, logo
# depois, a redação de verdade do mesmo artigo (CDC art. 15, PNMA art. 19,
# PIS art. 33...). Sem tratar isso, o placeholder fica com o path canônico e o
# texto real é empurrado para "art_N__1" — quem pedir o dispositivo recebe
# "(VETADO)". Artigo vetado por inteiro (LCP 95, art. 18-A) não tem concorrente
# e continua no índice, que é o comportamento correto.
_VETADO = re.compile(r"\(?\s*VETADO", re.IGNORECASE)


def _e_placeholder(texto: str) -> bool:
    t = (texto or "").strip()
    # a linha pontilhada é o "..............." das leis que só alteram outras
    return not t or bool(_VETADO.match(t)) or set(t) <= {".", " ", "…"}


# Marcador dentro de bloco citado: "A Lei nº X passa a vigorar com a seguinte
# redação: “Art. 14. ...”". O artigo citado é de OUTRA lei, e indexá-lo aqui
# atribui à norma um dispositivo que não é dela — exatamente a alucinação que o
# projeto existe para impedir. Só a aspa de ABERTURA conta: depois da aspa de
# fechamento ("...das obrigações.” Art. 92.") vem artigo de verdade, e derrubá-lo
# perderia texto vigente. A aspa ASCII é ambígua (serve para abrir e fechar), daí
# exigir dela o ":" ou o ")" do "(NR)" que antecede toda abertura de citação.
_ASPA_ABRE = re.compile(r"(?:[“«]|[:)]\s*\")\s*$")

# Marcador que é **referência** a artigo, não abertura de dispositivo. O que
# denuncia é o que vem logo DEPOIS do número: um caput começa com o texto da
# norma, nunca com vírgula nem com a preposição que emenda a citação. Achado no
# lote 6 (LDO/LOA), onde os títulos de anexo citam a LRF — "ANEXO IV - METAS
# FISCAIS (Art. 4º, § 1º, da Lei Complementar nº 101, de 4 de maio de 2000)" —
# e o Anexo de Riscos Fiscais cita processos ("art. 3º da Portaria AGU nº
# 40/2015", "art. 102, III, 'd', c/c com o art. 3º, § 2º"). Sem o guarda, cada
# uma dessas citações abria um falso dispositivo que engolia o pedaço de anexo
# seguinte e o servia rotulado como "Art. 4º" **da LDO** — o texto de outra
# norma atribuído a esta, que é a alucinação que o projeto existe para impedir.
# Descartar aqui, e não depois, é o que mantém o trecho colado ao dispositivo
# anterior: o marcador nunca entra em ``markers``, então não vira fronteira e
# nada se perde (é o mesmo mecanismo do guarda de aspas acima). Nos 662 HTMLs
# em cache o guarda mexe em 16 normas, e a inspeção uma a uma mostrou que
# sempre remenda artigo cortado no meio de uma citação (o art. 72 do ADCT vinha
# truncado em "nos termos do art. 22") ou apaga dispositivo que nunca existiu
# (o "art. 59" da LCP 49 e o "art. 21" da Lei 7.990 eram o preâmbulo citando a
# Constituição).
# A conjunção entra pelo mesmo motivo que a preposição: "art. 35 e seu parágrafo
# único", "art. 2º e 6º do Decreto-Lei 1.023/1969". Nenhum caput do corpus abre
# com "e" — nos 662 HTMLs em cache ela mexe em 4 normas, e nas quatro remenda
# artigo que vinha cortado no meio da citação (a Lei 6.360 servia o art. 35 como
# "...deverão satisfazer aos requisitos dispostos no", sem o objeto).
# "art. 1º desta Lei" e "art. 3º neste Decreto" entram com o lote 15: as Leis
# 4.749 e 7.394 abriam um falso art. 1º a cada referência interna.
_REFERENCIA = re.compile(r"\s*(?:,|(?:d[aeo]s?|[dn]est[aeo]s?|e|c/c|cumulado)\b)")

# Fecho da lei: "Brasília, 14 de agosto de 2018; 197º da Independência e 130º da
# República." Encerra o texto articulado — depois dele vêm assinaturas, o "Este
# texto não substitui o publicado no DOU" e os **anexos**, que o Planalto serve
# na mesma página. Como o parser só estrutura artigos, tudo isso ficava colado
# ao último dispositivo: o art. 155 da LDO de 2019 saía com 289 KB, o art. 37 do
# PNE com 160 KB, o art. 89 da LCP 123 com as tabelas do Simples — texto que não
# é daquele artigo, servido como se fosse. Truncar no fecho devolve o artigo de
# verdade ("Esta Lei entra em vigor na data de sua publicação").
# O corte é por dispositivo, não pelo documento: páginas de texto compilado
# trazem mais de um fecho (a lei e a alteradora reproduzida), e cortar o
# documento no primeiro deles decepava o resto da norma.
# Só o trecho "Nº da Independência" identifica o fecho com segurança — casar a
# cidade e a data acharia qualquer menção a data no corpo do texto.
_FECHO = re.compile(r"\b\d{1,3}\s*[ºo°]\s+da\s+Independ[êe]ncia\b", re.IGNORECASE)

# Marcador de cabeçalho estrutural (palavra-chave + numeral).
_HDR_MARK = re.compile(
    r"\b(LIVRO|PARTE|T[ÍI]TULO|CAP[ÍI]TULO|SUBSE[ÇC][ÃA]O|SE[ÇC][ÃA]O)\s+"
    r"([IVXLCDM]+|[ÚU]NIC[OA]|\d{1,3})\b",
    re.IGNORECASE,
)

# Cabeçalho de anexo. O Planalto serve os anexos na mesma página, depois do
# fecho, e até aqui o parser só os via como texto colado ao último artigo (ou
# perdido no corte do fecho) — e os artigos do Regulamento "anexo a este
# Decreto" colidiam com os do próprio decreto (``art_1`` do RIR era "Fica
# aprovado o Regulamento..."). A partir do cabeçalho, o parser entra em
# **escopo de anexo**: artigo ganha o prefixo do anexo (``anexo_art_1``,
# ``anexo_ii_art_3``) e anexo sem artigo (tabela, quadro, código de ética por
# incisos) vira dispositivo de texto, em partes se for grande.
# Só a grafia em caixa alta é cabeçalho — "Anexo I" no meio de frase é
# referência —, inclusive a forma espaçada "A N E X O I" do RPS. Medido nos
# 698 HTMLs em cache: ``ANEXO`` em caixa alta antes do fecho só ocorre dentro
# de texto citado entre aspas (que o guarda de aspas já descarta), então o
# cabeçalho pode ser reconhecido em qualquer posição da página. Numeral em
# letra ("ANEXO A") fica de fora de propósito: "ANEXO A QUE SE REFERE O ART."
# é frequente e o "A" ali é artigo definido.
_ANEXO_MARK = re.compile(
    r"\bA\s?N\s?E\s?X\s?O\b(?:\s+([IVXLCDM]+|[ÚU]NICO|\d{1,3})(?![A-Za-zÀ-ÿ0-9]))?"
)
# "no ANEXO XV", "do ANEXO I": referência em caixa alta dentro de título de
# anexo (a LCP 214 grafa "RELACIONADOS NO ANEXO XV)" no cabeçalho do Anexo I).
_REF_ANEXO = re.compile(r"\b(?:n[oa]s?|d[oa]s?|a[oa]s?|nest[ea]|dest[ea]|conforme|vide)\s+$",
                        re.IGNORECASE)
# Marcador de artigo por extenso, como grafam os tratados promulgados por
# decreto ("Artigo 8º - Garantias judiciais", "ARTIGO 1"). Só vale em escopo
# de anexo, e só com inicial maiúscula: no corpo da lei "artigo" por extenso é
# sempre referência ("nos termos do artigo 5º"), e aceitá-lo lá abriria falso
# dispositivo em cada uma. Aceita numeral romano ("Artigo I", "Artigo XII" —
# quatro convenções da OIT no Dec. 10.088 são assim). O path é normalizado para
# ``art_N`` em arábico — a citação por path não deve depender da grafia da fonte.
_ARTIGO_MARK = re.compile(
    r"\b(?:Artigo|ARTIGO)\s+(?:(\d{1,3})(?:\s*\.?\s*[º°ª]|\s*o(?![A-Za-zÀ-ÿ]))?"
    r"|([IVXLCDM]{1,7})(?![A-Za-zÀ-ÿ]))"
)
# Nos tratados a referência corrida também é por extenso e com maiúscula ("em
# conformidade com o Artigo 8º", "prevista no Artigo 9.2 da Convenção de
# Berna") — o guarda do que vem DEPOIS do número não a pega ("Artigo 4(1) para
# todos"). O que a denuncia é o que vem ANTES: artigo definido ou preposição em
# minúscula; o cabeçalho de verdade vem depois de ponto final ou de "seguinte:".
# Medido no Tratado de Marraqueche: 35 falsos dispositivos em 60.
_REF_ARTIGO_ANTES = re.compile(
    r"\b(?:[oa]s?|d[oa]s?|n[oa]s?|aos?|às?|pel[oa]s?|e|ou|d?este|d?esse|neste|nesse|com|"
    r"conforme|vide|ver)\s+$"
)
_ROMANO = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _romano_para_int(s: str) -> int:
    total = 0
    for i, c in enumerate(s):
        v = _ROMANO[c]
        total += -v if i + 1 < len(s) and _ROMANO[s[i + 1]] > v else v
    return total
# Anexo sem artigo entra como texto em partes deste tamanho (~1.000 tokens),
# que o embedder e o reranker enxergam inteiros; o anexo do PNE tem 160 KB.
_ANEXO_PARTE = 4000
# Anexo menor que isto é cabeçalho de imagem ou tabela vazia, não conteúdo.
_ANEXO_MIN = 30

# Níveis do contexto hierárquico (``parent_label``): o anexo é o nível 0 e os
# cabeçalhos estruturais recomeçam dentro dele.
_LEVEL = {"LIVRO": 1, "PARTE": 1, "TITULO": 2, "CAPITULO": 3, "SUBSECAO": 4, "SECAO": 4}
_NIVEIS = 5
_STRIKE = {"strike", "s", "del"}
_SKIP = {"script", "style"}


def _ate_o_fecho(texto: str) -> str:
    """Descarta o que vier depois do fecho: assinaturas, nota do DOU e anexos."""
    m = _FECHO.search(texto)
    return texto[:m.end()].rstrip() if m else texto


def _marcador(texto: str) -> re.Pattern[str]:
    """Regex do marcador de recorte, tolerante à quebra de linha da origem.

    A página da Câmara é uma exportação do LibreOffice e quebra a linha no meio
    do próprio título — ``RESOLUÇÃO`` numa linha, ``Nº 25, DE 2001`` na
    seguinte: busca por literal falha ali, e falhar num marcador aborta o
    documento inteiro.
    """
    return re.compile(r"\s+".join(re.escape(p) for p in texto.split()))


def recortar(html: str, recorte: tuple[str, str] | None) -> str:
    """Reduz a página ao trecho que é o documento, entre os dois marcadores.

    O Planalto serve uma norma por página, e o que vem depois do texto
    articulado o parser descarta no fecho (``_FECHO``). As páginas das Casas não
    são assim: a da Câmara traz **três** documentos na mesma URL (a resolução
    promulgadora, o Regimento anexo — que recomeça em ``Art. 1º`` — e o Código de
    Ética), e a do Senado fecha com a nota de compilação e o rodapé do portal,
    que ficariam colados ao último artigo.

    Marcador ausente é erro, e não corte silencioso: se a página mudar de forma,
    voltar a parsear tudo devolveria justamente a mistura de documentos que o
    recorte existe para impedir — com a cara de sucesso que o pipeline não
    consegue distinguir de uma carga boa.
    """
    if not recorte:
        return html
    inicio, fim = recorte
    corte_ini = 0
    if inicio:
        m = _marcador(inicio).search(html)
        if m is None:
            raise ValueError(f"marcador de início do recorte ausente na página: {inicio!r}")
        corte_ini = m.start()
    corte_fim = len(html)
    if fim:
        m = _marcador(fim).search(html, corte_ini)
        if m is None:
            raise ValueError(f"marcador de fim do recorte ausente na página: {fim!r}")
        corte_fim = m.start()
    return html[corte_ini:corte_fim]


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _norm(s: str) -> str:
    return _WS.sub(" ", s.replace("\xa0", " ").replace("​", "")).strip()


def _label_artigo(num: str, suf: str | None) -> str:
    base = f"Art. {num}º" if int(num) < 10 else f"Art. {num}"
    return f"{base}-{suf}" if suf else base


def _path_artigo(num: str, suf: str | None) -> str:
    return f"art_{num}_{suf}" if suf else f"art_{num}"


def _label_anexo(numeral: str | None, ordem: int) -> str:
    if numeral:
        return f"Anexo {numeral.upper() if numeral[0].isalpha() else numeral}"
    return "Anexo" if ordem == 1 else f"Anexo ({ordem}º)"


def _path_anexo(numeral: str | None, ordem: int) -> str:
    """``anexo``, ``anexo_i``, ``anexo_unico``, ``anexo_3``; sem numeral, o 2º é ``anexo_2``."""
    if numeral:
        return f"anexo_{_strip_accents(numeral).lower()}"
    return "anexo" if ordem == 1 else f"anexo_{ordem}"


def _partes(texto: str, tamanho: int = _ANEXO_PARTE) -> list[str]:
    """Divide texto longo em partes de até ``tamanho`` chars, cortando em espaço."""
    partes: list[str] = []
    while len(texto) > tamanho:
        corte = texto.rfind(" ", tamanho // 2, tamanho)
        if corte < 0:
            corte = tamanho
        partes.append(texto[:corte].rstrip())
        texto = texto[corte:].lstrip()
    if texto:
        partes.append(texto)
    return partes


def _e_tachado(node: Tag) -> bool:
    # O Planalto tacha por tag (<strike>/<s>/<del>) ou por CSS inline
    # (ex.: Lei 8.666 art. 3º usa span com text-decoration: line-through).
    if node.name in _STRIKE:
        return True
    return "line-through" in (node.get("style") or "")


def _flatten(soup: BeautifulSoup) -> tuple[str, list[tuple[int, int]]]:
    """Achata o texto preservando ordem e marca os trechos tachados (struck)."""
    pieces: list[str] = []
    struck: list[tuple[int, int]] = []
    cursor = 0
    stack: list[tuple[object, bool]] = [(soup, False)]
    while stack:
        node, in_strike = stack.pop()
        if isinstance(node, (Comment, Doctype)):
            continue  # comentários HTML contêm texto morto e gerariam artigos fantasmas
        if isinstance(node, NavigableString):
            txt = str(node).replace("\xa0", " ")
            if txt.strip():
                start = cursor
                pieces.append(txt)
                cursor += len(txt)
                pieces.append(" ")
                cursor += 1
                if in_strike:
                    struck.append((start, cursor))
            continue
        if isinstance(node, Tag):
            if node.name in _SKIP:
                continue
            child_strike = in_strike or _e_tachado(node)
            for child in reversed(list(node.children)):
                stack.append((child, child_strike))
    return "".join(pieces), struck


def _in_struck(pos: int, spans: list[tuple[int, int]]) -> bool:
    for a, b in spans:
        if a <= pos < b:
            return True
        if a > pos:
            break
    return False


def parse_dispositivos(html: str) -> list[Dispositivo]:
    soup = BeautifulSoup(html, "html.parser")
    text, struck_spans = _flatten(soup)

    def _e_citacao_ou_referencia(m: re.Match) -> bool:
        if _ASPA_ABRE.search(text[max(0, m.start() - 30):m.start()]):
            return True  # artigo de outra lei, citado dentro de um dispositivo alterador
        # referência a artigo dentro de citação, não abertura de dispositivo
        return bool(_REFERENCIA.match(text[m.end():m.end() + 20]))

    markers: list[tuple[int, int, str, tuple]] = []
    for m in _ART_MARK.finditer(text):
        if _e_citacao_ou_referencia(m):
            continue
        markers.append((m.start(), m.end(), "art", (m.group(1), m.group(2) or m.group(3))))
    for m in _HDR_MARK.finditer(text):
        markers.append((m.start(), m.end(), "hdr", (m.group(1), m.group(2))))
    # Anexo só existe depois do fecho da norma: o que aparece antes é anexo de
    # OUTRA lei, reproduzido por dispositivo alterador (a LCP 227 reescreve os
    # anexos da LCP 123 no corpo, com linha de pontos e sem aspa por perto).
    # Página sem fecho (regimento, texto recortado) aceita anexo em qualquer
    # posição.
    fecho = _FECHO.search(text)
    inicio_anexos = fecho.end() if fecho else 0
    ultimo_anexo: int | None = None
    for m in _ANEXO_MARK.finditer(text, inicio_anexos):
        if _ASPA_ABRE.search(text[max(0, m.start() - 30):m.start()]):
            continue  # anexo de outra lei, reproduzido em dispositivo alterador
        if _REF_ANEXO.search(text[max(0, m.start() - 12):m.start()]):
            continue  # "no ANEXO XV": referência, não cabeçalho
        # Cabeçalho duplo é um cabeçalho só: "ANEXO I (Anexo I da Lei 10.910)
        # ANEXO I ESTRUTURA DE CARGOS" (Lei 11.457) e o anexo aninhado da LCP
        # 214, "ANEXO XVIII Produção de efeitos (LCP 123) ANEXO I Alíquotas...",
        # que reproduz o anexo de outra lei dentro do seu. Sem isto o segundo
        # abria anexo novo e colidia com o Anexo I de verdade.
        if ultimo_anexo is not None and m.start() - ultimo_anexo < 120:
            continue
        ultimo_anexo = m.end()
        markers.append((m.start(), m.end(), "anexo", (m.group(1),)))
    primeiro_anexo = min((mk[0] for mk in markers if mk[2] == "anexo"), default=None)
    # "Artigo N" vale a partir do primeiro cabeçalho de anexo — ou, havendo
    # fecho, a partir dele: metade dos decretos de promulgação de tratado serve
    # a Convenção colada ao fecho, sem cabeçalho ("Este texto não substitui o
    # publicado... CONVENÇÃO CONTRA A TORTURA... Artigo 1"). Nesse caso o
    # primeiro "Artigo N" abre um anexo **implícito** (``anexo_art_N``); o
    # "Art." não é afetado, então a promulgação de partes vetadas, que repete
    # artigos da própria lei depois do fecho, continua como antes.
    inicio_artigo = inicio_anexos if fecho else primeiro_anexo
    if inicio_artigo is not None:
        implicito = False
        for m in _ARTIGO_MARK.finditer(text, inicio_artigo):
            if _e_citacao_ou_referencia(m):
                continue
            if _REF_ARTIGO_ANTES.search(text[max(0, m.start() - 12):m.start()]):
                continue  # "no Artigo 4(1)": referência corrida, não cabeçalho
            if not implicito and (primeiro_anexo is None or m.start() < primeiro_anexo):
                markers.append((m.start(), m.start(), "anexo", (None,)))
                implicito = True
            num = m.group(1) or str(_romano_para_int(m.group(2)))
            markers.append((m.start(), m.end(), "art", (num, None)))
    markers.sort(key=lambda x: x[0])

    # Para cada cabeçalho de anexo, se há artigo antes do anexo seguinte: com
    # artigo, o anexo é articulado e só os artigos entram (com prefixo); sem,
    # o anexo inteiro entra como texto.
    anexo_articulado: dict[int, bool] = {}
    fim_anexo: dict[int, int] = {}
    atual: int | None = None
    for i, (start, _end, kind, _payload) in enumerate(markers):
        if kind == "anexo":
            if atual is not None:
                fim_anexo[atual] = start
            atual = i
            anexo_articulado[i] = False
        elif kind == "art" and atual is not None:
            anexo_articulado[atual] = True
    if atual is not None:
        fim_anexo[atual] = len(text)

    context: list[str | None] = [None] * _NIVEIS
    entries: list[dict] = []  # artigos crus, antes da deduplicação
    anexo_path: str | None = None  # prefixo do path enquanto em escopo de anexo
    n_anexos = 0

    def parent_label() -> str:
        return " - ".join(s for s in context if s)

    for i, (start, label_end, kind, payload) in enumerate(markers):
        if i > 0 and start < markers[i - 1][1]:
            continue
        next_start = markers[i + 1][0] if i + 1 < len(markers) else len(text)
        content = _ate_o_fecho(_norm(text[label_end:next_start].strip(" .-–—")))

        if kind == "hdr":
            keyword, numeral = payload
            level = _LEVEL.get(_strip_accents(keyword).upper())
            if level is None:
                continue
            label = _norm(f"{keyword} {numeral}")
            context[level] = f"{label} - {content}" if content else label
            for deeper in range(level + 1, _NIVEIS):
                context[deeper] = None
            continue

        if kind == "anexo":
            n_anexos += 1
            numeral = payload[0]
            anexo_path = _path_anexo(numeral, n_anexos)
            label = _label_anexo(numeral, n_anexos)
            titulo = content[:120]
            context[0] = f"{label.upper()} - {titulo}" if titulo else label.upper()
            for deeper in range(1, _NIVEIS):
                context[deeper] = None
            if anexo_articulado[i]:
                continue
            texto = _ate_o_fecho(_norm(text[label_end:fim_anexo[i]].strip(" .-–—")))
            if len(texto) < _ANEXO_MIN:
                continue
            struck = _in_struck(start, struck_spans)
            for n, parte in enumerate(_partes(texto), 1):
                entries.append(
                    {
                        "base": anexo_path if n == 1 else f"{anexo_path}_p{n}",
                        "label": label if n == 1 else f"{label} (parte {n})",
                        "tipo": TipoDispositivo.anexo,
                        "struck": struck,
                        "content": parte,
                        "parent_label": "",
                    }
                )
            continue

        num = payload[0].replace(".", "")
        suf = payload[1]
        base = _path_artigo(num, suf)
        entries.append(
            {
                "base": f"{anexo_path}_{base}" if anexo_path else base,
                "label": _label_artigo(num, suf),
                "tipo": TipoDispositivo.artigo,
                "struck": _in_struck(start, struck_spans),
                "content": content,
                "parent_label": parent_label(),
            }
        )

    # Bases que possuem versão vigente (não-tachada): descartam a redação anterior tachada.
    bases_vigentes = {e["base"] for e in entries if not e["struck"]}
    # Bases que possuem redação de verdade: descartam o placeholder de veto.
    bases_com_texto = {e["base"] for e in entries if not _e_placeholder(e["content"])}

    out: list[Dispositivo] = []
    seen: dict[str, int] = {}
    for e in entries:
        if e["struck"] and e["base"] in bases_vigentes:
            continue  # redação anterior superada
        if _e_placeholder(e["content"]) and e["base"] in bases_com_texto:
            continue  # marca de veto ao lado da redação real do mesmo artigo
        path = e["base"]
        if path in seen:
            seen[path] += 1
            path = f"{path}__{seen[path]}"
        else:
            seen[path] = 0
        if e["struck"]:
            marca = extrair_marca_revogacao(e["content"])
            vigente, revogado_por = False, (marca or "Revogado")
        else:
            vigente, revogado_por = detectar_revogacao(e["content"])
        out.append(
            Dispositivo(
                path=path,
                label=e["label"],
                tipo=e["tipo"],
                texto=e["content"],
                parent_label=e["parent_label"],
                vigente=vigente,
                revogado_por=revogado_por,
            )
        )
    return out


def parse_norma(meta: NormaMeta, html: str) -> Norma:
    """Monta uma Norma combinando os metadados curados com os dispositivos parseados.

    Documento jurisprudencial não passa pelo parser: é um enunciado único, sem
    marcador ``Art. N`` para achar, e o regex devolveria lista vazia — que o
    pipeline registraria como sucesso, com zero pontos no índice.

    Norma com ``recorte`` é parseada só no trecho da página que lhe pertence
    (ver ``recortar``); o cache e o hash continuam sendo os da página inteira,
    para o delta enxergar qualquer mudança na fonte.
    """
    if meta.tipo in jurisprudencia.TIPOS_JURISPRUDENCIA:
        return jurisprudencia.montar_norma(meta, html)
    return Norma(
        urn_lex=meta.urn_lex,
        tipo=meta.tipo,
        numero=meta.numero,
        data=meta.data,
        epigrafe=meta.epigrafe,
        ementa=meta.ementa,
        url_canonica=meta.url_canonica,
        dispositivos=parse_dispositivos(recortar(html, meta.recorte)),
    )
