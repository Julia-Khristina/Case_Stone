"""Teste rápido da Graph API: confere, campo a campo, o que o Business Discovery devolve hoje.

Uso:
    python scripts/teste_graph_api.py                 # usa os perfis de config/perfis.csv
    python scripts/teste_graph_api.py chefrut oijedai # perfis escolhidos

Precisa de META_IG_USER_ID e META_ACCESS_TOKEN no .env. Pede só 5 posts por perfil (gasta pouco limite).
Grava o relatório em data/raw/teste_graph_api.json, sem o token.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src.collection.http import HttpError  # noqa: E402
from src.collection.instagram_graph import MEDIA_FIELDS, InstagramGraphCollector  # noqa: E402

EXPECTED = MEDIA_FIELDS.split(",")


def perfis_do_csv() -> list[str]:
    with (ROOT / "config" / "perfis.csv").open(encoding="utf-8") as file:
        return [row["perfil"] for row in csv.DictReader(file) if row["plataforma"] == "instagram"]


def main(usernames: list[str]) -> int:
    collector = InstagramGraphCollector()
    report = {"versao_api": collector.version, "perfis": {}}
    falhas = 0
    for username in usernames:
        try:
            page = collector.discovery_page(username, limit=5)
        except HttpError as exc:
            falhas += 1
            report["perfis"][username] = {"erro": str(exc)}
            print(f"✗ @{username}: {exc}")
            continue
        media = (page.get("media") or {}).get("data") or []
        presentes = Counter(field for item in media for field in EXPECTED if item.get(field) is not None)
        report["perfis"][username] = {
            "seguidores": page.get("followers_count"),
            "total_posts": page.get("media_count"),
            "posts_recebidos": len(media),
            "campos": {field: f"{presentes[field]}/{len(media)}" for field in EXPECTED},
        }
        faltando = [f for f in EXPECTED if presentes[f] == 0]
        print(f"✓ @{username}: {page.get('followers_count')} seguidores, {len(media)} posts"
              + (f" · campos ausentes: {', '.join(faltando)}" if faltando else " · todos os campos vieram"))
    out = ROOT / "data" / "raw" / "teste_graph_api.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRelatório: {out}")
    print("Ausência de like_count em alguns posts é esperada (curtidas ocultas). "
          "Ausência de media_url em todos indica limitação da API para terceiros.")
    return 1 if falhas == len(usernames) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or perfis_do_csv()))
