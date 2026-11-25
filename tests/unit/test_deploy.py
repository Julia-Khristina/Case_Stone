"""Deploy: o pacote de dados é extraído só dentro de data/, e a API avisa quando a base não existe."""
from __future__ import annotations

import io
import zipfile

from scripts.preparar_deploy import extrair_seguro


def _zip(arquivos: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
    return buf.getvalue()


def test_extrai_so_dentro_de_data(tmp_path):
    n = extrair_seguro(_zip({"data/processed/scores.csv": b"a,b", "data/../fora.txt": b"x", "src/api.py": b"x",
                             "/etc/passwd": b"x"}), tmp_path)
    assert n == 1 and (tmp_path / "data" / "processed" / "scores.csv").read_bytes() == b"a,b"
    assert not (tmp_path / "fora.txt").exists() and not (tmp_path / "src").exists()


def test_api_avisa_base_ausente(tmp_path, monkeypatch):
    import pytest
    from fastapi import HTTPException
    import src.api as api
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.delenv("BOAPAUTA_COLETA", raising=False)
    with pytest.raises(HTTPException) as erro:
        api.base()
    assert erro.value.status_code == 503 and "BOAPAUTA_DADOS_URL" in erro.value.detail
