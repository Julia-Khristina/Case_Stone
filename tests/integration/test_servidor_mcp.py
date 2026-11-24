"""O servidor MCP de verdade, pelo protocolo MCP (cliente FastMCP em memória), sobre a base real.

Pulado se a base processada ainda não existir. Não chama o LLM: usa os modos e ferramentas determinísticos.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp")
ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "data" / "processed" / "scores.csv").exists():
    pytest.skip("base processada ausente: rode a coleta e scripts/calcular_metricas.py", allow_module_level=True)

from src.servidor_mcp import mcp  # noqa: E402


def chamar(ferramenta: str, argumentos: dict):
    async def _rodar():
        async with fastmcp.Client(mcp) as cliente:
            nomes = {t.name for t in await cliente.list_tools()}
            resposta = await cliente.call_tool(ferramenta, argumentos)
            return nomes, resposta
    return asyncio.run(_rodar())


def _dados(resposta):
    if getattr(resposta, "data", None) is not None:
        return resposta.data
    return json.loads(resposta.content[0].text)


def test_servidor_lista_as_ferramentas_e_analisa_pela_base_real():
    nomes, resposta = chamar("run_agent", {"mode": "analisar", "query": "o que engaja?", "plataforma": "instagram"})
    assert {"run_agent", "padroes", "posts_de_referencia"} <= nomes
    saida = _dados(resposta)
    assert saida["explanation"] and saida["reference_posts"]
    assert all(r["plataforma"] == "instagram" for r in saida["reference_posts"])


def test_padroes_confiaveis_pelo_mcp():
    _, resposta = chamar("padroes", {"plataforma": "instagram"})
    achados = _dados(resposta)
    assert achados and all(a["leitura"] in ("mais no top", "menos no top") for a in achados)


def test_pecas_aprovadas_para_levar_ao_canva(tmp_path, monkeypatch):
    from src.app_store import Store
    loja = Store(tmp_path / "mcp.sqlite")
    criativo = {"titulo": "Caixa em dia", "caso": "Salão", "gancho": "Seu caixa fecha?", "corpo": ["Anote tudo", "Separe as contas"],
                "texto_tela": ["Anote", "Separe"], "legenda": "Legenda", "cta": "Comente CAIXA"}
    p1 = loja.criar("reels", "caixa", {"criativo": criativo, "conta": "stone", "juiz": {"media_ponderada": 8.2}})
    loja.registrar(p1["id"], "aprovada", {"acao": "aprovar", "quem": "Júlia"})
    loja.criar("reels", "rascunho", {"criativo": criativo})                    # não aprovada: fica de fora
    monkeypatch.setenv("BOAPAUTA_DB", str(tmp_path / "mcp.sqlite"))
    nomes, resposta = chamar("pecas_aprovadas", {"com_slides": False})
    pecas = _dados(resposta)
    assert "pecas_aprovadas" in nomes and len(pecas) == 1
    p = pecas[0]
    assert p["conta"] == "stone" and p["aprovado_por"] == "Júlia" and p["nota_avaliador"] == 8.2
    assert p["partes"][0] == {"n": 1, "texto": "Anote tudo", "texto_tela": "Anote"}
    assert _dados(chamar("pecas_aprovadas", {"conta": "impulsostone", "com_slides": False})[1]) == []
