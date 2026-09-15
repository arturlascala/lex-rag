# Plano de implementação — lex-rag

> Estado em 2026-09-15, **após os lotes 11 a 22-A da onda de expansão**
> ([PLANO_EXPANSAO_CORPUS.md](PLANO_EXPANSAO_CORPUS.md)). Corpus de **1.633
> documentos** e **49.482 pontos**: 893 normas do Planalto (38 curadas, com o
> ADCT em documento próprio + 235 LCs + 541 ordinárias + 84 decretos, entre
> eles 19 tratados promulgados), **63 Súmulas Vinculantes + 664 súmulas do
> STF** e **13 documentos das Casas** (RISF, RICD, Regimento Comum, resolução
> das MPs, CMO, dois Códigos de Ética e 6 resoluções do Senado do art. 52 da
> CF). Pendentes: lote 22-B (súmulas do STJ — sem fonte estruturada) e a
> Release do snapshot.
>
> Estado anterior, em 2026-08-31, após o 10º lote: 761 documentos / 39.393
> pontos (696 normas do Planalto, 63 SVs, 2 regimentos).
>
> São **três caminhos de ingestão**: o do Planalto (descoberta, download, parse
> de HTML em Windows-1252); o local de primeira classe, estreado no lote 7 para
> as súmulas, servido de JSON versionado — a separação é pela **forma do
> documento**, não pela fonte, porque o parser só produz dispositivo a partir de
> marcador `Art. N` e um enunciado único sairia dele com zero dispositivos, que
> é **sucesso silencioso** no pipeline; e o do sítio de cada Casa, estreado no
> lote 10, em UTF-8 e com **recorte** da página, porque a Casa serve mais de um
> documento na mesma URL.
>
> Os lotes 8 e 9 não mexeram em arquitetura: seguiram o procedimento já
> estabelecido — candidatas, descoberta, `verificar_parser --novos --baixar`,
> `POST /update` em delta —, e nenhum dos dois trouxe bug de parser. Os
> suspeitos que a verificação apontou (9 no lote 8, 15 no lote 9) eram, um a
> um, ruído já catalogado ou erro da própria fonte. O lote 10 seguiu o mesmo
> procedimento e também saiu sem bug de parser (0 suspeitos em 764
> dispositivos), mas exigiu duas peças novas — o fetcher das Casas e o recorte.
>
> Resta o item 6 (agendamento) e o backlog.
>
> Histórico: 266 normas / 14.657 pontos após o lote das LCs (2026-07-03);
> 347 / 20.920 após o 1º lote de ordinárias (2026-08-05); 479 / 28.148 após o
> 2º lote, que trouxe os bugs de parser nº 5, 6 e 7 (2026-08-07); 522 / 27.838
> após o 3º lote (fundos), em que o índice **encolheu ao crescer** porque o bug
> nº 8 — decodificação latin-1 no lugar de Windows-1252 — tirou mais lixo
> (1.355 fantasmas) do que os 43 fundos acrescentaram (2026-08-07); 594 /
> 29.209 após o 4º lote (políticas nacionais, 2026-08-10); 640 / 34.703 após o
> 5º lote (decretos, espécie nova, 2026-08-10); 670 / 37.267 após o 6º lote
> (LDOs e LOAs), que trouxe os bugs nº 9 e nº 10 (2026-08-12); 733 / 37.330
> após o 7º lote (súmulas vinculantes, que estreou o segundo caminho de
> ingestão, 2026-08-14); 736 / 37.456 após o 8º lote (regimes de incentivo
> setorial, 2026-08-18); 759 / 38.629 após o 9º lote (direito econômico,
> 2026-08-21); 762 / 41.552 após o 11º lote (ADCT + anexos, reindexação do
> cache, 2026-09-14); 856 / 44.631 após os lotes 13-15 (bug nº 11, 2026-09-14);
> 958 / 48.314 após os lotes 16, 17, 19 e 20 (tratados, 2026-09-14); 969 /
> 48.818 após o lote 21 (resoluções das Casas, 2026-09-15); 1.633 / 49.482
> após o lote 22-A (súmulas do STF, 2026-09-15).

---

## 🐛 Bug nº 1 (confirmado): normas em formato antigo corrompidas pelo regex de sufixo

### O problema

Nas leis que usam o formato **"Art. N - Texto"** (número seguido de traço
espaçado — padrão dos códigos antigos), o regex `_ART_MARK` em
[html_parser.py](src/lex_rag/ingest/html_parser.py) confunde a **primeira letra
do caput** com um **sufixo de artigo** (tipo "Art. 5º-A"). Resultado: rótulo
errado + primeira letra do texto faltando.

Reproduzido diretamente no parser:

```
'<p>Art. 312 - Apropriar-se o funcionário de dinheiro.</p>'
→ path='art_312_A', label='Art. 312-A', texto='propriar-se o funcionário...'
```

| No Planalto | Vira (errado) | Texto resultante |
|---|---|---|
| `Art. 2º - Ninguém pode ser punido...` (CP) | `Art. 2º-N` | "inguém pode ser punido..." |
| `Art. 1º - Esta Consolidação...` (CLT) | `Art. 1º-E` | "sta Consolidação..." |
| `Art. 312 - Apropriar-se o funcionário...` (CP) | `Art. 312-A` | "propriar-se o funcionário..." |

### Impacto (quantificado)

| Norma | Artigos | Corrompidos |
|---|---|---|
| Código Penal (DL 2.848/1940) | 431 | **299** |
| CLT (DL 5.452/1943) | 1.014 | **559** |
| Código de Processo Penal (DL 3.689/1941) | 851 | 1 |
| Constituição Federal | 415 | 1 |

Os dois códigos antigos mais importantes (Penal e CLT) estão majoritariamente
com **rótulo incorreto e caput truncado** — degradando tanto a busca quanto a
citação literal (que é o propósito anti-alucinação do sistema).

### Levantamento do formato real (feito — resolve a dúvida da versão anterior)

Varredura do corpus em `data/raw/` + fixtures:

- **Sufixos legítimos são colados** nos códigos: `Art. 10-A.`, `Art. 121-A.`,
  `Art. 359-M` (CLT, CP etc.).
- **Exceção única no corpus**: a LCP 95 grafa o sufixo **espaçado** —
  `Art. 18 - A (VETADO)`. É exatamente o caso protegido pelo teste
  `assert "art_18_A" in paths` em [test_ingest.py](tests/unit/test_ingest.py).
- Há **189 ocorrências** de `Art. N - X` espaçado com `X` maiúscula seguida de
  não-minúscula (CLT 143, CP 43, Lei 4.320 2, LCP 95 1). Fora a LCP 95, todas
  são **caputs começando com artigo definido**: `Art. 100 - A ação penal...`,
  `Art. 10 - O dia do começo...`.

Consequências para o desenho do fix:

- ❌ Aceitar **só sufixo colado** quebra o `art_18_A` da LCP 95.
- ❌ Lookahead "rejeita se vier minúscula depois" não basta: `Art. 100 - A ação`
  tem "A" seguida de espaço e viraria falso `art_100_A`.
- ✅ **Regra correta:** sufixo colado (`-[A-Z]` sem espaços, seguido de
  não-letra) **ou** sufixo espaçado apenas quando seguido de `\(\s*VETADO`.

```python
# hoje (over-matching):
_ART_MARK = re.compile(r"Art\.\s*(\d{1,3}(?:\.\d{3})*)(?:º|°|ª|o)?(?:\s*-\s*([A-Z]))?")

# direção do fix (validar contra o corpus antes de aplicar):
#   sufixo colado:   -A  -B  ... seguido de não-letra ("Art. 121-A. Matar...")
#   sufixo espaçado: " - A (VETADO" (caso único: LCP 95, art. 18-A)
_ART_MARK = re.compile(
    r"Art\.\s*(\d{1,3}(?:\.\d{3})*)(?:º|°|ª|o)?"
    r"(?:-([A-Z])(?![A-Za-zÀ-ÿ])|\s+-\s+([A-Z])(?=\s*\(\s*VETADO))?"
)
```

(Se usar dois grupos de sufixo, unificar com `m.group(2) or m.group(3)` no
`parse_dispositivos`.)

## 🐛 Bug nº 2 (confirmado, latente): comentários HTML vazam para o texto achatado

`bs4.Comment` é subclasse de `NavigableString`, e o `_flatten` de
[html_parser.py](src/lex_rag/ingest/html_parser.py) não o filtra. Testado:
`<!-- Art. 99 - Rascunho -->` vira um artigo fantasma `art_99_R` no índice.

Hoje **nenhuma** página do corpus tem "Art." dentro de comentário (varredura
feita em todo o `data/raw/`), então não há corrupção ativa — mas o Planalto usa
comentários extensivamente e basta uma recompilação de página para injetar
artigos fantasmas em silêncio. Fix de duas linhas, no mesmo PR do bug nº 1:

```python
from bs4 import Comment
# em _flatten, antes do tratamento de NavigableString:
if isinstance(node, Comment):
    continue
```

## 🐛 Bug nº 3 (descoberto na execução, corrigido): recreate do Qdrant local não purga pontos

No qdrant-client 1.18.0 em **modo local persistido** (`QdrantClient(path=...)`),
`delete_collection` não apaga os pontos do storage em disco e o
`create_collection` seguinte os **ressuscita**. Consequência: nenhum bootstrap
fazia carga limpa — a primeira reindexação pós-fix do parser terminou com
10.731 pontos para 9.838 chunks (893 paths corrompidos antigos, como
`art_312_A`, coexistindo com os corrigidos). Reproduzido em isolamento
(persistir → reabrir → delete+create → pontos antigos presentes).

**Fix aplicado:** `ensure_collection(recreate=True)` purga explicitamente os
pontos remanescentes após recriar (`delete` com filtro vazio). Teste de
regressão em [test_collection_schema.py](tests/unit/test_collection_schema.py).

## 🐛 Bug nº 5 (achado no lote 2, corrigido): marcador de artigo **sem ponto**

O Planalto grafa `Art 1º - ...`, sem ponto nenhum, nas leis dos anos 1940-1980.
O `_ART_MARK` exigia `Art\s*\.` e a norma inteira saía vazia: a **Lei 6.899/1981
parseava com ZERO dispositivos** — foi por isso que ela entrou como "falha de
download" na primeira rodada do lote (o `resolver` guardava só o erro da última
variante, um 404, e mascarava o `parse magro` que era o motivo real).

A grafia também aparece **solta no meio de normas grandes já indexadas**, onde o
efeito era perder o artigo em silêncio. Fix: ponto opcional (`Art\s*\.?\s*`),
com `\b` na frente para não casar "Art" no fim de outra palavra. Resgatou **21
marcadores em 11 normas**, todos conferidos um a um:

| Norma | Artigos resgatados |
|---|---|
| CLT | 554, 555, 571, 572, 575 |
| Duplicatas (5.474/1968) | 15, 16, 17, 18 |
| Código Penal | 187, 188 |
| Lei das Eleições | 25, 61 |
| Estatuto do Índio | 4º, 39 |
| CC, CTB, PNMA, CVM, LCP 33, LCP 148 | 1 cada (inclui `Art 1.636` e `Art 67-B`) |

## 🐛 Bug nº 6 (achado no lote 2, corrigido): artigo de **outra lei** indexado como se fosse da norma

Dispositivo alterador cita o texto novo entre aspas — *"A Lei nº 6.015 passa a
vigorar com a seguinte redação: “Art. 14. ...”"* — e o parser tratava esse
`Art. 14` como artigo **da norma sendo indexada**. É a alucinação que o projeto
existe para impedir: `obter_dispositivo` devolveria, sob o URN da Lei 13.465, um
artigo que é da Lei de Registros Públicos.

**661 dispositivos fantasma** no corpus, removidos pela regra "marcador
precedido de aspa de **abertura** não é artigo desta norma":

- aspa tipográfica `“`/`«` (288 casos) — sinal inequívoco, zero falso positivo
  na amostra;
- aspa ASCII `"` (373 casos) — ambígua (abre e fecha), aceita só depois de `:`
  ou do `)` de um `(NR)`, que é o que antecede toda abertura de citação.

O caso **oposto** é o que dá a medida do cuidado: depois da aspa de
**fechamento** (`...das obrigações.” Art. 92.`) vem artigo de verdade (21
ocorrências), e derrubá-lo perderia texto vigente. Por isso só a abertura entra
na regra, e os 205 casos de aspa ASCII sem `:`/`)` antes ficam de fora
(conservador: mantém fantasma, nunca perde artigo real).

O texto citado **não se perde**: continua no caput do artigo alterador, que é
onde ele de fato está.

## 🐛 Bug nº 7 (menor, corrigido junto): marca de veto roubava o path canônico

O Planalto imprime a marca de veto e, logo depois, a redação de verdade do mesmo
artigo. O placeholder vinha primeiro e ficava com `art_N`; o texto real ia para
`art_N__1`. Quem pedisse o dispositivo recebia `"(VETADO)"`. **12 dispositivos**
(CDC art. 15, PNMA art. 19, PIS art. 33, LC 3 arts. 8/10/13, SNUC art. 40...),
**11 deles pré-existentes**. Fix na mesma forma dos outros dois desempates do
parser: placeholder (veto ou linha pontilhada) é descartado **só quando outra
ocorrência da mesma base tem redação de verdade** — artigo vetado por inteiro
(LCP 95, art. 18-A) não tem concorrente e continua no índice.

## 🐛 Bug nº 8 (achado no lote 3, corrigido): página decodificada como latin-1

O Planalto serve **Windows-1252**, e o `decode_planalto` usava `latin-1`. As
duas codificações só divergem na faixa `0x80-0x9F` — que em ISO-8859-1 são
códigos de controle C1 e nunca aparecem em texto. O Planalto usa exatamente
essa faixa para pontuação tipográfica, então o corpus guardava **7.571
caracteres de controle em 284 normas (59% do corpus)** no lugar de:

