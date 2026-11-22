"""Posts excluídos da análise por decisão humana (fora do tema ou da proposta do projeto).

A lista fica em config/posts_excluidos.csv (versionada: é decisão de curadoria, como config/perfis_recusados.csv).
A camada 0 (scripts/calcular_metricas.py) tira esses posts antes de montar o top e o grupo de comparação, então
eles somem dos achados, das referências do agente e do playbook. Quem marca é a pessoa na página de validação
(botão "Fora do tema"); scripts/validar_rotulos.py leva a marcação para a lista.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARQUIVO = ROOT / "config" / "posts_excluidos.csv"
COLUNAS = ["post_id", "plataforma", "motivo", "excluido_em"]


def carregar(arquivo: Path = ARQUIVO) -> set[str]:
    if not arquivo.exists():
        return set()
    with arquivo.open(encoding="utf-8-sig") as f:
        return {r["post_id"].strip() for r in csv.DictReader(f) if r.get("post_id", "").strip()}


def registrar(posts: list[dict], motivo: str = "fora do tema (validação humana)", arquivo: Path = ARQUIVO) -> int:
    """Acrescenta os posts que ainda não estão na lista; devolve quantos entraram."""
    ja = carregar(arquivo)
    novos = [p for p in posts if str(p.get("post_id", "")).strip() and str(p["post_id"]).strip() not in ja]
    if not novos:
        return 0
    existe = arquivo.exists()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    with arquivo.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        if not existe:
            w.writeheader()
        for p in novos:
            w.writerow({"post_id": str(p["post_id"]).strip(), "plataforma": p.get("plataforma", ""),
                        "motivo": p.get("motivo") or motivo, "excluido_em": date.today().isoformat()})
    return len(novos)
