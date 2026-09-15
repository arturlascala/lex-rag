# Onda de expansão do corpus — lotes 11 a 22 (sem o 12)

> Planejada em 2026-09-14, sobre o estado do 10º lote: **761 documentos / 39.393
> pontos**. Meta da onda: **~975 documentos / ~49.000 pontos** (+215 docs,
> +10.000 pontos), com **duas espécies novas** (tratado promulgado e resolução
> do Senado/Congresso), **um conserto estrutural** que o
> backlog vinha adiando (anexo como dispositivo próprio) e **um defeito medido
> na CF** (o ADCT colide com o corpo da Constituição) corrigido antes de tudo.
>
> A onda respeita o que os 10 lotes ensinaram: cada lote passa por
> `verificar_parser.py --novos --baixar` **antes** de indexar; suspeito se
> inspeciona um a um; fix de parser exige bump de `pipeline_version` e
> reindexação do cache; entrada curada exige reiniciar o daemon; e o Planalto
> estrangula depois de algumas centenas de downloads seguidos, então os lotes
> são de 25 a 60 páginas e ficam dias entre si.

---

## Diagnóstico — o que falta e por quê

Medido por varredura do `REGISTRO` (761 entradas) contra o mapa da legislação
federal, não de memória de nomes:

| Flanco | Situação hoje | O que a onda faz |
|---|---|---|
| **ADCT** | Está no índice, mas como fantasma: a página da CF traz o ADCT recomeçando em `Art. 1º`, e o parser gera **128 paths `__N`** (`art_1__1` = ADCT art. 1º). `obter_dispositivo(cf_1988, art_3)` nunca alcança o ADCT; `art_97` (precatórios) só existe como `art_97__1` se o corpo tiver art. 97 — e tem. | Lote 11-A: dois documentos via `recorte` (mecanismo do lote 10). |
| **Anexos** | Item de backlog com três justificativas acumuladas: decreto e anexo dividem o path (RIR, ANEEL, BPC, RPS); o que vive só em anexo entra vazio (Dec. 1.171: 3 disp.; Dec. 10.088/OIT: 6; Pacto de São José: 3); e o corte no fecho do bug nº 10 tirou 1,23 MB de anexo normativo (tabelas da LCP 123 e 214, metas do PNE). | Lote 11-B: parser reconhece cabeçalho de anexo e emite `anexo_*`; reindexação do cache. |
| **Tratados internacionais** | Zero utilizável (Dec. 678 entrou com 3 dispositivos, nenhum da Convenção). Inclui os de **status constitucional** (Convenção sobre PcD, Marraqueche, Convenção Interamericana contra o Racismo). | Lote 20, dependente do 11-B. |
| **Decretos-lei de base** | Só os codificados e os fiscais/econômicos. Faltam DL 200/1967 (organização administrativa), DL 3.365/1941 (desapropriação), DL 25/1937 (tombamento), DL 3.688/1941 (contravenções), DL 911/1969, DL 70/1966, DL 167/1967, DL 1.598/1977 (lucro real), DL 9.760/1946 (imóveis da União). | Lotes 13, 14 e 16. |
| **Leis de base do direito privado e processual** | Faltam bem de família (8.009), cheque (7.357), alimentos (5.478), paternidade (8.560), divórcio (6.515), medidas contra a Fazenda (8.437, 9.494), prescrição administrativa (9.873), notários (8.935), organização da JF (5.010). | Lotes 13 e 14. |
| **Profissões regulamentadas** | Só advocacia, magistério federal e (via CLT) o geral. Falta o bloco inteiro: medicina, enfermagem, engenharia, contabilidade, farmácia, psicologia... | Lote 15, por varredura da API do LexML. |
| **Tributário estrutural** | Tem PIS/Cofins, IRPJ 9.249/9.430, mas falta **CSLL (7.689)**, **DL 1.598**, **12.973/2014** (IRPJ pós-IFRS), 11.941, IOF (8.894), Cide-combustíveis (10.336). | Lote 16. |
| **Setoriais recentes de alto uso** | Mercado de carbono (15.042/2024), Combustível do Futuro (14.993/2024), Eletrobras (14.182/2021), apostas (14.790/2023), segurança privada (14.967/2024), marco das garantias (14.711/2023), SAF (14.193/2021), marco temporal (14.701/2023), cotas em concursos (15.142/2025). | Lotes 14 a 17. |
| **Decretos de técnica normativa e governança** | Falta o Dec. 9.191/2017 (elaboração de atos normativos — o regulamento da LCP 95, que está no corpus), Dec. 9.830/2019 (LINDB arts. 20-30), Dec. 10.411/2020 (AIR), Dec. 7.203/2010 (nepotismo), Dec. 8.539/2015 (SEI). | Lote 19. |
| **Resoluções do Senado (art. 52 CF) e do Congresso** | Zero. O Regimento Comum, as resoluções de limite de dívida (40 e 43/2001, 48/2007) e de alíquota de ICMS (22/1989, 13/2012) são consultadas tanto quanto lei. | Lote 21, espécie e fonte novas. |
| **Súmulas STF (não vinculantes) e STJ** | Zero, por decisão do lote 7 (só força *erga omnes*). | Lote 22, opcional, pelo caminho local de jurisprudência já existente. |