| Byte | Vinha como | É |
|---|---|---|
| `0x96` | U+0096 (2.766×) | `–` travessão |
| `0x94` | U+0094 (2.214×) | `”` aspa de fechamento |
| `0x93` | U+0093 (2.196×) | `“` aspa de abertura |
| `0x92`, `0x85`, `0x91`, `0x95` | controle (395×) | `’` `…` `‘` `•` |

Dois estragos. O primeiro é direto: o sistema serve **texto literal** como
produto, e entregava caractere de controle no meio da citação. O segundo é
indireto e maior — a regra do bug nº 6 procura a aspa de abertura `“`, que
nessas páginas chegava como U+0093 e não casava. Corrigido o decode, o mesmo
filtro removeu **mais 1.355 artigos-fantasma** em 284 normas: o fix anterior
só alcançava um terço dos casos (661 de 2.016).

Fix: `cp1252` com queda para `latin-1` nos 5 bytes que o cp1252 deixa
indefinidos (`0x81`, `0x8D`, `0x8F`, `0x90`, `0x9D`), que não ocorrem em
nenhuma das 522 páginas do corpus. `pipeline_version` 0.3.0 → 0.4.0.

**Lição para os próximos lotes:** o bug nº 6 foi dado por resolvido com uma
medição que parecia completa (288 + 373 casos, amostra conferida à mão, zero
falso positivo). Estava certa e ainda assim cobria um terço do problema, porque
a medição rodou sobre o texto **já corrompido** pelo decode. Medir sobre o
artefato errado dá um número consistente e enganoso.

## ⚠️ Riscos de confiabilidade do `update` (promovidos da avaliação da codebase)

1. **Fallback para fixture pode regredir o índice.** No update semanal, se o
   download do Planalto falhar, [source.py](src/lex_rag/ingest/source.py) cai
   para o fixture *antigo*; o hash difere do que está indexado (versão viva) →
   o delta considera "mudou" e **sobrescreve o índice com conteúdo
   desatualizado**, silenciosamente. O fallback é adequado só no bootstrap
   inicial. No [pipeline.py](src/lex_rag/update/pipeline.py), falha de download
   deve ir para `falhas` (mantendo os pontos atuais), nunca substituir por
   fixture.
2. **Delta cego ao estado real do Qdrant.** [diff.py](src/lex_rag/update/diff.py)
   consulta só o `state.sqlite`. Se `data/qdrant/` for recriado/apagado sem
   apagar o state, o `update` responde "nenhuma norma alterada" sobre um índice
   vazio. Checagem barata: comparar a contagem de pontos da norma no Qdrant com
   `n_dispositivos` do state; divergiu → reindexar.

Ambos são **pré-requisitos do agendamento** (item 6): sem eles, uma queda do
Planalto numa madrugada regride o índice sem ninguém perceber.

---

## Roadmap

### 1. ⭐ Corrigir o parser (bugs nº 1 e nº 2) — alto valor, primeiro PR

- [x] Ajustar `_ART_MARK` conforme a regra validada (colado + exceção
      `(VETADO`); unificar os grupos de sufixo em `parse_dispositivos`.
- [x] Filtrar `bs4.Comment` (e `Doctype`) no `_flatten`.
- [x] **Testes de regressão com HTML sintético** (não depender do site vivo),
      cobrindo: sufixo colado (`Art. 121-A. Matar...`), sufixo espaçado-VETADO
      (`Art. 18 - A (VETADO)`), traço de caput (`Art. 312 - Apropriar-se...`),
      caput iniciando com artigo definido (`Art. 100 - A ação penal...`) e
      comentário HTML contendo `Art.`.
- [x] Rodar `pytest tests/unit` (o `art_18_A` da LCP 95 continua passando).
- [x] Reindexar: `lexrag daemon-stop` → **bootstrap** (não `update delta` — o
      hash do HTML não muda com fix de parser, o delta pularia tudo).
- [x] Revalidar com a heurística de suspeitos: CP, CLT, CPP e CF com
      **suspeitos = 0** (contra o HTML em cache); CP art. 312 e art. 2º com
      caput íntegro; único path alterado na CF foi `art_40_A` → absorvido
      corretamente em `art_40` (era o caput antigo tachado).
- **Critério de aceite:** `Art. 312` (não `312-A`) com caput "Apropriar-se...";
  `art_18_A` presente na LCP 95; contagem de suspeitos ≈ 0 nos códigos.
- [x] **Mecanismo permanente (feito em 2026-08-05):** o `pipeline_version` era
  gravado em [state.py](src/lex_rag/storage/state.py) mas **nunca lido** — todas
  as 266 linhas do state estavam em `0.1.0` e o campo era decorativo. Agora
  [diff.py](src/lex_rag/update/diff.py) compara a versão gravada com a de
  [config.py](src/lex_rag/config.py): bump da versão → o próximo
  `update --mode delta` reindexa mesmo com hash igual, eliminando o passo manual
  de apagar linhas do `state.sqlite` (o que foi preciso fazer com a CLT). O
  `get_content_hash` do state virou `get_indexed` (devolve hash + versão numa só
  consulta). Regressão em [test_update.py](tests/unit/test_update.py):
  hash igual + pontos presentes + versão nova → reindexa; depois volta a
  inalterada. Verificado também contra o `state.sqlite` real.

### 2. Fechar o que já foi feito

- [x] Commit da expansão do corpus (35 normas) — feito após o item 1.
- [x] Daemon no ar e buscas testadas **ponta a ponta** pelo caminho das tools
      MCP (client HTTP → daemon): `obter_dispositivo` (CP art. 312 íntegro),
      `pesquisar_norma` (CF art. 37 no topo), filtro novo `urn_lex` (busca
      restrita à LGPD só devolve LGPD) e `listar_alteracoes` (143 dispositivos
      da Lei 8.666).

### 3. Confiabilidade do `update` (pré-requisito do agendamento)

- [x] No update, falha de download → `falhas` (sem fallback para fixture);
      fallback continua valendo apenas no bootstrap (`permitir_fixture: bool`
      em `obter_html`, `False` no pipeline de update).
- [x] Delta verifica o Qdrant além do hash (norma sem pontos → reindexa,
      mesmo com hash igual; cobre coleção recriada sem zerar o state).
- [x] Testes: fallback de fixture nos dois modos; "delta reindexará norma
      ausente do Qdrant mesmo com hash igual" (Qdrant em memória + embedder
      fake); decode ciente de BOM (UTF-16 com byte final truncado, UTF-8 BOM,
      Latin-1) em [planalto_fetcher.py](src/lex_rag/ingest/planalto_fetcher.py).

### 4. Qualidade da busca e da camada MCP

- [x] **Reranker com contexto:** o rerank agora pontua o mesmo texto
      contextualizado do embedding (`[epígrafe] [parent] Label: texto`),
      preservando consultas que nomeiam a norma ("o que a LGPD diz sobre...").
- [x] **Expor filtros nas tools MCP:** `pesquisar_norma` aceita `tipo_norma` e
      `urn_lex`, propagados por tool → client → daemon → motor.
- [x] **Sinalizar corte de qualidade:** quando nenhum candidato atinge
      `reranker_score_min`, os melhores voltam com `confiavel=False` e a
      formatação antepõe "[AVISO] ..." (sem emoji: MCP stdio no Windows pode
      usar cp1252). `is_grounded` agora é usado em `formatar_resultados` para
      descartar resultado sem grounding.

### 5. Crescimento do corpus *(executado em 2026-07-03)*

- [x] **Todas as Leis Complementares** (231, conjunto fechado — LC 1/1962 à
      LC 233/2026) incluídas no corpus.
- A descoberta acabou **mais simples que o planejado**: em vez de LexML SRU +
  resolvedor de padrões candidatos, o **quadro oficial do Planalto**
  (`ccivil_03/leis/lcp/quadro_lcp.htm`) já traz, para cada LC, o link exato,
  o número, a data e a ementa — resolvendo de uma vez a parte difícil (URL não
  deriva mecanicamente do URN). Parser puro em
  [quadro_lcp.py](src/lex_rag/ingest/quadro_lcp.py); orquestração em
  [scripts/descobrir_lcps.py](scripts/descobrir_lcps.py), que valida cada LC
  por **download + parse** e grava
  [registro_lcp.json](src/lex_rag/ingest/registro_lcp.json) (checado no repo).
  O [urn_mapper.py](src/lex_rag/ingest/urn_mapper.py) mescla o JSON ao
  `REGISTRO` na importação; em conflito de URN, a entrada curada vence (as 4
  LCs que já eram curadas: 95, 101, 116, 123).
- **Bug de parser descoberto na validação**: a LCP 36/1979 (e a CLT no art.
  597) grafam o marcador com o ponto **em tag separada** (`Art</font><font>.
  1º` / `Art<b>.</b> 597`), que o achatamento vira "Art . 1º" — e o
  `_ART_MARK` exigia `Art\.` colado. Fix: aceitar espaço antes do ponto
  (`Art\s*\.`). Além de destravar a LCP 36, o fix **resgatou dispositivos
  perdidos** em normas já indexadas (CLT art. 597; LC 214: 663→668 disp;
  LC 89: 8→13; LC 86: 1→4). A CLT foi reindexada à força (remoção da linha no
  `state.sqlite`, já que o hash da página não mudou). Regressão em
  [test_ingest.py](tests/unit/test_ingest.py).
- **Segundo bug descoberto na indexação — delta quebrado por hash instável**:
  o WAF do Planalto (F5/BIG-IP) injeta um `<script id="f5_cspm">` com token
  **aleatório a cada resposta**, então o hash do HTML cru mudava a cada
  download e o `update --mode delta` reindexava o corpus inteiro, sempre (foi
  o que aconteceu na carga: as 35 curadas foram reindexadas junto com as 231
  LCs). Havia ainda um segundo vetor: `raw_cache.put` gravava em modo texto e
  o Windows traduzia `\r\n` → `\r\r\n` (cache ≠ download). Fix em
  [raw_cache.py](src/lex_rag/ingest/raw_cache.py): `content_hash` remove
  `<script>` e colapsa espaço em branco antes de hashear, e `put` grava com
  `newline=""`. Os hashes do `state.sqlite` foram recomputados a partir do
  cache e o delta foi verificado **ao vivo** (CF, LC 214, CLT, LC 36 →
  `norma_mudou = False`). Teste em [test_update.py](tests/unit/test_update.py).
- Estado final: **índice com 14.657 pontos** (266 normas), busca e
  `obter_dispositivo` validados ponta a ponta pelo daemon (LC 64/1990 art. 1º
  íntegro; CLT art. 597 presente; `pesquisar_norma` alcança as LCs novas).
- Reprodutibilidade: `python scripts/descobrir_lcps.py` regenera o JSON (LC
  nova promulgada → reroda e chama o `update`).
- [x] **Lote de 81 leis ordinárias** *(executado em 2026-08-05)*: 266 → 347
  normas, 14.657 → 20.920 pontos. Lista curada à mão (não há quadro utilizável
  para ordinárias); o que o script resolve é a **URL canônica**, em
  [planalto_urls.py](src/lex_rag/ingest/planalto_urls.py) —
  variantes testadas do consolidado para o simples (em várias leis antigas o
  `l{n}.htm` é o texto *original*: pegar a página errada serviria texto
  revogado como vigente), três diretórios distintos para 1999-2003, número com
  e sem ponto. A data declarada é conferida contra a epígrafe impressa na
  página, e quem diverge **não entra** (data errada = URN errado, e o URN é a
  chave do corpus). 81/81 validadas. Orquestração em
  [descobrir_ordinarias.py](scripts/descobrir_ordinarias.py), registro em
  `registro_ordinarias.json`; o `urn_mapper` agora mescla os dois JSONs
  gerados. A espécie do URN (`decreto.lei`) não vaza para o campo `tipo` do
  corpus, que alimenta o filtro `tipo_norma` e tem vocabulário próprio.
- **4º bug de parser, achado na verificação do lote**: o Planalto grafa
  `Art. 1<sup>o</sup>`, que achatado vira `Art. 1 o`, e o `_ART_MARK` exigia o
  ordinal colado ao número — o `o` sobrava como primeira letra do caput (a
  LINDB art. 1º abria com "o Salvo disposição contrária..."). **839
  dispositivos em 130 normas (4% do corpus)**, incluindo LCs indexadas em
  julho: pré-existente, revelado pelo lote. Idem para `Art. 2.º - ` (ponto
  antes do símbolo). Após o fix: 1 — a Lei 8.080 art. 46, onde a fonte grafa o
  artigo "o" em minúscula depois do ponto, palavra do texto preservada de
  propósito. Os dois ramos do ordinal são assimétricos por isso. Regressões em
  [test_ingest.py](tests/unit/test_ingest.py).
- **Padrão confirmado pela 4ª vez: toda expansão do corpus revela um bug de
  parser.** A heurística de suspeitos deixa de ser opcional — é etapa
  obrigatória de qualquer lote futuro.
- **Não** varrer os quadros de ordinárias do Planalto: são milhares, a maioria
  de artigo único (denominação de rodovia, crédito orçamentário) — relação
  sinal/ruído muito pior que a das LCs, e o
  [quadro_lcp.py](src/lex_rag/ingest/quadro_lcp.py) é LC-específico (regex de
  epígrafe). Daí a lista curada.
- [x] **2º lote de ordinárias — 132 normas** *(executado em 2026-08-07)*:
  347 → **479 normas**, ordinárias de 81 → 213. Cobertura setorial: processo e
  carreiras jurídicas (Lei 8.038, mediação, OAB, LONMP, juizados federais e da
  Fazenda), militar e segurança pública (CPM, CPPM, Estatuto dos Militares,
  Susp, terrorismo, tortura, racismo), trabalho (repouso semanal, rural,
  temporário, seguro-desemprego, PLR, estágio), saúde (planos de saúde, Anvisa,
  ANS, vigilância sanitária, saúde mental, biossegurança), educação, cultura e
  esporte (PNE, Fundeb, Fies, ProUni, Lei Pelé, Rouanet), agrário e ambiental
  (Estatuto da Terra, reforma agrária, Mata Atlântica, clima, barragens),
  urbano e transportes (mobilidade, regularização fundiária, CBA, ferrovias),
  energia e mineração (Código de Mineração, pré-sal, Lei do Gás, GD),
  tributário complementar (IRPF, PIS/Cofins, RFB, Cadin), organização do Estado
  (Lei 14.600, controle interno, conflito de interesses) e direitos sociais.
  **213/213 validadas** (100%), incluindo as 3 que a 1ª rodada rejeitou.
