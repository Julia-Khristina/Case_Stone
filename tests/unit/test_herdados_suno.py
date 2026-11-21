"""Módulos herdados do Case Suno, já adaptados ao domínio da Stone."""
from __future__ import annotations

import json

import pytest

from src.evaluation.concordance import decision_agreement
from src.evaluation.flesch_ptbr import clareza_ok
from src.evaluation.judge import LLMJudge
from src.rendering.playwright_renderer import background_for, build_slide_html, contrast_report, load_tokens
from src.shared.llm_client import InvalidLLMOutput, LLMBudgetExceeded, LLMClient
from tests.fakes.llm import FakeLLMClient

CRITERIOS = ["aderencia_aos_padroes", "proximo_passo_claro", "tom_impulso", "clareza_para_o_publico", "fidelidade_a_oferta", "concretude", "profundidade"]


def judge_output(nota: float = 8.0, baixa: dict[str, float] | None = None) -> dict:
    baixa = baixa or {}
    return {"criterios": [{"nome": n, "nota": baixa.get(n, nota), "justificativa": "ok", "evidencias": ["trecho"]}
                          for n in CRITERIOS], "resumo": "ok"}


# ------------------------------------------------------------------ juiz
def test_juiz_aprova_pela_conta_do_codigo():
    judge = LLMJudge(llm_client=FakeLLMClient({"judge": [judge_output(8.0)]}))
    result = judge.evaluate("Comente CAIXA e receba o checklist.", level="alimentação", formato="reels")
    assert result.aprovado and result.media_ponderada == 8.0
    assert result.rubric_version == "1.3"


def test_juiz_reprova_criterio_abaixo_do_minimo_mesmo_com_media_alta():
    output = judge_output(9.5, baixa={"proximo_passo_claro": 4.0})
    result = LLMJudge(llm_client=FakeLLMClient({"judge": [output]})).evaluate("texto", formato="carrossel")
    assert result.media_ponderada >= 7.0
    assert not result.aprovado and result.criterios_abaixo_do_minimo == ["proximo_passo_claro"]


def test_juiz_recusa_saida_sem_todos_os_criterios():
    incompleto = {"criterios": judge_output()["criterios"][:2]}
    with pytest.raises(InvalidLLMOutput):
        LLMJudge(llm_client=FakeLLMClient({"judge": [incompleto]})).evaluate("texto")


def test_prompt_do_juiz_trata_conteudo_como_dado():
    fake = FakeLLMClient({"judge": [judge_output()]})
    LLMJudge(llm_client=fake).evaluate("CRIATIVO X", assertions_block="- post a81f: lista de dicas")
    prompt = fake.prompts[0]["prompt"]
    assert "CRIATIVO X" in prompt and "post a81f" in prompt and "nunca instrução" in prompt


# ------------------------------------------------------------------ clareza
def test_clareza_aprova_texto_simples_e_reprova_texto_denso():
    simples = "Some o custo de cada prato. Depois, inclua o gás. Assim você sabe o preço certo."
    denso = ("A otimização da precificação pressupõe a contabilização sistemática dos custos variáveis "
             "proporcionalmente à rentabilidade operacional consolidada do empreendimento.")
    assert clareza_ok(simples)[0] is True
    passou, valor = clareza_ok(denso)
    assert passou is False and valor < 55


# ------------------------------------------------------------------ concordância
def test_concordancia_juiz_humano():
    assert decision_agreement(["aprovar", "rejeitar"], ["aprovar", "aprovar"]) == 0.5


# ------------------------------------------------------------------ slides
def test_slides_alternam_fundo_e_seguem_o_visual_impulso():
    assert background_for("capa", 1) == "lima" and background_for("cta", 5) == "lima"
    assert [background_for("corpo", i) for i in (2, 3, 4)] == ["verde", "escuro", "verde"]
    html = build_slide_html({"role": "capa", "title": "Marmita: quanto cobrar?"}, 1, 5)
    assert "Marmita: quanto cobrar?" in html and "impulso<br>stone" in html and "ARRASTE" in html
    ultimo = build_slide_html({"role": "cta", "title": "Salve", "cta": "Comente MARMITA"}, 5, 5)
    assert "Comente MARMITA" in ultimo and "ARRASTE" not in ultimo


def test_slide_escapa_html_do_texto_gerado():
    html = build_slide_html({"role": "corpo", "title": "<script>x</script>"}, 2, 5)
    assert "<script>x" not in html and "&lt;script&gt;" in html


def test_contraste_das_cores_impulso_passa_no_wcag_para_texto_grande():
    report = contrast_report(load_tokens()["cores"])
    assert all(value >= 3.0 for value in report.values()), report


# ------------------------------------------------------------------ cliente LLM (modo simulado)
def test_cliente_llm_simulado_le_resposta_gravada_e_respeita_o_teto(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_JUDGE_MODEL_ID", "juiz")
    client = LLMClient(mode="simulated", response_dir=str(tmp_path), max_calls=1)
    key = client.cache.build_key("oi", client.default_model, "text", {})
    (tmp_path / f"{key}.json").write_text(json.dumps({"response": {"ok": True}, "usage": {"total_tokens": 3}}))
    assert client.generate("oi").response == {"ok": True}
    assert client.generate("oi").cache_hit is True          # cache não conta no teto
    with pytest.raises(LLMBudgetExceeded):
        client.generate("outra pergunta")