**Fora da onda, de propósito:** medidas provisórias em vigor (voláteis — o URN
morre em 120 dias), acórdãos e informativos (fora de escopo por decisão do lote
7), varredura cega de ordinárias (relação sinal/ruído medida no lote 1) e
portarias/instruções normativas (fonte sem página canônica estável) e as
**Emendas Constitucionais como espécie**: a CF compilada já registra, dispositivo
a dispositivo, qual EC deu cada redação, então o texto constitucional está
coberto — resta só o resíduo das emendas com artigos próprios, tratado como
item opcional no fim.

---

## Fase 0 — máquina da onda (antes do primeiro lote)

Tudo aqui é código testado offline, sem tocar no índice.

- [x] **Vocabulário do filtro `tipo_norma`**: `resolucao` (a resolução do
      Senado/CN) *(lote 21)*. Tratado promulgado fica como
      `decreto` — é o que ele é — com o nome do tratado no apelido da
      epígrafe, que entra no texto embedado. Propagar até o docstring da tool
      MCP, como no lote 5.
- [x] ~~**`conferir_data` por espécie**~~ — não se aplica: a epígrafe do
      Senado traz só o ano; a data vem do `dataassinatura` da API (lote 21).
- [x] **CLI do `update` imprime `falhas`** — já fazia (o backlog estava
      desatualizado neste ponto).
- [ ] **Registrar a tarefa do `update` semanal** (item 6 do plano principal),
      porque a onda vai deixar 1.100 normas para o delta vigiar.
- [ ] **Teste de unicidade de URN** já cobre o corpus inteiro — os lotes de
      leis avulsas passam por ele antes de gravar (o defeito da Lei 14.600
      repetida sob dois slugs, lote 5).

---

## Lote 11 — estrutural: ADCT e anexos *(executado em 2026-09-14; registro no PLANO_DE_IMPLEMENTACAO.md)*

É o único lote da onda que muda o esquema de identificadores, e por isso vai
**primeiro**: reindexar 761 normas custa menos que reindexar 1.100, e os lotes
20 (tratados) e 19 (regulamentos anexos) dependem dele.

### 11-A — ADCT como documento próprio *(via `recorte`, sem parser)*

- Entrada curada nova `adct_1988` (tipo `constituicao`) com `recorte` a partir
  de `ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS` — e `cf_1988` ganha
  `recorte=("", "ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS")`. Mesma
  URL canônica, dois slugs, dois URNs. O marcador se casa com tolerância a
  quebra de linha (`_marcador`), como no RICD.