- Carga: **20.920 → 28.148 pontos**, 479 normas reindexadas, **zero falhas**
  (delta disparado pelo bump de `pipeline_version`, com o daemon parado para
  liberar o lock do Qdrant). Validado ponta a ponta pelas tools MCP: Lei 6.899
  art. 1º íntegro (a norma que saía vazia), `art_195_A` **ausente** da Lei
  13.465 (o fantasma do bug nº 6), PNMA art. 19 com a redação real em vez de
  "(VETADO)", busca alcançando o lote novo (Lei 9.656 art. 11) e o filtro
  `tipo_norma="codigo"` trazendo o CPM com a hierarquia correta.
- Três melhorias de máquina saíram da execução deste lote, todas em código
  testado offline:
  - **URL zerada à esquerda** em [planalto_urls.py](src/lex_rag/ingest/planalto_urls.py):
    normas antigas de numeração baixa ficam em `l0605.htm`/`del0037.htm`, não em
    `l605.htm`. Sem isso, Lei 605/1949, Lei 818/1949, DL 37, DL 73 e DL 227 não
    resolviam.
  - **`fetch` não repete 4xx** ([planalto_fetcher.py](src/lex_rag/ingest/planalto_fetcher.py)):
    a resolução de URL testa variantes até uma existir, então o 404 é o caso
    *esperado* e determinístico — repeti-lo 3× com espera exponencial
    multiplicava o custo da descoberta. Transitório (5xx, timeout) segue
    repetindo.
  - **Lote incremental**: o `descobrir_ordinarias.py` reaproveita do JSON as URLs
    já resolvidas e só vai à rede pelas normas novas (`--revalidar` força o
    contrário). Os demais metadados são sempre reconstruídos de `CANDIDATAS`,
    então corrigir uma ementa não custa download.
  - Piso do "parse magro" de 3 → **2 dispositivos**: há lei legítima de dois
    artigos (Lei 12.506/2011, aviso prévio; Lei 10.446/2002, atribuição da PF),
    e o piso antigo as rejeitava como se fossem página errada.
- [x] **A heurística de suspeitos virou script no repo**:
  [verificar_parser.py](scripts/verificar_parser.py). Roda sobre o HTML em cache
  (`--baixar` busca o que falta) e agrupa os sintomas por regra — caput em
  minúscula, ordinal solto, sufixo + caput minúsculo, path duplicado. O
  `--novos --baixar` verifica um lote **antes** de indexá-lo, que é o que muda a
  economia: bug achado aqui custa uma correção; achado depois, custa uma
  reindexação do corpus inteiro (foi o que aconteceu nos lotes anteriores).
- **Padrão confirmado pela 5ª vez** — e desta vez em triplicata (bugs nº 5, 6 e
  7). Os dois maiores (nº 5 e nº 6) eram **pré-existentes**, não introduzidos
  pelo lote: o lote só os tornou visíveis. Vale para o próximo lote: o que a
  verificação encontra costuma já estar no índice há meses.
- [x] **3º lote — leis que regem fundos, 43 normas** *(executado em 2026-08-07)*:
  479 → **522 normas**, ordinárias de 213 → 256. Recorte pedido: a norma que
  **institui ou disciplina** o fundo, não a que apenas o menciona. Blocos:
  fundos constitucionais e garantidores de crédito (FNO/FNE/FCO, FGO, FGI,
  ABGF, FGE, FGPC); fundos de investimento e patrimoniais (FII, FIP-IE,
  *endowments* da Lei 13.800, tributação da Lei 14.754); socioambientais e de
  direitos (FNMA, Fundo Clima, FNDF, FDD, FNCA, Fundo do Idoso, Funad);
  infraestrutura, comunicações, habitação e educação (FNDCT, FNDE, Fust,
  Funttel, Fistel, FMM, FNHIS, CDE, FCVS, FCDF); os **fundos setoriais de C&T**
  que abastecem o FNDCT (CT-Energ, CT-Transporte, CT-Hidro/Mineral,
  CT-Espacial, CT-Verde-Amarelo, CT-Agro/Saúde/Biotec/Aeronáutico, Lei de
  Informática, ZFM); audiovisual (Funcines, FSA); e Fundaf e Funcafé.
  **43/43 validadas.** Carga: 522 normas reindexadas, **zero falhas**,
  27.838 pontos. Validado pelas tools MCP: a busca pelo FNDCT devolve os arts.
  10-12 da Lei 11.540, e o art. 10 (receitas do Fundo) cita nominalmente as
  Leis 9.991, 9.992, 9.993, 9.994, 10.168, 10.332, 8.248, 8.387 e 10.893 —
  todas trazidas por este lote, o que confirma o recorte. Zero caracteres de
  controle C1 no corpus (eram 7.571).
- Vários fundos **já estavam cobertos** e por isso ficaram de fora: FGTS,
  FAT, Fundeb, Fies, FNS, FNAS, FNSP, Fundo Social do pré-sal, Funpresp, FNC,
  FGP, FGHab — e, pelo lado das LCs, Funpen (LC 79), FPE/FPM (LC 62 e 143),
  Combate à Pobreza (LC 111), PIS/Pasep (LC 7, 8 e 26), FDA/FDNE (LC 124 e
  125) e Fundo de Terras (LC 93).
- Conferir a **ementa oficial** antes de gravar mudou duas entradas: o DL
  2.295/1986 não cria o Funcafé (isenta o café do imposto de exportação e
  destina a quota de contribuição ao fundo já existente) e o DL 1.437/1975 é
  uma lei de IPI que institui o Fundaf no art. 6º. A ementa gravada passou a
  dizer isso, em vez de descrevê-los como leis instituidoras.
- O rastro levou a uma norma que não estava na lista: a Lei 8.387/1991 aponta
  que o FNDCT foi criado pelo **DL 719/1969**, não pela Lei 11.540/2007 — que
  o reorganizou e revogou apenas os arts. 2º e 3º. O art. 1º segue vigente, e
  o DL entrou no lote.
- **Primeiro lote sem bug de parser** — a série de 5 parou. Os três fixes do
  lote 2 cobriram justamente as grafias das leis antigas, e este lote é quase
  todo de 1966 em diante. Mas apareceu um bug **de decodificação** (nº 8), que
  a verificação só revelou porque os `__N` remanescentes foram inspecionados um
  a um em vez de creditados ao backlog conhecido.
- Fora do recorte, de propósito: Fundo Soberano (Lei 11.887/2008, extinto em
  2019 pela Lei 13.874), Fundo Amazônia e FGC (criados por decreto e por
  resolução do CMN — o Amazônia cabe no lote de decretos), e os fundos Naval,
  do Exército e Aeronáutico (decretos-lei antigos, valor de consulta baixo).
- [x] **4º lote — políticas nacionais, 72 normas** *(executado em 2026-08-10)*:
  522 → **594 normas**, ordinárias de 256 → 328. Recorte: a lei que **institui
  ou define** a política, não a que a altera. Motivo do lote: o corpus tinha só
  **12** leis com "Política Nacional" na ementa, e o tipo é justamente o que se
  consulta por tema.
- **A descoberta mudou de método — de memória para varredura.** Duas fontes,
  ambas exaustivas:
  - **Quadros oficiais do Planalto** (`ccivil_03/leis/quadro/{ano}.htm`): lista
    número + ementa de todas as ordinárias do ano. **Só existem de 1988 a
    2000** — os outros anos são 404, e o portal `www4` que os substituiu está
    atrás de desafio JS (F5 Shape).
  - **API pública de metadados do LexML**
    (`normas.leg.br/api/public/metadados/simples?urn=...`), que devolve data e
    ementa oficiais por URN e aceita a forma curta
    `urn:lex:br:federal:lei:{ano};{numero}` — o que permite varrer a numeração
    inteira. Foram **15.396 leis, de 1934 a 2026**. (A busca SRU do LexML,
    `www.lexml.gov.br/busca/SRU`, que seria o caminho óbvio, está atrás do
    mesmo tipo de desafio.)
- **Armadilha da API, achada na conferência:** o `urn` casa o número por
  **sufixo** — pedir `lei:1962;118` devolve a **Lei 4.118/1962**, e
  `lei:1934;1` devolve a Lei 11. Numa varredura sequencial isso desloca o ano
  corrente e passa a rotular leis com número errado. O conserto é conferir o
  `name` da resposta contra o número pedido e tratar divergência como "não
  existe". Sem isso, todo o trecho pré-1988 (números de 1 a 3 dígitos) sairia
  corrompido — e silenciosamente, porque as ementas devolvidas são de leis
  reais.
- Resultado da varredura: **115 leis mencionam "Política Nacional"** na ementa,
  **83** a instituem ou definem (as demais só alteram). Dessas, 13 já estavam
  no corpus e **8 ficaram de fora por revogação ou superação**: Lei 2.004/1953
  (petróleo, revogada pela 9.478/1997, que está no corpus), Lei 5.318/1967
  (saneamento, pela 11.445/2007, idem), Lei 6.662/1979 (irrigação, pela
  12.787/2013, que entra no lote) e as cinco leis de política nacional de
  salários (8.073, 8.222, 8.419, 8.542 e 8.700), superadas pela desindexação da
  Lei 10.192/2001.
- Entraram também **10 correlatas estruturantes** do mesmo tipo, que a
  varredura por "Sistema Nacional"/"Plano Nacional" revelou ausentes: Sinase
  (12.594), Sinaes (10.861), Sine (13.667), Sinamob (11.631), Sistema Nacional
  de Prevenção e Combate à Tortura (12.847), Sistema Nacional de Sementes e
  Mudas (10.711), marco do SNC (14.835), Plano Nacional de Gerenciamento
  Costeiro (7.661), Pnatrans (13.614) e o **novo PNE (15.388/2026)** — o corpus
  tinha só o PNE anterior (13.005/2014).
- **72/72 validadas** (100%), todas com a data conferindo contra a epígrafe.
  Carga por `POST /update` no daemon (modo delta, modelos quentes): **73
  reindexadas** — as 72 novas mais o Código Penal, que o Planalto alterou desde
  a última carga —, **zero falhas**, 27.838 → **29.209 pontos**. Zero
  caracteres de controle C1 no lote.
- **Segundo lote seguido sem bug de parser, e o primeiro sem bug algum.** A
  verificação apontou **1 suspeito** (`path duplicado (__N)` no art. 6º da Lei
  7.232/1984) e a inspeção mostrou comportamento **correto**: a página traz as
  duas redações do artigo, ambas tachadas, e o parser as marca como não
  vigentes — `listar_alteracoes` devolve "Art. 6º: Revogado" e "Art. 6º:
  Revogado pela Lei nº 8.248, de 1991". Inspecionar em vez de creditar ao
  ruído conhecido continua valendo: foi o que revelou o bug nº 8.
- Próxima fatia possível: **decretos regulamentadores** (lote à parte — amplia
  escopo e hierarquia, e exige `tipo` novo no vocabulário do filtro
  `tipo_norma`, além de padrões de URL próprios em `variantes_url`). Boa parte
  das políticas nacionais deste lote remete a decreto regulamentador, o que
  reforça o encaixe.
- [x] **5º lote — decretos (espécie nova) + 5 ordinárias** *(executado em
  2026-08-10)*: 594 → **640 normas**, com **41 decretos** e o tipo `decreto`
  estreando no vocabulário do filtro `tipo_norma`. Recorte: o decreto que
  **regulamenta** lei já no corpus ou que **consolida** um regulamento de
  consulta frequente. Blocos: regulamentos consolidados (RIR, RIPI, Aduaneiro,
  RPS, IOF, ITR, PAF 70.235, eSocial, consolidação trabalhista 10.854,
  convenções da OIT 10.088); contratações públicas (SRP 11.462, agente de
  contratação 11.246, PCA 10.947, credenciamento 11.878, margem de preferência
  11.890, equidade 11.430, execução indireta 9.507, ME/EPP 8.538, e o par do
  regime antigo — SRP 7.892 e pregão eletrônico 10.024); administração e
  integridade (LAI 7.724, anticorrupção 11.129, governança 9.203, ética 1.171,
  PNDP 9.991, jornada 1.590, MROSC 8.726); direitos, saúde, consumidor e
  ambiente (SUS 7.508, BPC 6.214, PcD 3.298, acessibilidade 5.296, migração
  9.199, Bolsa Família 12.064, SNDC 2.181, comércio eletrônico 7.962, SAC
  11.034, infrações ambientais 6.514); e setoriais (energia 5.163, ANEEL 2.335,
  desarmamento 11.615, florestas públicas 12.046).
- **A descoberta voltou a ser lista curada, e a medição explica por quê.** O
  piloto de varredura de 2024 na API do LexML (faixa 11.700-12.400) achou 472
  decretos, dos quais só **28 regulamentam de fato** — o resto é "altera o
  Decreto X", estrutura regimental e crédito orçamentário — e **10** tratam de
  lei já presente no corpus. Extrapolado para 1988-2026, o filtro semântico
  "regulamenta" renderia ordem de mil normas, boa parte já superada: largo
  demais para o método que funcionou com "Política Nacional" no lote 4.
- **Três frentes de máquina**, todas com teste de regressão em
  [test_planalto_urls.py](tests/unit/test_planalto_urls.py): `variantes_url`
  ganhou `_dirs_decreto` (o Planalto muda de convenção por faixa de ano —
  `_ato{faixa}/{ano}/decreto/` de 2004 em diante, `decreto/{ano}/` ou `decreto/`
  entre 1999 e 2003, `decreto/1990-1994/` ou `decreto/` na primeira metade dos
  1990, `decreto/` com sufixo de consolidado ou `decreto/antigos/` antes disso), e só
  gera minúsculas, porque o portal responde 301 de qualquer grafia maiúscula
  para o mesmo arquivo; `conferir_data` passou a **escolher o rótulo pela
  espécie**; e o `tipo` novo foi propagado até o docstring da tool MCP.
