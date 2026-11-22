"""Camada 3: concordância entre a rotulagem manual e a da IA, campo a campo (kappa de Cohen).

Uso: python scripts/validar_rotulos.py

Lê data/validacao/rotulagem_manual.csv e data/processed/rotulos_texto.jsonl. Campos com kappa abaixo de
kappa_minimo_campo (config/limiares.yaml) ficam marcados como pouco confiáveis: as peças e o playbook não devem tirar
conclusão deles. Grava data/processed/kappa.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from sklearn.metrics import cohen_kappa_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import exclusoes  # noqa: E402
from src.collection.storage import read_jsonl  # noqa: E402
from src.evaluation.thresholds import load_thresholds  # noqa: E402

CAMPOS = ["tema_principal", "tipo_hook", "tipo_cta", "convite_participacao", "mensagem_generica", "patrocinado"]
BOOLEANOS = {"convite_participacao", "mensagem_generica", "patrocinado"}


def normalizar(campo: str, valor) -> str:
    texto = str(valor).strip().lower()
    if campo in BOOLEANOS:
        return {"true": "sim", "false": "nao", "não": "nao", "1": "sim", "0": "nao"}.get(texto, texto)
    return texto


def concordancia(manual: pd.DataFrame, ia: pd.DataFrame, minimo: float) -> dict:
    df = manual.merge(ia, on="post_id", suffixes=("_manual", "_ia"))
    resultado = {}
    for campo in CAMPOS:
        pares = df[[f"{campo}_manual", f"{campo}_ia"]].dropna()
        pares = pares[pares[f"{campo}_manual"].astype(str).str.strip() != ""]
        if len(pares) < 2:
            continue
        a = [normalizar(campo, v) for v in pares[f"{campo}_manual"]]
        b = [normalizar(campo, v) for v in pares[f"{campo}_ia"]]
        kappa = cohen_kappa_score(a, b) if len(set(a) | set(b)) > 1 else 1.0
        resultado[campo] = {"n": len(pares), "concordancia": round(sum(x == y for x, y in zip(a, b)) / len(a), 3),
                            "kappa": round(float(kappa), 3), "confiavel": bool(kappa >= minimo)}
    return resultado


def main() -> int:
    planilha = ROOT / "data" / "validacao" / "rotulagem_manual.csv"
    if not planilha.exists():
        print("Planilha não encontrada. Rode antes: python scripts/preparar_validacao.py --coleta data/raw/<data>")
        return 1
    manual = pd.read_csv(planilha, encoding="utf-8-sig", dtype=str)
    if "fora_do_tema" in manual:                        # marcados na página de validação: saem daqui e da análise
        fora = manual[manual["fora_do_tema"].fillna("").str.strip().str.lower() == "sim"]
        novos = exclusoes.registrar(fora[["post_id", "plataforma"]].to_dict("records"))
        manual = manual.drop(fora.index)
        if len(fora):
            print(f"{len(fora)} post(s) fora do tema fora da concordância ({novos} novo(s) em config/posts_excluidos.csv).")
        if novos:
            print("Para tirá-los também dos achados: python scripts/atualizar_base.py --sem-coleta\n")
    ia = pd.DataFrame(read_jsonl(ROOT / "data" / "processed" / "rotulos_texto.jsonl")).drop_duplicates("post_id", keep="last")
    minimo = float(load_thresholds(ROOT / "config" / "limiares.yaml").req("kappa_minimo_campo"))
    resultado = concordancia(manual, ia[["post_id", *CAMPOS]], minimo)
    if not resultado:
        print("Nenhum campo preenchido ainda na planilha.")
        return 1
    for campo, r in resultado.items():
        marca = "ok" if r["confiavel"] else "POUCO CONFIÁVEL"
        print(f"{campo:22} n={r['n']:3}  concordância {r['concordancia']:5.0%}  kappa {r['kappa']:5.2f}  {marca}")
    (ROOT / "data" / "processed" / "kappa.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2),
                                                             encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