- **URN**: proposta `urn:lex:br:federal:constituicao:1988-10-05;1988!adct` (o
  `!` é o componente de fragmento do padrão LexML). Conferir no resolvedor do
  LexML antes de gravar; se não resolver, registrar como sintético, como se
  fez nas súmulas.
- **Medida esperada:** os 128 `__N` da CF somem; a CF fica com ~285 dispositivos
  e o ADCT com ~130 (a numeração vai ao art. 133, com sufixos). Regressão em
  `test_ingest.py` com o HTML da CF do fixture.
- **Carga:** o HTML não muda, logo o delta não reindexa a CF sozinho — ou
  `DELETE FROM norma_state WHERE urn_lex='urn:lex:br:federal:constituicao:1988-10-05;1988'`
  ou, como o 11-B já obriga a reindexação completa, deixar ir junto.
- **Conferir pelas tools:** `obter_dispositivo(adct_1988, art_97)` devolve o
  regime especial de precatórios e `obter_dispositivo(cf_1988, art_97)` a
  cláusula de reserva de plenário — hoje o primeiro só existe como
  `art_97__1`; `art_3` da CF devolve os objetivos fundamentais, sem `__1`.

### 11-B — anexo como dispositivo próprio *(parser, bump de `pipeline_version`)*

- **Reconhecer o cabeçalho de anexo** depois do fecho — `ANEXO`, `ANEXO I`,
  `ANEXO ÚNICO`, com ou sem título na linha seguinte — pelo mesmo mecanismo do
  `_HDR_MARK` que o parser já usa para Título/Capítulo/Seção. Tudo que vem
  entre um cabeçalho de anexo e o próximo (ou o fim) fica no **escopo do
  anexo**.
- **No escopo do anexo, o path leva prefixo**: `anexo_art_1`,
  `anexo_ii_art_3`. O corpo do decreto fica com `art_1`, o Regulamento com
  `anexo_art_1` — resolve a colisão medida no lote 5 (RIR, ANEEL, BPC, RPS) e
  a do RICD deixa de precisar de recorte (mantém-se o recorte, que também
  poda a Res. 25/2001).
- **Marcador `Artigo N` só no escopo do anexo.** Tratados grafam "Artigo 1",
  "Artigo 8º", não "Art.". Aceitar `Artigo` no corpo principal abriria falso
  dispositivo em toda referência ("nos termos do Artigo 5"); restrito ao
  anexo e protegido pelo guarda `_REFERENCIA`, o risco cai ao dos "Art."
  correntes. Path `anexo_artigo_8`? Não: normalizar para `anexo_art_8` — a
  citação por path deve ser a mesma para "Art." e "Artigo".
- **Anexo sem artigo** (tabelas do Simples, metas do PNE, lista de cargos): um
  dispositivo por anexo, `anexo_i`, com o texto achatado e **teto de tamanho**
  (o art. 37 do PNE tinha 160 KB; acima de N KB, cortar por cabeçalho interno
  ou dividir em `anexo_i__parte_2`... decidir na implementação, medindo). Isso
  devolve ao índice o 1,23 MB que o bug nº 10 tirou, agora com citação certa.
- **O `recorte` continua valendo e vence**: quem tem recorte é parseado só no
  trecho recortado; o reconhecimento de anexo age dentro dele.
- **Medição obrigatória antes de gravar** (é a regra dos lotes 2 e 6): rodar o
  parser novo sobre `data/raw/` inteiro e comparar norma a norma com o índice
  atual — contagem de dispositivos, paths que somem, paths que aparecem,
  tamanho do último artigo. Toda norma cujo último dispositivo **encolher**
  é um anexo reconhecido; toda norma que **perder** path canônico é
  regressão. Inspecionar as 5 maiores diferenças de cada lado.
