# lex-rag

MCP server de RAG sobre a base normativa federal brasileira (Constituição, Leis Complementares, Leis Ordinárias, Decretos). Foco em anti-alucinação: o MCP devolve **sempre texto literal** do dispositivo + URN-LEX + URL canônica do Planalto, e nunca paráfrase.

## Stack

- **Python 3.12**
- **Qdrant embedded** (sem Docker — escreve em `data/qdrant/`)
- **BGE-M3** (denso + esparso num único pass) — embedding local, acelerado por GPU quando disponível
- **BGE-reranker-v2-m3** — reranker (Fase 2)
- **MCP SDK** (stdio para Claude Desktop / Claude Code)
- **Daemon de inferência** (FastAPI/uvicorn) — segura os modelos quentes; o MCP server é um cliente fino que fala com ele por HTTP no loopback

## Arquitetura: daemon de inferência

Os modelos (BGE-M3 + reranker, ~4,6 GB) são carregados **uma única vez** por um daemon residente (`lex_rag.service`), que também é o dono único do Qdrant embedded. O MCP server que o Claude Code inicia é apenas um **cliente HTTP fino** — sobe em milissegundos e encaminha cada consulta ao daemon.

```
Claude Code ──spawn──> MCP server (cliente fino)
                           │ HTTP 127.0.0.1:8765
                           ▼
                 Daemon de inferência (lex_rag.service)
                 BGE-M3 + reranker quentes + Qdrant
```

Por que: sem o daemon, cada sessão do Claude recriava o processo MCP e recarregava os ~4,6 GB na primeira pergunta (cold start de vários segundos). Com o daemon, esse custo é pago **uma vez** ao iniciá-lo; toda consulta seguinte (e qualquer reinício do Claude) responde quente.

**É preciso ter o daemon no ar para o MCP funcionar.** Controle manual (sob demanda):

```powershell
.\tasks.ps1 serve          # foreground: sobe o daemon e mostra os logs (Ctrl+C encerra)
# ou, em background:
.\tasks.ps1 daemon-start   # inicia escondido (pythonw), grava o PID em data\daemon.pid
.\tasks.ps1 daemon-status  # confere o processo + GET /health
.\tasks.ps1 daemon-stop    # encerra e libera a VRAM
```

## Hardware / GPU

A escolha de device é automática (`src/lex_rag/device.py`): usa **CUDA + fp16** quando há GPU NVIDIA, senão cai para CPU em fp32. Para forçar, defina `LEX_RAG_DEVICE=cuda` ou `LEX_RAG_DEVICE=cpu`.

Desenvolvido numa RTX 3060 (12 GB), mas **roda sem GPU dedicada**. O que muda em CPU:

- **Consulta:** embedar a pergunta é rápido; o gargalo é o reranker sobre os 40
  candidatos — espere alguns segundos por busca, contra frações de segundo em GPU.
- **RAM:** os dois modelos em fp32 ocupam ~5 GB; 8 GB é o mínimo prático, 16 GB
  é confortável. Em disco, os modelos baixados do Hugging Face somam ~6,5 GB.
