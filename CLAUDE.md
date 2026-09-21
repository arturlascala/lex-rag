# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é

MCP server de RAG sobre a legislação federal brasileira. Princípio central: **anti-alucinação** — toda resposta é o texto literal do dispositivo + URN-LEX + URL canônica da fonte, nunca paráfrase. Idioma do código, comentários, commits e docs: **português brasileiro com acentuação correta**.

## Comandos

Windows usa `.\tasks.ps1 <alvo>`; Linux/macOS usa `make <alvo>` (mesmos nomes). Python **3.12 obrigatório** (`py -3.12`); o venv fica em `.venv`.

```powershell
.\scripts\setup_env.ps1 [-Cpu]       # cria .venv e instala torch (CUDA cu121 por padrão; -Cpu sem GPU)
.\tasks.ps1 test                     # pytest -m "not network" -q
.\tasks.ps1 lint                     # ruff check src tests scripts (line-length 100)
.\tasks.ps1 serve | daemon-start | daemon-stop | daemon-status
.\tasks.ps1 update                   # delta incremental (prefira POST /update no daemon quente)
.\tasks.ps1 descobrir-novas          # leis novas desde o último ponto + verificar_parser (não toca o Qdrant)
.\tasks.ps1 bootstrap                # recarga total — PARE O DAEMON ANTES
.\tasks.ps1 snapshot-criar | snapshot-restaurar <zip|URL> [-Forcar]   # corpus pré-montado (Release)
```

Um teste só: `.venv\Scripts\python -m pytest tests/unit/test_ingest.py::test_nome -q`. Testes de rede têm marker `network` (excluído por padrão); `tests/integration/test_search.py` auto-skipa se `data/qdrant` estiver vazio e carrega os modelos (lento).

Scripts de manutenção do corpus (rodar com `.venv\Scripts\python`): `scripts/descobrir_{lcps,ordinarias,decretos,sumulas,sumulas_stf}.py` geram os JSONs de registro (`verificar_sumulas.py [--stf]` confere os de súmula); `scripts/gerar_tabela_corpus.py` regrava a tabela do corpus no README a partir do `REGISTRO` (rode após cada lote); `scripts/verificar_parser.py --novos --baixar` **antes de indexar qualquer lote**; `scripts/reindexar_do_cache.py` reparseia `data/raw/` sem rede (para correção de parser; pare o daemon); com `--novos` indexa só as normas ausentes do `state` (lote recém-verificado), e com `--slug` reprocessa normas nomeadas. `scripts/descobrir_novas.py` varre as leis ordinárias sancionadas depois do último ponto (API de metadados do LexML, a partir da maior lei do catálogo ou de onde a rodada anterior parou em `triagem_novas.json`), classifica pela ementa (`ingest/descoberta_novas.py`: ruído, coberta pelo consolidado, mãe ausente, revisar, candidata) e grava as candidatas validadas em `registro_novas.json`; as "mãe ausente" ficam para decisão humana (o certo é incluir a norma alterada na lista curada, não a alteradora). O `update` **não** descobre norma nova — só reprocessa o catálogo.

## Arquitetura

```
Claude Code ──stdio──> mcp_server/server.py (cliente fino, sem torch/qdrant)
                            │ HTTP 127.0.0.1:8765  (service/client.py)
                            ▼
                     service/app.py (FastAPI) — daemon residente
                     BGE-M3 + reranker quentes; DONO ÚNICO do Qdrant embedded
                     endpoints reusam mcp_server/tools/* (lógica num lugar só)
```

