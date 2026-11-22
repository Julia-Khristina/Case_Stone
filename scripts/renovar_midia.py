"""Renova os links de mídia do Instagram (media_url e thumbnail_url) dos posts do top e do controle.

    python scripts/renovar_midia.py [--coleta data/raw/<data>]

Os links da Graph API expiram em poucos dias. Esta "passada 2" consulta de novo o Business Discovery de cada perfil
do Instagram que tem post no top ou no controle e grava os links atuais em data/raw/<data>/midia_renovada.jsonl.
A coleta original não muda; a camada 2 e o download de capas usam os links renovados quando existem
(src/collection/storage.py → posts_com_midia_renovada).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src.collection.http import get_json  # noqa: E402
from src.collection.instagram_graph import InstagramGraphCollector, parse_timestamp  # noqa: E402
from src.collection.ritmo import LimitadorChamadas  # noqa: E402
from src.collection.storage import append_jsonl, read_jsonl  # noqa: E402
from src.evaluation.thresholds import load_thresholds  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coleta", default=str(max((p for p in (ROOT / "data" / "raw").iterdir() if p.is_dir() and p.name[:4].isdigit()),
                                                key=lambda p: p.name)))
    args = ap.parse_args()
    coleta = Path(args.coleta)
    scores = pd.read_csv(ROOT / "data" / "processed" / "scores.csv", dtype={"post_id": str}, low_memory=False)
    alvo = scores[scores["grupo"].isin(["top", "controle"]) & (scores["plataforma"] == "instagram")]
    saida = coleta / "midia_renovada.jsonl"
    feitos = {str(r["post_id"]) for r in read_jsonl(saida)}
    faltam = alvo[~alvo["post_id"].isin(feitos)]
    if faltam.empty:
        print("Todos os posts do Instagram no top e no controle já têm links renovados.")
        return 0
    limiares = load_thresholds(ROOT / "config" / "limiares.yaml")
    limitador = LimitadorChamadas(int(limiares.req("instagram_chamadas_por_hora")))
    # sem cache: o objetivo é justamente buscar links novos
    coletor = InstagramGraphCollector(http=partial(get_json, antes_da_rede=limitador.antes_da_chamada))
    total = 0
    for username, grupo in faltam.groupby("username"):
        procurados = set(grupo["post_id"])
        mais_antigo = pd.to_datetime(grupo["publicado_em"], utc=True).min() - timedelta(days=1)
        achados, after, paginas = [], None, 0
        while procurados and paginas < 20:
            pagina = coletor.discovery_page(username, after, limit=50)
            paginas += 1
            media = pagina.get("media") or {}
            passou = False
            for item in media.get("data") or []:
                if str(item["id"]) in procurados:
                    achados.append({"post_id": str(item["id"]), "media_url": item.get("media_url"),
                                    "thumbnail_url": item.get("thumbnail_url"),
                                    "renovado_em": datetime.now(timezone.utc).isoformat()})
                    procurados.discard(str(item["id"]))
                if parse_timestamp(item["timestamp"]) < mais_antigo:
                    passou = True
            proximo = ((media.get("paging") or {}).get("cursors") or {}).get("after")
            if passou or not media.get("data") or not proximo or proximo == after:
                break
            after = proximo
        total += append_jsonl(saida, achados)
        print(f"@{username}: {len(achados)} de {len(grupo)} links renovados em {paginas} página(s)"
              + (f" · {len(procurados)} não encontrados (apagados ou arquivados)" if procurados else ""), flush=True)
    print(f"{total} links renovados → {saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
