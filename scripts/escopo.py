"""Aplica o filtro de escopo (src/analysis/escopo.py) e rotula o que for preciso, até o top e o controle estabilizarem.

    python scripts/escopo.py                 # usa a coleta mais recente
    python scripts/escopo.py --rodadas 5

A cada rodada: calcula o ranking sem os posts já reprovados → rotula (escopo e camada 1) os posts do top e do
controle que ainda não têm rótulo → recalcula. Para quando nenhum post novo precisa de rótulo. Grava
data/processed/rotulos_escopo.jsonl e mostra quantos posts saíram e por quê.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src.analysis.escopo import PROMPT_VERSAO, rotular_lote  # noqa: E402
from src.collection.storage import append_jsonl, read_jsonl  # noqa: E402
from src.shared.llm_client import InvalidLLMOutput, LLMClient  # noqa: E402

PROC = ROOT / "data" / "processed"
SAIDA = PROC / "rotulos_escopo.jsonl"


def coleta_mais_recente() -> Path:
    return max((p for p in (ROOT / "data" / "raw").iterdir() if p.is_dir() and p.name[:4].isdigit()), key=lambda p: p.name)


def rodar(cmd: list[str]) -> None:
    r = subprocess.run([sys.executable, "-u", *cmd], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                       env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    linhas = [l for l in (r.stdout + r.stderr).splitlines() if l.strip() and not l.startswith(("{", "}", " ", "\""))]
    for l in linhas[-4:]:
        print("   ", l)
    if r.returncode not in (0,):
        print(f"    (código {r.returncode})")


def pendentes_escopo() -> list[dict]:
    s = pd.read_csv(PROC / "scores.csv", dtype={"post_id": str}, low_memory=False)
    amostra = s[s["grupo"].isin(["top", "controle"])]
    feitos = {str(r["post_id"]) for r in read_jsonl(SAIDA) if r.get("prompt_versao") == PROMPT_VERSAO}
    return amostra[~amostra["post_id"].isin(feitos)][["post_id", "plataforma", "titulo", "legenda"]].fillna("").to_dict("records")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coleta", default=None)
    ap.add_argument("--rodadas", type=int, default=6)
    ap.add_argument("--lote", type=int, default=20)
    args = ap.parse_args()
    coleta = args.coleta or str(coleta_mais_recente())
    client = LLMClient()
    for rodada in range(1, args.rodadas + 1):
        print(f"Rodada {rodada}: ranking")
        rodar(["scripts/calcular_metricas.py", "--jsonl", coleta])
        posts = pendentes_escopo()
        print(f"  {len(posts)} post(s) do top/controle sem rótulo de escopo")
        if not posts:
            break
        for i in range(0, len(posts), args.lote):
            lote = posts[i:i + args.lote]
            for tentativa in range(5):
                try:
                    append_jsonl(SAIDA, rotular_lote(client, lote, tentativa))
                    break
                except InvalidLLMOutput:
                    continue
                except RuntimeError as exc:           # cota esgotada: para e usa o que já foi rotulado
                    print(f"  parei: {str(exc)[:160]}")
                    return 1
        print("  camada 1 nos posts novos")
        rodar(["scripts/camada1.py", "--coleta", coleta])
    s = pd.read_csv(PROC / "scores.csv", dtype={"post_id": str}, low_memory=False)
    fora = s[s["fora_escopo"].fillna("").astype(str) != ""]
    print(f"\nFora do escopo: {len(fora)} posts elegíveis")
    print(fora["fora_escopo"].str.replace(r"tema sensível: .*", "tema sensível (termo)", regex=True)
          .str.replace(r"menos de .*", "poucas curtidas", regex=True).value_counts().to_string())
    print(f"Top: {(s['grupo'] == 'top').sum()} · controle: {(s['grupo'] == 'controle').sum()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