- **Qdrant embedded** (`data/qdrant/`) é um diretório com lock de arquivo: só um processo o abre. Bootstrap, reindexação, snapshot e testes de integração conflitam com o daemon no ar — por isso os scripts checam `/health` e recusam. O `update` semanal (`scripts/weekly_update.ps1`) prefere `POST /update` no daemon e só cai para a CLI se ele estiver fora.
- **Busca** (`retrieve/hybrid_search.py`): BGE-M3 gera vetor denso + esparso da consulta → dois prefetches no Qdrant fundidos por RRF → reranker BGE-reranker-v2-m3 reordena e corta por `reranker_score_min` (0,55). O texto passado ao reranker é o **mesmo texto contextualizado** do embedding (`[epígrafe] [parent_label] Label: texto`, ver `index/chunker.py`) — mudar um sem o outro degrada a busca.
- **Chunking**: 1 dispositivo (artigo) = 1 ponto; `point_id = uuid5(urn_lex#path)`, determinístico, então reindexar sobrescreve em vez de duplicar. O payload guarda o texto literal.
- **Anexos** (lote 11): a partir do cabeçalho `ANEXO` (ou do primeiro `Artigo N` depois do fecho, nos tratados) o artigo sai com prefixo (`anexo_art_1`, `anexo_ii_art_3`) e o anexo sem artigo vira texto em partes (`anexo_i`, `anexo_i_p2`). Quando o texto apenso **é** o documento (CLT no DL 5.452, RIR, RPS, BPC), o `recorte` do `NormaMeta` descarta o ato de aprovação e o apenso fica dono de `art_N` — o `verificar_parser` aponta caso novo ("texto apenso sem recorte"). O ADCT é documento próprio (`adct_1988`), por recorte da mesma página da CF.
- **Device** (`device.py`): CUDA+fp16 se houver, senão CPU fp32; override `LEX_RAG_DEVICE`. Config toda em `config.py` (pydantic-settings, prefixo `LEX_RAG_`, lê `.env`).
- **Catálogo** = `ingest/urn_mapper.py::REGISTRO`: `REGISTRO_CURADO` (à mão) mesclado com os JSONs gerados (`registro_lcp/ordinarias/decretos.json`, `sumulas_vinculantes.json`, `sumulas_stf.json`, `registro_novas.json`). Em conflito de URN, o curado vence, e `registro_novas.json` perde para todos (promover uma lei descoberta à lista curada não a duplica). Para incluir norma avulsa: entrada curada + `update`.
- **Três caminhos de ingestão**, despachados por `meta.tipo` em `ingest/source.py` e em `parse_norma`:
  1. **Planalto** (`planalto_fetcher.py` + `html_parser.py`): HTML em **Windows-1252** (não latin-1 — a faixa 0x80-0x9F carrega travessão e aspas), UA de navegador obrigatório (o WAF derruba outros), coleta sequencial com `http_polite_delay`.
  2. **Jurisprudência** (`jurisprudencia.py`): Súmulas Vinculantes (`sumula_vinculante`) e súmulas simples do STF (`sumula_stf`, lote 22-A) servidas do JSON versionado, norma de dispositivo único (`path=enunciado`); a situação (cancelada/revogada/superada) é a que o STF marca. A data do URN vem da página do STF; para os enunciados 1–370 sem data impressa vale 13/12/1963 (Súmula original), e 72 acima de 370 ficaram fora por falta de data. Existe porque o parser só produz dispositivo a partir de `Art. N` e um enunciado sairia com **zero dispositivos = sucesso silencioso** (entra no `state.sqlite`, nenhum ponto no índice, nenhum erro).
  3. **Parlamento** (`parlamento_fetcher.py`): regimentos e resoluções das Casas (tipos `regimento` e `resolucao`), do sítio de cada Casa, UTF-8, sempre com `recorte` — a página serve mais de um documento ou o rodapé do portal, e o fecho da Casa não tem o "Nº da Independência" que corta assinaturas no Planalto. No Senado, a API de dados abertos dá o id da norma e a página `norma/{id}` aponta a "Compilação Multivigente" (ver `_RESOLUCOES_SENADO` em `urn_mapper.py`).
- **Estado** (`storage/state.py`, `data/state.sqlite`): hash do conteúdo + `pipeline_version` por norma. O `update` delta reindexa só o que mudou de hash **ou** cuja versão de pipeline não bate com `settings.pipeline_version` — **bump `pipeline_version` em `config.py` após qualquer fix de parser/chunker**, senão o delta não reprocessa nada.
- No update, falha de download **pula** a norma preservando os pontos atuais; o fallback para fixture (`tests/fixtures/`, 5 normas) é só do bootstrap.
- `src/lex_rag/__init__.py` pré-carrega `pyarrow` no Windows antes do `qdrant_client` (access violation na ordem inversa). Não mova esse import.

## Distribuição

O git guarda só o código; `data/` é ignorado. O corpus (índice + `state.sqlite` + `data/raw`) circula como `dist/lex-rag-snapshot.zip` anexado a Release (`scripts/snapshot.py`), com `MANIFEST.json` gravando a versão do `qdrant-client` — por isso ela é **pinada exata** no `pyproject.toml`; ao subir a versão, gere e publique snapshot novo. Fluxo de lote novo: commit → `daemon-stop` → `snapshot-criar` → `gh release create vX.Y.Z dist/lex-rag-snapshot.zip` → `daemon-start`.

## Histórico e decisões

`PLANO_DE_IMPLEMENTACAO.md` registra os 11 bugs de parser já encontrados (com heurísticas de detecção reproduzíveis), o histórico dos 10 lotes do corpus e o backlog. Consulte antes de mexer em `html_parser.py`: quatro das nove expansões do corpus revelaram bug de parser, e os suspeitos apontados por `verificar_parser.py` devem ser inspecionados um a um mesmo quando parecem ruído conhecido.
