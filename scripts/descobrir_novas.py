"""Descobre leis ordinárias sancionadas depois do último número do catálogo e
incorpora ao corpus as que fazem sentido (``registro_novas.json``).

O ``update`` só reprocessa o que já está no catálogo. Este script varre a
numeração na API de metadados do LexML a partir do último ponto conhecido (a
maior lei do catálogo, ou onde a rodada anterior parou), classifica cada lei
pela ementa oficial (``lex_rag.ingest.descoberta_novas``) e, para as
candidatas, resolve a URL no Planalto com a mesma validação do lote curado:
download + parse com dispositivos plausíveis + data conferida com a epígrafe.

O que entra vai para ``registro_novas.json``, que o ``REGISTRO`` carrega (e que
perde para a lista curada em conflito de URN). O que fica de fora vai para
``triagem_novas.json`` com o motivo, para auditoria, junto com o ponto de
parada da varredura — sem ele, cada rodada reconsultaria as leis já descartadas.

Uso::

    python scripts/descobrir_novas.py                # a partir do último ponto
    python scripts/descobrir_novas.py --ate 15600    # limite superior explícito
    python scripts/descobrir_novas.py --revalidar    # re-resolve as URLs já gravadas

Depois: ``verificar_parser.py --novos`` (o HTML validado já fica em cache) e a
carga por ``POST /update`` no daemon (que relê o catálogo) ou
``reindexar_do_cache.py --novos`` com o daemon parado.

Candidata cuja página o Planalto ainda não publicou fica **pendente**: o ponto
de parada não avança além dela e a próxima rodada tenta de novo. ``--revalidar``
existe pelo mesmo motivo do ``descobrir_ordinarias``: a lei nova entra pela
página do texto original, e quando for alterada o Planalto passa a servir o
vigente num ``...compilado.htm`` que só uma nova resolução encontra.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date

from lex_rag.config import settings
from lex_rag.ingest import raw_cache
from lex_rag.ingest.descoberta_novas import (
    classificar,
    metadados_lexml,
    normas_presentes,
    ultima_lei,
)
from lex_rag.ingest.html_parser import parse_dispositivos
from lex_rag.ingest.planalto_fetcher import fetch
from lex_rag.ingest.planalto_urls import BASE, conferir_data, epigrafe, variantes_url
from lex_rag.ingest.urn_mapper import REGISTRO, REGISTRO_NOVAS_PATH

TRIAGEM_PATH = REGISTRO_NOVAS_PATH.with_name("triagem_novas.json")
ESPECIE = "lei"


def resolver(numero: str, d: date) -> tuple[str, str, int, str]:
    """Primeira URL que baixa e parseia com dispositivos plausíveis (+ o HTML).

    Mesma mecânica do ``descobrir_ordinarias``: piso de 2 dispositivos (página
    errada parseia com 0 ou 1; lei legítima de dois artigos existe) e todos os
    motivos de falha no erro, não só o da última variante.
    """
    erros: list[str] = []
    for url in variantes_url(ESPECIE, numero, d.year):
        try:
            html = fetch(url)
            disp = parse_dispositivos(html)
            if len(disp) < 2:
                erros.append(f"parse magro ({len(disp)} disp) em {url.replace(BASE, '')}")
                continue
            return url, html, len(disp), conferir_data(html, numero, d, ESPECIE)
        except Exception as exc:
            erros.append(type(exc).__name__)
        finally:
            time.sleep(settings.http_polite_delay)  # coleta educada
    raise RuntimeError("; ".join(dict.fromkeys(erros)) or "sem variante")


def entrada(numero: str, d: date, ementa: str, url: str) -> dict:
    return {
        "slug": f"lei_{numero}_{d.year}",
        "urn_lex": f"urn:lex:br:federal:{ESPECIE}:{d.isoformat()};{numero}",
        "tipo": "lei",
        "numero": numero,
        "data": d.isoformat(),
        "epigrafe": epigrafe(ESPECIE, numero, d),
        "ementa": ementa,
        "url_canonica": url,
    }


def _ler(caminho, padrao):
    return json.loads(caminho.read_text("utf-8")) if caminho.exists() else padrao


def _gravar(caminho, dados) -> None:
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def revalidar(novas: list[dict]) -> int:
    """Re-resolve a URL de cada lei já gravada; devolve o número de falhas."""
    falhas = 0
    for e in novas:
        d = date.fromisoformat(e["data"])
        try:
            url, html, n_disp, confere = resolver(e["numero"], d)
        except Exception as exc:
            falhas += 1
            print(f"  {e['slug']:20} FALHOU: {exc}")
            continue
        if confere.startswith("DIVERGE"):
            falhas += 1
            print(f"  {e['slug']:20} REJEITADA: {confere}")
            continue
        mudou = " (URL nova)" if url != e["url_canonica"] else ""
        e["url_canonica"] = url
        raw_cache.put(e["slug"], html)
        print(f"  {e['slug']:20} ok ({n_disp} disp) {url.replace(BASE, '')}{mudou}")
    return falhas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ate", type=int, help="último número a consultar (padrão: até esgotar)")
    ap.add_argument("--max-faltas", type=int, default=10,
                    help="números seguidos sem norma no LexML que encerram a varredura")
    ap.add_argument("--desde", type=int,
                    help="primeiro número a consultar (padrão: onde a rodada anterior parou, "
                         "ou a maior lei do catálogo)")
    ap.add_argument("--revalidar", action="store_true",
                    help="re-resolve as URLs das leis já em registro_novas.json antes de varrer")
    args = ap.parse_args()

    novas: list[dict] = _ler(REGISTRO_NOVAS_PATH, [])
    triagem: dict = _ler(TRIAGEM_PATH, {"lei": {}, "normas": []})
    descartadas = {e["numero"]: e for e in triagem["normas"]}
    presentes = normas_presentes(REGISTRO.values())
    urns_catalogo = {m.urn_lex for m in REGISTRO.values()}

    if args.revalidar and novas:
        print(f"[novas] revalidando {len(novas)} URLs...")
        if revalidar(novas):
            _gravar(REGISTRO_NOVAS_PATH, novas)
            return 1

    # Ponto de partida: onde a rodada anterior parou (vale mesmo abaixo da
    # maior lei do catálogo — é assim que uma pendente é retomada), ou a maior
    # lei do catálogo na primeira rodada.
    parada = triagem["lei"]
    if parada.get("varrido_ate"):
        numero, ano = parada["varrido_ate"], parada["ano"]
    else:
        numero, ano = ultima_lei(REGISTRO.values())
    if args.desde:
        numero = args.desde - 1
    print(f"[novas] varrendo leis a partir de {numero + 1} ({ano})...")

    incluidas: list[str] = []
    para_revisar: list[dict] = []  # mãe ausente e ementa inconclusiva: decisão humana
    pendente: int | None = None
    contagem: dict[str, int] = {}

    def contar(categoria: str) -> None:
        contagem[categoria] = contagem.get(categoria, 0) + 1

    # Ano de cada número encontrado: o ponto de parada precisa ser gravado com
    # o ano certo, senão a retomada na virada do ano consulta o URN errado.
    anos = {numero: ano}
    n, faltas, ultimo = numero + 1, 0, numero
    while faltas < args.max_faltas and (args.ate is None or n <= args.ate):
        meta = metadados_lexml(ESPECIE, ano, n) or metadados_lexml(ESPECIE, ano + 1, n)
        time.sleep(settings.http_polite_delay)
        if meta is None:
            faltas += 1
            n += 1
            continue
        faltas, ultimo, ano = 0, n, meta["data"].year
        anos[n] = ano
        num, d, ementa = meta["numero"], meta["data"], meta["ementa"]
        urn = f"urn:lex:br:federal:{ESPECIE}:{d.isoformat()};{num}"
        rotulo = f"[{num}] {d.isoformat()}"
        if urn in urns_catalogo:
            print(f"{rotulo} já no catálogo")
            n += 1
            continue
        t = classificar(ementa, presentes)
        if t.categoria != "candidata":
            contar(t.categoria)
            descartadas[num] = {"numero": num, "data": d.isoformat(), "ementa": ementa,
                                "categoria": t.categoria, "motivo": t.motivo}
            if t.categoria in ("mae_ausente", "revisar"):
                para_revisar.append(descartadas[num])
            print(f"{rotulo} {t.categoria:12} {t.motivo} | {ementa[:90]}")
            n += 1
            continue
        try:
            url, html, n_disp, confere = resolver(num, d)
        except Exception as exc:
            # Planalto ainda sem a página (ou fora do ar): fica para a próxima
            # rodada, e o ponto de parada não passa daqui.
            pendente = pendente or n
            contar("pendente")
            print(f"{rotulo} PENDENTE     {exc} | {ementa[:90]}")
            n += 1
            continue
        if confere.startswith("DIVERGE"):
            # Data errada = URN errado, e o URN é a chave do corpus: não entra.
            descartadas[num] = {"numero": num, "data": d.isoformat(), "ementa": ementa,
                                "categoria": "divergente", "motivo": confere}
            contar("divergente")
            print(f"{rotulo} REJEITADA    {confere} | {ementa[:90]}")
            n += 1
            continue
        e = entrada(num, d, ementa, url)
        novas.append(e)
        raw_cache.put(e["slug"], html)  # o verificar_parser --novos já acha o HTML
        incluidas.append(e["slug"])
        contar("incluida")
        print(f"{rotulo} INCLUÍDA     {n_disp} disp, {confere}, {url.replace(BASE, '')} "
              f"| {ementa[:90]}")
        n += 1

    novas.sort(key=lambda e: (e["data"], int(e["numero"])))
    _gravar(REGISTRO_NOVAS_PATH, novas)
    varrido_ate = min(ultimo, pendente - 1) if pendente else ultimo
    ano_parada = anos[pendente] if pendente else anos[ultimo]
    triagem = {
        "lei": {"varrido_ate": varrido_ate, "ano": ano_parada, "em": date.today().isoformat()},
        "normas": sorted(descartadas.values(), key=lambda e: int(e["numero"])),
    }
    _gravar(TRIAGEM_PATH, triagem)

    resumo = ", ".join(f"{k}: {v}" for k, v in sorted(contagem.items()))
    print(f"\n[novas] varrido até {varrido_ate}; {resumo or 'nenhuma lei nova'}")
    print(f"[novas] {len(incluidas)} incluídas -> {REGISTRO_NOVAS_PATH} "
          f"({len(novas)} no total); triagem -> {TRIAGEM_PATH}")
    if para_revisar:
        print(f"[novas] {len(para_revisar)} para decisão humana (alteram norma fora do corpus "
              f"— considere incluir a norma alterada na lista curada — ou ementa inconclusiva):")
        for e in para_revisar:
            print(f"    {e['numero']} ({e['categoria']}): {e['motivo']} | {e['ementa'][:80]}")
    if pendente:
        print(f"[novas] pendente desde {pendente}: rode de novo quando o Planalto publicar.")
    if incluidas:
        print("[novas] próximo passo: scripts/verificar_parser.py --novos, depois a carga "
              "(POST /update no daemon ou reindexar_do_cache.py --novos com ele parado).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
