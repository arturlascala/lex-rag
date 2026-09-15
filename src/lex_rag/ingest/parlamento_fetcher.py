"""Download das páginas de regimento e de resolução publicadas pelas Casas do Congresso.

Caminho separado do Planalto por causa da **decodificação**. As páginas do
Senado (``legis.senado.leg.br``) e da Câmara (``www2.camara.leg.br/legin``) são
servidas em UTF-8 e declaram o charset no cabeçalho; ``decode_planalto`` supõe
Windows-1252 quando não há BOM, e aplicá-lo aqui devolveria ``CÃ¢mara`` no lugar
de ``Câmara`` em cada palavra acentuada — a mesma classe de estrago do bug nº 8,
invertida, e igualmente silenciosa (o parser continua achando os artigos).

Ler o charset declarado — que é o que ``resp.text`` do httpx faz — resolve para
estas duas fontes e **não** serviria para o Planalto, que não declara nenhum.
Daí não haver uma função só: a suposição certa depende da fonte.
"""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from lex_rag.config import settings

# Tipos do corpus servidos por este módulo, e não pelo caminho do Planalto: os
# regimentos e as resoluções das Casas (lote 21), todos no portal do Senado ou
# da Câmara.
TIPOS_PARLAMENTO = frozenset({"regimento", "resolucao"})


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def fetch(url: str) -> str:
    headers = {"User-Agent": settings.http_user_agent}
    with httpx.Client(follow_redirects=True, timeout=60.0, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text
