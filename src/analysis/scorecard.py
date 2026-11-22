"""Scorecard de criadores: nota de 0 a 100 em cinco dimensões, sempre comparando com perfis da mesma plataforma e faixa.

Dimensões (pesos em config/limiares.yaml → scorecard_pesos):
- consistencia: % dos posts do perfil com ER acima da mediana da faixa (um viral isolado não basta)
- conversa: comentários ÷ curtidas, mediana do perfil (proxy de lead: o público responde, pergunta, pede contato)
- autenticidade: com 3+ posts vistos pela camada 2 (Gemini), é a fração de posts em que aparece o dono do negócio
  (ou um cliente) ou o negócio de verdade; sem isso, aproximação pelo tipo de perfil (setorial vale mais que
  transversal). Histórias de empreendedor nos posts somam nos dois casos.
- marca: % dos posts rotulados com tema acionável e sem frase motivacional genérica
- frequencia: posts nos últimos 90 dias
Cada dimensão vira percentil dentro de (plataforma, faixa). Alertas ficam fora da nota e nunca são escondidos.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TEMAS_ACIONAVEIS = {"vendas", "financas", "marketing", "atendimento", "gestao", "ferramentas",
                    "historia_de_empreendedor", "receita_ou_tecnica"}
MIN_VISTOS = 3            # posts analisados pela camada 2 para a autenticidade sair do vídeo
PESOS_PADRAO = {"consistencia": 25, "conversa": 20, "autenticidade": 20, "marca": 20, "frequencia": 15}


def _como_bool(serie: pd.Series | None, indice) -> pd.Series:
    """Converte sim/não com valores faltando (vazio = não), sem a conversão implícita que o pandas vai remover."""
    if serie is None:
        return pd.Series(False, index=indice)
    return serie.map(lambda v: bool(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else False)


def _percentil(serie: pd.Series) -> pd.Series:
    return (serie.rank(pct=True, method="average") * 100).round(0)


def calcular(posts: pd.DataFrame, perfis_lista: pd.DataFrame, concorrentes: list[str],
             pesos: dict[str, float] | None = None) -> pd.DataFrame:
    """`posts`: base com er, comment_ratio, janela, elegivel, faixa e rótulos da camada 1.
    `perfis_lista`: config/perfis.csv (plataforma, perfil, nome, tipo, segmento, parceiro_atual)."""
    pesos = pesos or PESOS_PADRAO
    eleg = posts[posts["elegivel"].astype(bool)].copy()
    mediana_faixa = eleg.groupby(["plataforma", "faixa"])["er"].transform("median")
    eleg["acima_da_faixa"] = eleg["er"] > mediana_faixa
    concorrentes_min = [c.lower() for c in concorrentes]

    linhas = []
    for (plataforma, perfil_id), g in eleg.groupby(["plataforma", "perfil_id"]):
        rotulados = g[g["tema_principal"].notna()] if "tema_principal" in g else g.iloc[0:0]
        if len(rotulados):
            generica = _como_bool(rotulados.get("mensagem_generica"), rotulados.index)
            marca_ok = rotulados["tema_principal"].isin(TEMAS_ACIONAVEIS) & ~generica
            historias = (rotulados["tema_principal"] == "historia_de_empreendedor").mean()
            publi = rotulados[_como_bool(rotulados.get("patrocinado"), rotulados.index)]
        else:
            marca_ok, historias, publi = [], 0.0, rotulados
        if "quem_aparece" in g:
            vistos = g[g["quem_aparece"].notna()]
            real = vistos["quem_aparece"].isin(["dono_do_negocio", "cliente"]) | (vistos.get("cenario") == "negocio_real")
        else:                                   # camada 2 ainda não rodou: autenticidade fica na aproximação
            vistos, real = g.iloc[0:0], pd.Series(dtype=bool)
        marcas_publi = {str(m).lower() for m in publi.get("marca_patrocinadora", pd.Series(dtype=object)).dropna()}
        linhas.append({
            "plataforma": plataforma, "perfil_id": perfil_id, "username": str(g["username"].iloc[0]),
            "faixa": g["faixa"].iloc[0], "seguidores": g.get("seguidores", pd.Series([np.nan])).iloc[0],
            "posts_elegiveis": len(g), "posts_rotulados": len(rotulados),
            "consistencia_bruta": float(g["acima_da_faixa"].mean()),
            "conversa_bruta": float(g["comment_ratio"].median()) if g["comment_ratio"].notna().any() else 0.0,
            "historias": float(historias),
            "posts_vistos": len(vistos), "real_visual": float(real.mean()) if len(vistos) >= MIN_VISTOS else np.nan,
            "marca_bruta": float(np.mean(marca_ok)) if len(rotulados) else np.nan,
            "frequencia_bruta": int((g["janela"] == "momento").sum()),
            "publi_concorrente": sorted(m for m in marcas_publi if any(c in m for c in concorrentes_min)),
        })
    df = pd.DataFrame(linhas)
    if df.empty:
        return df

    lista = perfis_lista.copy()
    lista["chave"] = [p.lower() if pl == "instagram" else p for pl, p in zip(lista["plataforma"], lista["perfil"])]
    df["chave"] = [u.lower() if pl == "instagram" else pid for pl, u, pid in zip(df["plataforma"], df["username"], df["perfil_id"])]
    df = df.merge(lista[["plataforma", "chave", "nome", "tipo", "segmento", "parceiro_atual"]], on=["plataforma", "chave"], how="left")
    df["tipo"] = df["tipo"].fillna("")
    proxy = df["tipo"].map({"setorial": 1.0, "transversal": 0.6, "marca": 0.0}).fillna(0.5)
    df["autenticidade_fonte"] = np.where(df["real_visual"].notna(), "video", "aproximacao")
    df["autenticidade_bruta"] = df["real_visual"].fillna(proxy) + df["historias"]

    grupo = df.groupby(["plataforma", "faixa"])
    for dim in ("consistencia", "conversa", "autenticidade", "marca", "frequencia"):
        df[dim] = grupo[f"{dim}_bruta"].transform(_percentil).fillna(50)
    total = sum(pesos.values())
    df["nota"] = sum(df[d] * p for d, p in pesos.items()).div(total).round(0).astype(int)

    def alertas(r) -> list[str]:
        a = []
        if str(r.get("parceiro_atual")).lower() in {"sim", "true", "1"}:
            a.append("parceiro_atual")
        if r["tipo"] == "marca":
            a.append("conta_de_marca")
        if r["publi_concorrente"]:
            a.append("publi_concorrente")
        if r["posts_rotulados"] < 3:
            a.append("poucos_posts_rotulados")
        return a
    df["alertas"] = df.apply(alertas, axis=1)
    df["macrossetor"] = np.where(df["tipo"] == "setorial", df["segmento"], None)
    df["tema"] = np.where(df["tipo"] == "transversal", df["segmento"], None)
    df["perfil"] = df["chave"]
    return df.sort_values("nota", ascending=False).drop(columns=["chave"]).reset_index(drop=True)
