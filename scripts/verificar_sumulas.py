"""Confere o lote de súmulas (Vinculantes, ou as do STF com ``--stf``) antes da carga.

O gêmeo de ``verificar_parser.py`` para o caminho jurisprudencial. Lá o risco é
o parser fatiar o texto errado; aqui não há parser — o risco é o **registro**
estar errado: número faltando, URN que não bate com a data, enunciado truncado
na coleta, situação divergente do que o STF publica.

Roda offline, sobre o ``sumulas_vinculantes.json`` já gerado. Como
``descobrir_sumulas.py`` só grava o que conferiu contra o portal, este script é
a segunda barreira: pega o que passou pela coleta mas não fecha internamente, e
o que se degradou depois (edição manual do JSON, merge malfeito).

Uso::

    python scripts/verificar_sumulas.py
    python scripts/verificar_sumulas.py --stf     # sumulas_stf.json (lote 22-A)
    python scripts/verificar_sumulas.py --json    # despeja o que foi carregado
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date

from lex_rag.ingest.jurisprudencia import montar_norma
from lex_rag.ingest.urn_mapper import REGISTRO, SUMULAS_STF_PATH, SUMULAS_VINCULANTES_PATH

# As SV têm situação curada; as súmulas simples levam a palavra que o STF marca.
_SITUACOES = {"vigente", "cancelada", "publicacao_suspensa", "revogada", "superada"}
_URN_SV = re.compile(
    r"^urn:lex:br:supremo\.tribunal\.federal:sumula\.vinculante:(\d{4}-\d{2}-\d{2});(\d+)$"
)
_URN_STF = re.compile(r"^urn:lex:br:supremo\.tribunal\.federal:sumula:(\d{4}-\d{2}-\d{2});(\d+)$")
# Mojibake de UTF-8 lido como Latin-1/cp1252 — o defeito do bug nº 8, que passou
# despercebido por 284 normas porque o texto continua "legível".
_MOJIBAKE = re.compile(r"[ÃÂ][-¿]|�")


# Súmulas simples cujo enunciado o STF publica sem ponto final (inspecionadas:
# o texto está completo; a regra existe para pegar truncamento da coleta).
_SEM_PONTO_NA_FONTE = {323}


def conferir(entradas: list[dict], stf: bool = False) -> list[str]:
    """Devolve a lista de problemas encontrados (vazia = lote íntegro)."""
    problemas: list[str] = []
    rotulo = "Súmula" if stf else "SV"
    padrao_urn = _URN_STF if stf else _URN_SV

    def erro(numero: object, msg: str) -> None:
        problemas.append(f"{rotulo} {numero}: {msg}")

    numeros = [e.get("numero") for e in entradas]
    if len(numeros) != len(set(numeros)):
        repetidos = sorted({n for n in numeros if numeros.count(n) > 1})
        problemas.append(f"número repetido no registro: {repetidos}")
    # A numeração das súmulas é contínua: buraco é súmula que ficou de fora da
    # coleta, não súmula inexistente. A 30 é caso conhecido e entra como
    # publicação suspensa, então nem ela abre buraco.
    faltando = sorted(set(range(1, max(numeros) + 1)) - set(numeros)) if numeros else []
    # Nas súmulas simples o buraco é conhecido e medido: as páginas sem data
    # nenhuma que o coletor rejeita (72, quase todas entre 371 e 497). Fica no
    # relatório como aviso, não como erro.
    if faltando and not stf:
        problemas.append(f"buraco na numeração: {faltando}")
    elif faltando:
        print(f"[súmulas] aviso: {len(faltando)} números ausentes (rejeitados na coleta)")

    urns = [e.get("urn_lex") for e in entradas]
    if len(urns) != len(set(urns)):
        problemas.append("URN repetido no registro")

    for e in entradas:
        numero = e.get("numero")
        enunciado = (e.get("enunciado") or "").strip()

        casa = padrao_urn.match(e.get("urn_lex", ""))
        if not casa:
            erro(numero, f"URN fora do padrão: {e.get('urn_lex')!r}")
        else:
            data_urn, numero_urn = casa.groups()
            # A data de aprovação (ou, nas súmulas simples que só a têm, a de
            # publicação) é parte do URN, e o URN é a chave do corpus:
            # divergência aqui é erro de identidade, não de metadado.
            data_registro = e.get("data_aprovacao") or (stf and e.get("data_publicacao"))
            if data_urn != data_registro:
                erro(numero, f"URN tem data {data_urn}, registro tem {data_registro}")
            if int(numero_urn) != numero:
                erro(numero, f"URN tem número {numero_urn}")

        for campo in ("data_aprovacao", "data_publicacao"):
            valor = e.get(campo)
            if valor is None:
                continue
            try:
                date.fromisoformat(valor)
            except (TypeError, ValueError):
                erro(numero, f"{campo} não é data ISO: {valor!r}")

        situacao = e.get("situacao")
        if situacao not in _SITUACOES:
            erro(numero, f"situação fora do vocabulário: {situacao!r}")
        if situacao != "vigente" and not e.get("cancelada_por"):
            erro(numero, f"situação {situacao!r} sem motivo em cancelada_por")
        if situacao == "vigente" and e.get("cancelada_por"):
            erro(numero, "vigente, mas com cancelada_por preenchido")
        # A página das súmulas simples não imprime o DJ; só as SV têm a data.
        if situacao == "vigente" and not e.get("data_publicacao") and not stf:
            erro(numero, "vigente sem data de publicação")

        if not enunciado:
            erro(numero, "enunciado vazio")
            continue
        if _MOJIBAKE.search(enunciado):
            erro(numero, "enunciado com mojibake (encoding errado na coleta)")
        if not enunciado[0].isupper():
            erro(numero, f"enunciado não começa com maiúscula: {enunciado[:40]!r}")
        if enunciado[-1] not in ".?!" and numero not in _SEM_PONTO_NA_FONTE:
            erro(numero, f"enunciado sem pontuação final: {enunciado[-40:]!r}")
        # Enunciado é texto curto por natureza; o maior hoje tem ~540 chars.
        # Muito acima disso é sinal de que a coleta pegou os precedentes junto.
        if len(enunciado) > 1200:
            erro(numero, f"enunciado longo demais ({len(enunciado)} chars) — coleta vazou?")

        if not (e.get("fonte_stf") or "").startswith("https://portal.stf.jus.br/"):
            erro(numero, f"fonte fora do portal do STF: {e.get('fonte_stf')!r}")

    return problemas


def conferir_registro(entradas: list[dict], stf: bool = False) -> list[str]:
    """Confere que cada súmula chega ao catálogo e produz um dispositivo."""
    problemas: list[str] = []
    for e in entradas:
        slug = f"{'sumula_stf' if stf else 'sv'}_{e['numero']}"
        meta = REGISTRO.get(slug)
        if meta is None:
            problemas.append(f"{slug}: ausente do REGISTRO")
            continue
        if meta.urn_lex != e["urn_lex"]:
            problemas.append(f"{slug}: URN do REGISTRO difere do JSON")
        norma = montar_norma(meta, json.dumps(e, ensure_ascii=False, sort_keys=True))
        if len(norma.dispositivos) != 1:
            problemas.append(f"{slug}: {len(norma.dispositivos)} dispositivos (esperado 1)")
    return problemas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="despeja as entradas carregadas")
    ap.add_argument("--stf", action="store_true",
                    help="confere sumulas_stf.json (súmulas simples) em vez das Vinculantes")
    args = ap.parse_args()

    caminho = SUMULAS_STF_PATH if args.stf else SUMULAS_VINCULANTES_PATH
    if not caminho.exists():
        print(f"[súmulas] {caminho} não existe — rode o descobrir_sumulas correspondente")
        return 1
    entradas = json.loads(caminho.read_text(encoding="utf-8"))
    if args.json:
        print(json.dumps(entradas, ensure_ascii=False, indent=1))

    problemas = conferir(entradas, args.stf) + conferir_registro(entradas, args.stf)
    situacoes: dict[str, int] = {}
    for e in entradas:
        situacoes[e.get("situacao", "?")] = situacoes.get(e.get("situacao", "?"), 0) + 1

    resumo = ", ".join(f"{n} {s}" for s, n in sorted(situacoes.items()))
    print(f"[súmulas] {len(entradas)} enunciados ({resumo})")
    if problemas:
        print(f"[súmulas] {len(problemas)} problema(s):")
        for p in problemas:
            print(f"  - {p}")
        return 1
    print("[súmulas] lote íntegro")
    return 0


if __name__ == "__main__":
    sys.exit(main())
