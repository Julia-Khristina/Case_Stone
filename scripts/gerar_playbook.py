"""Gera o Playbook de conteúdo para a Stone (HTML único, abre offline e imprime em PDF).

    python scripts/gerar_playbook.py                       # → docs/playbook_stone.html
    python scripts/gerar_playbook.py --saida outro.html

Usa a coleta mais recente em data/raw/ (ou BOAPAUTA_COLETA) e as peças aprovadas no app (BOAPAUTA_DB).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import api  # noqa: E402
from src.playbook import MINIMO_CRIATIVOS, gerar  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saida", type=Path, default=ROOT / "docs" / "playbook_stone.html")
    args = ap.parse_args()
    pecas = api.store().listar()
    aprovadas = sum(1 for p in pecas if p.get("status") == "aprovada" and p.get("atual", {}).get("criativo"))
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(gerar(api.base(), pecas, api.frase), encoding="utf-8")
    print(f"Playbook salvo em {args.saida} ({aprovadas} criativo(s) aprovado(s)).")
    if aprovadas < MINIMO_CRIATIVOS:
        print(f"Atenção: o TAPI pede no mínimo {MINIMO_CRIATIVOS} criativos prontos. Aprove mais peças no app e gere de novo.")


if __name__ == "__main__":
    main()
