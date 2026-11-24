"""Playbook de conteúdo para a Stone: só peças aprovadas, aviso quando faltam criativos, sem modelo de linguagem."""
from __future__ import annotations

import pytest

from src.agent import ferramentas as fx
from src.playbook import MINIMO_CRIATIVOS, gerar, montar


def peca(pid, status="aprovada"):
    return {"id": pid, "status": status, "data_agenda": "2026-12-01", "horario": "18h–20h", "atualizado_em": "2026-11-23T10:00:00",
            "formato": "reels", "segmento": "beleza_estetica", "objetivo": "caixa do salão",
            "atual": {"criativo": {"titulo": f"Peça {pid}", "caso": "Salão que mistura caixa e casa.", "gancho": "Seu salão lucra?",
                                   "corpo": ["Cena 1: abra uma conta", "anote as saídas"], "cta": "Comente CAIXA",
                                   "legenda": "Legenda <com> tag", "justificativa": ["segue o gancho de dor"]},
                      "conferencias": {"referencias_existem": True, "caso_concreto": True},
                      "juiz": {"media_ponderada": 8.6},
                      "referencias": [{"perfil": "perfil_real", "link": "https://www.instagram.com/p/x/", "formato": "carrossel", "lift_perfil": 3.2}],
                      "padroes": [{"plataforma": "instagram", "caracteristica": "tipo_hook", "valor": "dor", "lift": 3.0, "leitura": "mais no top"}]}}


@pytest.fixture(scope="module")
def base():
    if not (fx.ROOT / "data" / "processed" / "scores.csv").exists():
        pytest.skip("base processada ausente")
    from src.api import base as carregar
    return carregar()


def test_so_aprovadas_entram_e_avisa_quando_faltam(base):
    from src.api import frase
    d = montar(base, [peca("a"), peca("b", status="revisar")], frase)
    assert [p["id"] for p in d["criativos"]] == ["a"]
    html = gerar(base, [peca("a"), peca("b", status="revisar")], frase)
    assert "Peça a" in html and "Peça b" not in html
    assert f"Faltam {MINIMO_CRIATIVOS - 1} criativo" in html
    assert "Legenda &lt;com&gt; tag" in html                       # texto do modelo sempre escapado
    assert "abra uma conta" in html and "Cena 1: abra" not in html      # tira o "Cena 1:" que o modelo repete


def test_com_cinco_aprovadas_nao_avisa_e_traz_todas_as_secoes(base):
    from src.api import frase
    html = gerar(base, [peca(str(i)) for i in range(MINIMO_CRIATIVOS)], frase)
    assert "Faltam" not in html
    for secao in ("O que engaja no nicho", "O que aparece menos", "Perfis para parceria", "Quando publicar",
                  "Criativos prontos para produção", 'data-aba="impulso"', 'data-aba="stone"', 'data-aba="nicho"'):
        assert secao in html
    # cada seção diz para qual conta é
    assert "Para @impulsostone" in html and "Para @stone" in html and "Para as duas contas" in html


def test_nome_da_caracteristica_nao_corta_quem_aparece():
    from src.analysis.contas_stone import nome_caracteristica
    assert nome_caracteristica("Quem aparece “dono do negócio” aparece 2,0 vezes mais nos posts") == "Quem aparece “dono do negócio”"
    assert nome_caracteristica("Texto na tela logo no início: aparece menos nos posts") == "Texto na tela logo no início"


def test_criativo_da_stone_vai_para_a_aba_da_stone(base):
    from src.api import frase
    pecas = [peca("i1"), {**peca("s1"), "atual": {**peca("s1")["atual"], "conta": "stone"}}]
    html = gerar(base, pecas, frase)
    aba_stone = html.split('id="stone"')[1].split('id="nicho"')[0]
    aba_impulso = html.split('id="impulso"')[1].split('id="stone"')[0]
    assert "Peça s1" in aba_stone and "Peça s1" not in aba_impulso
    assert "Peça i1" in aba_impulso and "oferta da marca Stone" in aba_stone