- **Regressões**: RIR (`art_1` = cláusula de aprovação, `anexo_art_1` =
  Regulamento), Dec. 10.088 (as convenções da OIT aparecem), Dec. 1.171 (o
  Código de Ética aparece), LCP 123 (tabelas voltam como `anexo_i`...), LDO
  2019 (art. 155 continua pequeno; os anexos entram como `anexo_*` e não como
  `art_4__N` — o guarda `_REFERENCIA` segue ativo dentro do anexo).
- **`pipeline_version` 0.4.0 → 0.5.0**; `verificar_parser.py` ganha regra para
  anexo (anexo com zero dispositivos e mais de N KB é suspeito).
- **Carga:** `daemon-stop` → `reindexar_do_cache.py` (sem rede) → conferir
  contagem → `daemon-start`. **Snapshot intermediário** (`snapshot-criar` +
  Release), porque o esquema de path mudou e quem restaurar snapshot antigo
  sobre código novo teria índice inconsistente.

---

## Lotes 13 a 17 — leis avulsas por tema *(procedimento estabelecido)*

Cinco lotes de 25 a 45 normas, um por vez, com dias de intervalo (o Planalto
estrangulou o lote 6 no meio). **Todas as listas abaixo são candidatas**: o
número/ano vai à API do LexML pela data e pela ementa oficiais, a data se
confere contra a epígrafe impressa, e quem diverge não entra — o script já
faz isso. As candidatas que já existem no corpus foram excluídas por
varredura do `REGISTRO`; a que se revelar revogada na conferência da ementa
sai (e, se ainda for consultada, entra com `somente_vigente=false`, como a
Lei 10.520).

### Lote 13 — direito público de base (~24) *(executado em 2026-09-14; revelou o bug nº 11)*

Organização administrativa: **DL 200/1967**, Lei 9.962/2000 (emprego público),
Lei 11.416/2006 (carreiras do Judiciário), Lei 10.480/2002 (PGF), Lei
13.327/2016 (honorários da advocacia pública). Patrimônio e desapropriação:
**DL 3.365/1941**, Lei 4.132/1962, **DL 9.760/1946**, **Lei 9.636/1998**, DL
2.398/1987, Lei 13.240/2015. Processo contra a Fazenda: **Lei 8.437/1992**,
**Lei 9.494/1997**, **Lei 9.873/1999**, Lei 5.010/1966 (Justiça Federal), Lei
12.562/2011 (ADO). Segurança e defesa: Lei 4.375/1964 (serviço militar), Lei
9.883/1999 (ABIN/Sisbin), Lei 14.751/2023 (LO da PF e PRF), Lei 11.473/2007
(Força Nacional). Urbano e comunicação pública: Lei 13.089/2015 (Estatuto da
Metrópole), Lei 12.232/2010 (licitação de publicidade), Lei 13.726/2018
(desburocratização), Lei 8.935/1994 (notários e registradores).

### Lote 14 — direito privado, família e penal especial (~32) *(executado em 2026-09-14)*

**DL 3.688/1941** (contravenções), **DL 25/1937** (tombamento), DL 911/1969,
DL 70/1966, DL 167/1967, DL 986/1969 (alimentos), **Lei 8.009/1990**, **Lei
7.357/1985**, **Lei 5.478/1968**, Lei 8.560/1992, Lei 6.515/1977, Lei
11.804/2008, Lei 12.318/2010, Lei 13.786/2018 (distrato), Lei 14.711/2023
(garantias), Lei 14.193/2021 (SAF), Lei 7.960/1989 (prisão temporária), Lei
13.344/2016 (tráfico de pessoas), Lei 13.431/2017 (escuta protegida), Lei
13.257/2016 (primeira infância), Lei 13.185/2015 (bullying), Lei 12.845/2013,
Lei 14.786/2023, Lei 14.192/2021 (violência política de gênero), Lei
7.853/1989 e Lei 8.899/1994 (PcD), Lei 10.436/2002 (Libras), Lei 9.474/1997
(refúgio), Lei 14.701/2023 (terras indígenas), Lei 15.142/2025 (cotas em
concursos — confirmar que substituiu a 12.990/2014), Lei 6.091/1974.

