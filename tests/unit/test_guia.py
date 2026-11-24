"""Guia detalhado da semana: escolha das peças da semana, conferências do texto e HTML de e-mail sem dados pessoais."""
from __future__ import annotations

from datetime import date

import pytest

from src.agent import ferramentas as fx
from src.guia import gerar_guia, pecas_da_semana
from tests.fakes.llm import FakeLLMClient

BOM = {"titulo": "Separe o dinheiro da loja do seu", "por_que_importa": "Misturar contas esconde o lucro. Você perde o controle.",
       "passo_a_passo": ["Abra uma conta só para a loja.", "Defina um salário para você.", "Anote toda saída do caixa."],
       "exemplo_pratico": "Na padaria, a dona tirava dinheiro do caixa para o mercado de casa e não sabia o lucro.",
       "erro_comum": "Pagar conta de casa com o dinheiro da loja.",
       "como_o_impulso_ajuda": "O Impulso tem conteúdos e mentoria sobre organizar as finanças do negócio.",
       "pergunta_para_refletir": "Você sabe quanto a sua loja lucrou no mês passado?"}


def peca(pid, status="aprovada", data="2026-11-24"):
    return {"id": pid, "status": status, "data_agenda": data, "atualizado_em": "2026-11-22T10:00:00", "formato": "reels",
            "objetivo": "separar contas", "segmento": None,
            "atual": {"criativo": {"titulo": f"Post {pid}", "gancho": "g", "corpo": ["a"], "legenda": "l", "cta": "Comente"}}}


def test_so_aprovadas_da_semana_entram():
    pecas = [peca("a"), peca("b", status="revisar"), peca("c", data="2026-12-10"), peca("d", data=None)]
    escolhidas = pecas_da_semana(pecas, date(2026, 11, 23), date(2026, 11, 29))
    assert [p["id"] for p in escolhidas] == ["a"]          # "d" foi aprovada em 22/11, semana anterior


def test_guia_reescreve_o_que_falha_e_gera_html_de_email():
    if not (fx.ROOT / "data" / "processed" / "scores.csv").exists():
        pytest.skip("base processada ausente")
    from src.api import base
    ruim = {**BOM, "como_o_impulso_ajuda": "O Impulso Stone oferece maquininha com taxa zero e crédito garantido."}
    fake = FakeLLMClient({"guia": [ruim, BOM]})
    pb = gerar_guia(fake, base(), [peca("a")], date(2026, 11, 25), [{"data": "2026-12-01", "tema": "Natal"}])
    assert len(fake.prompts) == 2 and "Corrija" in fake.prompts[1]["prompt"]      # a primeira versão foi barrada
    assert pb["secoes"][0]["titulo"] == BOM["titulo"] and not pb["falhas"]
    assert pb["inicio"] == "2026-11-23" and "{{link_descadastro}}" in pb["html"] and "@" not in pb["html"]


def test_sem_peca_aprovada_explica_o_que_falta():
    with pytest.raises(ValueError, match="aprove ao menos uma"):
        gerar_guia(FakeLLMClient(), None, [peca("x", status="revisar")], date(2026, 11, 25), [])


def test_clareza_baixa_vira_pendencia_mas_afirmacao_proibida_tira_a_secao():
    from src.evaluation.thresholds import load_thresholds
    from src.guia import aprofundar
    lim = load_thresholds(fx.ROOT / "config" / "limiares.yaml")
    longo = {**BOM, "por_que_importa": "Organizacionalmente, empreendedores responsabilizam-se administrativamente "
                                       "pela contabilização sistemática e periodicamente documentada das movimentações."}
    sec, pend = aprofundar(FakeLLMClient({"guia": [longo]}), peca("a"), {}, lim, tentativas=2)
    assert sec and pend and pend[0].startswith("clareza=")
    proibido = {**longo, "como_o_impulso_ajuda": "O Impulso Stone oferece maquininha com taxa zero."}
    sec2, falhas = aprofundar(FakeLLMClient({"guia": [proibido]}), peca("b"), {}, lim, tentativas=2)
    assert sec2 is None and any("não oferece" in f or "retire" in f for f in falhas)
