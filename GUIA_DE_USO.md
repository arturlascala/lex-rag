# Guia de uso do lex-rag (linguagem simples)

## O que é

Um mecanismo de busca na legislação federal (Constituição, Leis Complementares,
Leis Ordinárias) que funciona **dentro do Claude**. Você pergunta em português
normal e ele devolve o **texto literal** do artigo + o link do Planalto. Ele não
inventa nem parafraseia — só mostra o que a lei diz.

## Como funciona (só 2 peças)

1. **O motor (daemon)** — o processo pesado. Carrega os modelos de busca na placa
   de vídeo. **Precisa estar ligado** para as buscas funcionarem.
2. **A ponte (MCP)** — o pedacinho que liga o Claude ao motor. O **Claude liga
   sozinho**; você não mexe nela.

> Analogia: o daemon é o **motor do carro** — tem que estar ligado. O Claude é o
> **motorista** que dá a partida e dirige. Você só precisa girar a chave.

## Passo a passo do dia a dia

**1. Ligar o motor** (uma vez, no começo do trabalho, na pasta do projeto):

```powershell
.\tasks.ps1 daemon-start
```

Espere uns **30 a 60 segundos** (ele está carregando os modelos).

**2. Conferir se está pronto:**

```powershell
.\tasks.ps1 daemon-status
```

Você quer ver "processo no ar" e o `/health` respondendo.

**3. Usar** — abra o Claude e pergunte em português normal. Exemplos:

- "O que diz o art. 5º da Constituição sobre liberdade de expressão?"
- "Busque normas federais sobre licitação."
- "Me traz o texto literal do art. 37 da CF."
- "O que o STF sumulou sobre nepotismo?" — as Súmulas Vinculantes estão na base
  e vêm junto com a legislação, com o número do enunciado e a data da sessão.
- "Como se pede urgência para um projeto no Senado?" — os regimentos internos do
  Senado (RISF) e da Câmara (RICD) também estão na base, para as perguntas de
  rito que a lei não responde.

O Claude aciona as ferramentas do lex-rag sozinho e devolve o texto com a fonte.

**4. Ao terminar** (libera a memória da placa de vídeo):

```powershell
.\tasks.ps1 daemon-stop
```

## Cola de comandos

| Comando | O que faz |
|---|---|
| `.\tasks.ps1 daemon-start`  | Liga o motor em segundo plano |
| `.\tasks.ps1 daemon-status` | Mostra se está ligado e respondendo |
| `.\tasks.ps1 daemon-stop`   | Desliga e libera a placa de vídeo |
| `.\tasks.ps1 serve`         | Liga mostrando os logs na tela (Ctrl+C encerra) |
| `.\tasks.ps1 update`        | Atualiza a base com normas novas |
| `.\tasks.ps1 bootstrap`     | Recarrega a base inteira (⚠ pare o daemon antes) |
| `.\tasks.ps1 test`          | Roda os testes |

## Dúvidas comuns

- **Preciso estar na pasta do projeto?** Sim, para o `.\tasks.ps1`. Se quiser
  chamar de qualquer pasta, crie um atalho no seu perfil do PowerShell
  (`notepad $PROFILE`):
  `function lexrag { & "C:\caminho\para\lex_rag\tasks.ps1" @args }` — daí
  `lexrag daemon-start` funciona de onde estiver.
- **Esqueci se liguei o motor.** Rode `.\tasks.ps1 daemon-status`.
- **Reiniciei o Claude — preciso religar o motor?** Não. O daemon continua no ar
  por conta própria; só religa se você tiver dado `daemon-stop` ou reiniciado o PC.
- **Reiniciei o computador.** O motor **não** sobe sozinho — rode
  `.\tasks.ps1 daemon-start` de novo.
- **Deu "indisponível" logo depois do start.** Normal: os modelos ainda estão
  carregando. Espere ~1 minuto e rode `.\tasks.ps1 daemon-status` de novo.
- **Vou recarregar a base (`bootstrap`).** Rode `.\tasks.ps1 daemon-stop` antes — o
  motor segura o banco e atrapalha a recarga.

## Manutenção da base

Para atualizar na mão: `.\tasks.ps1 update`. Para deixar automático (toda
segunda, às 03h), registre a tarefa uma vez com
`.\scripts\register_update_task.ps1`.

## Instalando numa máquina nova

Não precisa reconstruir a base: baixe o zip do corpus pronto no Release do
repositório e rode `.\tasks.ps1 snapshot-restaurar <arquivo ou link>`. Funciona
sem placa de vídeo — só fica mais lento na busca. Detalhes no README.