### Lote 15 — trabalho, profissões regulamentadas e previdência (~40) *(executado em 2026-09-14)*

Trabalho: **Lei 4.090/1962** (13º), Lei 4.749/1965, **Lei 7.418/1985**
(vale-transporte), Lei 6.321/1976 (PAT), Lei 9.029/1995, Lei 13.103/2015
(motorista profissional), Lei 12.023/2009 (avulso), Lei 12.690/2012, Lei
14.967/2024 (segurança privada). Previdência: **Lei 10.887/2004** (RPPS da
União), Lei 10.666/2003, Lei 13.846/2019.
Profissões — aqui a descoberta é **por varredura**, como no lote 4: filtrar a
API do LexML por "regulamenta a profissão", "exercício da profissão", "dispõe
sobre a profissão" e "conselho federal de" e selecionar as vigentes.
Candidatas de memória para conferir a cobertura da varredura: Lei 12.842/2013
(medicina), Lei 7.498/1986 e 14.434/2022 (enfermagem), Lei 5.194/1966
(engenharia), Lei 12.378/2010 (arquitetura), DL 9.295/1946 (contabilidade),
Lei 13.021/2014 (farmácia), Lei 4.119/1962 (psicologia), Lei 8.662/1993
(serviço social), Lei 9.696/1998, Lei 8.234/1991, Lei 5.517/1968, Lei
5.081/1966, Lei 6.530/1978, Lei 4.594/1964, Lei 12.468/2011, Lei 6.533/1978,
Lei 6.615/1978, DL 972/1969, Lei 3.999/1961, Lei 5.811/1972, Lei
11.901/2009, Lei 8.623/1993, Lei 4.769/1965, Lei 1.411/1951, DL 938/1969,
Lei 6.684/1979, Lei 7.394/1985.

### Lote 16 — tributário e financeiro estrutural (~26) *(executado em 2026-09-14)*

**Lei 7.689/1988** (CSLL), **DL 1.598/1977**, **Lei 8.383/1991**, **Lei
12.973/2014**, Lei 11.941/2009, Lei 9.065/1995, Lei 8.894/1994 (IOF), Lei
10.336/2001 (Cide-combustíveis), Lei 10.925/2004, Lei 11.508/2007 (ZPE), Lei
11.484/2007 (Padis), DL 1.455/1976 (perdimento), DL 1.025/1969, Lei
13.606/2018, Lei 14.973/2024 (desoneração — transição), Lei 14.740/2023, Lei
14.689/2023 (Carf), Lei 14.148/2021 (Perse), Lei 12.741/2012, Lei
13.259/2016, Lei 8.001/1990 e 13.540/2017 (CFEM), Lei 10.742/2003 (CMED),
Lei 12.810/2013, Lei 13.476/2017, Lei 14.690/2023.
A Lei 8.383 fecha um buraco medido: o `art_72` da Rota 2030 é, no índice, o
art. 72 da 8.383 citado entre aspas (lote 8) — com a 8.383 no corpus o
usuário chega ao texto de verdade.

### Lote 17 — saúde, educação, ambiente, energia e agrário (~36) *(executado em 2026-09-14)*

