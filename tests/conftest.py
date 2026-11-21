"""Configuração comum dos testes: execuções do agente vão para um registro temporário, nunca para o real."""
import pytest


@pytest.fixture(autouse=True)
def registro_temporario(tmp_path, monkeypatch):
    monkeypatch.setenv("BOAPAUTA_RUNS", str(tmp_path / "agent_runs.jsonl"))
