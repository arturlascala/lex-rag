"""CLI de atualização do índice: ``lex-rag-update --mode delta|full``."""

from __future__ import annotations

import argparse

import lex_rag  # noqa: F401  (dispara o preload de DLL no Windows antes do qdrant_client)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="lex-rag-update", description="Atualiza o índice da legislação federal."
    )
    parser.add_argument(
        "--mode",
        choices=["delta", "full"],
        default="delta",
        help="delta = só reindexa o que mudou; full = reindexa tudo.",
    )
    args = parser.parse_args()

    from lex_rag.update.pipeline import run

    resumo = run(args.mode)
    print(f"[update] modo={resumo['mode']}")
    if resumo["atualizadas"]:
        for slug, n in resumo["atualizadas"].items():
            print(f"  reindexada: {slug} ({n} dispositivos)")
    else:
        print("  nenhuma norma alterada.")
    print(f"  inalteradas: {len(resumo['inalteradas'])}")

    # Normas que falharam mantêm os pontos que já tinham (o pipeline nunca
    # regride o índice), mas ficam com o conteúdo defasado — e numa rodada
    # agendada não há ninguém olhando. Daí o relato explícito e o código de
    # saída != 0, que o agendador registra como falha da tarefa.
    falhas = resumo["falhas"]
    if falhas:
        print(f"  FALHAS ({len(falhas)}): {', '.join(falhas)}")
        print("  (essas normas seguem no índice com o conteúdo da última carga bem-sucedida)")
    print(f"  total de pontos no índice: {resumo['total_pontos']}")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
