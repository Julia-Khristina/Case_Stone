"""Baixa a capa de cada post do top e do grupo de comparação, para o app mostrar junto dos exemplos e referências.

YouTube: miniatura oficial do vídeo. Instagram: capa do Reels (thumbnail_url) ou a própria imagem (media_url), links
devolvidos pela Graph API. Os links do Instagram expiram em poucos dias; por isso a capa é guardada em data/capas/
(fora do git). Quando o link já expirou, o post fica sem capa e o app mostra só o texto.

Uso: python scripts/baixar_capas.py [--coleta data/raw/2026-11-22]
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collection.storage import read_jsonl  # noqa: E402

DESTINO = ROOT / "data" / "capas"


def baixar(item: tuple[str, str]) -> tuple[str, bool, str]:
    post_id, url = item
    arquivo = DESTINO / f"{post_id}.jpg"
    if arquivo.exists():
        return post_id, True, "já existia"
    try:
        r = requests.get(url, timeout=30)
    except requests.RequestException as exc:
        return post_id, False, type(exc).__name__
    if r.status_code != 200 or not r.headers.get("Content-Type", "").startswith("image"):
        return post_id, False, f"HTTP {r.status_code}"
    arquivo.write_bytes(r.content)
    return post_id, True, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description="Capas dos posts de referência")
    parser.add_argument("--coleta", default=str(max((p for p in (ROOT / "data" / "raw").iterdir() if p.is_dir() and p.name[:4].isdigit()),
                                                    key=lambda p: p.name)))
    args = parser.parse_args()
    DESTINO.mkdir(parents=True, exist_ok=True)
    scores = pd.read_csv(ROOT / "data" / "processed" / "scores.csv", dtype={"post_id": str})
    alvo = set(scores.loc[scores["grupo"].isin(["top", "controle"]), "post_id"])
    itens = []
    from src.collection.storage import posts_com_midia_renovada
    for p in posts_com_midia_renovada(args.coleta):                 # links do Instagram renovados, quando houver
        pid = str(p["post_id"])
        if pid not in alvo:
            continue
        url = p.get("thumbnail_url") or (p.get("media_url") if p.get("tipo") in ("imagem", "carrossel") else None)
        if url:
            itens.append((pid, url))
    with ThreadPoolExecutor(max_workers=8) as pool:
        resultado = list(pool.map(baixar, itens))
    ok = sum(1 for _, certo, _ in resultado if certo)
    falhas = [(pid, motivo) for pid, certo, motivo in resultado if not certo]
    print(f"{ok} capas em data/capas/ · {len(falhas)} sem capa · {len(alvo) - len(itens)} posts sem link de capa")
    for pid, motivo in falhas[:10]:
        print(f"  sem capa: {pid} ({motivo})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
