"""Testes de confiabilidade da coleta e do update incremental.

Cobrem o decode ciente de BOM, o fallback para fixture (permitido só no
bootstrap) e o delta que confere o Qdrant além do hash do state.sqlite.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from lex_rag.config import settings
from lex_rag.ingest.planalto_fetcher import decode_planalto
from lex_rag.ingest.urn_mapper import REGISTRO, NormaMeta


def test_decode_cp1252_default():
    assert decode_planalto("ação distânça".encode("latin-1")) == "ação distânça"


def test_decode_pontuacao_tipografica_do_planalto():
    # cp1252 e ISO-8859-1 só divergem em 0x80-0x9F, que em ISO-8859-1 são
    # controles C1. O Planalto põe pontuação ali; decodificar como latin-1
    # devolvia caractere de controle no lugar de travessão e aspas — corrompendo
    # o texto literal e cegando o filtro de artigo citado ("“Art. 14.").
    bruto = b"Art. 1\xba \x96 A Lei passa a vigorar: \x93Art. 14. Texto.\x94 (NR)"
    texto = decode_planalto(bruto)
    assert "–" in texto and "“Art. 14." in texto and "”" in texto
    assert not any("\u0080" <= c <= "\u009f" for c in texto)


def test_decode_cai_para_latin1_em_byte_indefinido():
    # 0x81 não existe em cp1252; a página inteira cai para latin-1 em vez de falhar.
    assert decode_planalto(b"Art. 1\xba \x81 texto") == "Art. 1º \x81 texto"


def test_decode_utf16_bom_com_byte_final_truncado():
    txt = "Art. 1º Coibir a violência doméstica"
    raw = txt.encode("utf-16") + b"\xff"  # comprimento ímpar: byte final truncado
    assert txt in decode_planalto(raw)


def test_decode_utf8_bom():
    txt = "Art. 5º Todos são iguais"
    assert decode_planalto(b"\xef\xbb\xbf" + txt.encode("utf-8")) == txt


def test_content_hash_ignora_script_injetado_pelo_waf():
    # O WAF do Planalto injeta <script id="f5_cspm"> com token aleatório a cada
    # resposta; o hash precisa ser estável para o delta não reindexar tudo.
    from lex_rag.ingest.raw_cache import content_hash

    base = "<html><body><p>Art. 1º Texto.</p></body></html>"
    waf_a = base.replace(
        "<body>", '<body><script id="f5_cspm">(function(){var t="AAA111";})()</script>'
    )
    waf_b = waf_a.replace("AAA111", "ZZZ999")
    assert content_hash(waf_a) == content_hash(waf_b) == content_hash(base)

    # Quebras de linha traduzidas (cache em modo texto no Windows) tampouco
    # podem mudar o hash — só conteúdo real muda o hash.
    crlf, lf = base.replace("<p>", "\r\n<p>"), base.replace("<p>", "\n<p>")
    assert content_hash(crlf) == content_hash(lf)
    assert content_hash(base.replace("Texto.", "Texto novo.")) != content_hash(base)


def test_fetch_nao_repete_404_mas_repete_falha_transitoria(monkeypatch):
    # A resolução de URL canônica testa variantes até uma existir: o 404 é o
    # caso esperado e determinístico, e repetí-lo triplicaria o custo de
    # descobrir um lote novo. Falha transitória (5xx/timeout) continua repetindo.
    import httpx

    from lex_rag.ingest import planalto_fetcher

    chamadas = []

    def responder(status: int):
        def _get(self, url, *a, **kw):
            chamadas.append(url)
            req = httpx.Request("GET", url)
            return httpx.Response(status, request=req, content=b"<p>ok</p>")

        return _get

    monkeypatch.setattr(httpx.Client, "get", responder(404))
    with pytest.raises(httpx.HTTPStatusError):
        planalto_fetcher.fetch("https://www.planalto.gov.br/ccivil_03/leis/l0000.htm")
    assert len(chamadas) == 1

    chamadas.clear()
    monkeypatch.setattr(httpx.Client, "get", responder(503))
    monkeypatch.setattr(planalto_fetcher.fetch.retry, "wait", lambda *a, **kw: 0)
    with pytest.raises(httpx.HTTPStatusError):
        planalto_fetcher.fetch("https://www.planalto.gov.br/ccivil_03/leis/l8666cons.htm")
    assert len(chamadas) == 3


def test_obter_html_fallback_para_fixture(monkeypatch):
    from lex_rag.ingest import source

    def boom(url):
        raise RuntimeError("Planalto fora do ar")

    monkeypatch.setattr(source.planalto_fetcher, "fetch", boom)

    # Com fixture: o bootstrap pode cair para o HTML offline.
    html = source.obter_html(REGISTRO["lcp_95_1998"])
    assert "Art. 1" in html

    # No update (permitir_fixture=False) a falha deve propagar, nunca regredir.
    with pytest.raises(RuntimeError):
        source.obter_html(REGISTRO["lcp_95_1998"], permitir_fixture=False)

    # Norma sem fixture: sempre propaga.
    with pytest.raises(RuntimeError):
        source.obter_html(REGISTRO["cp_2848_1940"])


class _FakeEmbedder:
    def encode_passages(self, texts):
        return np.full((len(texts), 1024), 0.1, dtype=np.float32), [{0: 1.0} for _ in texts]


@pytest.fixture
def pipeline_isolado(monkeypatch, tmp_path):
    """Pipeline apontando para uma norma sintética e armazenamento temporário."""
    from lex_rag.update import pipeline

    meta = NormaMeta(
        slug="fake",
        urn_lex="urn:lex:br:federal:lei:2020-01-01;1",
        tipo="lei",
        numero="1",
        data=date(2020, 1, 1),
        epigrafe="Lei nº 1, de 2020",
        ementa="Norma sintética de teste.",
        url_canonica="https://example.invalid/l1.htm",
    )
    monkeypatch.setattr(pipeline, "REGISTRO", {"fake": meta})
    monkeypatch.setattr(pipeline, "fonte_html", lambda m: "<p>Art. 1º Texto de teste.</p>")
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "qdrant_path", tmp_path / "qdrant")
    monkeypatch.setattr(settings, "raw_cache_path", tmp_path / "raw")
    monkeypatch.setattr(settings, "state_db", tmp_path / "state.sqlite")
    monkeypatch.setattr(settings, "collection_name", "test_update")
    monkeypatch.setattr(settings, "http_polite_delay", 0.0)
    return pipeline


def test_delta_reindexa_norma_ausente_do_qdrant(pipeline_isolado):
    from qdrant_client import QdrantClient

    pipeline = pipeline_isolado
    client = QdrantClient(":memory:")
    emb = _FakeEmbedder()

    # 1ª rodada: indexa a norma nova.
    r1 = pipeline.run("delta", client=client, embedder=emb)
    assert r1["atualizadas"] == {"fake": 1} and r1["total_pontos"] == 1

    # 2ª rodada: hash igual e pontos presentes → inalterada.
    r2 = pipeline.run("delta", client=client, embedder=emb)
    assert r2["inalteradas"] == ["fake"] and not r2["atualizadas"]

    # Coleção recriada sem zerar o state → delta deve reindexar mesmo com hash igual.
    client.delete_collection(settings.collection_name)
    r3 = pipeline.run("delta", client=client, embedder=emb)
    assert r3["atualizadas"] == {"fake": 1} and r3["total_pontos"] == 1


def test_delta_reindexa_apos_bump_do_pipeline_version(pipeline_isolado, monkeypatch):
    """Fix de parser não muda o HTML: quem dispara a reindexação é a versão."""
    from qdrant_client import QdrantClient

    pipeline = pipeline_isolado
    client = QdrantClient(":memory:")
    emb = _FakeEmbedder()

    pipeline.run("delta", client=client, embedder=emb)
    assert pipeline.run("delta", client=client, embedder=emb)["inalteradas"] == ["fake"]

    # Mesmo HTML, mesmo hash, pontos presentes — só a versão do pipeline mudou.
    # A versão nova é derivada da corrente para o teste não envelhecer junto com
    # o config (uma constante literal vira no-op no dia em que o config a alcança).
    monkeypatch.setattr(settings, "pipeline_version", settings.pipeline_version + "-teste")
    assert pipeline.run("delta", client=client, embedder=emb)["atualizadas"] == {"fake": 1}

    # Reindexado já sob a versão nova: volta a ser inalterada.
    assert pipeline.run("delta", client=client, embedder=emb)["inalteradas"] == ["fake"]
