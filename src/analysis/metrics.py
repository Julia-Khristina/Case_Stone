"""Camada 0: métricas, elegibilidade, ranking por faixa e grupo controle. Só pandas, sem LLM e sem rede.

Decisões (README e config/limiares.yaml):
- Métrica principal do TAPI: ER = (curtidas + comentários) / seguidores.
- Lift no perfil: ER do post / mediana do ER dos posts elegíveis do mesmo perfil. Isola o efeito do conteúdo
  do efeito do tamanho da conta.
- Top 10% calculado por plataforma e faixa de seguidores, com limite de posts por perfil: a taxa de engajamento
  cai quando os seguidores sobem, e uma conta viral não pode dominar o top.
- Grupo controle: amostra aleatória (semente fixa) dos elegíveis fora do top, do mesmo tamanho e na mesma
  plataforma e faixa. Sem ele, "padrão do top" pode ser só "padrão do nicho".
- Nada é apagado: post que não entra no ranking fica com `elegivel=False` e o motivo.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime

import numpy as np
import pandas as pd

MIN_POSTS_PARA_LIFT = 3


def faixa_seguidores(seguidores: float | None, micro_max: int, medio_max: int) -> str | None:
    if seguidores is None or pd.isna(seguidores) or seguidores <= 0:
        return None
    if seguidores <= micro_max:
        return "micro"
    if seguidores <= medio_max:
        return "medio"
    return "grande"


def janela_do_post(idade_dias: float, idade_minima: int, momento: int, anterior: int) -> str:
    if idade_dias < idade_minima:
        return "recente"        # métricas ainda não estabilizadas
    if idade_dias <= momento:
        return "momento"
    if idade_dias <= momento + anterior:
        return "anterior"
    return "fora"


def calcular_metricas(posts: pd.DataFrame, perfis: pd.DataFrame, agora: datetime, limiares) -> pd.DataFrame:
    """Junta posts e perfis e calcula idade, janela, faixa, ER, lift, comentários/curtidas e elegibilidade.

    `posts` precisa de: plataforma, post_id, perfil_id, publicado_em, curtidas, comentarios, visualizacoes.
    `perfis` precisa de: plataforma, perfil_id, seguidores.
    """
    faixas = limiares.req("faixas_seguidores")
    idade_minima = int(limiares.req("idade_minima_dias"))
    momento = int(limiares.req("janela_momento_dias"))
    anterior = int(limiares.req("janela_anterior_dias"))

    df = posts.merge(perfis[["plataforma", "perfil_id", "seguidores"]], on=["plataforma", "perfil_id"], how="left")
    if "visualizacoes" not in df:
        df["visualizacoes"] = np.nan
    publicado = pd.to_datetime(df["publicado_em"], utc=True)
    df["idade_dias"] = (pd.Timestamp(agora).tz_convert("UTC") - publicado).dt.total_seconds() / 86400
    df["janela"] = [janela_do_post(i, idade_minima, momento, anterior) for i in df["idade_dias"]]
    df["faixa"] = [faixa_seguidores(s, int(faixas["micro_max"]), int(faixas["medio_max"])) for s in df["seguidores"]]

    curtidas = pd.to_numeric(df["curtidas"], errors="coerce")
    comentarios = pd.to_numeric(df["comentarios"], errors="coerce").fillna(0)
    seguidores = pd.to_numeric(df["seguidores"], errors="coerce")
    visualizacoes = pd.to_numeric(df["visualizacoes"], errors="coerce")
    valid_followers = seguidores.where(seguidores > 0)
    df["er"] = (curtidas + comentarios) / valid_followers
    df["comment_ratio"] = comentarios / curtidas.where(curtidas > 0)
    df["views_por_seguidor"] = visualizacoes / valid_followers

    motivo = pd.Series(None, index=df.index, dtype="object")
    motivo[curtidas.isna()] = "curtidas_ocultas"
    motivo[valid_followers.isna()] = "seguidores_desconhecidos"
    motivo[df["idade_dias"] < idade_minima] = f"menos_de_{idade_minima}_dias"
    df["motivo_exclusao"] = motivo
    df["elegivel"] = motivo.isna()

    # Lift no perfil: só para perfis com posts elegíveis suficientes para uma mediana estável
    elegiveis = df[df["elegivel"]]
    mediana = elegiveis.groupby(["plataforma", "perfil_id"])["er"].agg(["median", "count"])
    mediana = mediana[mediana["count"] >= MIN_POSTS_PARA_LIFT]["median"].rename("er_mediano_perfil")
    df = df.merge(mediana, left_on=["plataforma", "perfil_id"], right_index=True, how="left")
    df["lift_perfil"] = np.where(df["elegivel"], df["er"] / df["er_mediano_perfil"].where(df["er_mediano_perfil"] > 0), np.nan)
    return df.drop(columns=["er_mediano_perfil"])


def selecionar_top_e_controle(df: pd.DataFrame, limiares, janela: str | None = "momento", semente: int = 42
                              ) -> pd.DataFrame:
    """Marca cada post como top, controle, resto ou inelegivel.

    `janela`: "momento" usa só os posts dos últimos 90 dias (com 14+ dias); None usa todos os elegíveis.
    Em cada grupo (plataforma, faixa e, onde `ranking_separar_formato` mandar, formato): o top tem
    round(percentil × n) posts (no mínimo 1), escolhidos por ER decrescente, pulando posts de perfis que já
    atingiram o limite. O controle sorteia o mesmo número de posts entre os elegíveis que sobraram no grupo.
    """
    percentil = float(limiares.req("top_percentil"))
    limite_perfil = int(limiares.req("max_posts_por_perfil_no_top"))
    separar = limiares.get("ranking_separar_formato") or {}
    out = df.copy()
    out["grupo"] = np.where(out["elegivel"], "resto", "inelegivel")
    # Formato usado no agrupamento: o tipo do post onde a plataforma separa formatos, "todos" onde não separa
    tipos = out["tipo"] if "tipo" in out else pd.Series("todos", index=out.index)
    out["formato_ranking"] = [t if separar.get(p) else "todos" for p, t in zip(out["plataforma"], tipos)]
    base = out[out["elegivel"] & out["faixa"].notna()]
    if "fora_escopo" in out:            # fora do escopo do TAPI (src/analysis/escopo.py): continua elegível, mas não concorre
        fora = out["fora_escopo"].fillna("").astype(str) != ""
        out.loc[out["elegivel"] & fora, "grupo"] = "fora_escopo"
        base = base[~fora.loc[base.index]]
    if janela is not None:
        base = base[base["janela"] == janela]
    rng = np.random.default_rng(semente)

    for _, grupo in base.groupby(["plataforma", "faixa", "formato_ranking"], sort=True):
        alvo = max(1, int(round(percentil * len(grupo))))
        escolhidos: list = []
        por_perfil: dict[str, int] = {}
        for idx, row in grupo.sort_values(["er", "post_id"], ascending=[False, True]).iterrows():
            if por_perfil.get(row["perfil_id"], 0) >= limite_perfil:
                continue
            escolhidos.append(idx)
            por_perfil[row["perfil_id"]] = por_perfil.get(row["perfil_id"], 0) + 1
            if len(escolhidos) == alvo:
                break
        out.loc[escolhidos, "grupo"] = "top"
        restantes = grupo.index.difference(escolhidos).sort_values()
        n_controle = min(len(escolhidos), len(restantes))
        if n_controle:
            # Sorteio estável: cada post tem um número aleatório fixo (semente + id). Tirar um post do escopo não
            # embaralha o resto do controle, então a rotulagem converge em vez de recomeçar a cada rodada.
            chave = out.loc[restantes, "post_id"].astype(str).map(
                lambda pid: int(hashlib.sha256(f"{semente}:{pid}".encode()).hexdigest()[:12], 16))
            controle = chave.sort_values(kind="stable").index[:n_controle]
            out.loc[controle, "grupo"] = "controle"
    return out


def resumo(df: pd.DataFrame) -> dict:
    """Números para o relatório de qualidade da base e o README."""
    chaves = ["plataforma", "faixa", "formato_ranking", "grupo"] if "formato_ranking" in df else ["plataforma", "faixa", "grupo"]
    grupos = df.groupby(chaves, dropna=False).size()
    return {
        "posts": int(len(df)),
        "perfis": int(df[["plataforma", "perfil_id"]].drop_duplicates().shape[0]),
        "elegiveis": int(df["elegivel"].sum()),
        "exclusoes": {k: int(v) for k, v in df["motivo_exclusao"].value_counts().items()},
        "por_janela": {k: int(v) for k, v in df["janela"].value_counts().items()},
        "por_grupo": {" / ".join("—" if (isinstance(p, float) and math.isnan(p)) else str(p) for p in k): int(v)
                      for k, v in grupos.items()},
    }
