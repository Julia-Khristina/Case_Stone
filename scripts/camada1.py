"""Camada 1: rotula título e legenda dos posts com o LLM e mostra os primeiros padrões top × controle.

Uso:
    python scripts/camada1.py --coleta data/raw/2026-11-22                 # só top + controle (padrão)
    python scripts/camada1.py --coleta data/raw/2026-11-22 --janela-toda   # todos os elegíveis dos últimos 90 dias

Precisa de data/processed/scores.csv (rode antes scripts/calcular_metricas.py) e, para chamar o modelo de verdade,
LLM_MODE=live com GROQ_API_KEY e GROQ_GENERATION_MODEL_ID no .env. Posts já rotulados não são enviados de novo.
Grava data/processed/rotulos_texto.jsonl.
"""
from __future__ import annotations

import argparse
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

from src.analysis.camada1 import PROMPT_VERSAO, rotular  # noqa: E402
from src.analysis.padroes import comparar  # noqa: E402
from src.collection.storage import append_jsonl, read_jsonl  # noqa: E402
from src.shared.llm_client import LLMClient  # noqa: E402

CAMPOS = ["tipo_hook", "tema_principal", "tipo_cta", "tom", "convite_participacao", "mensagem_generica",
          "patrocinado", "ferramentas_mencionadas", "data_sazonal"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Camada 1: rótulos de texto pelo LLM")
    parser.add_argument("--coleta", required=True, help="pasta da coleta, ex.: data/raw/2026-11-22")
    parser.add_argument("--janela-toda", action="store_true", help="rotular todos os elegíveis dos últimos 90 dias")
    parser.add_argument("--lote", type=int, default=15)
    parser.add_argument("--so-padroes", action="store_true", help="não chama o modelo; só mostra os padrões")
    args = parser.parse_args()

    scores = pd.read_csv(ROOT / "data" / "processed" / "scores.csv")
    posts = pd.DataFrame(read_jsonl(Path(args.coleta) / "posts.jsonl"))
    # Título e legenda sempre da coleta (a tabela de scores pode ou não trazê-los)
    base = scores.drop(columns=["titulo", "legenda"], errors="ignore").merge(
        posts[["plataforma", "post_id", "titulo", "legenda"]], on=["plataforma", "post_id"], how="left")
    alvo = (base[base["elegivel"] & (base["janela"] == "momento")] if args.janela_toda
            else base[base["grupo"].isin(["top", "controle"])])

    saida = ROOT / "data" / "processed" / "rotulos_texto.jsonl"
    feitos = {r["post_id"] for r in read_jsonl(saida) if r.get("prompt_versao") == PROMPT_VERSAO}
    pendentes = alvo[~alvo["post_id"].isin(feitos)]
    print(f"{len(alvo)} posts no alvo; {len(feitos & set(alvo['post_id']))} já rotulados; {len(pendentes)} a rotular")

    if len(pendentes) and not args.so_padroes:
        client = LLMClient()
        registros = pendentes[["post_id", "plataforma", "tipo", "titulo", "legenda"]].fillna("").to_dict("records")
        total_lotes = -(-len(registros) // args.lote)
        feitos_lotes = []

        def gravar(lote_rotulos):   # grava a cada lote: o progresso fica visível e nada depende do fim da execução
            append_jsonl(saida, lote_rotulos)
            feitos_lotes.append(1)
            print(f"  lote {len(feitos_lotes)}/{total_lotes} gravado", flush=True)

        rotulos, falhas = rotular(client, registros, tamanho_lote=args.lote, ao_concluir_lote=gravar)
        if falhas:
            print(f"  {len(falhas)} posts falharam; rode de novo com --lote menor (ex.: --lote 5) para tentar só eles")
        tokens = sum(c["total_tokens"] for c in client.calls)
        print(f"{len(rotulos)} rotulados, {len(falhas)} falharam · {len(client.calls)} chamadas · {tokens} tokens")

    rot = pd.DataFrame([r for r in read_jsonl(saida) if r.get("prompt_versao") == PROMPT_VERSAO])
    df = scores.merge(rot.drop(columns=["modelo", "prompt_versao"]), on="post_id", how="inner")
    df = df[df["grupo"].isin(["top", "controle"])]
    print(f"\nPadrões top × controle ({(df.grupo == 'top').sum()} top, {(df.grupo == 'controle').sum()} controle)")
    for campo in CAMPOS:
        tabela = comparar(df, campo)
        if tabela.empty:
            continue
        print(f"\n· {campo}")
        for valor, r in tabela.head(5).iterrows():
            lift = "—" if pd.isna(r["lift"]) else f"{r['lift']:.1f}×"
            alto = f"{r['ic_alto']:.1f}" if r["ic_alto"] < 1e6 else "∞"   # valor raro no controle: sem teto
            ic = f"[{r['ic_baixo']:.1f}–{alto}]"
            print(f"   {valor:26.26} top {r['pct_top']:5.0%}  controle {r['pct_controle']:5.0%}  lift {lift:>5} "
                  f"{ic:14} {r['leitura']:28} (n={int(r['n_top'])}, {int(r['n_perfis_top'])} perfis)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
