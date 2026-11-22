"""Antes × depois da limpeza de escopo (24/11/2026): qualidade do top e achados.

    python scripts/relatorio_escopo.py [pasta_do_backup]

Compara data/processed com um backup anterior à limpeza (padrão: o mais recente em .cache/backup_antes_escopo_*).
Grava data/processed/relatorio_escopo.json, usado no README e na apresentação.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collection.storage import read_jsonl  # noqa: E402

FORA = {"receita_ou_tecnica", "outro"}


def resumo(proc: Path, rotulos: Path | None = None) -> dict:
    s = pd.read_csv(proc / "scores.csv", dtype={"post_id": str}, low_memory=False)
    rot = pd.DataFrame(read_jsonl((rotulos or proc) / "rotulos_texto.jsonl"))
    rot = rot.assign(post_id=rot["post_id"].astype(str)).drop_duplicates("post_id", keep="last") if not rot.empty else rot
    top = s[s["grupo"] == "top"].merge(rot[["post_id", "tema_principal"]] if not rot.empty else pd.DataFrame(columns=["post_id", "tema_principal"]),
                                       on="post_id", how="left")
    return {"top": len(top), "controle": int((s["grupo"] == "controle").sum()), "perfis_no_top": int(top["perfil_id"].nunique()),
            "mediana_curtidas_top": float(top["curtidas"].median()),
            "top_com_menos_de_100_curtidas": int((top["curtidas"] < 100).sum()),
            "top_fora_do_tema": int(top["tema_principal"].isin(FORA).sum()),
            "top_sem_rotulo_de_tema": int(top["tema_principal"].isna().sum()),
            "temas_top": {str(k): int(v) for k, v in top["tema_principal"].value_counts().items()}}


def achados(base_dir: Path) -> list[dict]:
    from src.agent import ferramentas as fx
    coleta = max((p for p in (ROOT / "data" / "raw").iterdir() if p.is_dir() and p.name[:4].isdigit()), key=lambda p: p.name)
    b = fx.Base.carregar(coleta)
    return [f.model_dump() for f in fx.query_stats(b) if f.leitura in ("mais no top", "menos no top")]


def main() -> int:
    backups = sorted((ROOT / ".cache").glob("backup_antes_escopo_*"))
    antes_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else (backups[-1] / "processed" if backups else None)
    depois = resumo(ROOT / "data" / "processed")
    antes = resumo(antes_dir) if antes_dir and antes_dir.exists() else None
    fortes = achados(ROOT)
    s = pd.read_csv(ROOT / "data" / "processed" / "scores.csv", dtype={"post_id": str}, low_memory=False)
    fora = s.get("fora_escopo", pd.Series(dtype=str)).fillna("").astype(str)
    motivos = fora[fora != ""].str.replace(r"tema sensível: .*", "tema sensível", regex=True) \
        .str.replace(r"menos de .*", "poucas curtidas", regex=True).value_counts().to_dict()
    r = {"antes": antes, "depois": depois, "fora_do_escopo": {k: int(v) for k, v in motivos.items()},
         "achados_fortes": [{"plataforma": f["plataforma"], "caracteristica": f["caracteristica"], "valor": f["valor"],
                             "lift": f["lift"], "leitura": f["leitura"], "n_perfis": f["n_perfis"]} for f in fortes]}
    (ROOT / "data" / "processed" / "relatorio_escopo.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    if antes:
        print(f"{'':28}{'antes':>10}{'depois':>10}")
        for k in ("top", "perfis_no_top", "mediana_curtidas_top", "top_com_menos_de_100_curtidas", "top_fora_do_tema", "top_sem_rotulo_de_tema"):
            print(f"{k:28}{antes[k]:>10.0f}{depois[k]:>10.0f}")
    print("\nFora do escopo:", r["fora_do_escopo"])
    print(f"\n{len(fortes)} achados fortes:")
    for f in fortes:
        print(f"  {f['plataforma']:9} {f['caracteristica']}={f['valor']:<24} {f['lift'] if f['lift'] else '':>5}× {f['leitura']} ({f['n_perfis']} perfis)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
