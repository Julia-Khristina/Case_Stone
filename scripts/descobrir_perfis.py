"""Agente de descoberta de perfis: encontra candidatos, valida pela API oficial e propõe para aprovação humana.

Fontes de candidatos (--fonte):
    youtube   (padrão) busca canais do nicho pela API do YouTube; os canais viram candidatos do YouTube e os @ do
              Instagram citados na descrição de cada canal viram candidatos do Instagram.
    lista     arquivo com @ colados por uma pessoa (--candidatos arquivo.txt), um por linha, com ou sem @,
              ou o link instagram.com/perfil. Linhas começando com # são ignoradas.
    mencoes   @ nas legendas das sementes. Limitação da Graph API (confirmada em 22/11/2026): as menções vêm
              removidas das legendas de terceiros, então esta fonte só serve para contas que a usuária administra.

Uso:
    python scripts/descobrir_perfis.py
    python scripts/descobrir_perfis.py --fonte lista --candidatos data/descoberta/lista.txt

Gera data/descoberta/candidatos_<data>.csv. Marque "sim" na coluna aprovar e rode scripts/aprovar_perfis.py.
Nada entra em config/perfis.csv sem aprovação.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src.analysis.metrics import faixa_seguidores  # noqa: E402
from src.collection.discovery import (avaliar, classificar_perfil, contar_mencoes, info_canal,  # noqa: E402
                                      info_perfil, instagram_no_texto, limite_atingido, propor)
from src.collection.http import HttpError  # noqa: E402
from src.collection.instagram_graph import InstagramGraphCollector  # noqa: E402
from src.collection.youtube import YouTubeCollector  # noqa: E402
from src.evaluation.thresholds import load_thresholds  # noqa: E402
from src.shared.cache import VersionedCache  # noqa: E402

COLUNAS = ["aprovar", "status", "plataforma", "perfil", "nome", "seguidores", "faixa", "tipo", "macrossetor", "tema",
           "nicho", "n_mencoes", "mencionado_por", "total_posts", "ultimo_post", "motivo", "bio"]


def aviso_limite(exc: HttpError) -> str:
    espera = getattr(exc, "minutos_para_liberar", None)
    quando = f"daqui a até {espera} minutos" if espera else "mais tarde"
    return (f"⚠ Limite da Graph API atingido. As consultas que faltam ficam pendentes; rode de novo {quando}. "
            "Os perfis já verificados ficam no cache e não contam de novo.")


def adicionar(candidatos: dict, handle: str, origem: str, peso: int = 1) -> None:
    c = candidatos.setdefault(handle, {"n_mencoes": 0, "mencionado_por": set()})
    c["n_mencoes"] += peso
    c["mencionado_por"].add(origem)


def fonte_lista(arquivo: str, conhecidos: set[str]) -> dict:
    candidatos: dict = {}
    for linha in Path(arquivo).read_text(encoding="utf-8").splitlines():
        if linha.lstrip().startswith("#"):
            continue
        handle = linha.strip().rstrip("/").split("instagram.com/")[-1].split("?")[0].lstrip("@").lower()
        if handle and handle not in conhecidos:
            adicionar(candidatos, handle, f"lista {Path(arquivo).name}")
    return candidatos


def fonte_mencoes(ig: InstagramGraphCollector, perfis: list[str], conhecidos: set[str], n_posts: int) -> dict:
    posts = []
    for perfil in perfis:
        try:
            _, recentes, _ = ig.collect(perfil, max_posts=n_posts)
            posts += [p.model_dump() for p in recentes]
        except Exception as exc:  # noqa: BLE001
            print(f"✗ não consegui ler @{perfil}: {exc}")
    candidatos = {h: {"n_mencoes": m["n_mencoes"], "mencionado_por": {"@" + p for p in m["mencionado_por"]}}
                  for h, m in contar_mencoes(posts, ignorar=conhecidos).items()}
    if not candidatos:
        print("Nenhuma menção: a Graph API remove as menções das legendas de terceiros. Use --fonte youtube ou lista.")
    return candidatos


def fonte_youtube(yt: YouTubeCollector, buscas: list[str], ig_conhecidos: set[str], yt_conhecidos: set[str]
                  ) -> tuple[dict, list[dict]]:
    """Devolve (candidatos do Instagram achados nas descrições, canais do YouTube já no formato de info)."""
    ids: dict[str, set[str]] = {}
    for busca in buscas:
        for canal_id in yt.search_channels(busca):
            ids.setdefault(canal_id, set()).add(busca)
        print(f"· YouTube: \"{busca}\"")
    ig_candidatos: dict = {}
    canais = []
    for canal in yt.channels(list(ids)):
        info = info_canal(canal, yt.recent_uploads(canal["contentDetails"]["relatedPlaylists"]["uploads"]))
        nome = info["nome"] or info["perfil"]
        for handle in instagram_no_texto(info["bio"]):
            if handle not in ig_conhecidos:
                adicionar(ig_candidatos, handle, f"YouTube: {nome}", peso=2)    # @ citado explicitamente
        if info["handle_youtube"] and info["handle_youtube"] not in ig_conhecidos:
            adicionar(ig_candidatos, info["handle_youtube"], f"YouTube: mesmo @ de {nome}", peso=1)
        if info["perfil"] not in yt_conhecidos:
            canais.append({**info, "n_mencoes": len(ids[canal["id"]]),
                           "mencionado_por": "; ".join(f"busca: {b}" for b in sorted(ids[canal["id"]]))})
    print(f"{len(canais)} canais novos no YouTube; {len(ig_candidatos)} @ do Instagram citados nas descrições")
    return ig_candidatos, canais


def avaliar_info(info: dict, plataforma: str, base: dict, agora: datetime, limiares, faixas: dict) -> dict:
    classe = classificar_perfil(info["bio"], info.get("nome") or "")
    motivo_bio = classe.pop("motivo")
    info = {**info, **classe}
    passou, motivos = avaliar(info, agora, limiares, plataforma)
    return {**base, **info, "plataforma": plataforma,
            "faixa": faixa_seguidores(info["seguidores"], int(faixas["micro_max"]), int(faixas["medio_max"])),
            "status": "passou" if passou else "recusado", "motivo": motivo_bio if passou else "; ".join(motivos)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Agente de descoberta de perfis")
    parser.add_argument("--fonte", choices=["youtube", "lista", "mencoes"], default="youtube")
    parser.add_argument("--candidatos", help="arquivo com @ (só com --fonte lista)")
    parser.add_argument("--posts", type=int, default=40, help="posts lidos por perfil (só com --fonte mencoes)")
    parser.add_argument("--max-consultas", type=int, help="teto de @ verificados no Instagram nesta rodada "
                        "(padrão: descoberta_max_consultas). A API aceita cerca de 200 chamadas por hora; "
                        "os já verificados vêm do cache e não contam.")
    args = parser.parse_args()
    if args.fonte == "lista" and not args.candidatos:
        parser.error("--fonte lista precisa de --candidatos arquivo.txt")

    limiares = load_thresholds(ROOT / "config" / "limiares.yaml")
    faixas = limiares.req("faixas_seguidores")
    agora = datetime.now(timezone.utc)
    cache = VersionedCache(Path(os.getenv("CACHE_DIR", ".cache/stone")) / "http")
    config = yaml.safe_load((ROOT / "config" / "sementes.yaml").read_text(encoding="utf-8"))
    sementes = [s["perfil"] for s in config.get("instagram") or []]
    with (ROOT / "config" / "perfis.csv").open(encoding="utf-8") as file:
        atuais = list(csv.DictReader(file))
    ig_atuais = [r["perfil"].lower() for r in atuais if r["plataforma"] == "instagram"]
    yt_atuais = [r["perfil"] for r in atuais if r["plataforma"] == "youtube"]
    # Excluídos em revisões anteriores não voltam como candidatos (config/perfis_recusados.csv)
    recusados_csv = ROOT / "config" / "perfis_recusados.csv"
    recusados = list(csv.DictReader(recusados_csv.open(encoding="utf-8"))) if recusados_csv.exists() else []
    ig_recusados = {r["perfil"].lower() for r in recusados if r["plataforma"] == "instagram"}
    yt_recusados = {r["perfil"] for r in recusados if r["plataforma"] == "youtube"}
    ig_conhecidos = set(sementes) | set(ig_atuais) | ig_recusados
    yt_atuais = yt_atuais + sorted(yt_recusados)

    ig = InstagramGraphCollector(cache=cache)
    canais: list[dict] = []
    if args.fonte == "youtube":
        ig_candidatos, canais = fonte_youtube(YouTubeCollector(cache=cache), config.get("youtube_buscas") or [],
                                              ig_conhecidos, set(yt_atuais))
    elif args.fonte == "lista":
        ig_candidatos = fonte_lista(args.candidatos, ig_conhecidos)
    else:
        ig_candidatos = fonte_mencoes(ig, sementes + ig_atuais, ig_conhecidos, args.posts)

    # Faixas de quem já está na lista, para equilibrar as propostas
    faixas_ig = {"micro": 0, "medio": 0, "grande": 0}
    sem_limite = False
    for perfil in ig_atuais:
        try:
            info = info_perfil(ig, perfil)
        except HttpError as exc:
            if not limite_atingido(exc):
                raise
            sem_limite = True
            print(aviso_limite(exc))
            break
        f = info and faixa_seguidores(info["seguidores"], int(faixas["micro_max"]), int(faixas["medio_max"]))
        if f:
            faixas_ig[f] += 1
        elif info is None:
            print(f"✗ @{perfil} (já na lista) não foi encontrado ou não é conta profissional")

    # Valida no Instagram os mais citados, até o teto de consultas
    resultado = []
    teto = args.max_consultas or int(limiares.req("descoberta_max_consultas"))
    fila = sorted(ig_candidatos.items(), key=lambda kv: -kv[1]["n_mencoes"])
    if len(fila) > teto:
        print(f"{len(fila) - teto} @ do Instagram ficaram para a próxima rodada (use --max-consultas para aumentar)")
    for handle, m in fila[:teto]:
        base = {"perfil": handle, "n_mencoes": m["n_mencoes"], "mencionado_por": "; ".join(sorted(m["mencionado_por"]))}
        if sem_limite:
            resultado.append({**base, "plataforma": "instagram", "status": "pendente (limite da API)", "faixa": None})
            continue
        try:
            info = info_perfil(ig, handle)
        except HttpError as exc:
            if not limite_atingido(exc):
                raise
            sem_limite = True
            print(aviso_limite(exc))
            resultado.append({**base, "plataforma": "instagram", "status": "pendente (limite da API)", "faixa": None})
            continue
        if info is None:
            resultado.append({**base, "plataforma": "instagram", "status": "não é conta profissional", "faixa": None})
        else:
            resultado.append(avaliar_info(info, "instagram", base, agora, limiares, faixas))
    resultado_yt = [avaliar_info(c, "youtube", {k: c[k] for k in ("n_mencoes", "mencionado_por")}, agora, limiares,
                                 faixas) for c in canais]

    alvo = int(limiares.req("descoberta_alvo_por_faixa"))
    ordem = propor(resultado, faixas_ig, alvo) + propor(resultado_yt, {}, alvo)
    peso = {"proposto": 0, "passou (faixa cheia)": 1, "pendente (limite da API)": 2, "recusado": 3,
            "não é conta profissional": 4}
    ordem.sort(key=lambda c: (c["plataforma"] != "instagram", peso.get(c["status"], 9), -c["n_mencoes"]))

    out = ROOT / "data" / "descoberta" / f"candidatos_{agora:%Y-%m-%d}.csv"
    if out.exists():   # nunca sobrescreve: a pessoa pode estar marcando aprovações na lista anterior
        out = out.with_name(f"candidatos_{datetime.now():%Y-%m-%d_%Hh%M}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as file:   # utf-8-sig: abre certo no Excel
        writer = csv.DictWriter(file, fieldnames=COLUNAS, extrasaction="ignore")
        writer.writeheader()
        for c in ordem:
            writer.writerow({**c, "aprovar": "", "bio": (c.get("bio") or "").replace("\n", " ")[:160]})

    for plataforma in ("instagram", "youtube"):
        linhas = [c for c in ordem if c["plataforma"] == plataforma]
        if linhas:
            print(f"{plataforma}: " + ", ".join(f"{s}: {sum(1 for c in linhas if c['status'] == s)}" for s in peso))
    print(f"Faixas atuais no Instagram: {faixas_ig}")
    print(f"\nAbra {out}, marque 'sim' na coluna aprovar e rode: python scripts/aprovar_perfis.py {out}")
    return 0


if __name__ == "__main__":
    from src.collection.http import TokenExpirado

    try:
        sys.exit(main())
    except TokenExpirado as exc:
        print()
        print(f"✗ {exc}")
        sys.exit(1)
