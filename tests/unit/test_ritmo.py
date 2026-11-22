"""Limitador de chamadas por hora e retomada da coleta."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from src.collection.http import get_json
from src.collection.ritmo import LimitadorChamadas, LimiteLocalAtingido
from src.shared.cache import VersionedCache


class Relogio:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.t += s


def test_limitador_para_ao_encher_a_janela_e_libera_depois_de_uma_hora():
    rel = Relogio()
    lim = LimitadorChamadas(3, relogio=rel, dormir=rel.dormir)
    for _ in range(3):
        lim.antes_da_chamada()
        rel.t += 60
    with pytest.raises(LimiteLocalAtingido) as exc:
        lim.antes_da_chamada()
    assert 3300 < exc.value.segundos_para_liberar <= 3601
    rel.t = 3600.5                       # a primeira chamada saiu da janela
    lim.antes_da_chamada()
    assert lim.usadas == 3


def test_limitador_com_esperar_dorme_e_continua():
    rel = Relogio()
    avisos = []
    lim = LimitadorChamadas(2, esperar=True, relogio=rel, dormir=rel.dormir, avisar=avisos.append)
    for _ in range(3):
        lim.antes_da_chamada()
    assert rel.t >= 3600 and avisos and "esperando" in avisos[0]


def test_respostas_do_cache_nao_gastam_limite(tmp_path):
    chamadas = []

    class Resposta:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": 1}'

    cache = VersionedCache(tmp_path)
    for _ in range(3):
        get_json("https://x", {"a": 1}, cache=cache, opener=lambda r, timeout: Resposta(),
                 antes_da_rede=lambda: chamadas.append(1))
    assert len(chamadas) == 1


def test_coleta_retoma_pulando_perfis_ja_gravados(tmp_path):
    caminho = Path(__file__).resolve().parents[2] / "scripts" / "coletar.py"
    spec = importlib.util.spec_from_file_location("coletar", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    (tmp_path / "perfis.jsonl").write_text(
        json.dumps({"plataforma": "instagram", "username": "ChefRut", "perfil_id": "1784"}) + "\n" +
        json.dumps({"plataforma": "youtube", "username": "canal", "perfil_id": "UCabc"}) + "\n", encoding="utf-8")
    feitos = modulo.ja_coletados(tmp_path)
    assert ("instagram", "chefrut") in feitos and ("youtube", "UCabc") in feitos
    assert modulo.ja_coletados(tmp_path / "nao_existe") == set()
