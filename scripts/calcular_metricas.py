"""Camada 0: calcula métricas, top por faixa e grupo controle.

Uso:
    python scripts/calcular_metricas.py                          # usa a coleta mais recente em data/raw/
    python scripts/calcular_metricas.py --jsonl data/raw/2026-11-22   # uma coleta específica
    python scripts/calcular_metricas.py --janela todas           # top sobre todos os elegíveis, não só 90 dias

Sempre grava data/processed/scores.csv e data/processed/resumo.json para o README e a análise.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src.analysis import escopo, exclusoes  # noqa: E402
from src.analysis.metrics import calcular_metricas, resumo, selecionar_top_e_controle  # noqa: E402
from src.collection.storage import read_jsonl  # noqa: E402
from src.evaluation.thresholds import load_thresholds  # noqa: E402


def coleta_mais_recente():
    """Pasta datada mais recente em data/raw/ (as pastas começam pelo ano: 2026-11-22)."""
    pastas = sorted(p for p in (ROOT / "data" / "raw").glob("*") if p.is_dir() and p.name[:4].isdigit())
    return pastas[-1] if pastas else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Camada 0: métricas, top e controle")
    parser.add_argument("--jsonl", help="pasta de uma coleta (data/raw/<data>); padrão: a mais recente")
    parser.add_argument("--janela", choices=["momento", "todas"], default=None,
                        help="padrão: ranking_janela em config/limiares.yaml")
    parser.add_argument("--semente", type=int, default=42)
    args = parser.parse_args()

    limiares = load_thresholds(ROOT / "config" / "limiares.yaml")
    agora = datetime.now(timezone.utc)
    pasta = Path(args.jsonl) if args.jsonl else coleta_mais_recente()
    if pasta is None:
        print("Nenhuma coleta em data/raw/. Rode scripts/coletar.py antes.")
        return 1
    posts = pd.DataFrame(read_jsonl(pasta / "posts.jsonl"))
    perfis = pd.DataFrame(read_jsonl(pasta / "perfis.jsonl"))
    excluidos = exclusoes.carregar()
    if excluidos and not posts.empty:                  # fora do tema por decisão humana (config/posts_excluidos.csv)
        antes = len(posts)
        posts = posts[~posts["post_id"].astype(str).isin(excluidos)]
        print(f"{antes - len(posts)} post(s) fora do tema excluídos da análise")
    if posts.empty:
        print("Base vazia. Rode a coleta antes.")
        return 1

    metricas = calcular_metricas(posts, perfis, agora, limiares)
    # escopo do TAPI: fora o que não orienta o empreendedor, temas sensíveis e posts com poucas curtidas
    proc = ROOT / "data" / "processed"
    rot_texto = pd.DataFrame(read_jsonl(proc / "rotulos_texto.jsonl"))
    rot_escopo = pd.DataFrame([r for r in read_jsonl(proc / "rotulos_escopo.jsonl")
                               if r.get("prompt_versao") == escopo.PROMPT_VERSAO])    # só a versão atual do classificador
    fora = escopo.motivos_fora(metricas, rot_texto, rot_escopo, int(limiares.get("escopo_min_curtidas") or 0))
    marcar = metricas["elegivel"].astype(bool) & (fora != "")
    metricas["fora_escopo"] = fora.where(marcar, "")       # continua elegível (médias do nicho), mas não concorre
    janela = args.janela or str(limiares.get("ranking_janela") or "momento")
    print(f"Fora do escopo: {int(marcar.sum())} posts elegíveis "
          f"({fora[marcar].str.split(':').str[0].str.replace(r'menos de .*', 'poucas curtidas', regex=True).value_counts().to_dict()})")
    scores = selecionar_top_e_controle(metricas, limiares,
                                       janela=None if janela == "todas" else "momento", semente=args.semente)
    out = ROOT / "data" / "processed"
    out.mkdir(parents=True, exist_ok=True)
    scores.to_csv(out / "scores.csv", index=False)
    info = {"calculado_em": agora.isoformat(), "coleta": pasta.name, "posts_excluidos": len(excluidos), "fora_do_escopo": int(marcar.sum()), "janela": janela, "escopo_min_curtidas": int(limiares.get("escopo_min_curtidas") or 0), "semente": args.semente, **resumo(scores)}
    (out / "resumo.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
