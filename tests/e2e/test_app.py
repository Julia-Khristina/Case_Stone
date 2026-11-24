"""Testes de ponta a ponta do app no navegador (Playwright): o app compilado servido pela API de verdade.

Sobe a API numa porta livre com um banco temporário (nunca o banco real), abre as telas e confere o que a pessoa vê.
Pulado sem o app compilado (cd app && npm run build), sem o Playwright ou sem a base processada.
Não chama modelo de linguagem: só leitura, busca e navegação.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app" / "dist" / "index.html").exists():
    pytest.skip("app não compilado (cd app && npm run build)", allow_module_level=True)
if not (ROOT / "data" / "processed" / "scores.csv").exists():
    pytest.skip("base processada ausente", allow_module_level=True)
sync_api = pytest.importorskip("playwright.sync_api")


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def url(tmp_path_factory):
    porta = _porta_livre()
    env = {**os.environ, "BOAPAUTA_DB": str(tmp_path_factory.mktemp("e2e") / "app.sqlite"), "PYTHONIOENCODING": "utf-8",
           "BOAPAUTA_TOKEN": "", "BOAPAUTA_RUNS": str(tmp_path_factory.mktemp("runs") / "runs.jsonl")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "src.api:app", "--port", str(porta)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{porta}"
    for _ in range(120):
        try:
            urllib.request.urlopen(base + "/api/segmentos", timeout=2)
            break
        except Exception:  # noqa: BLE001 - ainda subindo
            time.sleep(0.5)
    else:
        proc.kill()
        pytest.fail("a API não subiu")
    yield base
    proc.kill()


@pytest.fixture(scope="module")
def pagina(url):
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch()
        pg = navegador.new_page(viewport={"width": 1366, "height": 900})
        erros: list[str] = []
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.erros = erros
        yield pg
        navegador.close()


def test_planejamento_mostra_a_agenda_e_a_busca_conta_resultados(pagina, url):
    pagina.goto(url + "/#/planejamento")
    pagina.wait_for_selector(".chip-cal.sug", timeout=60000)
    total = pagina.locator(".chip-cal").count()
    assert total > 5
    pagina.fill(".busca input", "xyzabc-nada")
    assert "Nada com" in pagina.locator(".cal-achados").inner_text()
    assert pagina.locator(".chip-cal:not(.apagado)").count() == 0
    pagina.fill(".busca input", "reels")
    pagina.wait_for_timeout(300)
    visiveis = pagina.locator(".chip-cal:not(.apagado)").count()
    assert 0 < visiveis <= total and str(visiveis) in pagina.locator(".cal-achados").inner_text()
    pagina.click(".busca-limpar")
    assert pagina.locator(".cal-achados").count() == 0


def test_busca_entende_sinonimos(pagina, url):
    pagina.goto(url + "/#/planejamento")
    pagina.wait_for_selector(".chip-cal.sug", timeout=60000)
    pagina.fill(".busca input", "13º")
    pagina.wait_for_timeout(300)
    com_simbolo = pagina.locator(".chip-cal:not(.apagado)").count()
    pagina.fill(".busca input", "decimo terceiro")
    pagina.wait_for_timeout(300)
    assert pagina.locator(".chip-cal:not(.apagado)").count() == com_simbolo


def test_sugestao_abre_o_painel(pagina, url):
    pagina.goto(url + "/#/planejamento")
    pagina.wait_for_selector(".chip-cal.sug", timeout=60000)
    pagina.locator(".chip-cal.sug").first.click()
    pagina.wait_for_selector(".painel", timeout=10000)


def test_pecas_insights_e_configuracoes_carregam(pagina, url):
    pagina.goto(url + "/#/pecas")
    pagina.wait_for_selector(".quadro-vazio, .cartao-peca", timeout=30000)
    pagina.goto(url + "/#/insights")
    pagina.wait_for_load_state("networkidle")
    pagina.goto(url + "/#/configuracoes")
    pagina.wait_for_selector("text=Desempenho do agente", timeout=30000)
    assert pagina.locator("text=Senha de acesso").count() == 0              # servidor sem senha não pede senha


def test_nenhum_erro_de_javascript(pagina):
    assert pagina.erros == []
