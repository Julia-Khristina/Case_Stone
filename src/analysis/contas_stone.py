"""Diagnóstico das contas da Stone (@stone e @impulsostone) contra o que engaja no nicho.

Três comparações, todas descritivas (cada conta é um perfil só, com algumas dezenas de posts):
1. conta × nicho: engajamento contra perfis da mesma faixa de seguidores; frequência; mistura de formatos;
2. lacunas: para cada achado confiável do Instagram (top × controle), quanto a conta usa aquela característica;
3. dentro da conta: o que rende acima ou abaixo da mediana da própria conta (lift no perfil), com mínimo de posts.

Os dados vêm de scripts/contas_stone.py (data/processed/contas_stone/), separados da base de referência.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.agent import ferramentas as fx
from src.collection.storage import read_jsonl

PROC = fx.ROOT / "data" / "processed" / "contas_stone"
JANELA_SEMANAS = (90 - 14) / 7          # posts da janela "momento": publicados entre 14 e 90 dias atrás
MIN_POSTS_GRUPO = 4                      # dentro da conta, um grupo menor que isso não vira leitura
CAMPOS_CONTA = ["tipo", "tema_principal", "tipo_hook", "tipo_cta", "convite_participacao",
                "quem_aparece", "gancho_visual", "cenario", "rosto_nos_3s", "texto_na_tela_inicio", "cta_no_final"]


def contas_config() -> dict[str, dict]:
    caminho = fx.ROOT / "config" / "contas_stone.csv"
    if not caminho.exists():
        return {}
    with caminho.open(encoding="utf-8") as f:
        return {r["perfil"].lower(): r for r in csv.DictReader(f)}


def carregar(pasta: Path = PROC) -> Optional[pd.DataFrame]:
    """Posts elegíveis dos últimos 90 dias das contas, com rótulos de texto e (quando houver) de vídeo."""
    if not (pasta / "scores.csv").exists():
        return None
    df = pd.read_csv(pasta / "scores.csv", dtype={"post_id": str, "perfil_id": str})
    df = df[df["elegivel"].astype(bool) & (df["janela"] == "momento")].copy()
    texto = pd.DataFrame(read_jsonl(pasta / "rotulos_texto.jsonl"))
    if not texto.empty:
        texto["post_id"] = texto["post_id"].astype(str)
        df = df.merge(texto.drop_duplicates("post_id", keep="last").drop(columns=["modelo", "prompt_versao", "plataforma"], errors="ignore"),
                      on="post_id", how="left", suffixes=("", "_rot"))
    visual = pd.DataFrame(read_jsonl(pasta / "rotulos_visuais.jsonl"))
    if not visual.empty:
        from src.analysis.camada2 import PROMPT_VERSAO
        visual = visual[visual.get("prompt_versao") == PROMPT_VERSAO]
    if not visual.empty:
        visual["post_id"] = visual["post_id"].astype(str)
        df = df.merge(visual.drop_duplicates("post_id", keep="last").drop(
            columns=["plataforma", "modelo", "prompt_versao", "posts_no_pedido"], errors="ignore").rename(columns={"resumo": "resumo_visual"}),
            on="post_id", how="left")
    posts = _posts_brutos()
    if posts is not None:
        df = df.merge(posts, on="post_id", how="left", suffixes=("", "_bruto"))
    return df


def _posts_brutos() -> Optional[pd.DataFrame]:
    raw = fx.ROOT / "data" / "contas_stone" / "raw"
    pastas = sorted(p for p in raw.iterdir() if p.is_dir()) if raw.exists() else []
    if not pastas:
        return None
    posts = pd.DataFrame(read_jsonl(pastas[-1] / "posts.jsonl"))
    posts["post_id"] = posts["post_id"].astype(str)
    return posts[[c for c in ("post_id", "link", "legenda", "username") if c in posts]]


def _tem(serie: pd.Series, valor: str) -> pd.Series:
    """A característica (valor) presente em cada post; sim/não chegam como True/False ou "True"/"False"."""
    return serie.astype(str) == str(valor)


def _nicho_instagram(base: fx.Base) -> pd.DataFrame:
    df = base.posts
    return df[(df["plataforma"] == "instagram") & df["elegivel"].astype(bool) & (df["janela"] == "momento")]


def diagnosticar(base: fx.Base, contas: pd.DataFrame, frase) -> list[dict]:
    """Um diagnóstico por conta, na ordem de config/contas_stone.csv."""
    cfg = contas_config()
    nicho = _nicho_instagram(base)
    top = nicho[nicho["grupo"] == "top"]
    achados = [f for f in fx.query_stats(base, "instagram") if f.leitura in ("mais no top", "menos no top")]
    formatos_nicho = {t.valor: t for t in fx.format_trends(base, "instagram")}
    por_perfil = nicho.groupby("perfil_id").agg(n=("post_id", "size"), faixa=("faixa", "first"))
    saida = []
    for username in [u for u in cfg if u in set(contas["username"].astype(str).str.lower())]:
        c = contas[contas["username"].astype(str).str.lower() == username].copy()
        info = cfg[username]
        faixa = c["faixa"].iloc[0]
        mesma_faixa = nicho[nicho["faixa"] == faixa]
        er_conta = float(c["er"].median())
        er_nicho = float(mesma_faixa["er"].median()) if len(mesma_faixa) else np.nan
        freq_nicho = float((por_perfil[por_perfil["faixa"] == faixa]["n"] / JANELA_SEMANAS).median()) if len(por_perfil) else np.nan

        # mistura de formatos: conta × top do nicho
        formatos = []
        for tipo in ["reels", "carrossel", "imagem"]:
            t = formatos_nicho.get(tipo)
            grupo = c[c["tipo"] == tipo]
            formatos.append({"tipo": tipo, "pct_conta": float((c["tipo"] == tipo).mean()),
                             "pct_top": t.pct_top if t else None, "pct_controle": t.pct_controle if t else None,
                             "leitura_nicho": t.leitura if t else None, "n_conta": int(len(grupo)),
                             "lift_mediano_conta": float(grupo["lift_perfil"].median()) if len(grupo) >= MIN_POSTS_GRUPO else None})

        # lacunas: achados confiáveis do nicho × quanto a conta usa
        lacunas = []
        for f in achados:
            if f.caracteristica not in c or c[f.caracteristica].isna().all():
                continue
            vistos = c[c[f.caracteristica].notna()]
            pct = float(_tem(vistos[f.caracteristica], f.valor).mean())
            a = f.model_dump()
            a.update(frase=frase(a), pct_conta=pct, n_conta=int(len(vistos)))
            if (f.caracteristica, f.valor) == ("mensagem_generica", "True"):
                a["acao"] = "nao_usar"           # engaja no orgânico, mas não gerou clique nos anúncios do Impulso
            elif f.leitura == "mais no top":
                a["acao"] = "fazer_mais" if pct < f.pct_top * 0.75 else "manter"
            else:
                a["acao"] = "fazer_menos" if pct > f.pct_top * 1.25 else "manter"
            if a["acao"] == "fazer_mais":
                a["referencias"] = [r.model_dump() for r in fx.search_posts(base, "instagram", filtros_rotulo={f.caracteristica: f.valor}, k=3)]
            lacunas.append(a)

        # dentro da conta: o que rende acima / abaixo da mediana da própria conta
        internos = []
        for campo in CAMPOS_CONTA:
            if campo not in c or c[campo].isna().all():
                continue
            for valor, g in c.dropna(subset=[campo]).groupby(c[campo].astype(str)):
                if len(g) < MIN_POSTS_GRUPO or valor in ("False", "nenhum", "nan", "outro"):
                    continue
                med = float(g["lift_perfil"].median())
                internos.append({"campo": campo, "valor": valor, "n": int(len(g)), "lift_mediano": med,
                                 "frase": _frase_interna(frase, campo, valor)})
        internos.sort(key=lambda x: -x["lift_mediano"])
        acima = [x for x in internos if x["lift_mediano"] >= 1.15][:5]
        abaixo = [x for x in internos if x["lift_mediano"] <= 0.85][-5:][::-1]

        melhores = []
        for _, r in c.sort_values("lift_perfil", ascending=False).head(3).iterrows():
            texto = " ".join(str(r.get("legenda") or "").split())
            melhores.append({"post_id": str(r["post_id"]), "link": r.get("link"), "tipo": r.get("tipo"), "lift": float(r["lift_perfil"]),
                             "trecho": texto[:180] + ("…" if len(texto) > 180 else ""),
                             "tema": r.get("tema_principal"), "gancho": r.get("tipo_hook")})

        saida.append({
            "username": username, "nome": info["conta"], "papel": info["papel"],
            "seguidores": int(c["seguidores"].iloc[0]), "faixa": faixa, "n_posts": int(len(c)),
            "posts_semana": len(c) / JANELA_SEMANAS, "posts_semana_nicho": freq_nicho,
            "er_conta": er_conta, "er_nicho": er_nicho, "n_nicho_faixa": int(len(mesma_faixa)),
            "perfis_nicho_faixa": int(mesma_faixa["perfil_id"].nunique()) if len(mesma_faixa) else 0,
            "tem_visual": bool("quem_aparece" in c and c["quem_aparece"].notna().any()),
            "n_visual": int(c["quem_aparece"].notna().sum()) if "quem_aparece" in c else 0,
            "patrocinados": float(_tem(c["patrocinado"], "True").mean()) if "patrocinado" in c else None,
            "formatos": formatos, "lacunas": lacunas, "acima": acima, "abaixo": abaixo, "melhores": melhores,
        })
    return saida


def _frase_interna(frase, campo: str, valor: str) -> str:
    if campo == "tipo":
        return f"Formato {valor}"
    return nome_caracteristica(frase({"caracteristica": campo, "valor": valor, "lift": 1.0}))


def nome_caracteristica(frase: str) -> str:
    """'Quem aparece “dono” aparece 2,0 vezes mais…' → 'Quem aparece “dono”' (corta só a comparação final)."""
    return re.split(r":? aparece (?=[\d,]+ vezes|menos)", frase)[0]
