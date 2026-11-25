"""Pacote com os dados que o app usa, para o deploy (Render, Docker em outra máquina).

    python scripts/pacote_dados.py              → dist/boapauta_dados.zip

Os dados ficam fora do git (dados de terceiros e banco local). O deploy baixa este pacote ao iniciar
(scripts/preparar_deploy.py, variável BOAPAUTA_DADOS_URL). Leva só o que o app lê: a coleta mais recente (posts e
perfis), a base processada (scores, rótulos, escopo, radar), os dados das contas da Stone, as fotos dos criadores,
as capas dos posts que o app mostra (reduzidas) e o banco com as peças. NÃO leva config/stone_interno.yaml
(persona e CTR internos da Stone): sem ele, o app funciona sem esses dados.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DESTINO = ROOT / "dist" / "boapauta_dados.zip"
PROCESSADOS = ["scores.csv", "resumo.json", "rotulos_texto.jsonl", "rotulos_visuais.jsonl", "rotulos_escopo.jsonl",
               "radar.json", "relatorio_escopo.json", "agent_runs.jsonl", "kappa.json", "calibracao_juiz.json"]


def _jpeg_reduzido(caminho: Path, largura: int = 480) -> bytes:
    from PIL import Image
    im = Image.open(caminho).convert("RGB")
    im.thumbnail((largura, int(largura * 1.8)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=72, optimize=True)
    return buf.getvalue()


def ultima(pasta: Path) -> Path:
    return max((p for p in pasta.iterdir() if p.is_dir() and p.name[:4].isdigit()), key=lambda p: p.name)


def main() -> int:
    coleta = ultima(ROOT / "data" / "raw")
    proc = ROOT / "data" / "processed"
    scores = pd.read_csv(proc / "scores.csv", dtype={"post_id": str}, low_memory=False)
    mostrados = set(scores.loc[scores["grupo"].isin(["top", "controle"]), "post_id"])
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(DESTINO, "w", zipfile.ZIP_DEFLATED) as z:
        def add(arq: Path):
            nonlocal n
            if arq.exists():
                z.write(arq, arq.relative_to(ROOT).as_posix())
                n += 1
        for nome in ("posts.jsonl", "perfis.jsonl", "midia_renovada.jsonl"):
            add(coleta / nome)
        for nome in PROCESSADOS:
            add(proc / nome)
        for arq in sorted((proc / "contas_stone").glob("*")):
            add(arq)
        contas_raw = ROOT / "data" / "contas_stone" / "raw"
        if contas_raw.exists():
            ult = ultima(contas_raw) if any(p.name[:4].isdigit() for p in contas_raw.iterdir()) else None
            for nome in ("posts.jsonl", "perfis.jsonl"):
                if ult:
                    add(ult / nome)
        for arq in sorted((ROOT / "data" / "fotos").glob("*.jpg")):
            add(arq)
        add(ROOT / "data" / "app" / "boapauta.sqlite")
        capas = [c for c in (ROOT / "data" / "capas").glob("*.jpg") if c.stem in mostrados]
        capas += list((ROOT / "data" / "contas_stone" / "capas").glob("*.jpg"))
        for c in capas:
            try:
                z.writestr(c.relative_to(ROOT).as_posix(), _jpeg_reduzido(c))
                n += 1
            except Exception:  # noqa: BLE001 - imagem corrompida não derruba o pacote
                continue
    print(f"{n} arquivos · {DESTINO.stat().st_size / 1e6:.1f} MB → {DESTINO}")
    print("Suba o arquivo num link público (ex.: anexo de uma Release do GitHub) e defina BOAPAUTA_DADOS_URL no Render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
