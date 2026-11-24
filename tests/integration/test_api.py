"""API sobre a base real (sem LLM): início, exemplos, post, proposta, agenda, criadores e o ciclo de uma peça.

O ciclo de peça usa um LLM falso injetado só para não gastar a cota nos testes automáticos; a geração real é
testada à parte (scripts e app). Pulado se a base processada não existir.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "data" / "processed" / "scores.csv").exists():
    pytest.skip("base processada ausente", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

import src.api as api  # noqa: E402
from src.agent import servico  # noqa: E402
from src.app_store import Store  # noqa: E402


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "store", lambda: Store(tmp_path / "teste.sqlite"))
    return TestClient(api.app)


def test_panorama_tem_kpis_e_achados_em_frase(cliente):
    r = cliente.get("/api/panorama").json()
    assert r["kpis"]["posts"] > 1000 and r["achados"]
    assert all("posts que mais engajam" in a["frase"] for a in r["achados"])


def test_exemplos_e_post(cliente):
    achado = cliente.get("/api/panorama").json()["achados"][0]
    ex = cliente.get("/api/exemplos", params={k: achado[k] for k in ("plataforma", "caracteristica", "valor")}).json()
    assert ex
    detalhe = cliente.get(f"/api/posts/{ex[0]['post_id']}").json()
    assert detalhe["grupo"] == "top" and detalhe["post_id"] == ex[0]["post_id"]


def test_proposta_nao_chama_o_llm(cliente, monkeypatch):
    monkeypatch.setattr("src.shared.llm_client.LLMClient.generate", lambda *a, **k: pytest.fail("proposta chamou o LLM"))
    r = cliente.post("/api/proposta", json={"objetivo": "atrair donos de mercadinho", "segmento": "comercio_bairro"}).json()
    assert r["formato"] and r["referencias"] is not None


def test_agenda_e_criadores(cliente):
    ag = cliente.get("/api/agenda", params={"inicio": "2026-11-23"}).json()
    assert ag["inicio"] == "2026-11-23" and ag["sugestoes"]
    cr = cliente.get("/api/criadores").json()
    assert cr["criadores"] and "transversais" in cr["indicados"]
    um = cr["criadores"][0]
    detalhe = cliente.get(f"/api/criadores/{um['plataforma']}/{um['perfil']}").json()
    assert detalhe["melhores_posts"]


def test_ciclo_da_peca_criar_ajustar_aprovar(cliente, monkeypatch):
    from tests.fakes.llm import FakeLLMClient
    from tests.unit.test_agente import criativo as criativo_falso
    refs = servico.proposta(api.base(), "x", None, "reels")["referencias"]
    resposta = criativo_falso(reference_post_ids=[refs[0]["post_id"]])
    juiz = {"criterios": [{"nome": n, "nota": 8, "justificativa": "ok", "evidencias": ["t"]} for n in
                          ["aderencia_aos_padroes", "proximo_passo_claro", "tom_impulso", "clareza_para_o_publico",
                           "fidelidade_a_oferta", "concretude", "profundidade"]]}
    fake = FakeLLMClient({"criativo": [resposta], "judge": [juiz]})
    monkeypatch.setattr(servico, "LLMClient", lambda: fake)
    monkeypatch.setattr("src.shared.llm_client.LLMClient", lambda *a, **k: fake)
    peca = cliente.post("/api/pecas", json={"objetivo": "x", "formato": "reels", "data_agenda": "2026-11-24"}).json()
    assert peca["status"] == "revisar" and peca["atual"]["criativo"]["cta"]
    ajustada = cliente.post(f"/api/pecas/{peca['id']}/ajuste", json={"motivo": "gancho mais concreto"}).json()
    assert ajustada["status"] == "revisar" and any(h.get("acao") == "pedir_ajuste" for h in ajustada["historico"])
    aprovada = cliente.post(f"/api/pecas/{peca['id']}/aprovar").json()
    assert aprovada["status"] == "aprovada"
    assert len(cliente.get("/api/pecas").json()) == 1


def test_cota_esgotada_vira_mensagem_clara(cliente, monkeypatch):
    def estoura(*a, **k):
        raise RuntimeError('Groq request failed (429): {"error":{"message":"Rate limit reached ... Please try again in 2m7.872s."}}')
    monkeypatch.setattr(servico, "criar_peca", estoura)
    r = cliente.post("/api/pecas", json={"objetivo": "x", "formato": "reels"})
    assert r.status_code == 503 and "cota diária" in r.json()["detail"] and "2 min 7s" in r.json()["detail"]


def test_criacao_ao_vivo_transmite_as_etapas_e_termina_com_a_peca(cliente, monkeypatch):
    import json as _json

    from tests.fakes.llm import FakeLLMClient
    from tests.unit.test_agente import criativo as criativo_falso
    refs = servico.proposta(api.base(), "x", None, "reels")["referencias"]
    juiz = {"criterios": [{"nome": n, "nota": 8, "justificativa": "ok", "evidencias": ["t"]} for n in
                          ["aderencia_aos_padroes", "proximo_passo_claro", "tom_impulso", "clareza_para_o_publico",
                           "fidelidade_a_oferta", "concretude", "profundidade"]]}
    fake = FakeLLMClient({"criativo": [criativo_falso(reference_post_ids=[refs[0]["post_id"]])], "judge": [juiz]})
    monkeypatch.setattr("src.shared.llm_client.LLMClient", lambda *a, **k: fake)
    r = cliente.post("/api/pecas/ao-vivo", json={"objetivo": "x", "formato": "reels"})
    assert r.headers["content-type"].startswith("text/event-stream")
    eventos = [(b.split("\n")[0][7:], _json.loads(b.split("\n")[1][6:])) for b in r.text.strip().split("\n\n")]
    tipos = [t for t, _ in eventos]
    assert tipos[0] == "dados" and "escrevendo" in tipos and "rascunho" in tipos and "conferencias" in tipos
    assert tipos[-1] == "pronto" and eventos[-1][1]["peca"]["status"] == "revisar"


def test_senha_protege_so_as_acoes(cliente, monkeypatch):
    monkeypatch.setenv("BOAPAUTA_TOKEN", "s3gredo")
    assert cliente.get("/api/acesso").json() == {"protegido": True}
    assert cliente.get("/api/pecas").status_code == 200                                # leitura continua aberta
    assert cliente.post("/api/pecas/x/aprovar").status_code == 401
    assert cliente.post("/api/pecas/x/aprovar", headers={"X-BoaPauta-Token": "errada"}).status_code == 401
    r = cliente.post("/api/pecas/x/aprovar", headers={"X-BoaPauta-Token": "s3gredo"})
    assert r.status_code != 401


def test_limite_de_geracoes_por_minuto(cliente, monkeypatch):
    monkeypatch.delenv("BOAPAUTA_TOKEN", raising=False)
    monkeypatch.setenv("BOAPAUTA_GERACOES_POR_MINUTO", "2")
    monkeypatch.setattr(api, "_geracoes", [])
    corpo = {"motivo": ""}                                    # 422 sem gastar cota: só conta a tentativa
    assert cliente.post("/api/pecas/x/ajuste", json=corpo).status_code == 422
    assert cliente.post("/api/pecas/x/ajuste", json=corpo).status_code == 422
    r = cliente.post("/api/pecas/x/ajuste", json=corpo)
    assert r.status_code == 429 and "por minuto" in r.json()["detail"]


def test_quem_aprovou_vai_para_o_historico(cliente, monkeypatch):
    monkeypatch.delenv("BOAPAUTA_TOKEN", raising=False)
    loja = api.store()
    monkeypatch.setattr(api, "store", lambda: loja)
    peca = loja.criar("reels", "teste", {"criativo": {"titulo": "t"}})
    r = cliente.post(f"/api/pecas/{peca['id']}/aprovar", headers={"X-BoaPauta-Quem": "J%C3%BAlia"}).json()
    assert r["status"] == "aprovada" and r["historico"][-1]["quem"] == "Júlia"


def test_metricas_do_agente(cliente, tmp_path, monkeypatch):
    import json
    runs = tmp_path / "runs.jsonl"
    runs.write_text("\n".join(json.dumps(x) for x in [
        {"momento": "2026-11-24T10:00", "criativos": 1, "tentativas": [1], "latencia_s": 40, "juiz": [{"nota": 8.0, "melhoria": None}], "chamadas_llm": 2},
        {"momento": "2026-11-24T11:00", "criativos": 1, "tentativas": [2], "latencia_s": 60, "juiz": [{"nota": 9.0, "melhoria": None}], "chamadas_llm": 3},
    ]), encoding="utf-8")
    monkeypatch.setenv("BOAPAUTA_RUNS", str(runs))
    m = cliente.get("/api/agente/metricas").json()
    assert m["execucoes"] == 2 and m["latencia_mediana_s"] == 50 and m["primeira_tentativa_pct"] == 0.5
    assert m["nota_media_juiz"] == 8.5 and m["juiz"]["criativos_avaliados"] == 2
