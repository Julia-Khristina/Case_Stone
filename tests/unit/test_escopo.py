"""Filtro de escopo do TAPI (src/analysis/escopo.py) e o grupo fora_escopo no ranking."""
from __future__ import annotations

import pandas as pd

from src.analysis.escopo import motivos_fora, termo_sensivel


def test_termos_sensiveis_sem_falso_positivo_de_politica_comercial():
    assert termo_sensivel("O que acontece agora com o Brasil e o Lula no poder?") == "lula"
    assert termo_sensivel("Domingo tem eleição, faça uma boa escolha") == "eleic"
    assert termo_sensivel("Racismo no atendimento: como agir") is not None
    assert termo_sensivel("Nossa política de trocas e cancelamento") is None        # política comercial não é política
    assert termo_sensivel("Como precificar o bolo de pote") is None


def test_motivos_fora_aplica_as_tres_travas_em_ordem():
    df = pd.DataFrame({"post_id": ["1", "2", "3", "4", "5", "6"],
                       "titulo": ["", "", "", "", "", ""],
                       "legenda": ["Lula e a eleição", "fluxo de caixa", "receita de bolo", "dicas de venda", "vlog", "gestão"],
                       "curtidas": [5000, 5000, 5000, 40, 5000, 5000]})
    texto = pd.DataFrame({"post_id": ["3"], "tema_principal": ["receita_ou_tecnica"]})
    esc = pd.DataFrame({"post_id": ["5", "6"], "orienta_empreendedor": ["nao", "sim"], "tema_sensivel": [False, False]})
    m = motivos_fora(df, texto, esc, min_curtidas=150)
    assert m[0].startswith("tema sensível") and m[1] == "" and m[2] == "tema receita_ou_tecnica"
    assert m[3] == "menos de 150 curtidas" and m[4] == "não orienta o empreendedor" and m[5] == ""
    esc2 = pd.DataFrame({"post_id": ["6"], "orienta_empreendedor": ["parcial"], "tema_sensivel": [False]})
    assert motivos_fora(df, texto, esc2, 150)[5] == "orienta só em parte (sem ensinar gestão)"   # só "sim" entra


def test_fora_do_escopo_nao_concorre_mas_continua_elegivel():
    from src.analysis.metrics import selecionar_top_e_controle

    class L:
        def req(self, k):
            return {"top_percentil": 0.5, "max_posts_por_perfil_no_top": 5}[k]

        def get(self, k, d=None):
            return {}
    df = pd.DataFrame({"post_id": list("abcd"), "perfil_id": ["p"] * 4, "plataforma": ["instagram"] * 4,
                       "faixa": ["micro"] * 4, "janela": ["momento"] * 4, "elegivel": [True] * 4,
                       "er": [0.9, 0.5, 0.4, 0.1], "fora_escopo": ["tema sensível: lula", "", "", ""]})
    s = selecionar_top_e_controle(df, L())
    assert s.loc[s.post_id == "a", "grupo"].item() == "fora_escopo"                  # o de maior ER não entra
    assert s.loc[s.post_id == "a", "elegivel"].item()                                # mas segue nas médias
    assert set(s.loc[s.grupo == "top", "post_id"]) <= {"b", "c", "d"}
