"""Camada 2: rótulos visuais e de fala (Gemini) para o top e o grupo controle, e os padrões top × controle.

Uso:
    python scripts/camada2.py --coleta data/raw/2026-11-22                 # pendentes, em lotes de 17 posts por pedido
    python scripts/camada2.py --coleta data/raw/2026-11-22 --max-pedidos 2 # teste curto
    python scripts/camada2.py --coleta data/raw/2026-11-22 --concordancia  # compara com os rótulos da versão anterior
    python scripts/camada2.py --coleta data/raw/2026-11-22 --so-padroes    # não chama o modelo

Precisa de GEMINI_API_KEY no .env (GEMINI_MODEL_ID opcional). O plano gratuito permite 20 pedidos por dia por modelo:
cada execução para sozinha quando a cota acaba e a próxima retoma de onde parou. Grava data/processed/rotulos_visuais.jsonl
a cada lote; falhas vão para data/processed/camada2_falhas.jsonl e voltam na próxima execução.
Links de mídia do Instagram expiram em poucos dias: se der 403, recolete o perfil (scripts/coletar.py) e rode de novo.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src.analysis.camada2 import PROMPT_VERSAO, AnalisadorVisual, GeminiIndisponivel  # noqa: E402
from src.analysis.padroes import comparar  # noqa: E402
from src.collection.storage import append_jsonl, read_jsonl  # noqa: E402

CAMPOS = ["quem_aparece", "gancho_visual", "cenario", "producao", "rosto_nos_3s", "fala_nos_3s", "texto_na_tela_inicio",
          "legendas_queimadas", "cta_no_final", "mostra_ferramenta", "tom_de_voz",
          "musica_fundo", "tipo_musica", "volume_musica", "tom_fala", "ritmo_fala", "qualidade_audio", "efeitos_sonoros"]
SAIDA = ROOT / "data" / "processed" / "rotulos_visuais.jsonl"
FALHAS = ROOT / "data" / "processed" / "camada2_falhas.jsonl"


def alvo(coleta: Path) -> pd.DataFrame:
    scores = pd.read_csv(ROOT / "data" / "processed" / "scores.csv", dtype={"post_id": str})
    from src.collection.storage import posts_com_midia_renovada
    posts = pd.DataFrame(posts_com_midia_renovada(coleta))      # links do Instagram renovados, quando houver
    posts["post_id"] = posts["post_id"].astype(str)
    return scores[scores["grupo"].isin(["top", "controle"])][["plataforma", "post_id", "grupo", "tipo", "perfil_id"]].merge(
        posts[["plataforma", "post_id", "titulo", "legenda", "link", "media_url", "thumbnail_url", "duracao_s"]],
        on=["plataforma", "post_id"], how="left")


def rotulos(versao: str) -> pd.DataFrame:
    df = pd.DataFrame([r for r in read_jsonl(SAIDA) if r.get("prompt_versao") == versao])
    return df.drop_duplicates("post_id", keep="last") if not df.empty else df


def concordancia() -> int:
    """Mesmos posts no protocolo novo (lote, trechos) × anterior (um por pedido, vídeo inteiro ou trechos de 20 s)."""
    from sklearn.metrics import cohen_kappa_score
    novo, antigo = rotulos(PROMPT_VERSAO), rotulos("camada2-v1")
    if novo.empty or antigo.empty:
        print("Faltam rótulos de uma das versões.")
        return 1
    m = novo.merge(antigo, on="post_id", suffixes=("_novo", "_antigo"))
    print(f"{len(m)} posts com as duas versões\n")
    for campo in CAMPOS:
        a, b = m[f"{campo}_novo"].astype(str), m[f"{campo}_antigo"].astype(str)
        acordo = (a == b).mean()
        kappa = cohen_kappa_score(a, b) if a.nunique() > 1 or b.nunique() > 1 else float("nan")
        print(f"  {campo:22} concordância {acordo:5.0%}   kappa {kappa:5.2f}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Camada 2: vídeo e imagem no Gemini")
    parser.add_argument("--coleta", required=True)
    parser.add_argument("--lote", type=int, default=17,
                        help="posts por pedido (17 × 20 pedidos cobre os 330 posts numa cota diária; testado em 22/11)")
    parser.add_argument("--max-pedidos", type=int, default=20, help="teto de pedidos nesta execução (cota gratuita: 20/dia)")
    parser.add_argument("--ids", help="só estes post_ids, separados por vírgula")
    parser.add_argument("--concordancia", action="store_true")
    parser.add_argument("--so-padroes", action="store_true")
    args = parser.parse_args()

    if args.concordancia:
        return concordancia()

    df = alvo(Path(args.coleta))
    feitos = set(rotulos(PROMPT_VERSAO).get("post_id", pd.Series(dtype=str)))
    pendentes = df[~df["post_id"].isin(feitos)]
    # Reels sem media_url (a Meta não entrega o vídeo de Reels com música licenciada) não têm o que analisar:
    # saem da fila antes de montar os lotes, para não gastar pedido da cota com lote quase vazio.
    sem_midia = (pendentes["plataforma"] == "instagram") & pendentes["media_url"].isna()
    if sem_midia.any():
        print(f"{int(sem_midia.sum())} posts do Instagram sem link de mídia ficam de fora "
              f"({pendentes[sem_midia].groupby('grupo').size().to_dict()})")
        pendentes = pendentes[~sem_midia]
    inacessiveis = json.loads((ROOT / "config" / "camada2_inacessiveis.json").read_text(encoding="utf-8"))
    bloqueados = {pid for plat, ids in inacessiveis.items() if not plat.startswith("_") for pid in ids}
    if bloqueados & set(pendentes["post_id"]):
        print(f"{len(bloqueados & set(pendentes['post_id']))} posts inacessíveis ao Gemini ficam de fora "
              "(config/camada2_inacessiveis.json)")
        pendentes = pendentes[~pendentes["post_id"].isin(bloqueados)]
    if args.ids:
        pendentes = pendentes[pendentes["post_id"].isin(args.ids.split(","))]
    # Ordem: primeiro os posts que já têm rótulo da versão anterior (a concordância sai no primeiro pedido),
    # depois o Instagram (os links de mídia expiram em poucos dias) e por fim o YouTube (link público, não expira).
    antigos = set(rotulos("camada2-v1").get("post_id", pd.Series(dtype=str)))
    pendentes = pendentes.assign(_ordem=[0 if pid in antigos else (1 if plat == "instagram" else 2)
                                         for pid, plat in zip(pendentes["post_id"], pendentes["plataforma"])])
    pendentes = pendentes.sort_values(["_ordem", "plataforma", "tipo", "post_id"]).drop(columns="_ordem")
    print(f"{len(df)} posts no alvo; {len(feitos & set(df['post_id']))} já analisados ({PROMPT_VERSAO}); "
          f"{len(pendentes)} pendentes · lotes de {args.lote}")

    if len(pendentes) and not args.so_padroes:
        analisador = AnalisadorVisual(max_pedidos=args.max_pedidos)
        registros = [{k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in r.items()}
                     for r in pendentes.to_dict("records")]
        ok = 0
        for i in range(0, len(registros), args.lote):
            lote = registros[i:i + args.lote]
            try:
                prontos, erros = analisador.analisar_lote(lote)
            except GeminiIndisponivel as exc:
                print(f"  parei: {str(exc)[:200]}\n  O que já foi feito está salvo; rode de novo quando a cota voltar.")
                break
            except Exception as exc:  # noqa: BLE001 - um lote com problema não derruba a execução
                append_jsonl(FALHAS, [{"post_id": str(r["post_id"]), "erro": f"lote: {str(exc)[:200]}",
                                       "versao": PROMPT_VERSAO, "em": datetime.now().isoformat(timespec="seconds")}
                                      for r in lote])
                print(f"  lote {i // args.lote + 1} falhou ({type(exc).__name__}: {str(exc)[:120]}); sigo para o próximo",
                      flush=True)
                continue
            novos =[r for r in prontos if r["post_id"] not in feitos]
            append_jsonl(SAIDA, novos)
            feitos |= {r["post_id"] for r in novos}
            ok += len(novos)
            if erros:
                append_jsonl(FALHAS, [{"post_id": pid, "erro": e, "versao": PROMPT_VERSAO,
                                       "em": datetime.now().isoformat(timespec="seconds")} for pid, e in erros.items()])
            print(f"  pedido {analisador.pedidos}: {len(novos)} rotulados, {len(erros)} de fora"
                  + (f" ({list(erros.values())[0][:90]})" if erros else "") + f" · total {ok}", flush=True)
        print(f"{ok} posts rotulados · {analisador.pedidos} pedidos · {analisador.tokens} tokens")

    rot = rotulos(PROMPT_VERSAO)
    if rot.empty:
        return 0
    base = df.merge(rot.drop(columns=["plataforma"]), on="post_id", how="inner")
    for plat, d in base.groupby("plataforma"):
        print(f"\nPadrões visuais · {plat} ({(d.grupo == 'top').sum()} top, {(d.grupo == 'controle').sum()} controle)")
        for campo in CAMPOS:
            tabela = comparar(d, campo)
            for valor, r in tabela.head(4).iterrows():
                if str(valor) == "False":
                    continue
                lift = "—" if pd.isna(r["lift"]) else f"{r['lift']:.1f}×"
                print(f"   {campo:20.20} {str(valor):22.22} top {r['pct_top']:5.0%}  controle {r['pct_controle']:5.0%} "
                      f"lift {lift:>5}  {r['leitura']:28} ({int(r['n_perfis_top'])} perfis)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
