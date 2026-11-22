"""Contas da própria Stone (@stone e @impulsostone): coleta, métricas e rótulos, SEPARADOS da base de referência.

As contas da Stone não entram em config/perfis.csv: se entrassem, mudariam o top e o grupo de comparação dos 55
perfis de referência. Aqui elas passam pelas mesmas funções (mesma API, mesmas métricas, mesmos prompts de
rótulo), e o Playbook compara cada conta com o que engaja no nicho.

    python scripts/contas_stone.py coletar          # Graph API (Business Discovery), últimos 120 dias
    python scripts/contas_stone.py texto            # camada 1 (Groq) nos posts dos últimos 90 dias
    python scripts/contas_stone.py visual           # camada 2 (Gemini); para sozinha quando a cota acaba
    python scripts/contas_stone.py capas            # guarda as capas dos posts (os links do Instagram expiram)

Grava em data/contas_stone/raw/<data>/ (fora de data/raw, que guarda só as coletas da base de referência) e data/processed/contas_stone/.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src.collection.storage import append_jsonl, read_jsonl  # noqa: E402
from src.evaluation.thresholds import load_thresholds  # noqa: E402

CONTAS = ROOT / "config" / "contas_stone.csv"
RAW = ROOT / "data" / "contas_stone" / "raw"   # fora de data/raw: lá a pasta mais recente é a coleta da base de referência
PROC = ROOT / "data" / "processed" / "contas_stone"


def ultima_coleta() -> Path:
    pastas = sorted(p for p in RAW.iterdir() if p.is_dir()) if RAW.exists() else []
    if not pastas:
        sys.exit("Nenhuma coleta das contas da Stone. Rode: python scripts/contas_stone.py coletar")
    return pastas[-1]


def coletar(dias: int) -> int:
    from src.collection.http import get_json
    from src.collection.instagram_graph import InstagramGraphCollector
    from src.collection.ritmo import LimitadorChamadas
    from src.shared.cache import VersionedCache

    limiares = load_thresholds(ROOT / "config" / "limiares.yaml")
    out = RAW / datetime.now().strftime("%Y-%m-%d")
    out.mkdir(parents=True, exist_ok=True)
    cache = VersionedCache(Path(os.getenv("CACHE_DIR", ".cache/stone")) / "http")
    limitador = LimitadorChamadas(int(limiares.req("instagram_chamadas_por_hora")))
    coletor = InstagramGraphCollector(cache=cache, http=partial(get_json, antes_da_rede=limitador.antes_da_chamada))
    since = datetime.now(timezone.utc) - timedelta(days=dias)
    feitos = {p.get("username", "").lower() for p in read_jsonl(out / "perfis.jsonl")}
    with CONTAS.open(encoding="utf-8") as f:
        contas = [r for r in csv.DictReader(f) if r["plataforma"] == "instagram"]
    for conta in contas:
        if conta["perfil"].lower() in feitos:
            print(f"· @{conta['perfil']} já coletada hoje")
            continue
        perfil, posts, _ = coletor.collect(conta["perfil"], since=since)
        append_jsonl(out / "perfis.jsonl", [{**perfil.model_dump(mode="json"), "conta": conta["conta"], "papel": conta["papel"]}])
        n = append_jsonl(out / "posts.jsonl", posts)
        print(f"✓ @{perfil.username}: {perfil.seguidores} seguidores, {n} posts desde {since:%d/%m/%Y}")
    metricas(out)
    return 0


def insights(coleta: Path) -> int:
    """Alcance, salvamentos e compartilhamentos de cada post, com o token de quem administra a conta.

    Token por conta no .env: STONE_IG_TOKEN_STONE e STONE_IG_TOKEN_IMPULSOSTONE (permissão instagram_manage_insights,
    pedida à equipe da Stone). Conta sem token fica de fora sem erro. Grava insights.jsonl na pasta da coleta.
    """
    from src.collection.instagram_graph import insights_da_midia

    posts = pd.DataFrame(read_jsonl(coleta / "posts.jsonl"))
    feitos = {r["post_id"] for r in read_jsonl(coleta / "insights.jsonl")}
    total = 0
    for conta in sorted(posts["username"].str.lower().unique()) if not posts.empty else []:
        token = os.getenv(f"STONE_IG_TOKEN_{conta.upper()}", "")
        if not token:
            print(f"· @{conta}: sem STONE_IG_TOKEN_{conta.upper()} no .env, Insights não coletados")
            continue
        novos = []
        for pid in posts.loc[posts["username"].str.lower() == conta, "post_id"]:
            if str(pid) in feitos:
                continue
            try:
                novos.append({"post_id": str(pid), **insights_da_midia(str(pid), token)})
            except Exception as exc:  # noqa: BLE001 - post antigo ou sem permissão: segue com os outros
                print(f"  post {pid}: {str(exc)[:120]}")
        total += append_jsonl(coleta / "insights.jsonl", novos)
        print(f"✓ @{conta}: Insights de {len(novos)} posts")
    return total


def metricas(coleta: Path) -> pd.DataFrame:
    """Mesmas métricas da base de referência (src/analysis/metrics.py): ER, faixa, janela e lift no próprio perfil."""
    from src.analysis.metrics import calcular_metricas

    limiares = load_thresholds(ROOT / "config" / "limiares.yaml")
    posts = pd.DataFrame(read_jsonl(coleta / "posts.jsonl"))
    perfis = pd.DataFrame(read_jsonl(coleta / "perfis.jsonl"))
    df = calcular_metricas(posts, perfis, datetime.now(timezone.utc), limiares)
    df = df.merge(perfis[["perfil_id", "conta"]], on="perfil_id", how="left")
    ins = pd.DataFrame(read_jsonl(coleta / "insights.jsonl"))
    if not ins.empty:                                  # com Insights: engajamento sobre quem viu, com salvar e compartilhar
        ins = ins.drop_duplicates("post_id", keep="last").rename(columns={
            "reach": "alcance", "saved": "salvamentos", "shares": "compartilhamentos", "total_interactions": "interacoes"})
        df = df.merge(ins, on="post_id", how="left")
        df["er_alcance"] = (df["interacoes"] / df["alcance"]).where(df["alcance"] > 0)
    PROC.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROC / "scores.csv", index=False)
    elegiveis = df[df["elegivel"] & (df["janela"] == "momento")]
    print(f"Métricas: {len(elegiveis)} posts elegíveis nos últimos 90 dias "
          f"({elegiveis.groupby('conta').size().to_dict()}) → {PROC / 'scores.csv'}")
    return df


def alvo() -> pd.DataFrame:
    coleta = ultima_coleta()
    scores = pd.read_csv(PROC / "scores.csv", dtype={"post_id": str, "perfil_id": str})
    posts = pd.DataFrame(read_jsonl(coleta / "posts.jsonl"))
    posts["post_id"] = posts["post_id"].astype(str)
    df = scores[scores["elegivel"] & (scores["janela"] == "momento")][["plataforma", "post_id", "tipo", "perfil_id", "conta"]]
    colunas = [c for c in ("titulo", "legenda", "link", "media_url", "thumbnail_url", "duracao_s") if c in posts]
    return df.merge(posts[["post_id", *colunas]], on="post_id", how="left")


def texto(lote: int) -> int:
    from src.analysis.camada1 import PROMPT_VERSAO, rotular
    from src.shared.llm_client import LLMClient

    saida = PROC / "rotulos_texto.jsonl"
    df = alvo()
    feitos = {r["post_id"] for r in read_jsonl(saida) if r.get("prompt_versao") == PROMPT_VERSAO}
    pendentes = df[~df["post_id"].isin(feitos)]
    print(f"{len(df)} posts no alvo; {len(pendentes)} a rotular")
    if pendentes.empty:
        return 0
    for c in ("titulo", "legenda"):
        if c not in pendentes:
            pendentes = pendentes.assign(**{c: ""})
    client = LLMClient()
    registros = pendentes[["post_id", "plataforma", "tipo", "titulo", "legenda"]].fillna("").to_dict("records")
    rot, falhas = rotular(client, registros, tamanho_lote=lote, ao_concluir_lote=lambda r: append_jsonl(saida, r))
    print(f"{len(rot)} rotulados, {len(falhas)} falharam · {len(client.calls)} chamadas → {saida}")
    return 0


def visual(lote: int, max_pedidos: int) -> int:
    from src.analysis.camada2 import PROMPT_VERSAO, AnalisadorVisual, GeminiIndisponivel

    saida = PROC / "rotulos_visuais.jsonl"
    df = alvo()
    feitos = {r["post_id"] for r in read_jsonl(saida) if r.get("prompt_versao") == PROMPT_VERSAO}
    pendentes = df[~df["post_id"].isin(feitos) & df["media_url"].notna()] if "media_url" in df else df.iloc[0:0]
    print(f"{len(df)} posts no alvo; {len(pendentes)} com mídia a analisar (lotes de {lote})")
    if pendentes.empty:
        return 0
    analisador = AnalisadorVisual(max_pedidos=max_pedidos)
    registros = [{k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in r.items()}
                 for r in pendentes.to_dict("records")]
    for i in range(0, len(registros), lote):
        try:
            prontos, erros = analisador.analisar_lote(registros[i:i + lote])
        except GeminiIndisponivel as exc:
            print(f"  parei (cota do Gemini): {str(exc)[:160]}. O que já foi feito está salvo.")
            break
        novos = [r for r in prontos if r["post_id"] not in feitos]
        append_jsonl(saida, novos)
        feitos |= {r["post_id"] for r in novos}
        print(f"  lote {i // lote + 1}: {len(novos)} analisados, {len(erros)} sem mídia utilizável", flush=True)
    return 0


def capas() -> int:
    """Guarda a capa de cada post (imagem, capa do carrossel ou do Reels): os links do Instagram expiram em dias."""
    import requests

    destino = ROOT / "data" / "contas_stone" / "capas"
    destino.mkdir(parents=True, exist_ok=True)
    feitas = 0
    for p in read_jsonl(ultima_coleta() / "posts.jsonl"):
        arq = destino / f"{p['post_id']}.jpg"
        url = p.get("thumbnail_url") or (p.get("media_url") if p.get("tipo") != "reels" else None)
        if arq.exists() or not url:
            continue
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                arq.write_bytes(r.content)
                feitas += 1
        except requests.RequestException:
            pass
    print(f"{feitas} capas novas em {destino}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="etapa", required=True)
    c = sub.add_parser("coletar")
    c.add_argument("--dias", type=int, default=120)
    sub.add_parser("metricas")
    sub.add_parser("insights")
    sub.add_parser("capas")
    t = sub.add_parser("texto")
    t.add_argument("--lote", type=int, default=15)
    v = sub.add_parser("visual")
    v.add_argument("--lote", type=int, default=17)
    v.add_argument("--max-pedidos", type=int, default=6)
    a = ap.parse_args()
    if a.etapa == "coletar":
        return coletar(a.dias)
    if a.etapa == "metricas":
        metricas(ultima_coleta())
        return 0
    if a.etapa == "insights":
        insights(ultima_coleta())
        metricas(ultima_coleta())
        return 0
    if a.etapa == "capas":
        return capas()
    if a.etapa == "texto":
        return texto(a.lote)
    return visual(a.lote, a.max_pedidos)


if __name__ == "__main__":
    sys.exit(main())
