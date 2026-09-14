"""Heurística de suspeitos: procura sintomas de bug de parser no corpus.

Toda expansão do corpus até aqui revelou um bug de parser (sufixo de artigo
comendo a primeira letra do caput, ponto em tag separada, indicador de ordinal
solto), e todos tinham o mesmo sintoma observável: **o caput sai truncado ou
começa com um resto do rótulo**. Este script varre o HTML já em cache
(``data/raw/``, sem tocar no Planalto) e lista os dispositivos que exibem esse
sintoma, para que a verificação de um lote novo não dependa de olhar norma a
norma.

Uso::

    python scripts/verificar_parser.py                 # corpus inteiro
    python scripts/verificar_parser.py --slug lindb_4657_1942 cpm_1001_1969
    python scripts/verificar_parser.py --novos --baixar  # o lote recém-descoberto

Nenhum dos sinais é prova de bug — são candidatos a inspeção. O ruído conhecido
está anotado em cada regra.
"""

from __future__ import annotations

import argparse
import re
import sys
import time

from bs4 import BeautifulSoup

from lex_rag.config import settings
from lex_rag.ingest import html_parser, raw_cache
from lex_rag.ingest.html_parser import parse_dispositivos, recortar
from lex_rag.ingest.jurisprudencia import TIPOS_JURISPRUDENCIA
from lex_rag.ingest.source import obter_html
from lex_rag.ingest.urn_mapper import REGISTRO

# Caput que começa com minúscula é o sintoma comum a todos os bugs achados: o
# rótulo comeu a primeira letra ("propriar-se o funcionário") ou sobrou um
# pedaço do próprio rótulo ("o Salvo disposição contrária"). Casos legítimos
# existem (a Lei 8.080 grafa "Art. 46. o Sistema Único de Saúde" na fonte), daí
# "suspeito", não "erro".
_INICIO_MINUSCULO = re.compile(r"^[a-zà-ÿ]")
# Sufixo de artigo é raro e sempre vem de "-A" colado; combinado com caput
# minúsculo é a assinatura exata do bug nº 1.
_SUFIXO = re.compile(r"-[A-Z]$")


def suspeitos(dispositivos) -> dict[str, list[str]]:
    """Agrupa os dispositivos suspeitos por regra."""
    achados: dict[str, list[str]] = {}

    def anota(regra: str, d) -> None:
        achados.setdefault(regra, []).append(f"{d.label}: {d.texto[:60]!r}")

    for d in dispositivos:
        if not d.texto:
            anota("caput vazio", d)
            continue
        # Parte de anexo (``anexo_i_p2``) começa onde a anterior cortou, no
        # meio da frase: minúscula ali é do corte, não do rótulo.
        if _INICIO_MINUSCULO.match(d.texto) and d.tipo != "anexo":
            regra = "sufixo + caput minusculo" if _SUFIXO.search(d.label) else "caput minusculo"
            anota(regra, d)
        # Rótulo repetido dentro do próprio texto: marcador não consumido.
        if re.match(r"^[ºo°ª]\s", d.texto):
            anota("ordinal solto no caput", d)

    # Paths deduplicados (__N) denunciam "Art." casado no meio de um caput.
    fantasmas = [d.label for d in dispositivos if "__" in d.path]
    if fantasmas:
        achados["path duplicado (__N)"] = fantasmas
    return achados


def texto_apenso_sem_recorte(html: str) -> int:
    """Artigos depois do fecho e fora de anexo, quando são mais que os do corpo.

    É a forma do ato que aprova um texto e o serve apenso (a CLT no DL 5.452,
    o Regulamento no decreto que o aprova): o corpo tem 2-5 artigos e o apenso
    recomeça em "Art. 1º" e é o documento que se cita. O parser trata o corpo
    como a norma, então o apenso colide (``art_1__1``) ou, sob cabeçalho
    ``ANEXO``, vira ``anexo_art_N``. A resposta certa é o ``recorte`` no
    registro (lote 11), e esta regra existe para apontar o caso novo. Devolve o
    número de artigos apensos (0 = forma normal).
    """
    text, _ = html_parser._flatten(BeautifulSoup(html, "html.parser"))
    fecho = html_parser._FECHO.search(text)
    if not fecho:
        return 0
    corpo = len(html_parser._ART_MARK.findall(text[:fecho.start()]))
    cauda = text[fecho.end():]
    anexo = html_parser._ANEXO_MARK.search(cauda)
    apenso = len(html_parser._ART_MARK.findall(cauda[:anexo.start()] if anexo else cauda))
    # Corpo sem artigo numerado ("Artigo único. Fica aprovado o regulamento...",
    # Dec. 21.981/1932) não colide com nada: o apenso já é dono de ``art_N``.
    return apenso if corpo and apenso > corpo else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", nargs="*", help="verifica só estes slugs (padrão: corpus inteiro)")
    ap.add_argument("--novos", action="store_true",
                    help="só as normas ainda ausentes do state.sqlite (o lote recém-descoberto)")
    ap.add_argument("--limite", type=int, default=5, help="exemplos exibidos por regra")
    ap.add_argument("--baixar", action="store_true",
                    help="baixa e cacheia as normas ainda sem HTML local, para verificar um "
                         "lote novo ANTES de indexá-lo (um bug de parser achado aqui custa uma "
                         "correção; achado depois, custa uma reindexação do corpus inteiro)")
    args = ap.parse_args()

    # Documento jurisprudencial não passa pelo parser de HTML, e as regras daqui
    # (rótulo comendo o caput, ordinal solto) pressupõem artigo — aplicá-las a um
    # enunciado só produziria ruído. Quem verifica esse lote é verificar_sumulas.py.
    slugs = [s for s in (args.slug or REGISTRO) if REGISTRO[s].tipo not in TIPOS_JURISPRUDENCIA]
    if args.novos:
        from lex_rag.storage import state

        slugs = [s for s in slugs if state.get_indexed(REGISTRO[s].urn_lex) is None]

    total_disp = total_susp = 0
    sem_cache: list[str] = []
    for slug in slugs:
        html = raw_cache.get(slug)
        if html is None and args.baixar:
            try:
                html = obter_html(REGISTRO[slug], permitir_fixture=False)
                raw_cache.put(slug, html)
                time.sleep(settings.http_polite_delay)  # coleta educada
            except Exception as exc:
                print(f"{slug}: download falhou ({type(exc).__name__})")
                html = None
        if html is None:
            sem_cache.append(slug)
            continue
        # Mesmo recorte que o pipeline aplica: sem ele o regimento apareceria
        # aqui com dezenas de paths duplicados que a carga não tem.
        recortado = recortar(html, REGISTRO[slug].recorte)
        disp = parse_dispositivos(recortado)
        achados = suspeitos(disp)
        apensos = texto_apenso_sem_recorte(recortado)
        if apensos:
            achados["texto apenso sem recorte"] = [f"{apensos} artigos depois do fecho"]
        total_disp += len(disp)
        total_susp += sum(len(v) for v in achados.values())
        if achados:
            print(f"\n{slug} ({len(disp)} disp)")
            for regra, itens in sorted(achados.items()):
                print(f"  {regra}: {len(itens)}")
                for item in itens[: args.limite]:
                    print(f"    - {item}")

    print(f"\n[verificar] {len(slugs) - len(sem_cache)} normas, {total_disp} dispositivos, "
          f"{total_susp} suspeitos")
    if sem_cache:
        print(f"[verificar] sem HTML em cache ({len(sem_cache)}): {', '.join(sem_cache[:20])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
