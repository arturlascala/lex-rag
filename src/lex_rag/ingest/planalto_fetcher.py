"""Download de páginas do Planalto (HTML em Windows-1252, com casos UTF-16/UTF-8)."""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from lex_rag.config import settings


def decode_planalto(content: bytes) -> str:
    """Decodifica a página do Planalto conforme o BOM.

    A maioria das páginas vem em Windows-1252, mas algumas (ex.: Lei Maria da
    Penha) são servidas em UTF-16, e há casos com BOM UTF-8. Sem essa detecção,
    o texto UTF-16 vira letras intercaladas por bytes nulos e o parser não
    encontra os artigos.

    O byte-a-byte importa: cp1252 e ISO-8859-1 só divergem na faixa 0x80-0x9F,
    que em ISO-8859-1 são códigos de controle C1 — nunca texto. O Planalto usa
    essa faixa para pontuação tipográfica, então decodificar como latin-1
    entregava caractere de controle no lugar de travessão, aspas e reticências:
    **7.571 ocorrências em 284 normas**. Além de corromper o texto literal (que
    é o produto do sistema), isso cegava o filtro de artigo citado entre aspas
    do html_parser, porque a aspa de abertura chegava como U+0093 e não “.
    """
    # errors="ignore": algumas páginas UTF-16 chegam com um byte final truncado
    # (comprimento ímpar); descartá-lo não afeta o texto da norma.
    if content[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return content.decode("utf-16", errors="ignore")
    if content[:3] == b"\xef\xbb\xbf":
        return content.decode("utf-8-sig", errors="ignore")
    try:
        return content.decode("cp1252")
    except UnicodeDecodeError:
        # cp1252 deixa 5 bytes indefinidos (0x81, 0x8D, 0x8F, 0x90, 0x9D);
        # página que os use cai para latin-1, que aceita a faixa inteira.
        return content.decode("latin-1")


def _vale_repetir(exc: BaseException) -> bool:
    """Repete falha transitória (timeout, 5xx, conexão), nunca resposta 4xx.

    A resolução de URL canônica testa variantes até uma existir, então o 404 é
    o caso *esperado* e determinístico: repetí-lo três vezes com espera
    exponencial só multiplica o custo da descoberta de um lote novo.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return not (400 <= exc.response.status_code < 500)
    return True


@retry(
    reraise=True,
    retry=retry_if_exception(_vale_repetir),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
def fetch(url: str) -> str:
    headers = {"User-Agent": settings.http_user_agent}
    with httpx.Client(follow_redirects=True, timeout=30.0, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return decode_planalto(resp.content)
