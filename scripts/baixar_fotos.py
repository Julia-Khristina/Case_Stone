"""Baixa a foto de perfil de cada criador no radar, pelas APIs oficiais, para o app mostrar rostos reais.

Instagram: campo profile_picture_url do Business Discovery (Graph API). YouTube: miniatura do canal (Data API v3,
1 unidade a cada 50 canais). Os links do Instagram expiram; por isso a imagem é guardada em data/fotos/
(fora do git) e servida pela API do app. Perfis sem foto continuam com a inicial.

Uso: python scripts/baixar_fotos.py [--coleta data/raw/2026-11-22]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src.collection.storage import read_jsonl  # noqa: E402

DESTINO = ROOT / "data" / "fotos"


def salvar(url: str, arquivo: Path) -> bool:
    r = requests.get(url, timeout=30)
    if r.status_code != 200 or not r.headers.get("Content-Type", "").startswith("image"):
        return False
    arquivo.write_bytes(r.content)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Fotos de perfil dos criadores (APIs oficiais)")
    parser.add_argument("--coleta", default=str(max((p for p in (ROOT / "data" / "raw").iterdir() if p.is_dir() and p.name[:4].isdigit()),
                                                    key=lambda p: p.name)))
    args = parser.parse_args()
    DESTINO.mkdir(parents=True, exist_ok=True)
    perfis = read_jsonl(Path(args.coleta) / "perfis.jsonl")
    ok = falhas = 0

    versao = os.getenv("META_GRAPH_VERSION") or "v27.0"
    token, ig_user = os.getenv("META_ACCESS_TOKEN"), os.getenv("META_IG_USER_ID")
    for p in [p for p in perfis if p["plataforma"] == "instagram"]:
        arquivo = DESTINO / f"instagram_{p['username'].lower()}.jpg"
        if arquivo.exists():
            ok += 1
            continue
        r = requests.get(f"https://graph.facebook.com/{versao}/{ig_user}",
                         params={"fields": f"business_discovery.username({p['username']}){{profile_picture_url}}",
                                 "access_token": token}, timeout=30)
        url = (r.json().get("business_discovery") or {}).get("profile_picture_url") if r.ok else None
        if url and salvar(url, arquivo):
            ok += 1
        else:
            falhas += 1
            print(f"  sem foto: instagram/{p['username']} ({r.status_code})")
        time.sleep(0.5)

    yt = [p for p in perfis if p["plataforma"] == "youtube"]
    for i in range(0, len(yt), 50):
        lote = yt[i:i + 50]
        r = requests.get("https://www.googleapis.com/youtube/v3/channels",
                         params={"part": "snippet", "id": ",".join(p["perfil_id"] for p in lote),
                                 "key": os.getenv("YOUTUBE_API_KEY")}, timeout=30)
        itens = {it["id"]: it for it in r.json().get("items", [])} if r.ok else {}
        for p in lote:
            arquivo = DESTINO / f"youtube_{p['perfil_id']}.jpg"
            if arquivo.exists():
                ok += 1
                continue
            thumbs = (itens.get(p["perfil_id"]) or {}).get("snippet", {}).get("thumbnails", {})
            url = (thumbs.get("medium") or thumbs.get("default") or {}).get("url")
            if url and salvar(url, arquivo):
                ok += 1
            else:
                falhas += 1
                print(f"  sem foto: youtube/{p['perfil_id']}")
    print(f"{ok} fotos em data/fotos/, {falhas} sem foto")
    return 0


if __name__ == "__main__":
    sys.exit(main())
