"""Fonte do texto cru de um documento do corpus.

Em produção baixa da URL canônica do Planalto; se o download falhar e a norma
tiver um fixture offline (as 5 normas da carga original), cai para o arquivo
local. As demais normas dependem do download ao vivo.

Dois tipos não seguem esse caminho: o **jurisprudencial**, cujo texto mora no
JSON curado do repositório (ver ``ingest/jurisprudencia.py``), e o **regimento**,
publicado pela própria Casa e servido em UTF-8 (ver
``ingest/parlamento_fetcher.py``).
"""

from __future__ import annotations

import logging

from lex_rag.config import PROJECT_ROOT
from lex_rag.ingest import jurisprudencia, parlamento_fetcher, planalto_fetcher
from lex_rag.ingest.urn_mapper import NormaMeta

logger = logging.getLogger(__name__)

FIXTURES = PROJECT_ROOT / "tests" / "fixtures"


def obter_html(meta: NormaMeta, permitir_fixture: bool = True) -> str:
    """Texto cru do documento (download ao vivo, com fallback para fixture).

    ``permitir_fixture=False`` desliga o fallback: no update incremental, cair
    para o fixture antigo sobrescreveria o índice com conteúdo desatualizado —
    é melhor falhar e preservar os pontos atuais da norma.

    Para os tipos jurisprudenciais o parâmetro não se aplica: a fonte local não
    é um retrato velho de uma página remota, é a versão corrente do documento.
    Para os regimentos também não, por falta de fixture — falha de download os
    pula, que é o comportamento certo nos dois modos.
    """
    if meta.tipo in jurisprudencia.TIPOS_JURISPRUDENCIA:
        return jurisprudencia.conteudo_canonico(jurisprudencia.entrada_de(meta))
    if meta.tipo in parlamento_fetcher.TIPOS_PARLAMENTO:
        # Sem fixture: os regimentos entraram depois da carga original, e a
        # página das Casas precisa da decodificação pelo charset declarado.
        return parlamento_fetcher.fetch(meta.url_canonica)
    try:
        return planalto_fetcher.fetch(meta.url_canonica)
    except Exception as exc:  # fallback proposital para o fixture offline
        if permitir_fixture and meta.fixture and (FIXTURES / meta.fixture).exists():
            logger.warning(
                "download falhou para %s (%s); usando fixture %s",
                meta.slug, exc, meta.fixture,
            )
            return (FIXTURES / meta.fixture).read_text(encoding="latin-1")
        raise