Saúde: **Lei 9.434/1997** (transplantes), Lei 9.294/1996 (tabaco), Lei
5.991/1973, Lei 10.205/2001 (sangue), Lei 6.259/1975, Lei 14.454/2022 (rol
da ANS). Educação: **Lei 11.892/2008** (Institutos Federais), **Lei
11.738/2008** (piso), Lei 11.947/2009 (PNAE), Lei 9.766/1998
(salário-educação), Lei 9.131/1995 (CNE), Lei 10.880/2004, Lei 13.935/2019,
Lei 12.858/2013. Ambiente: **Lei 5.197/1967** (fauna), Lei 7.735/1989
(Ibama), Lei 11.516/2007 (ICMBio), Lei 10.650/2003, Lei 6.803/1980, Lei
7.643/1987, Lei 12.512/2011. Energia e clima: **Lei 15.042/2024** (mercado
de carbono), **Lei 14.993/2024** (Combustível do Futuro), Lei 15.097/2025
(eólica *offshore*), Lei 14.182/2021 (Eletrobras), Lei 10.847/2004 (EPE),
Lei 12.783/2013. Agrário: **Lei 5.709/1971** (terras a estrangeiros), Lei
11.952/2009, Lei 10.267/2001, Lei 4.829/1965 (crédito rural), Lei 8.427/1992,
Lei 9.456/1997 (cultivares), Lei 10.831/2003, Lei 9.973/2000, Lei 10.696/2003
(PAA). Comunicação: Lei 9.612/1998, Lei 11.652/2008 (EBC), Lei 13.188/2015,
Lei 14.790/2023 (apostas).

---

## Lote 19 — decretos, 2ª fatia (~20) *(executado em 2026-09-14)*

Mesmo recorte do lote 5 (regulamenta lei do corpus ou consolida regulamento de
consulta frequente), lista curada: **Dec. 9.191/2017** (elaboração de atos
normativos), **Dec. 9.830/2019** (LINDB), **Dec. 10.411/2020** (AIR), **Dec.
7.203/2010** (nepotismo), **Dec. 8.539/2015** (processo eletrônico/SEI), Dec.
6.017/2007 (consórcios públicos), Dec. 8.945/2016 (estatais), Dec. 7.983/2013
(orçamento de obras), Dec. 1.775/1996 (demarcação de terras indígenas), Dec.
4.887/2003 (quilombolas), Dec. 6.040/2007 (povos tradicionais), Dec.
5.626/2005 (Libras), Dec. 10.139/2019, Dec. 9.759/2019 (colegiados), Dec.
8.777/2016 (dados abertos), Dec. 7.574/2011, Dec. 10.278/2020, Dec. 4.073/2002
(arquivos), Dec. 7.845/2012, Dec. 9.094/2017, Dec. 99.658/1990, Dec.
5.992/2006 (diárias), Dec. 21.981/1932 (leiloeiros).
Com o lote 11-B no lugar, os que "aprovam o Regulamento anexo" entram
inteiros — antes seriam 2-6 artigos de casca.

---

## Lote 20 — tratados internacionais promulgados *(executado em 2026-09-14)*

Entram pelo decreto promulgador, `tipo=decreto`, com o nome do tratado no
apelido ("Decreto nº 678, de 6 de novembro de 1992 (Pacto de São José da Costa
Rica)"). O texto do tratado é o anexo, e o marcador `Artigo N` do 11-B é o que
o estrutura.

Bloco de direitos humanos: Dec. 678/1992 (Pacto de São José), Dec. 592/1992
(PIDCP), Dec. 591/1992 (PIDESC), Dec. 40/1991 (tortura), Dec. 99.710/1990
(criança), Dec. 4.377/2002 (CEDAW), Dec. 1.973/1996 (Belém do Pará), Dec.
65.810/1969 (discriminação racial), **os três de status constitucional (CF,
art. 5º, § 3º)**: Dec. 6.949/2009 (PcD), Dec. 9.522/2018 (Marraqueche), Dec.
10.932/2022 (Convenção Interamericana contra o Racismo). Penal e cooperação:
Dec. 4.388/2002 (Roma), Dec. 5.015/2004 (Palermo), Dec. 5.687/2006 (Mérida),
Dec. 3.413/2000 (Haia — sequestro), Dec. 8.660/2016 (apostila). Direito dos
tratados e comércio: Dec. 7.030/2009 (Viena), Dec. 350/1991 (Assunção), Dec.
57.663/1966 (Lei Uniforme de Genebra). Ambiente: Dec. 9.073/2017 (Paris), Dec.
2.519/1998 (biodiversidade). Fora, pelo tamanho: Dec. 1.355/1994 (OMC/GATT)
— avaliar depois de medir o custo do 11-B nos demais.

