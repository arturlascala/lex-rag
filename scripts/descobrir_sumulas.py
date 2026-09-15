"""Gera o registro das Súmulas Vinculantes do STF (``sumulas_vinculantes.json``).

Mesma divisão de trabalho dos ``descobrir_*`` de legislação — tabela curada à
mão, script busca o texto na fonte oficial e confere o que a página afirma —,
com três diferenças que a espécie jurisprudencial impõe:

- **A fonte é o portal do STF**, não o Planalto: a página-índice
  (``sumariosumulas.asp?base=26``) dá o id opaco de cada súmula e cada página
  traz o enunciado dentro do primeiro ``div.parCOM`` depois do título. O portal
  fica atrás de WAF e responde 403 a requisição sem cabeçalho de navegador
  completo, daí ``_HEADERS`` abaixo ir bem além do User-Agent.
- **A conferência é de situação, não de data.** A página do Planalto imprime a
  epígrafe com a data, e ``conferir_data`` a casa contra o registro; a do STF
  não imprime data nenhuma, mas marca no título a súmula fora de vigor —
  ``Súmula Vinculante 9 (cancelada)``. É essa marca que o script casa contra a
  ``SITUACAO`` curada: divergência é erro, porque uma súmula que o STF cancelou
  e o corpus serve como vigente é pior do que não a ter.
- **As datas vêm de fora da página.** ``DATAS`` traz sessão de aprovação e DJe,
  extraídas do livro oficial *Súmulas Vinculantes* (2ª ed., Secretaria de
  Documentação) para as súmulas 1 a 56 e conferidas uma a uma nas fontes de
  2020 em diante. A data de aprovação entra no URN, então erro aqui é erro de
  identidade — o mesmo peso que ``conferir_data`` tem na legislação.

O arquivo gerado é a **fonte de ingestão**, não um cache: ao contrário da
legislação, cujo texto é rebaixado do Planalto a cada update, o enunciado da
súmula é servido do próprio JSON versionado (ver ``ingest/jurisprudencia.py``).
Rodar este script é o único jeito de o corpus incorporar súmula nova ou
cancelamento — no ritmo de uma ou duas por ano que o STF pratica.
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import ssl
import sys
import time

import httpx
import truststore
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from lex_rag.config import settings
from lex_rag.ingest.urn_mapper import SUMULAS_VINCULANTES_PATH

BASE = "https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp"
INDICE = f"{BASE}?base=26"

# O WAF do portal responde 403 a cliente que não se pareça com navegador; os
# cabeçalhos de navegação (Sec-Fetch-*, Referer) são o que faz a página vir.
_HEADERS = {
    "User-Agent": settings.http_user_agent,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": INDICE,
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Upgrade-Insecure-Requests": "1",
}

# numero -> (data da sessão de aprovação, data de publicação no DJe).
# 1 a 56: livro oficial "Súmulas Vinculantes" (2ª ed.), que registra por súmula
# "aprovada na [PSV N, julgada na] sessão plenária de D-M-AAAA" e "Fonte de
# publicação DJE N de D-M-AAAA". 57 em diante: notícias e publicações oficiais
# do STF, conferidas caso a caso (ver OBSERVACOES).
DATAS: dict[int, tuple[str, str | None]] = {
    1: ("2007-05-30", "2007-06-06"),
    2: ("2007-05-30", "2007-06-06"),
    3: ("2007-05-30", "2007-06-06"),
    4: ("2008-04-30", "2008-05-09"),
    5: ("2008-05-07", "2008-05-16"),
    6: ("2008-05-07", "2008-05-16"),
    7: ("2008-06-11", "2008-06-20"),
    8: ("2008-06-12", "2008-06-20"),
    9: ("2008-06-12", "2008-06-20"),
    10: ("2008-06-18", "2008-06-27"),
    11: ("2008-08-13", "2008-08-22"),
    12: ("2008-08-13", "2008-08-22"),
    13: ("2008-08-21", "2008-08-29"),
    14: ("2009-02-02", "2009-02-09"),
    15: ("2009-06-25", "2009-07-01"),
    16: ("2009-06-25", "2009-07-01"),
    17: ("2009-10-29", "2009-11-10"),
    18: ("2009-10-29", "2009-11-10"),
    19: ("2009-10-29", "2009-11-10"),
    20: ("2009-10-29", "2009-11-10"),
    21: ("2009-10-29", "2009-11-10"),
    22: ("2009-12-02", "2009-12-11"),
    23: ("2009-12-02", "2009-12-11"),
    24: ("2009-12-02", "2009-12-11"),
    25: ("2009-12-16", "2009-12-23"),
    26: ("2009-12-16", "2009-12-23"),
    27: ("2009-12-18", "2009-12-23"),
    28: ("2010-02-03", "2010-02-17"),
    29: ("2010-02-03", "2010-02-17"),
    30: ("2010-02-03", None),  # aprovada na PSV 41; publicação suspensa no dia seguinte
    31: ("2010-02-04", "2010-02-17"),
    32: ("2011-02-16", "2011-02-24"),
    33: ("2014-04-09", "2014-04-24"),
    34: ("2014-10-16", "2014-10-24"),
    35: ("2014-10-16", "2014-10-24"),
    36: ("2014-10-16", "2014-10-24"),
    37: ("2014-10-16", "2014-10-24"),
    38: ("2015-03-11", "2015-03-20"),
    39: ("2015-03-11", "2015-03-20"),
    40: ("2015-03-11", "2015-03-20"),
    41: ("2015-03-11", "2015-03-20"),
    42: ("2015-03-11", "2015-03-20"),
    43: ("2015-04-08", "2015-04-17"),
    44: ("2015-04-08", "2015-04-17"),
    45: ("2015-04-08", "2015-04-17"),
    46: ("2015-04-09", "2015-04-17"),
    47: ("2015-05-27", "2015-06-02"),
    48: ("2015-05-27", "2015-06-02"),
    49: ("2015-06-17", "2015-06-23"),
    50: ("2015-06-17", "2015-06-23"),
    51: ("2015-06-18", "2015-06-23"),
    52: ("2015-06-18", "2015-06-23"),
    53: ("2015-06-18", "2015-06-23"),
    54: ("2016-03-17", "2016-03-28"),
    55: ("2016-03-17", "2016-03-28"),
    56: ("2016-06-29", "2016-08-08"),
    57: ("2020-04-15", "2020-04-24"),
    58: ("2020-04-27", "2020-05-07"),
    59: ("2023-10-19", "2023-10-27"),
    60: ("2024-09-16", "2024-09-20"),
    61: ("2024-09-20", "2024-10-03"),
    62: ("2024-12-16", "2024-12-19"),
    63: ("2025-09-25", "2025-10-01"),
}

# Só o que foge de "vigente". A marca impressa no título da página do STF é
# conferida contra este dicionário em _conferir_situacao().
SITUACAO: dict[int, tuple[str, str]] = {
    9: ("cancelada", "Cancelada em 26/09/2025 (PSV 60), por incompatibilidade com a "
                     "redação do art. 127 da LEP dada pela Lei 12.433/2011"),
    30: ("publicacao_suspensa", "Publicação suspensa em 04/02/2010; nunca produziu efeitos"),
}

OBSERVACOES: dict[int, str] = {
    30: "Aprovada na PSV 41 em 03/02/2010; o Plenário suspendeu a publicação no dia "
        "seguinte, e o enunciado nunca chegou a ser publicado.",
    57: "Acolhida na PSV 132, em sessão virtual de 03 a 14/04/2020.",
    58: "Acolhida na PSV 26, em sessão virtual de 17 a 24/04/2020.",
    59: "Aprovada na PSV 139.",
    62: "Aprovada em sessão virtual de 06 a 13/12/2024; DOU de 09/01/2025.",
    63: "Aprovada na PSV 125, em sessão virtual encerrada em 25/09/2025.",
}

_SITUACOES = {"vigente", "cancelada", "publicacao_suspensa"}


def _contexto_ssl() -> ssl.SSLContext:
    """Verificação TLS pelo store do sistema, não pelo bundle do certifi.

    ``portal.stf.jus.br`` serve só o certificado folha, sem o intermediário da
    GlobalSign que o encadeia à raiz — com o certifi puro a verificação falha
    com ``unable to get local issuer certificate``. O store do sistema busca o
    elo faltante pela extensão AIA do próprio certificado, que é o que o
    navegador faz; assim a cadeia é conferida de verdade, em vez de desligar a
    verificação.
    """
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def _fetch(url: str, client: httpx.Client) -> str:
    resp = client.get(url)
    resp.raise_for_status()
    return resp.content.decode("utf-8", errors="replace")


def ids_do_indice(html: str, rotulo: str = "Súmula Vinculante") -> dict[int, int]:
    """numero da súmula -> id opaco que o portal usa na querystring.

    ``rotulo`` é o que o índice imprime antes do número: "Súmula Vinculante"
    (base 26) ou "Súmula" (base 30, as súmulas simples — lote 22-A).
    """
    flat = re.sub(r"\s+", " ", html_mod.unescape(html).replace("\xa0", " "))
    padrao = rf"sumula=(\d+)[^>]*>\s*{_regex_rotulo(rotulo)}\s*(\d+)\s*<"
    pares = re.findall(padrao, flat, re.IGNORECASE)
    return {int(numero): int(sid) for sid, numero in pares}


def _regex_rotulo(rotulo: str) -> str:
    return r"\s+".join(re.escape(p).replace("ú", "[úu]") for p in rotulo.split())


def extrair_enunciado(
    html: str, numero: int, rotulo: str = "Súmula Vinculante"
) -> tuple[str, str]:
    """Devolve (enunciado, marca de situação impressa no título).

    A página põe o enunciado no primeiro ``div.parCOM`` depois do
    ``div.titulo`` da súmula, e sinaliza a que saiu de vigor entre parênteses no
    próprio título — às vezes com um zero-width space no meio da palavra, que
    ``_limpar`` remove. Nas súmulas simples a mesma marca vem repetida no fim do
    enunciado ("...Ministro de Estado. (cancelada)"), e sai daqui: não é texto
    do STF, é sinalização do portal.
    """
    soup = BeautifulSoup(html, "html.parser")
    for div in soup.find_all("div", class_="titulo"):
        casa = re.fullmatch(
            rf"{_regex_rotulo(rotulo)}\s*{numero}\s*(?:\((.*)\))?",
            _limpar(div.get_text(" ", strip=True)),
        )
        if not casa:
            continue
        marca = (casa.group(1) or "").strip().lower()
        corpo = div.find_next_sibling("div")
        if corpo is None or "parCOM" not in (corpo.get("class") or []):
            raise RuntimeError(f"{rotulo} {numero}: div.parCOM ausente depois do título")
        enunciado = _limpar(corpo.get_text(" ", strip=True))
        if marca:
            enunciado = re.sub(rf"\s*\({re.escape(marca)}\)\s*$", "", enunciado, flags=re.I)
        return enunciado, marca
    raise RuntimeError(f"{rotulo} {numero}: título não encontrado na página")


def _limpar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto.replace("​", "").replace("\xa0", " ")).strip()


def _conferir_situacao(numero: int, marca: str, enunciado: str) -> str:
    """Casa o que o portal afirma sobre a súmula com a situação curada.

    Serve o mesmo papel que ``conferir_data`` na legislação: a fonte oficial tem
    a palavra final sobre o estado do documento, e divergir dela é erro de
    identidade, não detalhe de metadado.

    O portal sinaliza de dois jeitos, e é preciso olhar os dois: o cancelamento
    vem no título (``Súmula Vinculante 9 (cancelada)``), mas a suspensão de
    publicação vem no lugar do próprio enunciado ("A Súmula Vinculante 30 está
    pendente de publicação").
    """
    situacao = SITUACAO.get(numero, ("vigente", ""))[0]
    afirma_cancelada = marca.startswith("cancel")
    afirma_suspensa = bool(re.search(r"pendente de publica[çc][ãa]o", enunciado, re.IGNORECASE))
    portal = (
        "cancelada" if afirma_cancelada
        else "publicacao_suspensa" if afirma_suspensa
        else "vigente"
    )
    if portal == situacao:
        return "ok"
    return f"DIVERGE (portal diz {portal!r}, registro diz {situacao!r})"


def _entrada(numero: int, sid: int, enunciado: str) -> dict:
    aprovacao, publicacao = DATAS[numero]
    situacao, motivo = SITUACAO.get(numero, ("vigente", ""))
    return {
        "numero": numero,
        "urn_lex": f"urn:lex:br:supremo.tribunal.federal:sumula.vinculante:{aprovacao};{numero}",
        "enunciado": enunciado,
        "data_aprovacao": aprovacao,
        "data_publicacao": publicacao,
        "situacao": situacao,
        "cancelada_por": motivo or None,
        "fonte_stf": f"{BASE}?base=26&sumula={sid}",
        "observacao": OBSERVACOES.get(numero),
    }


def _conferir_tabelas(ids: dict[int, int]) -> None:
    """Barra incoerência entre o que o portal lista e o que a tabela curada cobre."""
    sem_data = sorted(n for n in ids if n not in DATAS)
    if sem_data:
        raise SystemExit(
            f"súmulas no portal sem data em DATAS: {sem_data}. "
            "Acrescente a data da sessão de aprovação (ela entra no URN) antes de reindexar."
        )
    sobrando = sorted(n for n in DATAS if n not in ids)
    if sobrando:
        raise SystemExit(f"DATAS tem súmula que o portal não lista: {sobrando}")
    ruins = {n: s for n, (s, _) in SITUACAO.items() if s not in _SITUACOES}
    if ruins:
        raise SystemExit(f"situação fora do vocabulário {_SITUACOES}: {ruins}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--limite", type=int, default=0,
        help="baixa só as N primeiras súmulas (para teste rápido do coletor).",
    )
    args = ap.parse_args()

    with httpx.Client(
        timeout=60.0, headers=_HEADERS, follow_redirects=True, verify=_contexto_ssl()
    ) as client:
        indice = _fetch(INDICE, client)
        ids = ids_do_indice(indice)
        if not ids:
            raise SystemExit("nenhuma súmula no índice do portal — o HTML mudou de forma?")
        print(f"[súmulas] índice do STF: {len(ids)} súmulas (1..{max(ids)})")
        _conferir_tabelas(ids)

        numeros = sorted(ids)[: args.limite or None]
        validadas, falhas, divergentes = [], [], []
        for i, numero in enumerate(numeros, 1):
            sid = ids[numero]
            try:
                pagina = _fetch(f"{BASE}?base=26&sumula={sid}", client)
                enunciado, marca = extrair_enunciado(pagina, numero)
            except Exception as exc:
                falhas.append(f"SV {numero}: {type(exc).__name__}: {exc}")
                print(f"[{i:3}/{len(numeros)}] SV {numero:<3} FALHOU: {exc}")
                continue
            finally:
                time.sleep(settings.http_polite_delay)  # coleta educada

            confere = _conferir_situacao(numero, marca, enunciado)
            if confere.startswith("DIVERGE"):
                # Situação errada = corpus servindo súmula morta como viva: não entra.
                divergentes.append(f"SV {numero} {confere}")
                print(f"[{i:3}/{len(numeros)}] SV {numero:<3} REJEITADA: {confere}")
                continue
            validadas.append(_entrada(numero, sid, enunciado))
            situacao = validadas[-1]["situacao"]
            rotulo = "" if situacao == "vigente" else f", {situacao}"
            print(f"[{i:3}/{len(numeros)}] SV {numero:<3} ok ({len(enunciado)} chars{rotulo})")

    validadas.sort(key=lambda e: e["numero"])
    SUMULAS_VINCULANTES_PATH.write_text(
        json.dumps(validadas, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"\n[súmulas] {len(validadas)} validadas -> {SUMULAS_VINCULANTES_PATH}")
    if divergentes:
        print(f"[súmulas] rejeitadas por situação divergente: {'; '.join(divergentes)}")
    if falhas:
        print(f"[súmulas] falhas ({len(falhas)}): {'; '.join(falhas)}")
    return 1 if falhas or divergentes else 0


if __name__ == "__main__":
    sys.exit(main())
