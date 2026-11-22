"""Padrões top × controle: quanto cada característica aparece mais nos posts do top do que no grupo controle.

É daqui que sai o "porquê" do engajamento: nenhuma ferramenta diz por que um post engajou; a comparação com o
controle separa o que é típico do sucesso do que é só comum no nicho.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _tem_valor(serie: pd.Series, valor: str) -> np.ndarray:
    """1 se o post tem o valor (em campos de lista, se a lista contém o valor), 0 se não."""
    def tem(v) -> bool:
        if isinstance(v, (list, tuple, np.ndarray)):
            return len(v) == 0 if valor == "—" else valor in [str(x) for x in v]   # "—" = lista vazia
        return ("—" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)) == valor
    return serie.map(tem).to_numpy(dtype=float)


def intervalo_lift(top: np.ndarray, controle: np.ndarray, n_boot: int = 1000, semente: int = 42,
                   nivel: float = 0.90) -> tuple[float, float]:
    """Intervalo de confiança do lift por bootstrap: reamostra top e controle com reposição, n_boot vezes.

    Com amostras pequenas (dezenas de posts), um lift de 1,8× pode ser só acaso. O intervalo mostra isso.
    """
    rng = np.random.default_rng(semente)
    n_t, n_c = len(top), len(controle)
    # Proporções suavizadas (+0,5 caso, +1 total): sem isso, um valor ausente no controle dava limite "infinito"
    # e marcava como confiável um padrão com 5 posts (achado em 22/11/2026).
    p_top = (rng.choice(top, size=(n_boot, n_t), replace=True).sum(axis=1) + 0.5) / (n_t + 1)
    p_ctl = (rng.choice(controle, size=(n_boot, n_c), replace=True).sum(axis=1) + 0.5) / (n_c + 1)
    lifts = p_top / p_ctl
    a = (1 - nivel) / 2
    return float(np.quantile(lifts, a)), float(np.quantile(lifts, 1 - a))


def comparar(df: pd.DataFrame, campo: str, n_minimo: int = 3, n_boot: int = 1000, semente: int = 42,
             min_perfis: int = 3) -> pd.DataFrame:
    """Para cada valor do campo: % no top, % no controle, lift (top ÷ controle), quantos posts do top têm o valor,
    o intervalo de confiança de 90% do lift e se o padrão é confiável (intervalo inteiro acima ou abaixo de 1).

    Um padrão só conta como "mais no top" se aparecer no top em pelo menos `min_perfis` perfis diferentes: um valor
    que vem de um criador só (ex.: o link de afiliado que ele sempre usa) é hábito dele, não o que engaja.

    Campos de lista (ex.: ferramentas_mencionadas) são abertos: um post pode contar para vários valores.
    Valores com menos de `n_minimo` posts no top ficam de fora, para não tirar conclusão de um caso isolado.
    """
    base = df[df["grupo"].isin(["top", "controle"])][["grupo", campo]].copy()
    if base[campo].map(lambda v: isinstance(v, list)).any():
        base = base.explode(campo)
    base[campo] = base[campo].map(lambda v: "—" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v))
    totais = df[df["grupo"].isin(["top", "controle"])].groupby("grupo").size()
    contagem = base.groupby([campo, "grupo"]).size().unstack(fill_value=0)
    for g in ("top", "controle"):
        if g not in contagem:
            contagem[g] = 0
    out = pd.DataFrame({
        "pct_top": contagem["top"] / totais.get("top", 1),
        "pct_controle": contagem["controle"] / totais.get("controle", 1),
        "n_top": contagem["top"],
    })
    out["lift"] = out["pct_top"] / out["pct_controle"].where(out["pct_controle"] > 0)
    out = out[out["n_top"] >= n_minimo].copy()

    grupo = df[df["grupo"].isin(["top", "controle"])]
    serie_top, serie_ctl = grupo[grupo["grupo"] == "top"][campo], grupo[grupo["grupo"] == "controle"][campo]
    baixos, altos = [], []
    for valor in out.index:
        lo, hi = intervalo_lift(_tem_valor(serie_top, valor), _tem_valor(serie_ctl, valor), n_boot, semente)
        baixos.append(lo)
        altos.append(hi)
    out["ic_baixo"], out["ic_alto"] = baixos, altos

    coluna_perfil = next((c for c in ("perfil_id", "username") if c in grupo.columns), None)
    if coluna_perfil:
        top_df = grupo[grupo["grupo"] == "top"]
        out["n_perfis_top"] = [int(top_df[_tem_valor(top_df[campo], v) > 0][coluna_perfil].nunique()) for v in out.index]
    else:
        out["n_perfis_top"] = min_perfis      # sem a coluna de perfil, não dá para checar a concentração
    # O lift pontual também precisa se afastar de 1: perto de 100% a suavização do intervalo pode criar um
    # "menos no top" artificial quando top e controle têm tamanhos diferentes (achado nos dados reais em 22/11/2026).
    lift_pontual = out["pct_top"] / out["pct_controle"].where(out["pct_controle"] > 0, np.nan)
    acima = (out["ic_baixo"] > 1) & (lift_pontual.isna() | (lift_pontual > 1.1))
    abaixo = (out["ic_alto"] < 1) & (lift_pontual < 0.9)
    out["leitura"] = np.select(
        [acima & (out["n_perfis_top"] >= min_perfis), acima, abaixo],
        ["mais no top", "concentrado em poucos perfis", "menos no top"], default="inconclusivo")
    return out.sort_values(["lift", "n_top"], ascending=[False, False])