**Gate próprio:** todo tratado sai com **≥ 1 dispositivo `anexo_art_*`**; zero é
o sucesso silencioso que o lote 7 catalogou. O `verificar_parser` do 11-B
apita anexo grande sem dispositivo.

---

## Lote 21 — resoluções do Senado e do Congresso *(executado em 2026-09-15; registro no PLANO_DE_IMPLEMENTACAO.md — a RSF 22/1989 ficou de fora por texto quebrado na fonte)*

- **O que entra:** Regimento Comum (Res. 1/1970-CN), Res. 1/2002-CN
  (tramitação de MPs), Res. 1/2006-CN (CMO), **Res. 25/2001-CD** (Código de
  Ética da Câmara — já vem na mesma página do RICD, só precisa da segunda
  entrada com o recorte complementar), Res. 20/1993-SF (Código de Ética do
  Senado) e as resoluções do art. 52 da CF: RSF 40/2001 e 43/2001 (dívida),
  48/2007 (crédito da União), 22/1989 e 13/2012 (ICMS), 95/1996, 9/1992
  (ITCMD).
- **Fonte é o problema, e foi sondada:** a página `legis.senado.leg.br/norma/
  582803/publicacao/15641285` da RSF 40 **não serve o texto** (47 KB, zero
  artigos) — é uma publicação de outro tipo; o RISF funciona porque a
  publicação 16433779 é o HTML consolidado (442 KB). O trabalho de descoberta
  é achar, por resolução, o id de publicação que serve HTML, e registrar
  `url_canonica` nele. Se alguma só existir em PDF, ela **não entra** — o
  pipeline não tem caminho de PDF e não é este o lote para abrir um.
- **URN pela autoridade** (lote 10): `urn:lex:br:senado.federal:resolucao:
  2001-12-20;40`, `urn:lex:br:congresso.nacional:resolucao:1970-08-11;1`. A
  API do LexML não resolveu a forma curta `senado.federal:resolucao:2001;40`
  (sondado) — tentar a forma com data; senão, sintético e registrado.
- **Tipo:** `regimento` para o Regimento Comum e os Códigos de Ética;
  `resolucao` para as do art. 52. Entradas curadas, então **daemon reiniciado
  antes do `POST /update`**.

---

## Lote 22 — súmulas do STJ e do STF *(opcional, caminho local de jurisprudência)*

- Reabre a decisão do lote 7 de propósito: as súmulas do STJ (~680) e as do
  STF (736) não vinculam, mas são o conhecimento jurisprudencial sintético
  mais citado em parecer e petição, e o caminho de ingestão já existe
  (`jurisprudencia.py`, JSON versionado, `path=enunciado`).
- **Não entra à mão.** O JSON vem de scraper com gate igual ao
  `verificar_sumulas.py`: numeração sem buraco, situação (cancelada/superada)
  conferida na fonte, enunciado sem truncamento. STJ tem base de súmulas com
  filtro de situação; STF tem a "Aplicação das Súmulas no STF". Se não houver
  fonte estruturada estável, o lote fica para depois — 1.400 enunciados
  editados à mão não cabem em manutenção.
- URN sintético no padrão das SV: `urn:lex:br:superior.tribunal.justica:
  sumula:{data};{n}`.

---

## Ordem, cadência e fechamento

