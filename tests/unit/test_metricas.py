"""Camada 0 com dados sintéticos: cada teste monta uma base pequena em que a resposta certa é conhecida."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.analysis.metrics import (calcular_metricas, faixa_seguidores, janela_do_post, resumo,
                                  selecionar_top_e_controle)
from src.evaluation.thresholds import Thresholds

AGORA = datetime(2026, 11, 22, 12, tzinfo=timezone.utc)
LIMIARES = Thresholds({
    "idade_minima_dias": 14, "janela_momento_dias": 90, "janela_anterior_dias": 90,
    "top_percentil": 0.10, "max_posts_por_perfil_no_top": 2,
    "faixas_seguidores": {"micro_max": 10000, "medio_max": 100000},
})


def post(pid, perfil, dias, curtidas, comentarios=0, plataforma="instagram", **extra):
    return {"plataforma": plataforma, "post_id": pid, "perfil_id": perfil,
            "publicado_em": (AGORA - timedelta(days=dias)).isoformat(), "curtidas": curtidas,
            "comentarios": comentarios, **extra}


def perfis(**seguidores):
    return pd.DataFrame([{"plataforma": "instagram", "perfil_id": k, "seguidores": v} for k, v in seguidores.items()])


def test_faixas_e_janelas():
    assert faixa_seguidores(10000, 10000, 100000) == "micro"
    assert faixa_seguidores(10001, 10000, 100000) == "medio"
    assert faixa_seguidores(250000, 10000, 100000) == "grande"
    assert faixa_seguidores(None, 10000, 100000) is None
    assert [janela_do_post(d, 14, 90, 90) for d in (3, 14, 90, 91, 180, 181)] == \
           ["recente", "momento", "momento", "anterior", "anterior", "fora"]


def test_er_e_comentarios_por_curtida():
    df = calcular_metricas(pd.DataFrame([post("p1", "a", 20, 90, 10)]), perfis(a=1000), AGORA, LIMIARES)
    assert df.loc[0, "er"] == pytest.approx(0.10)              # (90 + 10) / 1000
    assert df.loc[0, "comment_ratio"] == pytest.approx(10 / 90)
    assert df.loc[0, "faixa"] == "micro" and df.loc[0, "janela"] == "momento" and bool(df.loc[0, "elegivel"])


def test_motivos_de_exclusao_sem_apagar_o_post():
    base = pd.DataFrame([post("novo", "a", 5, 100), post("oculto", "a", 30, None, 4), post("sem_perfil", "x", 30, 10)])
    df = calcular_metricas(base, perfis(a=1000), AGORA, LIMIARES).set_index("post_id")
    assert len(df) == 3
    assert df.loc["novo", "motivo_exclusao"] == "menos_de_14_dias"
    assert df.loc["oculto", "motivo_exclusao"] == "curtidas_ocultas"
    assert df.loc["sem_perfil", "motivo_exclusao"] == "seguidores_desconhecidos"
    assert not df["elegivel"].any()


def test_lift_compara_o_post_com_a_mediana_do_proprio_perfil():
    base = pd.DataFrame([post(f"p{i}", "a", 20 + i, c) for i, c in enumerate([10, 20, 30, 60])])
    df = calcular_metricas(base, perfis(a=1000), AGORA, LIMIARES).set_index("post_id")
    # ER: 0,01 0,02 0,03 0,06 → mediana 0,025
    assert df.loc["p3", "lift_perfil"] == pytest.approx(0.06 / 0.025)
    sozinho = calcular_metricas(pd.DataFrame([post("q", "b", 20, 10)]), perfis(b=1000), AGORA, LIMIARES)
    assert pd.isna(sozinho.loc[0, "lift_perfil"])            # menos de 3 posts: sem lift


def base_ranking():
    """Micro: 30 posts de 3 perfis (o perfil 'viral' tem os 5 maiores ER). Grande: 10 posts de 1 perfil."""
    rows = []
    for i in range(10):
        rows.append(post(f"v{i}", "viral", 20 + i, 1000 - i))        # ER 0,100 … 0,091
        rows.append(post(f"m{i}", "medio_er", 20 + i, 500 - i))
        rows.append(post(f"b{i}", "baixo_er", 20 + i, 100 - i))
        rows.append(post(f"g{i}", "grande", 20 + i, 5000 + i))
    rows.append(post("antigo", "viral", 120, 5000))                  # janela anterior: fora do top de 90 dias
    return pd.DataFrame(rows), perfis(viral=9000, medio_er=9000, baixo_er=9000, grande=500000)


def test_top_por_faixa_respeita_o_limite_por_perfil():
    posts, perf = base_ranking()
    df = selecionar_top_e_controle(calcular_metricas(posts, perf, AGORA, LIMIARES), LIMIARES).set_index("post_id")
    top_micro = df[(df["grupo"] == "top") & (df["faixa"] == "micro")]
    assert len(top_micro) == 3                                       # 10% de 30
    assert top_micro["perfil_id"].value_counts()["viral"] == 2       # limite por perfil
    assert set(top_micro.index) == {"v0", "v1", "m0"}
    assert list(df[(df["grupo"] == "top") & (df["faixa"] == "grande")].index) == ["g9"]   # cada faixa tem o seu top
    assert df.loc["antigo", "grupo"] == "resto"                      # fora da janela de momento


def test_controle_tem_o_mesmo_tamanho_nao_cruza_com_o_top_e_e_reprodutivel():
    posts, perf = base_ranking()
    metr = calcular_metricas(posts, perf, AGORA, LIMIARES)
    a = selecionar_top_e_controle(metr, LIMIARES, semente=7)
    b = selecionar_top_e_controle(metr, LIMIARES, semente=7)
    for faixa in ("micro", "grande"):
        sub = a[a["faixa"] == faixa]
        assert (sub["grupo"] == "controle").sum() == (sub["grupo"] == "top").sum()
    assert a["grupo"].tolist() == b["grupo"].tolist()
    assert not set(a[a["grupo"] == "top"]["post_id"]) & set(a[a["grupo"] == "controle"]["post_id"])


def test_janela_todas_inclui_posts_antigos_e_inelegiveis_ficam_marcados():
    posts, perf = base_ranking()
    extra = pd.concat([posts, pd.DataFrame([post("recente", "viral", 2, 9999)])], ignore_index=True)
    df = selecionar_top_e_controle(calcular_metricas(extra, perf, AGORA, LIMIARES), LIMIARES, janela=None)
    df = df.set_index("post_id")
    assert df.loc["antigo", "grupo"] == "top"                        # maior ER da faixa micro
    assert df.loc["recente", "grupo"] == "inelegivel"


def test_resumo_conta_exclusoes_e_grupos():
    posts, perf = base_ranking()
    df = selecionar_top_e_controle(calcular_metricas(posts, perf, AGORA, LIMIARES), LIMIARES)
    info = resumo(df)
    assert info["posts"] == 41 and info["perfis"] == 4 and info["elegiveis"] == 41
    assert info["por_grupo"]["instagram / micro / todos / top"] == 3


def test_youtube_separa_shorts_de_videos_longos_e_instagram_nao():
    limiares = Thresholds({**LIMIARES, "ranking_separar_formato": {"youtube": True, "instagram": False}})
    rows = []
    for i in range(10):
        rows.append(post(f"s{i}", "canal", 20 + i, 900 - i, plataforma="youtube", tipo="short"))
        rows.append(post(f"v{i}", "canal", 20 + i, 100 - i, plataforma="youtube", tipo="video"))
        rows.append(post(f"r{i}", "insta", 20 + i, 900 - i, tipo="reels"))
        rows.append(post(f"c{i}", "insta", 20 + i, 100 - i, tipo="carrossel"))
    perf = pd.DataFrame([{"plataforma": "youtube", "perfil_id": "canal", "seguidores": 9000},
                         {"plataforma": "instagram", "perfil_id": "insta", "seguidores": 9000}])
    df = selecionar_top_e_controle(calcular_metricas(pd.DataFrame(rows), perf, AGORA, limiares), limiares)
    top = set(df[df["grupo"] == "top"]["post_id"])
    assert {"s0", "v0"} <= top            # cada formato do YouTube tem o seu top, mesmo o longo engajando menos
    assert "r0" in top and not any(p.startswith("c") for p in top)   # no Instagram, os formatos competem entre si
