"""Roda antes da API no container: baixa o pacote de dados quando a base não está no disco.

Variável BOAPAUTA_DADOS_URL: link público do zip gerado por scripts/pacote_dados.py. Sem a variável, ou com a base
já presente (ex.: volume montado no docker compose), não faz nada. Só extrai arquivos dentro de data/; qualquer
caminho absoluto ou com ".." no zip é recusado.
"""
from __future__ import annotations

import io
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def extrair_seguro(dados: bytes, raiz: Path) -> int:
    n = 0
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        for info in z.infolist():
            nome = info.filename.replace("\\", "/")
            destino = (raiz / nome).resolve()
            if info.is_dir():
                continue
            if not nome.startswith("data/") or ".." in nome.split("/") or raiz.resolve() not in destino.parents:
                print(f"  recusado: {nome}")
                continue
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(z.read(info))
            n += 1
    return n


def main() -> int:
    url = os.getenv("BOAPAUTA_DADOS_URL", "").strip()
    if (ROOT / "data" / "processed" / "scores.csv").exists():
        print("Base de dados já presente.")
        return 0
    if not url:
        print("Sem base de dados e sem BOAPAUTA_DADOS_URL: o app sobe, mas mostra o aviso de base ausente.")
        return 0
    print("Baixando o pacote de dados…", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "BoaPauta-deploy/1.0"})
    dados = urllib.request.urlopen(req, timeout=180).read()
    n = extrair_seguro(dados, ROOT)
    print(f"{n} arquivos extraídos em data/.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - falha no download não impede a API de subir (com o aviso)
        print(f"Não deu para baixar o pacote de dados: {exc}")
        sys.exit(0)