| # | Lote | Docs | Pontos (est.) | Rede | Parser | Daemon |
|---|---|---|---|---|---|---|
| 0 | Máquina | 0 | 0 | não | não | — |
| 11 | ADCT + anexos | +1 | ±2.000 (anexos voltam) | não | **sim** | parado (reindex do cache) + snapshot |
| 13 | Público de base | +24 | +1.400 | 24 | não | no ar |
| 14 | Privado/penal | +32 | +1.100 | 32 | não | no ar |
| 15 | Trabalho/profissões | +40 | +900 | 40 | não | no ar |
| 16 | Tributário | +26 | +1.500 | 26 | não | no ar |
| 17 | Saúde…agrário | +36 | +1.300 | 36 | não | no ar |
| 19 | Decretos 2 | +20 | +1.200 | 20 | não | no ar |
| 20 | Tratados | +22 | +900 | 22 | não (11-B) | no ar |
| 21 | Resoluções | +12 | +500 | 12 (Casas) | não | **reiniciado** (curadas) |
| 22 | Súmulas STJ/STF | +1.400 | +1.400 | scraper | não | no ar (JSON) |
| | **Total (sem 22)** | **~975** | **~49.000** | ~215 págs | | |

- **Ritmo:** um lote por semana é o que o Planalto e a inspeção de suspeitos
  aguentam (lotes 8-10 saíram em intervalos de 3 a 10 dias). A onda inteira
  leva ~2 meses e meio; o lote 11 sozinho é uma semana de implementação e medição.
- **Cada lote fecha com:** parágrafo no `PLANO_DE_IMPLEMENTACAO.md` (histórico
  de contagem, suspeitos inspecionados, conferência pelas tools) e commit.
- **Snapshot/Release:** um depois do lote 11 (esquema novo) e um ao fim da
  onda; o `MANIFEST.json` continua pinando o `qdrant-client`.
- **Critério de parada de um lote:** suspeito que não se explica por ruído
  catalogado é bug; o lote para, o bug entra no plano com heurística
  reproduzível, o fix leva bump de versão, e só então o lote segue. Quatro em
  dez lotes revelaram bug — a onda deve esperar dois ou três.

## Riscos específicos da onda

- **11-B é o único item que pode regredir o que existe.** Por isso a medição
  norma a norma contra o índice atual é gate, não opcional, e o snapshot
  anterior fica guardado até o fim da onda.
- **WAF do Planalto:** 215 páginas ao longo de 3 meses é menos que os 670 do
  bootstrap que o estrangulou, mas o `update` baixa de novo o que o
  `verificar --baixar` já baixou. Se estrangular, a norma cai em `falhas` sem
  perder pontos (comportamento do delta), e a CLI passa a mostrá-la (Fase 0).
- **Tratado com numeração romana ou por "Artigo Primeiro"** escapa ao marcador
  `Artigo N`; medir no lote 20 e, se for 1-2 casos, tratar por `recorte` ou
  entrada manual em vez de alargar o marcador.
- **Fonte do Senado** pode não servir HTML para todas as resoluções; o lote 21
  encolhe em vez de abrir caminho de PDF.

---

## Item opcional, fora da onda — emendas com artigos próprios

A CF compilada cobre o texto constitucional; o que **não** está nela são os
artigos que algumas emendas trazem por conta própria, sem alterar dispositivo
algum da Constituição, e que seguem em vigor: as regras de transição da EC
103/2019 (arts. 3º a 36 — pedágio de 100%, idade mínima escalonada, cálculo
do benefício para quem já era segurado), as da EC 132/2023 (arts. 2º a 22 —
transição do IBS/CBS até 2033), as da EC 41/2003 e EC 47/2005 (transições
previdenciárias anteriores, ainda aplicadas) e da EC 20/1998. Sondado: o
parser atual serve a EC 103 limpa (36 dispositivos, 0 duplicados), a página
fica em `constituicao/emendas/emc/emc103.htm` e a API do LexML resolve o URN.
Se um dia entrar, é entrada curada dessas **5 a 8 emendas**, tipo
`emenda_constitucional`, sem quadro nem varredura — não o conjunto das 139.

