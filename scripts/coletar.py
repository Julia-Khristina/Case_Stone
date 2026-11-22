"""Coleta os perfis de config/perfis.csv pelas APIs oficiais e grava em data/raw/<data>.

Uso:
    python scripts/coletar.py                                   # Instagram e YouTube, últimos 180 dias
    python scripts/coletar.py --plataforma instagram --esperar  # espera a janela de limite liberar e continua

180 dias cobrem a janela de "momento" (90 dias) e a janela anterior, usada para calcular a tendência.

Limite do Instagram: no máximo instagram_chamadas_por_hora (config/limiares.yaml) chamadas à rede por hora;
respostas do cache não contam. Ao atingir o limite (o local ou o da Meta), o coletor para e diz como retomar,
ou, com --esperar, espera e continua sozinho.
Retomada: perfis já gravados na pasta do dia são pulados, e as páginas já baixadas saem do cache. Rodar de novo
não baixa nada duas vezes nem duplica posts.
Um perfil que falhar por outro motivo não interrompe os outros: o erro vai para data/raw/<data>/erros.jsonl.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src.collection.discovery import limite_atingido  # noqa: E402
from src.collection.http import HttpError, TokenExpirado, get_json  # noqa: E402
from src.collection.instagram_graph import InstagramGraphCollector  # noqa: E402
from src.collection.ritmo import LimitadorChamadas, LimiteLocalAtingido  # noqa: E402
from src.collection.storage import append_jsonl, read_jsonl  # noqa: E402
from src.collection.youtube import YouTubeCollector  # noqa: E402
from src.evaluation.thresholds import load_thresholds  # noqa: E402
from src.shared.cache import VersionedCache  # noqa: E402


def ja_coletados(pasta: Path) -> set[tuple[str, str]]:
    """(plataforma, perfil) já gravados na pasta do dia, pelo @ (Instagram) ou pelo ID do canal (YouTube)."""
    feitos = set()
    for p in read_jsonl(pasta / "perfis.jsonl"):
        feitos.add((p["plataforma"], (p.get("username") or "").lower()))
        feitos.add((p["plataforma"], p.get("perfil_id") or ""))
    return feitos


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plataforma", choices=["instagram", "youtube", "todas"], default="todas")
    parser.add_argument("--dias", type=int, default=180)
    parser.add_argument("--perfis", default=str(ROOT / "config" / "perfis.csv"))
    parser.add_argument("--esperar", action="store_true", help="esperar a janela de limite liberar em vez de parar")
    args = parser.parse_args()

    limiares = load_thresholds(ROOT / "config" / "limiares.yaml")
    since = datetime.now(timezone.utc) - timedelta(days=args.dias)
    out = ROOT / "data" / "raw" / datetime.now().strftime("%Y-%m-%d")
    cache = VersionedCache(Path(os.getenv("CACHE_DIR", ".cache/stone")) / "http")
    limitador = LimitadorChamadas(int(limiares.req("instagram_chamadas_por_hora")), esperar=args.esperar,
                                  avisar=lambda msg: print(f"⏳ {msg}", flush=True))
    with open(args.perfis, encoding="utf-8") as file:
        rows = [r for r in csv.DictReader(file) if args.plataforma in ("todas", r["plataforma"])]
    feitos = ja_coletados(out)
    pendentes = [r for r in rows
                 if (r["plataforma"], r["perfil"].lower() if r["plataforma"] == "instagram" else r["perfil"]) not in feitos]
    print(f"{len(rows)} perfis na lista; {len(rows) - len(pendentes)} já coletados hoje; {len(pendentes)} a coletar")

    collectors: dict[str, object] = {}
    total, interrompido = 0, False
    for row in pendentes:
        plataforma, perfil = row["plataforma"], row["perfil"]
        while True:   # repete o mesmo perfil depois de esperar um limite (só com --esperar)
            try:
                if plataforma not in collectors:
                    collectors[plataforma] = (
                        InstagramGraphCollector(cache=cache, http=partial(get_json, antes_da_rede=limitador.antes_da_chamada))
                        if plataforma == "instagram" else YouTubeCollector(cache=cache))
                profile, posts, raw = collectors[plataforma].collect(perfil, since=since)
                break
            except TokenExpirado as exc:
                print(f"\n✗ {exc}")
                return 1
            except (LimiteLocalAtingido, HttpError) as exc:
                if isinstance(exc, HttpError) and not limite_atingido(exc):
                    # Outro erro da API (ex.: perfil inexistente): registra e segue para o próximo perfil
                    append_jsonl(out / "erros.jsonl", [{"plataforma": plataforma, "perfil": perfil, "erro": str(exc)}])
                    print(f"✗ {plataforma} @{perfil}: {str(exc)[:160]}")
                    profile = None
                    break
                minutos = (getattr(exc, "segundos_para_liberar", 0) / 60) or getattr(exc, "minutos_para_liberar", None) or 60
                if not args.esperar:
                    print(f"\n⚠ Limite de chamadas atingido em @{perfil}. Rode o mesmo comando de novo daqui a "
                          f"~{minutos:.0f} min (ou use --esperar): os perfis já coletados são pulados.")
                    interrompido = True
                    break
                print(f"⏳ Limite atingido em @{perfil}; esperando {minutos:.0f} min e continuando…", flush=True)
                time.sleep(minutos * 60)
            except Exception as exc:  # noqa: BLE001 - registra e segue para o próximo perfil
                append_jsonl(out / "erros.jsonl", [{"plataforma": plataforma, "perfil": perfil, "erro": str(exc)}])
                print(f"✗ {plataforma} @{perfil}: {exc}")
                profile = None
                break
        if interrompido:
            break
        if profile is None:
            continue
        # Campos da nossa lista; o nome da lista não sobrescreve o nome que veio da API
        extra = {k: row.get(k) for k in ("origem", "segmento", "tipo", "nicho", "parceiro_atual")}
        extra["nome_lista"] = row.get("nome")
        append_jsonl(out / f"{plataforma}_bruto.jsonl", [{"perfil": perfil, "paginas": raw}])
        append_jsonl(out / "perfis.jsonl", [{**profile.model_dump(mode="json"), **extra}])
        total += append_jsonl(out / "posts.jsonl", posts)
        print(f"✓ {plataforma} @{perfil}: {profile.seguidores} seguidores, {len(posts)} posts", flush=True)

    print(f"\n{total} posts gravados em {out} · chamadas ao Instagram na última hora: {limitador.usadas}")
    return 2 if interrompido else 0


if __name__ == "__main__":
    sys.exit(main())
