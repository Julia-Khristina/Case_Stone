"""Calibração do avaliador com notas humanas (scripts/calibrar_juiz.py) e página de rotulagem."""
from __future__ import annotations

import pandas as pd

from scripts.calibrar_juiz import comparar, criterios, preparar
from src.app_store import Store


def _loja(tmp_path, notas_juiz: list[float]):
    loja = Store(tmp_path / "c.sqlite")
    for i, n in enumerate(notas_juiz):
        loja.criar("reels", f"p{i}", {"criativo": {"titulo": f"T{i}", "caso": "c", "gancho": "g", "corpo": ["a"], "cta": "Comente"},
                                      "juiz": {"scores": {k: n for k in criterios()}, "aprovado": n >= 7}})
    return loja


def test_preparar_nao_apaga_o_que_ja_foi_preenchido(tmp_path):
    loja, planilha = _loja(tmp_path, [9, 8]), tmp_path / "notas.csv"
    assert preparar(loja, planilha) == 2
    df = pd.read_csv(planilha, dtype=str, encoding="utf-8-sig")
    df.loc[0, "humano_concretude"] = "5"
    df.to_csv(planilha, index=False, encoding="utf-8-sig")
    assert preparar(loja, planilha) == 0                                      # nada novo, nada sobrescrito
    assert pd.read_csv(planilha, dtype=str, encoding="utf-8-sig").loc[0, "humano_concretude"] == "5"


def test_comparar_mede_erro_e_vies(tmp_path):
    loja, planilha = _loja(tmp_path, [10, 9, 8, 7]), tmp_path / "notas.csv"
    preparar(loja, planilha)
    df = pd.read_csv(planilha, dtype=str, encoding="utf-8-sig")
    k = criterios()[0]
    df[f"humano_{k}"] = ["7", "6", "5", "4"]                                  # a pessoa dá 3 pontos a menos
    df["humano_aprovaria"] = ["sim", "nao", "nao", "nao"]
    df.to_csv(planilha, index=False, encoding="utf-8-sig")
    r = comparar(loja, planilha)
    assert r["por_criterio"][k]["vies_do_avaliador"] == 3.0 and r["por_criterio"][k]["spearman"] == 1.0
    assert r["por_criterio"][k]["ate_2_pontos"] == 0.0
    assert r["aprovacao"] == {"n": 4, "concordancia": 0.25}         # o avaliador aprovou as 4; a pessoa, 1


def test_posts_fora_do_tema_vao_para_a_lista_de_exclusao(tmp_path):
    from src.analysis import exclusoes
    arq = tmp_path / "excluidos.csv"
    assert exclusoes.registrar([{"post_id": "a1", "plataforma": "instagram"}, {"post_id": "b2", "plataforma": "youtube"}], arquivo=arq) == 2
    assert exclusoes.registrar([{"post_id": "a1", "plataforma": "instagram"}], arquivo=arq) == 0    # não duplica
    assert exclusoes.carregar(arq) == {"a1", "b2"}
    assert exclusoes.carregar(tmp_path / "nao_existe.csv") == set()