- **Indexar o corpus do zero (`bootstrap`) leva horas.** Por isso o corpus é
  distribuído pronto — veja [Instalação a partir do snapshot](#instalação-a-partir-do-snapshot).
- Apple Silicon: não há tratamento de `mps`; cai em CPU e funciona.

## Corpus

São **761 documentos**: **696 normas** baixadas **ao vivo do Planalto** — o
núcleo essencial curado à mão (35), **todas as Leis Complementares** (conjunto
fechado, descoberto no quadro oficial), um lote curado de **leis ordinárias de
consulta frequente** (388) e um núcleo de **decretos** (42) —, os **63
enunciados de Súmula Vinculante do STF**, servidos de um JSON versionado, e os
**2 regimentos internos** do Senado e da Câmara, baixados do sítio de cada Casa.

- **Constituição Federal de 1988**
- **Códigos:** Civil, Penal, Processo Penal, Processo Civil, Tributário Nacional,
  CLT, Defesa do Consumidor, Trânsito, Eleitoral, Florestal, Penal Militar,
  Processo Penal Militar, Brasileiro de Aeronáutica, de Telecomunicações,
  de Mineração
- **Leis Complementares:** todas (LC 1/1962 à mais recente, incluindo 95/1998,
  101/2000 — LRF, 116/2003 — ISS, 123/2006 — Simples, 214/2025 — reforma
  tributária)
- **Leis ordinárias**, por eixo: processo e carreiras jurídicas (MS, ação civil
  pública, mediação, OAB, LONMP), controle e finanças públicas, administração e
  contratação pública, eleitoral, penal extravagante, civil e empresarial,
  urbano e ambiental, agrário, saúde, educação, cultura e esporte, trabalho,
  transportes, energia e mineração, sistema financeiro e tributário,
  comunicações e direitos sociais. Entre os **regimes de incentivo
  setorial**, a **Rota 2030** (Lei 13.755/2018) e o **Mover** (Lei
  14.902/2024) entram como par, porque o Mover sucede a Rota 2030 e revoga
  dispositivos dela — quem consulta um precisa do outro para saber o que
  sobrou —, ao lado do **Reidi** (Lei 11.488/2007)
- **Direito econômico:** além da ordem econômica já coberta (defesa da
  concorrência, liberdade econômica, consumidor, as agências reguladoras e a
  Lei 13.848/2019, concessões, PPP, estatais), entram os quatro flancos que
  faltavam — **defesa comercial** (Lei 9.019/1995 e o Decreto 8.058/2013, o
  regulamento antidumping) com a **Zona Franca de Manaus** (DL 288/1967, cujo
  texto-base faltava embora a Lei 8.387/1991, que o altera, já estivesse no
  corpus); **resolução bancária** (Leis 6.024/1974 e 9.447/1997, que a Lei
  11.101/2005 exclui do seu âmbito) com o processo sancionador do BCB e da CVM
  (Lei 13.506/2017); **infraestrutura de mercado** (Lei 10.214/2001, o SPB, base
  da Lei 12.865/2013, já presente) e o mercado de capitais de 1965 (Lei
  4.728/1965); e os **títulos que financiam a atividade produtiva** — CPR,
  CDA/WA, CDCA, LCA e CRA, LCI, CCI e CCB, arrendamento mercantil, consórcio,
  debêntures de infraestrutura, PNMPO e Pronampe. Junto vieram portos (Lei
  12.815/2013) e a relicitação de contratos de parceria (Lei 13.448/2017), o
  registro público de empresas (Lei 8.934/1994) e os canais de distribuição
  (representação comercial e Lei Ferrari)
- **Fundos:** as leis que instituem ou disciplinam os principais fundos
  federais — constitucionais de financiamento (FNO/FNE/FCO) e garantidores
  (FGO, FGI, FGE), de investimento e patrimoniais (FII, FIP-IE, *endowments*),
  socioambientais (FNMA, Fundo Clima, FNDF), de infraestrutura e comunicações
  (Fust, Funttel, Fistel, FMM, FNHIS, CDE, FCVS), o FNDCT e os fundos setoriais
  de C&T que o abastecem, além de FNDE, FCDF e audiovisual
- **Políticas nacionais:** as leis que **instituem ou definem** uma Política
  Nacional — conjunto levantado por varredura exaustiva, não por memória
  (quadros oficiais do Planalto para 1988-2000 e a API de metadados do LexML
  para 1934-2026, 15.396 leis, filtrando a ementa). Ficaram de fora só as
  revogadas ou superadas. Junto vieram as correlatas estruturantes do mesmo
  tipo — Sistema Nacional (Sinase, Sinaes, Sine, Sinamob, prevenção à tortura,
  sementes e mudas, marco do SNC) e Plano Nacional (gerenciamento costeiro,
  Pnatrans, PNE 2026)
- **Leis orçamentárias:** a **parte textual** da LDO e da LOA de cada exercício
  de **2012 a 2026** (15 pares). Entra a lei que fixa as diretrizes ou que
  estima a receita e fixa a despesa; ficam de fora as que só as alteram e as
  dezenas anuais de crédito suplementar, especial e extraordinário. A parte
  textual é o que o pipeline indexa por construção — os anexos são tabelas, e o
  parser só produz dispositivo a partir de artigo (a LOA de 2024 tem 309 KB de
  HTML e rende 10 artigos; a LDO, 130 a 199). O apelido leva o exercício
  (`LDO 2024`), o que distingue na busca artigos que se repetem quase iguais de
  um ano para o outro
- **Decretos:** o que **regulamenta** lei já presente no corpus ou **consolida**
  um regulamento de consulta frequente — RIR, RIPI, Regulamento Aduaneiro, RPS,
  IOF, ITR, processo administrativo fiscal e eSocial; contratações públicas sob
  a Lei 14.133 (registro de preços, agente de contratação, plano anual,
  credenciamento, margem de preferência) e o par do regime antigo (pregão
  eletrônico, SRP da 8.666); administração e integridade (LAI, anticorrupção,
  governança, Código de Ética, PNDP, MROSC); direitos e consumidor (SUS, BPC,
  acessibilidade, migração, Bolsa Família, SNDC, SAC, comércio eletrônico); e
  setoriais (infrações ambientais, energia, ANEEL, desarmamento, florestas
  públicas)
- **Regimentos internos:** o **RISF** (Resolução do Senado Federal nº 93, de
  1970 — 448 dispositivos) e o **RICD** (Resolução da Câmara dos Deputados nº
  17, de 1989 — 316), no texto compilado que cada Casa publica. Entram porque o
  rito das Casas não está na lei: prazo de emenda, regime de urgência, quórum,
  competência de comissão e questão de ordem são matéria regimental, e sem eles
  o corpus respondia processo legislativo só pelo art. 59 e seguintes da
  Constituição. O Planalto não os publica, então são a única parte do corpus com
  fonte fora dele — e a página de cada Casa serve **mais de um documento na
  mesma URL** (a da Câmara traz a resolução promulgadora, o Regimento anexo e o
  Código de Ética), daí o campo `recorte` do catálogo. Ficam de fora, por ora, o
  **Regimento Comum do Congresso Nacional** e o **Código de Ética e Decoro
  Parlamentar** da Câmara
- **Súmulas Vinculantes do STF:** os **63 enunciados**, do portal oficial. É a
  única jurisprudência do corpus, e entra por ter força normativa *erga omnes*
  (CF, art. 103-A): é o degrau entre a lei e o acórdão, não uma amostra de
  julgados. Acórdãos, votos, informativos e ementas de ADI/ADC continuam **fora
  de escopo** — a proposta é conhecimento jurisprudencial sintético, não peça
  processual. As duas fora de vigor entram marcadas em vez de omitidas (a SV 9,
  cancelada em 2025, e a SV 30, cuja publicação foi suspensa em 2010 e que nunca
  produziu efeitos): o default `somente_vigente` as esconde da busca comum, e
  quem as procura recebe o enunciado com a marca em vez de silêncio

O catálogo fica em `src/lex_rag/ingest/urn_mapper.py` (`REGISTRO`): o núcleo
curado à mão (`REGISTRO_CURADO`) mesclado com quatro registros gerados e
validados — `registro_lcp.json` (de `scripts/descobrir_lcps.py`, a partir do
quadro oficial), `registro_ordinarias.json` (de
`scripts/descobrir_ordinarias.py`, que resolve a URL canônica, já que o Planalto
não a deriva do número, e confere a data contra a epígrafe impressa na página),
`registro_decretos.json` (de `scripts/descobrir_decretos.py`, pela mesma
mecânica, com as convenções de URL e o rótulo de epígrafe próprios da espécie) e
`sumulas_vinculantes.json` (de `scripts/descobrir_sumulas.py`). Em conflito de
URN, a entrada curada vence.

Para incluir uma norma avulsa, acrescente uma entrada curada com o URN-LEX e a
URL canônica e rode `bootstrap` (ou `update`). Para crescer o corpus por lote,
acrescente as candidatas a `CANDIDATAS` em `scripts/descobrir_ordinarias.py` e
rode o script (ele reaproveita as URLs já resolvidas e só vai à rede pelas
novas); para LC nova promulgada, rode `scripts/descobrir_lcps.py`. Depois de
qualquer lote, **rode `scripts/verificar_parser.py --novos --baixar` antes de
indexar**: das nove expansões do corpus, quatro revelaram bug de parser e uma um
bug de decodificação — achá-lo antes da carga custa uma correção em vez de uma
reindexação inteira. Vale inspecionar os suspeitos um a um, mesmo os que
parecem só o ruído já conhecido: foi assim que apareceram os bugs nº 8 e nº 9.

As **súmulas seguem outro caminho**, porque a forma do documento é outra: um
enunciado único, sem articulação. O parser só produz dispositivo a partir de
marcador `Art. N`, então uma súmula rodada nele sairia com zero dispositivos — e
zero dispositivo é sucesso silencioso (a norma vai para o `state.sqlite`, nenhum
ponto entra no índice, nada acusa erro). O dispatch fica em dois pontos por onde
bootstrap, update e reindexação já passam — `ingest/source.py` e `parse_norma` —,
e leva a `ingest/jurisprudencia.py`, que monta uma norma de dispositivo único
(path `enunciado`). O caminho do Planalto não é tocado.

Outra diferença: o enunciado **não é rebaixado a cada update**, é servido do
próprio `sumulas_vinculantes.json` versionado. São 63 textos curtos que o STF
edita uma ou duas vezes por ano; um scraper vigiando isso em produção custaria
mais manutenção do que a edição que evita. O hash que decide reindexação é o do
JSON canônico da entrada, então reindentar o arquivo não reindexa nada e editar
uma súmula reindexa só ela. Para incorporar súmula nova ou cancelamento, rode
`python scripts/descobrir_sumulas.py` (recolhe os enunciados do portal do STF e
confere a situação que ele publica contra a curada) e depois
`python scripts/verificar_sumulas.py`, que é o `verificar_parser.py` desse lote:
confere numeração sem buraco, URN batendo com a data de aprovação, enunciado sem
mojibake nem truncamento, e vocabulário de situação. As datas de sessão e DJe
não estão na página e vivem na tabela `DATAS` do script de descoberta.

Quando o que mudar for o **parser**, e não o conteúdo no Planalto, reindexe com
`scripts/reindexar_do_cache.py`: o `update` decide o que refazer pelo hash do
HTML, então correção de parser não dispara reindexação nenhuma, e o `bootstrap`
rebaixaria as 696 normas — o portal estrangula a conexão bem antes do fim.
Reparsear o HTML já em `data/raw/` dá o mesmo resultado sem tocar na rede. Como
ele recria a coleção, **pare o daemon antes**.

Para **descobrir o que falta** num recorte temático, a API pública de metadados
do LexML (`https://normas.leg.br/api/public/metadados/simples?urn=...`) devolve
data e ementa oficiais por URN e aceita `urn:lex:br:federal:lei:{ano};{numero}`,
o que permite varrer a numeração inteira sem tocar no Planalto. Duas ressalvas:
o `urn` casa o número por **sufixo** (pedir `lei:1962;118` devolve a Lei 4.118),
então confira o `name` da resposta contra o número pedido; e a busca do LexML
(`www.lexml.gov.br/busca/SRU`) está atrás de desafio de segurança — só a API de
metadados serve.

As 5 primeiras normas curadas têm um HTML offline em `tests/fixtures/`, usado
como fallback quando o download falha (só no bootstrap — no `update` uma falha
de download preserva o índice atual em vez de regredi-lo).

> O Planalto recusa User-Agents não-navegador (derruba a conexão); por isso o
> fetcher usa um UA de navegador e faz a coleta de forma sequencial e educada
> (`http_polite_delay`). O decodificador assume **Windows-1252** (não latin-1:
> a faixa 0x80-0x9F carrega travessão e aspas, que em latin-1 virariam
> caracteres de controle) e é ciente de BOM (algumas páginas vêm em UTF-16).

## Setup (Windows)

```powershell
.\scripts\setup_env.ps1        # cria .venv (Python 3.12) e instala torch CUDA + deps
.\scripts\setup_env.ps1 -Cpu   # idem, sem GPU NVIDIA (torch CPU)
.\tasks.ps1 smoke              # smoke test: indexa 3 artigos da CF e faz 1 busca
```

> Requer Python 3.12 acessível via `py -3.12`. Versões mais novas **não** atendem `requires-python`.

Em Linux/macOS, o `Makefile` (com `uv`) expõe os mesmos alvos: `make install-dev` (GPU) ou `make install-cpu`.

## Instalação a partir do snapshot

O git guarda só o código. O corpus pré-montado — índice Qdrant, `state.sqlite`
e o cache HTML das normas, ~620 MB — circula como um zip anexado a cada
[Release](../../releases) do repositório. Restaurá-lo dispensa o `bootstrap`
(horas de download do Planalto e de embedding), e é o **único caminho viável
sem GPU**.

```powershell
.\scripts\setup_env.ps1 -Cpu                                   # ou sem -Cpu, com GPU NVIDIA
.\tasks.ps1 snapshot-restaurar https://github.com/arturlascala/lex-rag/releases/latest/download/lex-rag-snapshot.zip
.\tasks.ps1 daemon-start                                        # 1ª vez: baixa ~6,5 GB de modelos do Hugging Face
.\tasks.ps1 daemon-status                                       # espere o /health responder
```

Um zip já baixado também serve (`snapshot-restaurar C:\caminho\lex-rag-snapshot.zip`);
`-Forcar` substitui um corpus existente. Em Linux/macOS:
`make snapshot-restaurar ORIGEM=<zip ou URL> [FORCAR=1]`. A URL `releases/latest/download/…`
aponta sempre para o Release mais recente; para um lote específico, use a página de Releases.

O zip traz um `MANIFEST.json` com a versão do `qdrant-client` que gerou o
índice — o formato do Qdrant embedded muda entre versões, então o
`pyproject.toml` fixa a versão exata e o `restaurar` avisa se a instalada for
outra. Depois de restaurado, o `update` semanal funciona normalmente: o
`state.sqlite` carrega os hashes, e só o que mudou no Planalto é reprocessado.

**Para publicar um snapshot** (mantenedor): pare o daemon, rode
`.\tasks.ps1 snapshot-criar` (ou `make snapshot-criar`) e anexe o
`dist/lex-rag-snapshot.zip` a um Release com a tag do lote (o nome do arquivo é
fixo de propósito, para a URL `latest` funcionar). O limite do GitHub é 2 GB por
arquivo.

## Comandos principais (Windows)

```powershell
.\tasks.ps1 bootstrap      # carga do corpus (baixa as ~696 normas do Planalto)
.\tasks.ps1 update         # delta incremental
.\tasks.ps1 serve          # daemon de inferência (foreground)
.\tasks.ps1 daemon-start   # daemon em background
.\tasks.ps1 daemon-stop    # encerra o daemon
.\tasks.ps1 daemon-status  # estado do daemon (/health)
.\tasks.ps1 mcp            # inicia MCP server (stdio) — exige o daemon no ar
.\tasks.ps1 test           # pytest (exclui marker 'network')
.\tasks.ps1 lint           # ruff check
.\tasks.ps1 clean          # remove caches
```

> **Pare o daemon antes de `bootstrap` e de `snapshot-criar`/`snapshot-restaurar`** (o daemon segura o lock do Qdrant).

Em Linux/macOS, o `Makefile` (com `uv`) expõe os mesmos alvos.

### Agendamento (atualização semanal)

`.\scripts\register_update_task.ps1` registra uma tarefa no Windows Task Scheduler (segunda, 03h) que roda `scripts\weekly_update.ps1`. O helper prefere o daemon (`POST /update`, reusando os modelos quentes) e cai para `lex-rag-update --mode delta` quando o daemon está fora do ar — evitando disputa pelo lock do Qdrant.

## Registro no Claude Desktop / Claude Code

Com o corpus no lugar (snapshot ou `bootstrap`), registre o servidor MCP (stdio). Lembre-se de subir o daemon (`.\tasks.ps1 serve` ou `daemon-start`) antes de usar as ferramentas.

**Claude Code** (na pasta do projeto; o comando grava o caminho absoluto do `.venv`):

```powershell
claude mcp add lex-rag -- "$PWD\.venv\Scripts\python.exe" -m lex_rag.mcp_server.server
```

```bash
claude mcp add lex-rag -- "$PWD/.venv/bin/python" -m lex_rag.mcp_server.server   # Linux/macOS
```

**Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json`), com o caminho absoluto do clone:

```json
{
  "mcpServers": {
    "lex-rag": {
      "command": "C:\\caminho\\para\\lex_rag\\.venv\\Scripts\\python.exe",
      "args": ["-m", "lex_rag.mcp_server.server"]
    }
  }
}
```

Ferramentas expostas: `pesquisar_norma`, `buscar_por_assunto`, `obter_dispositivo`, `listar_alteracoes`, `health`.

## Estrutura

- `src/lex_rag/ingest/` — descoberta (LexML), download (Planalto), parse, detecção de revogação
- `src/lex_rag/index/` — chunking, embedding, escrita no Qdrant
- `src/lex_rag/retrieve/` — busca híbrida, filtros, validação de grounding
- `src/lex_rag/mcp_server/` — tools MCP (cliente fino do daemon)
- `src/lex_rag/service/` — daemon de inferência (FastAPI) + cliente HTTP
- `src/lex_rag/update/` — pipeline incremental semanal
- `data/` — Qdrant embedded + HTML cru + state SQLite (gitignored)

## Status

Em desenvolvimento. Desenvolvido em Windows + GPU NVIDIA (CUDA); roda em CPU e, via `Makefile`, em Linux/macOS.

## Licença

MIT — veja [LICENSE](LICENSE). Os textos normativos indexados são de domínio público (Lei 9.610/1998, art. 8º, IV).