- **Por que o rótulo restrito importa:** a página de um decreto traz, logo
  abaixo da própria epígrafe, a lei que ele regulamenta ("Regulamenta a Lei nº
  14.133, de 1º de abril de 2021"). Um padrão que casasse "LEI" em qualquer
  página acharia essa referência quando a epígrafe do decreto escapasse do
  padrão, e o lote seria rejeitado por "data divergente" **com um número de lei
  plausível** — erro que parece certo. Com o rótulo por espécie, **41/41
  conferiram**.
- **Terceiro lote seguido sem bug de parser.** A verificação apontou 27 paths
  duplicados em 5.300 dispositivos (0,5%, contra 2,1% do corpus), e a inspeção
  um a um separou dois grupos, ambos corretos: **19 são a colisão
  decreto/anexo** (ver backlog) e **8 são páginas com duas redações do mesmo
  artigo** — Regulamento Aduaneiro arts. 722/791/792, Dec. 3.298 arts. 11/12/57
  (CONADE no Ministério da Justiça e depois nos Direitos Humanos), SRP art. 13
  e RIPI art. 209. Nos sete primeiros o Planalto tacha **as duas** redações e o
  parser marca as duas como não vigentes, fiel à fonte.
- **Revogado entra quando ainda se consulta**, e o índice o trata certo: Lei
  10.520 (pregão) e Decreto 7.892 (SRP da 8.666) vieram com **zero
  dispositivos vigentes**, porque o Planalto marca a revogação dispositivo a
  dispositivo — a busca padrão não os serve, e a consulta a contrato antigo os
  alcança com `somente_vigente=false`.
- **Dois defeitos silenciosos achados na execução, os dois corrigidos:**
  - **Norma repetida sob slug diferente.** A Lei 14.600/2023 foi reincluída
    como `orgpresidencia_...` sem que se notasse que já estava como
    `presidencia_...`: mesmo URN, dois slugs, e o `REGISTRO` — indexado por
    slug — aceitou as duas. Seriam a mesma lei duas vezes no índice, dobrando
    pontos e ocorrências na busca. Agora os dois scripts de descoberta
    conferem a unicidade do URN antes de gravar, e um teste cobre o corpus
    inteiro. O mini-lote ficou em **5** ordinárias, não 6.
  - **O daemon serve o catálogo do import.** Rodar `POST /update` com o daemon
    já no ar quando o lote foi descoberto devolveu `atualizadas: {}` e índice
    parado — um "não fez nada" com cara de sucesso. `recarregar_registro()`
    relê os JSON **no mesmo dicionário** (mutação, não reatribuição, para valer
    a quem já importou) e o `/update` o chama antes de rodar, devolvendo também
    o tamanho do catálogo. Sem isso o `update` **agendado** (item 6) nunca
    veria lote novo.
- **Carga**: `POST /update` em modo delta com os modelos quentes — **46
  reindexadas** (41 decretos + 5 ordinárias), **594 inalteradas**, **zero
  falhas**, 29.209 → **34.703 pontos**. Conferido pelas tools: a busca com
  `tipo_norma="decreto"` devolve o art. 22 do Dec. 11.462 (vigência da ata de
  registro de preços) e a consulta ao BPC devolve o art. 20 da Lei 8.742
  **seguido** dos arts. 4º e 8º do Dec. 6.214 — o pareamento lei + regulamento
  que motivou o lote. `listar_alteracoes` na Lei 10.520 devolve os 13 artigos
  revogados.
- **Pendência cosmética conhecida:** o apelido da Lei 13.844 foi corrigido no
  registro (`...(2019)` aninhado → `...até 2023`) **depois** da carga. Como o
  delta compara o hash do HTML, e não os metadados, o índice segue com a
  epígrafe antiga até que a página mude ou se apague a linha da norma em
  `state.sqlite` (`DELETE FROM norma_state WHERE urn_lex='urn:lex:br:federal:lei:2019-06-18;13844'`),
  o que faz o próximo delta reindexá-la sozinha.
- [x] **6º lote — a parte textual das LDOs e LOAs** *(executado em 2026-08-12)*:
  640 → **670 normas**, com os **15 pares** LDO+LOA dos exercícios de **2012 a
  2026**. Recorte: só a lei que fixa as diretrizes (LDO) ou estima receita e
  fixa despesa (LOA) do exercício — as que apenas as alteram e as dezenas anuais
  de crédito suplementar, especial e extraordinário ficam de fora. O corte em
  2012 acompanha os ciclos de PPA (2012-2015, 2016-2019, 2020-2023, 2024-2027);
  não há LDO de 2027 até esta data.
- **A descoberta voltou a ser varredura, e valeu.** A série saiu da API de
  metadados do LexML (faixa 12.100-15.800, filtrando a ementa oficial), não de
  memória: **nenhum exercício ficou sem par**, e a conferência pegou o que a
  memória erraria — a Lei 15.080/2024 é a **LDO de 2025**, não a LOA, cuja
  sanção escorregou para abril (Lei 15.121/2025, como já acontecera com as de
  2015 e 2021). Duas armadilhas de ementa: a LDO alternou "para a elaboração
  **e** execução" e "**e a** execução" a partir do exercício de 2020 — um filtro
  que exigisse uma das duas formas perderia metade da série, e perdeu, na
  primeira passada.
- **"Parte textual" sai de graça da arquitetura, mas só depois de dois
  consertos.** O pipeline indexa dispositivos parseados, e os anexos da LOA e da
  LDO são tabelas, que o parser não produz como dispositivo — a LOA de 2024 tem
  309 KB de HTML e rende 10 artigos. O que **não** saía de graça:
  - **Referência a artigo virava dispositivo** *(bug nº 9)*. Os títulos de anexo
    da LDO citam a LRF — "ANEXO IV - METAS FISCAIS (Art. 4º, § 1º, da Lei
    Complementar nº 101...)" — e o Anexo de Riscos Fiscais cita processos
    ("art. 3º da Portaria AGU nº 40/2015", "art. 102, III, 'd', c/c com o art.
    3º, § 2º"). Cada citação abria um falso dispositivo que engolia o pedaço de
    anexo seguinte e o servia rotulado "Art. 4º" **da LDO** — texto de outra
    norma atribuído a esta, que é exatamente a alucinação que o projeto existe
    para impedir. Eram ~20 por LDO. O guarda `_REFERENCIA` olha o que vem
    **depois** do número: caput nenhum abre com vírgula, com preposição ou com
    conjunção. Descartar o marcador **antes** de ele entrar em `markers` é o que
    mantém o trecho colado ao dispositivo anterior — mesmo mecanismo do guarda
    de aspas, e por isso nada se perde.
  - **O guarda sozinho piorava o outro flanco**, e a medição mostrou: sem os
    falsos marcadores para servir de fronteira, o anexo inteiro se fundia no
    último artigo, e o art. 155 da LDO de 2019 ia a **289 KB**.
- **O fecho encerra o texto articulado** *(bug nº 10, e ele era do corpus
  inteiro, não do lote)*. Depois de "Brasília, 14 de agosto de 2018; 197º da
  Independência" vêm assinaturas, o "Este texto não substitui o publicado" e os
  **anexos**, que o Planalto serve na mesma página — tudo colado ao último
  dispositivo. Medido em **651 das 662 normas** em cache: o art. 37 do PNE saía
  com 160 KB, o art. 382 do RPS com 211 KB, o art. 89 da LCP 123 com as tabelas
  do Simples. Truncar no fecho devolve o artigo de verdade ("Esta Lei entra em
  vigor na data de sua publicação") e poda **1,23 MB de 31,66 MB** (3,9%) de
  texto que não era daquele artigo. O corte é **por dispositivo, não pelo
  documento**: página de texto compilado traz mais de um fecho (a lei e a
  alteradora reproduzida), e cortar no primeiro decepava o resto da norma —
  16 normas do corpus estão nessa situação.
- **Preço aceito conscientemente:** anexo com conteúdo normativo sai do índice
  junto — as tabelas de alíquotas da LCP 123 e da LCP 214, as metas do PNE. Hoje
  eles eram encontráveis, porém atribuídos ao último artigo. A saída boa é o
  item de backlog (anexo como dispositivo próprio, `anexo_*`), que preserva
  conteúdo **e** citação; este lote escolheu a correção da citação.
- **Inspeção do lote**: 30 normas, 2.604 dispositivos, **5 suspeitos**, todos
  inspecionados e corretos — são blocos de elisão ("......") do texto de lei
  alteradora reproduzido na página compilada (LDO 2020 arts. 73/75/76, LDO 2026
  arts. 95/98), com o path canônico intacto. Antes dos consertos eram **57**.
- **Reindexação sem rede** ([reindexar_do_cache.py](scripts/reindexar_do_cache.py),
  novo). O `update` decide o que refazer pelo **hash do HTML**, então correção de
  parser não dispara reindexação nenhuma — o HTML é o mesmo e o índice fica com
  o texto antigo. A alternativa era o `bootstrap`, que rebaixa as ~670 normas e
  cujo download o Planalto estrangulou no meio deste lote (8 normas caíram por
  timeout, e a rede só voltou depois de uma pausa). Como não foi o HTML que
  mudou, reparsear o cache dá o mesmo resultado sem tocar no portal.
- **O apelido carrega o exercício** ("LDO 2024"), e como a epígrafe entra no
  texto embedado, o ano distingue artigos quase idênticos que se repetem de um
  exercício para o outro — sem isso a busca por "meta fiscal" devolveria 15
  vizinhos indistinguíveis.
- **Carga**: reindexação completa a partir do cache, **670 normas**, **zero
  falhas**, 34.703 → **37.267 pontos** (2.604 do lote; o saldo das demais normas
  cai um pouco, porque o corte no fecho encolheu o último dispositivo de 651
  delas). Conferido pelas tools: `obter_dispositivo` no art. 10 da LOA de 2024
  devolve "Esta Lei entra em vigor na data de sua publicação" em vez dos 15 KB
  de anexo; no art. 4º da LDO de 2019, as definições de subtítulo e unidade
  orçamentária, sem rastro dos falsos `art_4__N`; a CF art. 37 continua íntegra,
  do inciso I ao § 16. A busca por "meta de resultado primário" devolve o art.
  2º de LDOs de exercícios diferentes, cada um rotulado com o seu ano — a série
  que motivou o lote (déficit de R$ 163 bi em 2017, R$ 132 bi em 2019, R$ 247 bi
  em 2021, meta zero em 2025).

- [x] **7º lote — as Súmulas Vinculantes do STF** *(executado em 2026-08-14)*:
  670 → **733 documentos**, com os **63 enunciados**. É a primeira
  jurisprudência do corpus, e entrou por ter força normativa *erga omnes* (CF,
  art. 103-A) — o degrau entre a lei e o acórdão. Acórdãos, votos, informativos
  e ementas de ADI/ADC ficam **fora de escopo** por decisão, não por limitação:
  a proposta é conhecimento jurisprudencial sintético.
- **O que exigiu caminho novo não foi a fonte, foi a forma.** Um decreto é
  isomorfo a uma lei (artigos numerados, epígrafe canônica, mesmo path scheme),
  e por isso o 5º lote não tocou no parser. Uma súmula não é: é enunciado único,
  e `parse_dispositivos` só produz dispositivo a partir de `Art. N`. O resultado
  não seria um erro, seria **zero dispositivos gravados como sucesso** — a norma
  entra no `state.sqlite`, nenhum ponto vai ao índice, nada acusa nada. O mesmo
  fenômeno já medido nos anexos (Dec. 1.171/1994 com 3 dispositivos, Pacto de
  São José com 3, nenhum da Convenção). Daí o dispatch em `ingest/source.py` e
  em `parse_norma`, os dois pontos por onde bootstrap, update e
  `reindexar_do_cache` já passam: um `if` em cada, e os três fluxos passaram a
  servir a espécie sem alteração própria.
- **A fonte local é de primeira classe, e isso é diferente de fixture.** O
  fixture é fallback de download falho, e o `update` o desliga de propósito
  (`permitir_fixture=False`) para não regredir o índice a um retrato velho.
  Aqui é o contrário: o JSON versionado **é** a versão corrente. São 63 textos
  curtos que o STF edita uma ou duas vezes por ano — um scraper vigiando isso em
  produção custaria mais manutenção do que a edição que evita. O que circula
  pelo pipeline é o JSON canônico da entrada (`sort_keys`), então reindentar o
  arquivo não reindexa nada e editar uma súmula reindexa só ela.
- **A conferência mudou de objeto: de data para situação.** Na legislação,
  `conferir_data` casa a epígrafe impressa contra o registro, porque data errada
  é URN errado. A página do STF não imprime data nenhuma — mas marca no título a
  súmula fora de vigor. É essa marca que `descobrir_sumulas.py` casa contra a
  tabela curada, e a divergência rejeita a entrada: servir como vigente uma
  súmula que o STF cancelou é pior do que não tê-la. **A conferência pegou um
  caso na primeira execução**: a SV 30 não marca nada no título, e sim no lugar
  do próprio enunciado ("está pendente de publicação") — o script só passou a
  olhar os dois lugares depois disso.
- **Duas súmulas fora de vigor, e elas entram marcadas em vez de omitidas.** A
  **SV 9** foi cancelada em 26/09/2025 (PSV 60), por incompatibilidade com a
  redação que a Lei 12.433/2011 deu ao art. 127 da LEP — o desenho inicial
  supunha que nenhuma SV tivesse sido cancelada, e a coleta desmentiu. A **SV
  30** teve a publicação suspensa em 04/02/2010, no dia seguinte à aprovação, e
  nunca produziu efeitos. Omiti-las devolveria silêncio a quem as procura;
  entrando com `vigente=False` + `revogado_por`, o default `somente_vigente` as
  esconde da busca comum e a citação as marca — mecanismo que já existia para
  artigo revogado, sem uma linha nova.
- **O URN é sintético, e isso está registrado.** O padrão adotado é
  `urn:lex:br:supremo.tribunal.federal:sumula.vinculante:{data da sessão};{n}`.
  O LexML **não indexa nem resolve** súmula vinculante (o SRU devolve vazio e o
  resolvedor dá "não encontrado" para URN bem formado), então não há como
  conferir contra a fonte canônica de URN. Por isso a `url_canonica` aponta para
  a página da súmula no portal do STF, e não para o resolvedor LexML: citar URL
  que não resolve seria pior do que citar a fonte real.
- **As datas vieram de fora da página**, que não as traz: as das súmulas 1 a 56
  saíram do livro oficial *Súmulas Vinculantes* (2ª ed., Secretaria de
  Documentação), que registra por súmula a sessão de aprovação e a fonte de
  publicação; as de 57 em diante, das publicações e notícias oficiais, uma a
  uma. Ficam na tabela `DATAS` do script de descoberta, e a data de aprovação
  entra no URN — erro ali é erro de identidade, e `verificar_sumulas.py` confere
  que as duas batem.
- **Defeito silencioso encontrado e corrigido no próprio lote:** `_carregar_sumulas`
  relê o JSON a cada `recarregar_registro()`, mas o cache de enunciados de
  `jurisprudencia` é separado e continuava quente — o `POST /update` atualizaria
  os metadados e serviria o **texto velho**, com a mesma cara de sucesso do
  defeito do lote 5. `recarregar_registro()` passou a invalidar os dois, e há
  teste que trava isso.
- **TLS do portal do STF.** `portal.stf.jus.br` serve só o certificado folha,
  sem o intermediário da GlobalSign, e a verificação falha com `unable to get
  local issuer certificate`. Em vez de desligar a verificação, o script usa
  `truststore` (dependência nova) para delegá-la ao store do sistema, que busca
  o elo faltante pela extensão AIA — que é o que o navegador faz. O WAF também
  exige cabeçalhos de navegação completos (`Sec-Fetch-*`, `Referer`), não só
  User-Agent.
- **Verificação:** `verificar_parser.py` passou a **pular** os tipos
  jurisprudenciais (as regras dele — rótulo comendo o caput, ordinal solto —
  pressupõem artigo, e num enunciado só produziriam ruído), e o lote ganhou o
  seu próprio gate, [verificar_sumulas.py](scripts/verificar_sumulas.py):
  numeração sem buraco, URN casando com a data de aprovação, enunciado sem
  mojibake nem truncamento, vocabulário de situação, motivo obrigatório para
  quem não está vigente. Lote conferido íntegro: 63 enunciados, 61 vigentes.
- **Carga:** `POST /update` em modo delta, sem tocar nas 670 normas do Planalto
  (hash inalterado) e sem recriar a coleção — 37.267 → **37.330 pontos**, 63
  documentos novos, zero falhas. Conferido pelas tools: a busca por nepotismo
  devolve a SV 13 ao lado do art. 37 da CF, que é o pareamento que motivou o
  lote; `obter_dispositivo` no path `enunciado` da SV 11 devolve o texto do uso
  de algemas; a SV 9 não aparece em busca com `somente_vigente`.

- [x] **8º lote — regimes de incentivo setorial** *(executado em 2026-08-18)*:
  733 → **736 documentos**, com a **Rota 2030** (Lei 13.755/2018), o **Mover**
  (Lei 14.902/2024) e o **Reidi** (Lei 11.488/2007). Motivo do lote: o corpus
  tinha o incentivo genérico (Lei do Bem, Marco Legal da Inovação) e não tinha
  os regimes setoriais, que respondem pela maior parte da renúncia — quem
  perguntasse por crédito financeiro de P&D automotivo ou por suspensão de
  PIS/Cofins em obra de infraestrutura não achava a lei, só o incentivo geral.
- **A Rota 2030 e o Mover entram como par, e o par é o ponto.** O Mover sucede
  a Rota 2030 e **revoga dispositivos dela** — consultar um sem o outro devolve
  texto que já não vale. Foi também o que decidiu a URL: a resolução ficou com
  `l13755compilado.htm`, o consolidado, e não com o `l13755.htm`, que é o texto
  original, anterior ao Mover. É exatamente o flanco que `variantes_url` cobre
  ao listar os sufixos do consolidado para o simples.
- **Datas conferidas na fonte, não de memória:** as três saíram da API de
  metadados do LexML (10/12/2018, 27/06/2024, 15/06/2007) e passaram de novo
  pela conferência contra a epígrafe impressa na página — data errada é URN
  errado, e o URN é a chave do corpus.
- **Inspeção do lote**: 3 normas, 126 dispositivos, **9 suspeitos**, todos
  inspecionados — **nenhum bug novo**. Reidi e Mover saem limpos; os 9 são da
  Rota 2030 e são as duas formas de ruído já catalogadas:
  - **texto de lei alterada reproduzido entre aspas** dentro dos arts. 34 a 37
    ("‘Art. 5º ....... § 1º Os componentes, chassis..." da Lei 9.826), que o
    parser abre como dispositivo próprio. Os que colidem com artigo real da
    Rota 2030 recebem `__N` e o artigo de verdade fica com o path canônico
    (`art_5` é o dela); o que **não** colide fica com o path canônico sozinho —
    o `art_72` da Rota 2030 é, no índice, o art. 72 da Lei 8.383. É o item de
    backlog do "Art." casado no meio do caput, sem agravamento.
  - **a página traz dois documentos**: depois do fecho de 10/12/2018 vem a
    *promulgação das partes vetadas*, com epígrafe e ementa próprias, que
    reproduz os arts. 34 a 37 outra vez. É a situação que o corte no fecho do
    bug nº 10 já prevê ao truncar **por dispositivo, e não pelo documento** —
    cortar no primeiro fecho decaparia essa segunda metade.
- **Carga:** `POST /update` em modo delta, com o daemon no ar (o endpoint
  chama `recarregar_registro()` antes de rodar, que é o que faz o lote novo
  aparecer para um processo já em execução) — 37.330 → **37.456 pontos**, zero
  falhas. O saldo é **exatamente os 126 dispositivos do lote** (42 + 49 + 35);
  o delta ainda rebaixou 3 normas cujo HTML mudou no Planalto (Lei 8.429,
  Lei 8.171, Lei 8.212), sem alterar a contagem delas.
- **Conferido pelas tools:** a busca por crédito financeiro de P&D automotivo
  devolve os arts. 15, 16 e 19 do Mover; a busca por suspensão de PIS/Cofins em
  obra de infraestrutura devolve o art. 3º do Reidi; e `obter_dispositivo` no
  `art_5` da Rota 2030 devolve o artigo **dela** — não o art. 5º da Lei 9.826
  reproduzido no corpo —, marcado "(Revogado pela Lei nº 14.902, de 2024)", que
  é o pareamento que motivou o lote.

- [x] **9º lote — direito econômico** *(executado em 2026-08-21)*: 736 →
  **759 documentos**, com 22 leis e 1 decreto. Motivo do lote: a ordem
  econômica constitucional já estava coberta (Lei 12.529/2011, Lei 13.874/2019,
  CDC, as oito agências e a Lei 13.848/2019, concessões, PPP, estatais, PND,
  6.385, 6.404, 4.595, 7.492, 9.279, 11.101), mas **quatro flancos inteiros
  não tinham nenhuma norma no corpus** — e a pergunta que os revelou foi
  levantada por varredura do `REGISTRO`, não de memória:
  - **defesa comercial**: `dumping`, `salvaguarda` e `defesa comercial` não
    tinham uma ocorrência sequer nas ementas. Entram a Lei 9.019/1995 e o
    **Decreto 8.058/2013** (o regulamento antidumping, 201 dispositivos — a
    norma mais pesada do lote), ao lado do **Decreto-Lei 288/1967**, cujo
    texto-base faltava embora a **Lei 8.387/1991, que o altera, já estivesse no
    corpus**: quem consultasse a Zona Franca de Manaus caía na lei alteradora
    sem o texto alterado.
  - **resolução bancária**: Leis 6.024/1974 e 9.447/1997. A Lei 11.101/2005
    está no corpus e **exclui expressamente** a instituição financeira do seu
    âmbito, então o corpus respondia recuperação judicial para banco quebrado.
    Junto veio o processo sancionador do BCB e da CVM (Lei 13.506/2017), que
    substituiu o rito da 4.595 e da 6.385 — ambas presentes, ambas com o rito
    velho.
  - **infraestrutura de mercado**: Lei 10.214/2001 (SPB), que é a base da Lei
    12.865/2013, já presente sem o alicerce; e a Lei 4.728/1965.
  - **títulos que financiam a atividade produtiva**: CPR (8.929/1994), títulos
    do agronegócio (11.076/2004), Lei do Agro (13.986/2020), patrimônio de
    afetação/LCI/CCI/CCB (10.931/2004), arrendamento mercantil (6.099/1974),
    consórcio (11.795/2008), debêntures de infraestrutura (14.801/2024, o par
    da 12.431 que já estava), PNMPO (13.636/2018) e Pronampe (13.999/2020).
  - completam o lote portos (12.815/2013) e relicitação de contratos de
    parceria (13.448/2017), registro público de empresas (8.934/1994), crimes
    contra a ordem econômica (8.176/1991) e os canais de distribuição —
    representação comercial (4.886/1965) e Lei Ferrari (6.729/1979).
- **Datas conferidas na fonte**: as 23 saíram da API de metadados do LexML e
  voltaram com o `name` batendo com o número pedido — a ressalva do casamento
  por sufixo não mordeu nenhuma. Depois passaram de novo pela conferência
  contra a epígrafe impressa na página. Três resolveram para o **consolidado**
  e não para o texto original (4.728, 8.934 e 11.076), que é o flanco coberto
  por `variantes_url`.
- **Inspeção do lote**: 23 normas, 1.173 dispositivos, **15 suspeitos**, todos
  inspecionados — **nenhum bug novo**. Um deles quase passou por bug de verdade:
  - **`pnmpo_13636_2018`, art. 9º, caput minúsculo** (`'esta Lei entra em
    vigor'`) — é exatamente o sintoma do bug da primeira letra comida pelo
    sufixo, e a regra existe para pegá-lo. Mas o HTML do Planalto traz
    literalmente `Art. 9º esta Lei entra em vigor`: o erro é da fonte, e a
    decisão foi **servir o que a fonte publica**, sem corrigir no parser.
  - **`leasing_6099_1974`, art. 16 duplicado** — texto original mais a redação
    da Lei 7.132/1983. Os dois saem com `vigente=False`, porque a Lei
    14.286/2021 (que está no corpus) revogou o artigo, então `somente_vigente`
    esconde ambos.
  - **`titulosimob_10931_2004` (arts. 38 e 50) e `leidoagro_13986_2020` (11
    casos)** — as duas formas de ruído já catalogadas: texto de lei alterada
    reproduzido entre aspas e a *promulgação das partes vetadas* como segundo
    documento na mesma página. Em todos, o path canônico ficou com o artigo
    **da própria lei**; o citado levou o `__N`.
- **Carga:** `POST /update` em delta com o daemon no ar — 37.456 → **38.629
  pontos**, zero falhas, 734 inalteradas. O saldo é **exatamente os 1.173
  dispositivos do lote**. As 25 normas reindexadas são as 23 do lote mais duas
  que o delta pegou por HTML alterado no Planalto — o **Código Penal** (433) e
  a Lei 9.656/1998, planos de saúde (58) —, sem mudança na contagem delas.
- **Conferido pelas tools:** a busca por investigação de dumping devolve os
  arts. 1º, 82 e 89 do Decreto 8.058; a busca por liquidação extrajudicial
  devolve os arts. 15, 18 e 36 da Lei 6.024; `obter_dispositivo` no `art_1` do
  DL 288 devolve a definição da Zona Franca de Manaus; e a busca por CPR e CRA
  devolve o art. 23 da Lei 11.076 e o art. 1º da Lei 8.929 **já com a redação
  da Lei 13.986/2020 e da Lei 14.421/2022** — a página `l8929.htm` do Planalto
  é ela própria consolidada.
- **Achado colateral, para o backlog** (agravado no lote 20: o art. 67 do
  Estatuto de Roma vem sob uma "Parte IX" cujo rótulo é o § 2º de outro artigo):
  o campo de contexto (`parent_label`)
  contamina-se com corpo de artigo quando o HTML quebra o cabeçalho de seção
  — o art. 67 do Decreto 8.058 aparece sob um "Capítulo X" cujo rótulo é um
  parágrafo inteiro. **Não é do lote**: medindo contexto que começa em
  minúscula, o sintoma já existia no CPC (44 casos), no Código Civil (26), no
  RIR (18), no Regulamento Aduaneiro (14) e no Código Penal (13). O texto
  literal servido não é afetado — só o rótulo de contexto entre parênteses.

- [x] **10º lote — os regimentos internos do Senado e da Câmara** *(executado em
  2026-08-31)*: 759 → **761 documentos**, com o **RISF** (Resolução do Senado
  Federal nº 93, de 1970 — 448 dispositivos) e o **RICD** (Resolução da Câmara
  dos Deputados nº 17, de 1989 — 316). Motivo do lote: **o rito das Casas não
  está na lei**. A Constituição fixa o processo legislativo em traço largo
  (arts. 59 a 69) e devolve o resto ao regimento de cada Casa (art. 51, III, e
  art. 52, XII); prazo e admissibilidade de emenda, regime de urgência,
  competência de comissão, quórum de deliberação, questão de ordem e recurso ao
  Plenário são matéria regimental. Antes deste lote o corpus respondia processo
  legislativo pela Constituição e pela LCP 95 — que é técnica de redação, não
  rito —, e não tinha uma linha sobre como uma proposição efetivamente tramita.
- **Primeira fonte fora do Planalto na parte legislativa do corpus.** As
  súmulas já vinham de outro lugar, mas de um JSON do próprio repositório; aqui
  o pipeline baixa HTML de terceiro pela primeira vez. Duas diferenças mordem, e
  as duas são silenciosas:
  - **Encoding.** As páginas das Casas são servidas em UTF-8 e declaram o
    charset; `decode_planalto` supõe Windows-1252 na ausência de BOM, e
    aplicá-lo devolveria `CÃ¢mara` em cada palavra acentuada — o bug nº 8 ao
    contrário, e igualmente invisível para o parser, que continuaria achando os
    artigos. Daí `ingest/parlamento_fetcher.py`, que lê o charset declarado.
    Não dá para unificar com o Planalto, que não declara nenhum: a suposição
    certa depende da fonte.
  - **Mais de um documento por URL.** A página da Câmara traz **três**: os 8
    artigos de promulgação da Resolução 17, o Regimento anexo — que recomeça em
    `Art. 1º` — e a Resolução 25/2001 com o Código de Ética. É o mesmo mecanismo
    já catalogado no backlog ("decreto e anexo dividem o mesmo espaço de path"),
    e aqui ele custava caro: sem tratamento, `art_1` do RICD seria *"O Regimento
    Interno da Câmara dos Deputados passa a vigorar na conformidade do texto
    anexo"* e o art. 1º de verdade levaria o sufixo `__1` — **31 paths
    duplicados, medidos antes do corte**. A página do Senado tem a versão branda
    do mesmo problema: fecha com a nota de compilação e o rodapé do portal, que
    entravam colados ao art. 413.
- **O `recorte` resolve os dois casos sem tocar no parser.** `NormaMeta` ganhou
  um par opcional de marcadores (início, fim) e `html_parser.recortar` reduz a
  página ao trecho que é o documento, antes de `parse_dispositivos`. Foi
  escolhido em vez da correção estrutural (o parser reconhecer cabeçalho de
  anexo e emitir `anexo_*`) por uma razão de custo: aquela muda o esquema de
  identificador e **obriga a reindexar o corpus inteiro** — segue no backlog,
  agora com um segundo caso para justificá-la. O cache e o hash continuam sendo
  os da **página inteira**, então o delta enxerga qualquer mudança na fonte,
  inclusive fora do recorte.
- **Marcador ausente aborta a norma, de propósito.** O fallback natural
  ("não achei o marcador, parseio tudo") traria de volta exatamente a mistura de
  documentos que o recorte existe para impedir, e com cara de sucesso — a
  assinatura de todos os defeitos caros deste projeto. `recortar` levanta
  `ValueError`, e o pipeline reporta a norma em `falhas` sem tocar nos pontos
  que ela já tem.
- **O marcador é casado com tolerância a quebra de linha.** A página da Câmara é
  uma exportação do LibreOffice e quebra a linha no meio do próprio título
  (`RESOLUÇÃO` numa linha, `Nº 25, DE 2001` na seguinte); busca por literal
  falhava. `_marcador` converte o texto do marcador em regex com `\s+` entre as
  palavras.
- **URN pela autoridade da Casa, não pela União.** `urn:lex:br:senado.federal:`
  `resolucao:1970-11-27;93` e `urn:lex:br:camara.deputados:resolucao:`
  `1989-09-21;17`: resolução de Casa é norma interna dela, e `federal` no LexML
  é a União. A conferência contra o resolvedor do LexML **não foi possível** — o
  serviço estava atrás de um desafio JS do WAF do Senado no dia da execução
  (503 no resolvedor, página de "verificação de segurança" no SRU). As datas
  vieram da fonte: a do RISF da própria página de metadados do Senado
  ("Resolução do Senado Federal nº 93 de 27/11/1970"), a do RICD do fecho
  impresso no texto ("Brasília, 21 de setembro de 1989").
- **Verificação:** `verificar_parser.py` passou a aplicar o mesmo recorte que o
  pipeline — sem isso a ferramenta que existe para achar path duplicado
  apontaria os 31 que a carga não tem. Lote conferido: **2 normas, 764
  dispositivos, 0 suspeitos** — o primeiro lote a sair limpo já na primeira
  passagem desde que a heurística existe.
- **Carga:** `POST /update` em delta, com o daemon **reiniciado antes**. Entrada
  curada nova não é vista por `recarregar_registro()`, que relê os JSON gerados
  mas não o `REGISTRO_CURADO`, que mora no código: com o daemon velho no ar, o
  `POST /update` teria devolvido `atualizadas: {}` — a mesma armadilha do lote 5,
  por outro caminho. 38.629 → **39.393 pontos**, zero falhas, 749 inalteradas.
  O saldo é **exatamente** os 764 dispositivos do lote: as 12 normas reindexadas
  são as 2 do lote mais 10 que o delta pegou por HTML alterado no Planalto
  (Lei 14.133, LRF, Maria da Penha, LDO 2026, LCP 214 e mais cinco), nenhuma
  com mudança na contagem de dispositivos.
- **Conferido pelas tools:** `obter_dispositivo` no `art_1` do RICD devolve *"A
  Câmara dos Deputados, com sede na Capital Federal, funciona no Palácio do
  Congresso Nacional"* — e não a cláusula de promulgação, que era o risco do
  lote; a busca por requerimento de urgência devolve os arts. 155 e 157 do RICD
  com a hierarquia certa (`TÍTULO V - CAPÍTULO VII - DA URGÊNCIA - Seção II`); a
  busca por questão de ordem devolve os arts. 405 e 408 do RISF; e o
  `tipo_norma="regimento"` isola a espécie na busca.
- **Ficaram de fora, e são os vizinhos óbvios do próximo lote:** o **Regimento
  Comum do Congresso Nacional** (Resolução nº 1, de 1970-CN, ~160 artigos), que
  rege sessão conjunta, veto e orçamento, e cuja página do Senado tem a mesma
  forma da do RISF; e o **Código de Ética e Decoro Parlamentar da Câmara**
  (Resolução nº 25/2001, 19 artigos), que já vem baixado na mesma página do RICD
  e só precisa de uma segunda entrada com o recorte complementar.

- [x] **11º lote — estrutural: ADCT e anexos** *(executado em 2026-09-14, abre a
  onda de expansão do [PLANO_EXPANSAO_CORPUS.md](PLANO_EXPANSAO_CORPUS.md))*:
  zero normas novas de rede, **um documento novo** (o ADCT) e o único lote da
  onda que muda o esquema de identificadores — por isso foi primeiro, com
  reindexação completa do cache (`pipeline_version` 0.4.0 → 0.5.0).
- **O ADCT estava no índice como fantasma.** A página da CF traz o ADCT
  recomeçando em `Art. 1º`, e o parser gerava **128 paths `__N`**: `art_1__1`
  era o art. 1º do ADCT e `art_97` (precatórios) só existia como `art_97__1`.
  Pior — e só a comparação norma a norma revelou —, **o índice servia o art.
  117 do ADCT como art. 117 da CF**: o art. 117 do corpo está revogado
  (tachado) e a regra "versão não tachada vence" elegia a do ADCT. É o `recorte`
  do lote 10, sem parser: `cf_1988` corta em `ATO DAS DISPOSIÇÕES
  CONSTITUCIONAIS TRANSITÓRIAS` e `adct_1988` começa ali (URN sintético
  `...;1988!adct`, com o `!` de fragmento do LexML). CF 413 → 276 dispositivos,
  0 duplicados; ADCT 149 (arts. 1 a 138, com sufixos).
- **Anexo como dispositivo próprio** (item de backlog, agora fechado). A
  medição no cache mostrou a forma real antes do regex: 64 normas com `ANEXO`
  depois do fecho; `ANEXO` maiúsculo **antes** do fecho só dentro de texto
  citado (LCP 227, Lei 11.105); o RPS grafa `A N E X O I` espaçado; a LCP 214
  aninha os anexos da LCP 123 dentro dos seus ("ANEXO XVIII ... ANEXO I
  Alíquotas"); a Lei 11.457 imprime cabeçalho duplo ("ANEXO I (Anexo I da Lei
  10.910) ANEXO I ESTRUTURA"). Daí as regras: cabeçalho é `ANEXO` maiúsculo
  (inclusive espaçado), só depois do primeiro fecho quando há fecho, não
  precedido de aspa de abertura nem de preposição ("no ANEXO XV"), e dois
  cabeçalhos a menos de 120 chars são um só. No escopo do anexo o artigo sai
  com prefixo (`anexo_art_1`, `anexo_ii_art_3`) e aceita a grafia por extenso
  dos tratados (`Artigo 8º`, `ARTIGO 1`, `Artigo XII` em romano — quatro
  convenções da OIT), normalizada para `art_N`; anexo sem artigo vira texto em
  partes de 4 KB (`anexo_i`, `anexo_i_p2`). O cache não muda, então a carga foi
  `reindexar_do_cache.py`.
- **Texto aprovado apenso é outro problema, e a resposta é `recorte`, não
  prefixo.** A medição achou 5 normas com mais artigos depois do fecho que
  antes: CLT (2 vs 1.018 — o DL 5.452 aprova a Consolidação e a serve apensa,
  **sem** cabeçalho de anexo, e `art_1` era "Fica aprovada a Consolidação..."),
  RPS (3 vs 470), RIR (5 vs 1.050), BPC (4 vs 60) e ANEEL (6 vs 32). Nas quatro
  primeiras o apenso é o documento que se cita — "CLT, art. 7º" tem de ser
  `art_7` — e o corpo é cláusula de aprovação: entraram com `recorte` no título
  em caixa alta (o `registro_decretos.json` ganhou o campo, gravado por
  `RECORTES` em `descobrir_decretos.py`). A ANEEL ficou sem recorte: os 6
  artigos do corpo constituem a agência e a Estrutura Regimental vai para
  `anexo_i_art_N`. `verificar_parser.py` ganhou a regra "texto apenso sem
  recorte" para apontar caso novo (dispara na CLT e no RPS sem o recorte; não
  dispara nas normas de forma normal).
- **Medição norma a norma (parser antigo × novo, 698 HTMLs):** 39.351 →
  41.374 dispositivos (+2.063 de anexo); duplicados `__N` 594 → 492 (CF 128 →
  0, RIR 5 → 0, BPC 4 → 0, RPS 3 → 0, CLT 7 → 5); nenhum path canônico
  perdido fora da ANEEL (decisão) e do ADCT (mudou de documento); art. 382 do
  RPS de 211 KB → 291 chars, art. 922 da CLT de 24 KB → 161 (o quadro do art.
  577 virou `anexo`). O Dec. 10.088 (OIT) passou de 6 para **1.651**
  dispositivos, todas as convenções estruturadas; o Código de Ética do Dec.
  1.171 entrou como `anexo` em partes. `__N` novos: OIT 56 (convenção +
  protocolo com a mesma numeração no mesmo anexo), LDO 2018 4 ("ANEXO IV" à
  frente de cada seção IV.1, IV.2...), LOA 2022 2, ANAC 1, ADCT 1 (art. 111 com
  duas redações não tachadas) — repetições reais da fonte, não do parser.
- **Suspeitos do corpus** (`verificar_parser`): 676 → 621 com o parser novo;
  parte de anexo (`_p2`...) fica isenta da regra de minúscula, porque começa
  onde a anterior cortou.
- **Preço aceito:** os 2-5 artigos de aprovação/vigência dos decretos com
  recorte (RIR, RPS, BPC) e os 2 do DL 5.452 saem do índice. O art. 4º do RIR
  ("Fica revogado o Decreto nº 3.000") não é o que se consulta num Regulamento
  de 1.049 artigos.

- [x] **13º lote — direito público de base, 24 normas** *(executado em
  2026-09-14)*: 762 → **786 documentos**. Organização administrativa (DL
  200/1967, emprego público 9.962, carreiras do Judiciário 11.416, PGF 10.480,
  honorários da advocacia pública 13.327), patrimônio e desapropriação (DL
  3.365/1941, Lei 4.132, DL 9.760/1946, Lei 9.636, DL 2.398/1987, Lei 13.240),
  processo contra a Fazenda (8.437, 9.494, 9.873, organização da JF 5.010,
  representação interventiva 12.562), segurança e defesa (serviço militar
  4.375, Sisbin/ABIN 9.883, LO das PMs e Bombeiros 14.751, Força Nacional
  11.473), urbano e cartórios (Estatuto da Metrópole 13.089, licitação de
  publicidade 12.232, desburocratização 13.726, notários 8.935). **24/24
  validadas**, datas e ementas da API do LexML com o `name` batendo, epígrafe
  conferida na página. A Lei 14.751 é a LO das **Polícias Militares**, não da
  PF, como o plano da onda supunha — entrou com o apelido certo.
- **Diretório novo de URL**: o DL 2.398/1987 só existe em
  `decreto-lei/1965-1988/`, que `variantes_url` não conhecia (o DL 200 e o DL
  288 estão em `decreto-lei/`). A faixa 1965-1988 passou a gerar os dois
  diretórios, com regressão em `test_planalto_urls.py`.
- **🐛 Bug nº 11, achado pela verificação do lote — e ele era do corpus
  inteiro.** `Art. 1º-A` saía como `art_1__1` com o texto "A. Estão
  dispensadas...": o Planalto grafa `Art. 1<sup>o</sup>-A`, o achatamento vira
  `Art. 1 o -A` (espaço antes do hífen) e o sufixo só era aceito colado. A Lei
  9.494 apontou (8 `__N` em 12 artigos: os arts. 1º-A a 1º-F, que são o que se
  consulta nela) e a medição no cache achou **148 artigos em 58 normas**, 139
  deles com `__N`: LCP 123 arts. 3º-A/3º-B, CTB art. 7º-A, LCP 116 art. 8º-A,
  Lei 8.666 art. 5º-A, Fies (12), seguro-desemprego (9)... Fix: espaço opcional
  **antes** do hífen, nunca depois — "Art. 100 - A ação penal" e "Art. 312 -
  Apropriar-se" continuam caput, e o teste trava os dois. Medido no corpus:
  `__N` 537 → 409, **133 paths com sufixo novos, zero suspeitos** (nenhum
  começa em minúscula). Restam 24 casos que são erro da fonte: `Art. 6ºA.` sem
  hífen (Lei 8.080), `Art. 359-M-A` com sufixo duplo (CP), letras espaçadas por
  `<span>` (LCP 123 art. 18-C) — ficam como a fonte publica.
  **Heurística de detecção (reproduzível):** artigo cujo texto casa
  `^[A-Z]\s?[.\-–]\s` — uma letra maiúscula seguida de ponto ou hífen.
- **Os demais suspeitos do lote** (36 no total) eram, um a um, ruído
  catalogado: duas redações do mesmo artigo (Lei 5.010 art. 75, Lei 9.636 art.
  16, DL 200 arts. 20/31/54 — este último com cabeçalhos de ministérios
  colados), caput minúsculo por erro da fonte (DL 9.760 art. 65 "poderão ser
  alienadas", Lei 4.375 art. 50 "incorrerá na multa") e anexo com duas
  redações (Lei 11.416, `anexo_i__1`).
- **Carga:** como o fix exigiu bump (`pipeline_version` 0.5.1) e as 24 já
  estavam em cache pelo `--baixar`, a carga foi uma só `reindexar_do_cache`
  com o daemon parado, em vez de `POST /update`.

- [x] **14º lote — direito privado, família e penal especial, 31 normas** e
  **15º lote — trabalho, profissões regulamentadas e previdência, 39 normas**
  *(executados em 2026-09-14)*: 786 → **856 documentos**. No 14: Lei das
  Contravenções (DL 3.688), tombamento (DL 25/1937), alienação fiduciária (DL
  911), cédula hipotecária (DL 70), títulos de crédito rural (DL 167), alimentos
  (DL 986), bem de família (8.009), cheque (7.357), ação de alimentos (5.478),
  paternidade (8.560), divórcio (6.515), alimentos gravídicos, alienação
  parental, distrato (13.786), marco das garantias (14.711), SAF (14.193),
  prisão temporária (7.960), tráfico de pessoas (13.344), escuta protegida
  (13.431), primeira infância (13.257), bullying, violência sexual (12.845),
  "Não é Não" (14.786), violência política de gênero (14.192), PcD (7.853,
  8.899), Libras (10.436), refúgio (9.474), terras indígenas (14.701), cotas em
  concursos (15.142/2025) e transporte de eleitores (6.091). No 15: 13º salário
  (4.090 e 4.749), vale-transporte, PAT, discriminação no trabalho (9.029),
  motorista (13.103), avulso (12.023), cooperativas de trabalho (12.690),
  Estatuto da Segurança Privada (14.967/2024), RPPS da União (10.887),
  aposentadoria especial do cooperado (10.666), revisão de benefícios (13.846)
  e **27 leis de profissão** (medicina, enfermagem, engenharia, arquitetura,
  contabilidade, farmácia, psicologia, serviço social, educação física,
  nutrição, veterinária, odontologia, corretores de imóveis e de seguros,
  taxista, artistas, radialista, jornalista, médicos, petroleiros, bombeiro
  civil, guia de turismo, administrador, economista, fisioterapia,
  biologia/biomedicina, radiologia). A Lei 14.434 (piso da enfermagem) ficou
  de fora por só alterar a 7.498, que entra compilada.
- **Três padrões de URL novos**, todos com regressão em `test_planalto_urls.py`:
  o DL 70/1966 só existe em `del0070-66.htm` (número repetido em anos
  distintos ganha o ano como sufixo); seis leis de profissão (4.119, 8.234,
  3.999, 5.811, 1.411, 6.684) moram nos subdiretórios por faixa `leis/1950-1969/`,
  `1970-1979/`, `1989_1994/` (este com sublinhado), que `variantes_url` passou a
  gerar depois de `leis/`; e o DL 25/1937 caiu na armadilha do sufixo da API do
  LexML na forma curta (resolvido com a data completa).
- **Guarda de referência estendido (lote 15):** "art. 1º **desta** Lei" e
  "art. 3º **neste** Decreto" abriam falso dispositivo (Leis 4.749 e 7.394, com
  o path canônico do art. 1º ameaçado). O `_REFERENCIA` do bug nº 9 passou a
  cobrir os demonstrativos; medido no corpus, mexe em 4 normas (as duas do
  lote, o Código de Mineração e a OIT) sem perder path canônico.
  `pipeline_version` 0.5.2.
- **Suspeitos** (44 no 14 + 15, todos inspecionados): promulgação de partes
  vetadas (Lei 14.701, 24 `__N`), duas redações (DL 70 art. 31, Lei 5.478 arts.
  16/18, Lei 6.091 art. 17), e erro da fonte — a Lei do Cheque grafa literalmente
  "Art . 52 portador", sem o "O". Nenhum bug novo.
- **Carga:** uma `reindexar_do_cache` só, com os lotes 13-15 e o parser 0.5.2:
  **44.631 pontos em 856 normas**, zero falhas.

- [x] **16º lote — tributário e financeiro, 22 normas; 17º lote — saúde,
  educação, ambiente, energia, agrário e comunicação, 38 normas; 19º lote —
  decretos de técnica normativa e governança, 23; 20º lote — tratados
  internacionais promulgados, 19** *(executados em 2026-09-14)*: 856 → **958
  documentos**.
- **16:** CSLL (7.689), lucro real (DL 1.598), Ufir/IR (8.383 — fecha o buraco
  medido no lote 8, em que o `art_72` da Rota 2030 era o art. 72 da 8.383
  citado), IRPJ pós-IFRS (12.973), parcelamento/RTT (11.941), compensação de
  prejuízos (9.065), IOF (8.894), Cide-Combustíveis, PIS/Cofins agro (10.925),
  ZPE, Padis, perdimento (DL 1.455), encargo legal (DL 1.025), PRR (13.606),
  desoneração da folha (14.973/2024), autorregularização (14.740), Carf
  (14.689), Perse, transparência tributária (12.741), CFEM (8.001), CMED
  (10.742) e parcelamento dos entes/registro de ativos (12.810). Ficaram de
  fora as que só alteram outra lei (13.476, 13.540, 13.259) e o Desenrola.
- **17:** transplantes (9.434), propaganda de fumo (9.294), comércio
  farmacêutico (5.991), sangue (10.205), vigilância epidemiológica/PNI (6.259),
  Institutos Federais (11.892), piso do magistério (11.738), PNAE, salário-
  educação (9.766), PNATE, psicologia nas escolas, royalties para educação
  (12.858), fauna (5.197), Ibama, ICMBio, informação ambiental (10.650),
  zoneamento industrial, cetáceos, Bolsa Verde, **mercado de carbono
  (15.042/2024)**, Combustível do Futuro (14.993), *offshore* (15.097/2025),
  Eletrobras (14.182), EPE, renovação das concessões (12.783), terras a
  estrangeiros (5.709), Terra Legal (11.952), crédito rural (4.829, 8.427),
  cultivares, orgânicos, armazenagem, rádio comunitária, EBC, direito de
  resposta e apostas (14.790). **Achado de mérito na inspeção:** o art. 19 da
  Lei 10.696 (PAA) está revogado — o PAA vigente é a **Lei 14.628/2023**, que
  entrou no lugar, e a 10.696 ficou com o apelido de repactuação de dívidas.
- **19:** elaboração de atos normativos (9.191), LINDB (9.830), AIR (10.411),
  nepotismo (7.203), SEI (8.539), consórcios (6.017), estatais (8.945),
  orçamento de obras (7.983), demarcação indígena (1.775), quilombolas (4.887),
  povos tradicionais (6.040), Libras (5.626), revisão de atos (10.139),
  colegiados (9.759), dados abertos (8.777), processo fiscal (7.574),
  digitalização (10.278), arquivos (4.073), informação classificada (7.845),
  simplificação (9.094), desfazimento de bens (9.373 — no lugar do 99.658,
  revogado), diárias (5.992) e leiloeiros (21.981/1932). A regra "texto apenso
  sem recorte" apitou no Dec. 21.981 e o caso mostrou o refinamento: corpo com
  "Artigo único" (sem número) não colide com o Regulamento apenso, e a regra
  passou a exigir corpo com artigo numerado.
- **20 — a espécie que o lote 11 destravou:** Pacto de São José, PIDCP,
  PIDESC, tortura, criança, CEDAW, Belém do Pará, discriminação racial, os
  **três de status constitucional** (PcD, Marraqueche, racismo), Estatuto de
  Roma, Palermo, Mérida, Haia (sequestro de crianças), apostila, Viena
  (tratados), Assunção (Mercosul) e Paris. **O gate próprio do lote pegou na
  primeira passada:** metade entrou com 2-3 dispositivos, nenhum da Convenção
  — o Planalto serve o tratado **colado ao fecho, sem cabeçalho `ANEXO`**
  ("Este texto não substitui o publicado... CONVENÇÃO CONTRA A TORTURA...
  Artigo 1"), e o marcador por extenso só valia em escopo de anexo. Fix: depois
  do fecho, o primeiro "Artigo N" abre um **anexo implícito** (`anexo_art_N`);
  "Art." não é afetado, então a promulgação de partes vetadas segue como
  antes. Segundo achado, também dos tratados: a **referência corrida por
  extenso** ("em conformidade com o Artigo 8º", "no Artigo 4(1)") abria falso
  dispositivo — 35 em 60 no Marraqueche; o que a denuncia é o que vem antes
  (artigo definido ou preposição), e o guarda `_REF_ARTIGO_ANTES` a descarta.
  Resultado: os 19 tratados com 22 a 128 artigos cada, `__N` só na Convenção
  sobre PcD (Convenção + Protocolo Facultativo numerados do 1) — e a OIT caiu
  de 1.651 para 1.618 dispositivos (33 referências que eram falsos artigos).
  `pipeline_version` 0.5.3. Ficaram de fora a Lei Uniforme de Genebra (Dec.
  57.663) e a CDB (Dec. 2.519): a página traz só o decreto e o texto do tratado
  está em arquivo à parte.
- **Mais três padrões de URL** (`test_planalto_urls.py`): decretos de 1995-1998
  em `decreto/{ano}/` (Dec. 1.973/1996), decretos anteriores a 1970 em
  `decreto/1950-1969/` e com extensão **`.html`** (Dec. 65.810/1969 — o portal
  responde 300 ao `.htm`), e decretos anteriores a 1950 em `decreto/1930-1949/`
  (Dec. 21.981/1932).
- **`reindexar_do_cache.py --novos` e `--slug`** (novos): indexam só as normas
  ausentes do `state` ou as nomeadas, sem recriar a coleção, reusando
  `reindex_norma` do pipeline (apaga + reinsere + registra) — a lógica deixou de
  estar duplicada no script. É o que o `POST /update` faria para o lote, menos
  o download do corpus inteiro para conferir hash.

- [x] **21º lote — resoluções do Senado e do Congresso, 11 documentos, espécie
  e fonte novas** *(executado em 2026-09-15)*: 958 → **969 documentos**,
  48.314 → **48.818 pontos**. Entram com tipo `regimento` o Regimento Comum
  (Res. 1/1970-CN), a resolução de tramitação das MPs (1/2002-CN), a da CMO
  (1/2006-CN) e os dois Códigos de Ética (Res. 20/1993-SF e 25/2001-CD); com
  tipo **`resolucao`** (novo no vocabulário do `tipo_norma`), as do art. 52 da
  CF: RSF 40 e 43/2001 (dívida e crédito dos entes), 48/2007 (crédito e
  garantias da União), 13/2012 (ICMS de importados), 95/1996 (ICMS no
  transporte aéreo) e 9/1992 (ITCMD).
- **Fonte, resolvida pela API de dados abertos do Senado:**
  `legis.senado.leg.br/dadosabertos/legislacao/lista?tipo=RSF&numero=40&ano=2001`
  dá o **id da norma** (562458), a data de assinatura e a ementa; a página
  `norma/{id}` lista as publicações, e a que serve o texto compilado é a
  **"Compilação Multivigente"** (`norma/562458/publicacao/16433576`) — ou a
  publicação original quando é a única. O id `582803` sondado no planejamento
  era outra norma (uma permissão de radiodifusão), daí os "zero artigos". As
  URNs (`urn:lex:br:senado.federal:resolucao:2001-12-20;40`,
  `urn:lex:br:congresso.nacional:resolucao:1970-08-11;1`) são as que a própria
  API imprime em `urlDocumento` — oficiais, não sintéticas. O documento vem
  como um `<html>` interno (exportação do Word) embutido na página do portal.
- **Fecho da Casa não tem "Nº da Independência"**, então o `_FECHO` não corta
  assinatura e notas — e casar cidade+data está descartado de propósito no
  próprio comentário do regex. Solução coerente com o RISF: `recorte`
  terminando no fecho impresso ("Senado Federal, em 9 de abril de 2002") ou,
  quando a página não o imprime, no traço/nota que fecha o articulado. Todas as
  11 entradas são curadas (`_RESOLUCOES_SENADO` em `urn_mapper.py`, mais o
  Código de Ética da Câmara como **terceiro documento da página do RICD**, com
  recorte a partir do cabeçalho do Código). `TIPOS_PARLAMENTO` passou a incluir
  `resolucao`. O `conferir_data` por espécie previsto na Fase 0 **não se
  aplica**: a epígrafe do Senado traz só o ano ("RESOLUÇÃO Nº 40, DE 2001"); a
  data conferida é o `dataassinatura` da API.
- **Ficou de fora a RSF 22/1989** (alíquotas interestaduais do ICMS, 7% e 12%):
  a única publicação disponível é uma conversão de PDF com as palavras
  quebradas na fonte ("alí quota", "sobr e", "Faç o"), e reconstituir o texto
  seria inventar o que o Senado não publicou. Fica no backlog, a reincluir se
  o portal servir uma compilação limpa. Suspeito único do lote: o art. 69-A
  da CMO com duas redações (`__1`, padrão conhecido). Verificação por tools:
  RSF 40 art. 3º (limites de 2 e 1,2 RCL), Res. 1/2002-CN arts. 2º e 3º
  (comissão mista), Código de Ética da Câmara art. 4º.

- [x] **22-A — súmulas simples do STF, 664 enunciados, tipo `sumula_stf`**
  *(executado em 2026-09-15)*: 969 → **1.633 documentos**, 48.818 → **49.482
  pontos**. Reabre a decisão do lote 7 só para o STF: mesma fonte das SV
  (`sumariosumulas.asp`, base 30 em vez de 26), mesmo caminho local de
  jurisprudência (`sumulas_stf.json`, dispositivo único `enunciado`), coletor
  `descobrir_sumulas_stf.py` reaproveitando o das SV (`ids_do_indice` e
  `extrair_enunciado` ganharam o rótulo como parâmetro) e gate
  `verificar_sumulas.py --stf`. As páginas ficam em `data/raw/pagina_sumula_stf_N`
  (prefixo próprio: sob o slug o pipeline grava o JSON canônico), e
  `reindexar_do_cache --novos` aprendeu a servir tipo jurisprudencial do JSON.
- **Situação é a do STF, sem juízo próprio:** cancelada (6), revogada (3),
  superada (1) entram não vigentes com a palavra do Tribunal; "alterada" (359)
  é vigente com o texto atual. Súmula materialmente superada mas não
  cancelada segue como o STF a mantém. A marca vem repetida no fim do
  enunciado ("...Ministro de Estado. (cancelada)") e é removida — é
  sinalização do portal, não texto do Tribunal.
- **A data foi o problema — e a suposição da sondagem estava errada.** A
  página imprime a data em só 502 das 736: "Data de aprovação do enunciado:
  Sessão Plenária de D-M-AAAA" (157) ou "Data de publicação do enunciado: DJ
  de D-M-AAAA" (o resto), com variações de forma ("13.12.1963", "1º-6-1964",
  rótulo trocado na Súmula 359) — o regex casa pelo que vem depois dos
  dois-pontos, não pelo rótulo. Regra do URN: aprovação quando impressa, senão
  publicação (as duas são datas do STF; `_referencia` rotula cada uma). Para as
  **234 páginas sem data nenhuma**: os enunciados 1 a 370 são a Súmula original,
  aprovada na Sessão Plenária de 13/12/1963 (única data de aprovação que o
  portal imprime nessa faixa, em 187 páginas), e essa data vale para as 162
  irmãs sem data, com `observacao` dizendo isso — toda a faixa 1–370 tem URN
  em 1963-12-13. **Ficaram de fora 72** (371–497, quase todas, e a 679): acima
  de 370 os lotes de aprovação têm datas variadas e não há como saber a de
  cada uma sem inventar. A pesquisa de jurisprudência do STF, que as teria,
  está atrás de desafio JavaScript do WAF da AWS (`x-amzn-waf-action:
  challenge`) e a antiga `listarJurisprudencia.asp` responde 404. Backlog: as
  72 entram se o portal imprimir a data ou se surgir fonte estruturada.
  A Súmula 323 é publicada sem ponto final (exceção explícita no verificador).
- **Verificação por tools:** "apreensão de mercadorias como meio coercitivo"
  traz a Súmula 323 em 1º, antes do RIPI; a Súmula 4 (cancelada) só aparece
  com `somente_vigente=false`, marcada.

### 6. Operação

- [ ] **Agendamento do `update` — falta só registrar a tarefa.** A máquina já
      existe no repo: [weekly_update.ps1](scripts/weekly_update.ps1) (prefere o
      daemon via `POST /update`, reusando os modelos quentes, e cai para
      `lex-rag-update --mode delta` quando o daemon está fora do ar, evitando
      disputa pelo lock do Qdrant) e
      [register_update_task.ps1](scripts/register_update_task.ps1). Verificado
      em 2026-08-07: **nenhuma tarefa registrada** no Task Scheduler — o script
      de registro nunca foi executado. Ao registrar, evitar "segunda 3h" (o PC
      costuma estar desligado); preferir gatilho de logon ou horário útil com
      `-StartWhenAvailable`.
- [x] `/update` no daemon serializado com `threading.Lock` (retorna "update já
      em andamento" se concorrente) e cliente com timeout próprio de 30 min.
      *(Evolução possível: disparo em background com endpoint de status.)*

### 7. Onda de expansão do corpus *(planejada em 2026-09-14)*

- [ ] Plano completo em [PLANO_EXPANSAO_CORPUS.md](PLANO_EXPANSAO_CORPUS.md):
      lotes 11 a 22, de 761 para ~975 documentos. Abre com o conserto
      estrutural dos anexos (`anexo_*`, item do backlog abaixo) e com o
      **ADCT**, que hoje colide com o corpo da CF — **128 paths `__N`**
      medidos, `art_1__1` é o art. 1º do ADCT —, e segue com cinco lotes
      temáticos de leis, decretos, tratados (dependem dos anexos) e
      resoluções do Senado/CN. Emendas Constitucionais ficaram **fora**: a
      CF compilada já registra a redação de cada EC; só o resíduo das
      emendas com artigos próprios (EC 103, 132) ficou como opcional.

### Backlog menor (sem urgência)

- [x] **Revogação parcial marca o artigo inteiro** *(corrigido em 2026-07-03)*:
  `detectar_revogacao` agora só derruba a vigência quando a marca "(Revogado...)"
  **abre** o texto do dispositivo; marca no meio (parágrafo/inciso inlinado) não
  revoga o caput. Para dispositivos tachados, `extrair_marca_revogacao` continua
  buscando a marca em qualquer posição. **228 dispositivos resgatados** em 23
  normas (CF art. 40, CP art. 121, CLT etc.). O fix desmascarou um segundo bug,
  corrigido junto: o Planalto também tacha por **CSS inline**
  (`text-decoration: line-through` — ex.: Lei 8.666 art. 3º), que `_flatten` não
  reconhecia; a detecção via `_e_tachado` eliminou ~70 chunks fantasma de
  redação superada (Cód. Florestal −19, LCP 123 −19, LGPD −11...). Testes de
  regressão em [test_ingest.py](tests/unit/test_ingest.py).
- **A CLI do `update` não imprime `falhas`** ([cli.py](src/lex_rag/update/cli.py)
  mostra só `atualizadas`, `inalteradas` e `total_pontos`). Numa rodada
  desatendida, norma que falhou no download some do relatório — hoje só dá para
  inferir por aritmética. Corrigir **antes** do agendamento (item 6).
- **Decreto e anexo dividem o mesmo espaço de `path`** *(achado no lote 5)*: nos
  decretos que "aprovam o Regulamento anexo", o corpo do decreto tem seus 2-6
  artigos e o anexo **recomeça em Art. 1º**. Os primeiros colidem e o anexo leva
  o sufixo `__N` (RIR: `art_1` é "Fica aprovado o Regulamento...", e o art. 1º do
  Regulamento vira `art_1__1`); do art. 3º em diante não há colisão e o **anexo
  ocupa o path canônico** — `art_10` do RIR é do Regulamento, `art_1` é do
  decreto. Medido: **19 dispositivos em 4 normas** (RIR 6, ANEEL 6, BPC 4, RPS
  3). O texto está íntegro e a busca acha os dois; o que fica ambíguo é a
  citação por path — `obter_dispositivo(art_1)` no RIR devolve a cláusula de
  aprovação, não o art. 1º do Regulamento. Corrigir exige o parser reconhecer o
  cabeçalho de anexo e prefixar o path (`anexo_art_1`), o que muda o esquema de
  identificador e obriga a reindexar o corpus inteiro — daí ficar no backlog, e
  não no lote. **O mesmo mecanismo esvazia o que vive só em anexo:** o Código de
  Ética do servidor (Dec. 1.171/1994) entrou com 3 dispositivos e as convenções
  da OIT (Dec. 10.088/2019) com 6 — o corpo do decreto, não o anexo, que o
  parser não estrutura. Foi por isso que o bloco de tratados ficou fora deste
  lote (Dec. 678/1992, Pacto de São José: 3 dispositivos, nenhum da Convenção).
  **O lote 6 encareceu este item e mediu o seu tamanho.** O corte no fecho tirou
  do índice o anexo que antes entrava colado ao último artigo: as tabelas de
  alíquotas da LCP 123 (Simples) e da LCP 214, as metas do PNE (160 KB no art.
  37 da Lei 15.388) — 1,23 MB de 31,66 MB do corpus. A troca foi deliberada
  (citação exata em vez de conteúdo mal atribuído), mas quem consulta anexo
  perdeu o que tinha. Reconhecer o cabeçalho de anexo e emitir `anexo_*` resolve
  os dois lados de uma vez, e agora tem um caminho barato de volta: a
  reindexação a partir do cache
  ([reindexar_do_cache.py](scripts/reindexar_do_cache.py)) não precisa da rede.
- **Faixa de artigos revogada em bloco vira dispositivo vigente**: o Planalto
  colapsa "Art. 58-A a 58-V (Revogado pela Lei nº 13.097, de 2015)" numa linha,
  e o parser indexa isso como `art_58_A` vigente, com texto "a 58-V (Revogado
  ...)". Com o lote 2 passou de 2 para ~15 ocorrências (entraram CBA arts.
  77/177/180/184/187, CPPM arts. 458/460, CBT art. 73). Segue cosmético — o
  texto diz que está revogado —, e mexer aqui toca a lógica de revogação, que é
  delicada.
- Ordenação de [listar_alteracoes](src/lex_rag/mcp_server/tools/listar_alteracoes.py)
  ignora sufixos `-A` e duplicatas `__N` (cosmético).
- `http_max_parallel` em [config.py](src/lex_rag/config.py) não é usado (config morta).
- **Referência com "Art." maiúsculo no meio de frase ainda gera chunk fantasma**
  ("...impostas no parágrafo único do Art. 23 e no Art. 26 deste Código"), com
  `__N` quando o artigo real também existe — e, quando a referência vem
  **antes**, é ela que fica com o path canônico. Quantificado no lote 2 em
  **1.202 paths duplicados** (4,3% dos dispositivos) — bem mais do que as "2
  ocorrências" registradas antes. Depois do bug nº 8, caiu para **575 em
  27.837 (2,1%)**, mesmo com 43 normas a mais no corpus: o que sobrou é a
  referência solta, sem aspas em volta.
  **A correção óbvia não é segura, e isso está medido:** a regra "marcador
  precedido de minúscula é referência" derruba artigo de verdade, porque os
  cabeçalhos do Planalto terminam em minúscula e colam no marcador seguinte —
  "Seção II Do Juiz **Art. 146.**", "Capítulo III Da Acumulação **Art. 118.**".
  São 4.689 marcadores nessa forma, quase todos artigos legítimos. Quem for
  mexer aqui precisa de um sinal melhor que a vizinhança imediata (candidato:
  reconhecer o cabeçalho estrutural pelo `_HDR_MARK`, que o parser já casa, e
  tratar só o que sobra como frase em curso).

---

## Referência rápida

- **Catálogo de normas:** `REGISTRO` em [urn_mapper.py](src/lex_rag/ingest/urn_mapper.py)
  (curado + [registro_lcp.json](src/lex_rag/ingest/registro_lcp.json) gerado por
  [scripts/descobrir_lcps.py](scripts/descobrir_lcps.py) +
  [registro_ordinarias.json](src/lex_rag/ingest/registro_ordinarias.json) gerado
  por [scripts/descobrir_ordinarias.py](scripts/descobrir_ordinarias.py) +
  [registro_decretos.json](src/lex_rag/ingest/registro_decretos.json) gerado por
  [scripts/descobrir_decretos.py](scripts/descobrir_decretos.py))
- **Verificação obrigatória de lote:** `python scripts/verificar_parser.py --novos --baixar`
- **Parser:** [html_parser.py](src/lex_rag/ingest/html_parser.py) — inclui o
  `recortar`, que reduz a página ao trecho que é o documento (só os regimentos
  usam; ver o campo `recorte` do `NormaMeta`)
- **Fonte de HTML (fetch + fallback):** [source.py](src/lex_rag/ingest/source.py),
  que despacha para [planalto_fetcher.py](src/lex_rag/ingest/planalto_fetcher.py)
  (Windows-1252), [parlamento_fetcher.py](src/lex_rag/ingest/parlamento_fetcher.py)
  (UTF-8, regimentos) ou [jurisprudencia.py](src/lex_rag/ingest/jurisprudencia.py)
  (JSON local)
- **Bootstrap:** [scripts/bootstrap_full_index.py](scripts/bootstrap_full_index.py)
- **Update incremental:** [update/pipeline.py](src/lex_rag/update/pipeline.py)
- **Controle do daemon:** `lexrag daemon-start | daemon-status | daemon-stop`

### Heurística de detecção do bug nº 1 (para revalidar após o fix)

```python
import re
from lex_rag.ingest.source import obter_html
from lex_rag.ingest.html_parser import parse_dispositivos
from lex_rag.ingest.urn_mapper import REGISTRO

for slug in ["cp_2848_1940", "clt_5452_1943"]:
    ds = parse_dispositivos(obter_html(REGISTRO[slug]))
    susp = [d for d in ds if re.search(r"-[A-Z]$", d.label) and d.texto[:1].islower()]
    print(slug, "suspeitos:", len(susp))  # esperado ~0 após o fix
```

### Varredura que fundamentou a regra do sufixo (reproduzível)

```bash
# sufixos colados legítimos:
grep -oh "Art\. [0-9]\{1,4\}[ºo°]\?-[A-Z]" data/raw/*.html | sort | uniq -c
# candidatos a sufixo espaçado (única legítima: LCP 95 "Art. 18 - A (VETADO)"):
grep -oh "Art\. [0-9]\{1,4\}[ºo°]\? - [A-Z][^a-zà-ú][^<]\{0,40\}" data/raw/*.html | sort -u
```
