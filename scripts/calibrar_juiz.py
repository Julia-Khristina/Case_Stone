"""Calibração do avaliador (LLM-as-a-judge) com notas humanas.

    python scripts/calibrar_juiz.py preparar     # planilha data/validacao/notas_humanas.csv com as peças avaliadas
    python scripts/calibrar_juiz.py comparar     # compara as notas humanas com as do avaliador

Na planilha, uma pessoa da equipe dá de 0 a 10 em cada critério da rubrica (src/evaluation/rubric_criativo.yaml)
sem olhar a nota do avaliador, e diz se aprovaria a peça (sim/nao). A comparação mostra, por critério:
erro médio absoluto, correlação de postos (Spearman), quantas notas ficaram a até 2 pontos e o viés (o avaliador dá
nota maior ou menor que a pessoa). Se o viés for grande, ajuste as âncoras da rubrica ou o juiz_media_minima.
Grava data/processed/calibracao_juiz.json.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.app_store import Store  # noqa: E402

PLANILHA = ROOT / "data" / "validacao" / "notas_humanas.csv"
SAIDA = ROOT / "data" / "processed" / "calibracao_juiz.json"


def criterios() -> list[str]:
    rubrica = yaml.safe_load((ROOT / "src" / "evaluation" / "rubric_criativo.yaml").read_text(encoding="utf-8"))
    return [c["nome"] for c in rubrica["criterios"]]


def texto_da_peca(c: dict) -> str:
    partes = [f"Caso: {c.get('caso', '')}", f"Gancho: {c.get('gancho', '')}",
              *[f"{i}. {t}" for i, t in enumerate(c.get("corpo") or [], 1)], f"Chamada: {c.get('cta', '')}"]
    return "\n".join(partes)


def preparar(store: Store, planilha: Path = PLANILHA) -> int:
    """Acrescenta à planilha as peças com nota do avaliador que ainda não estão nela (não apaga o que foi preenchido)."""
    existentes = pd.read_csv(planilha, dtype=str, encoding="utf-8-sig") if planilha.exists() else pd.DataFrame()
    ja = set(existentes.get("peca_id", pd.Series(dtype=str)))
    novas = []
    for p in store.listar():
        a = p.get("atual") or {}
        if p["id"] in ja or not (a.get("juiz") or {}).get("scores") or not a.get("criativo"):
            continue
        linha = {"peca_id": p["id"], "conta": a.get("conta") or "impulsostone", "formato": p["formato"],
                 "titulo": a["criativo"].get("titulo", ""), "texto": texto_da_peca(a["criativo"])}
        linha.update({f"humano_{k}": "" for k in criterios()})
        linha["humano_aprovaria"] = ""
        novas.append(linha)
    if not novas:
        return 0
    planilha.parent.mkdir(parents=True, exist_ok=True)
    pd.concat([existentes, pd.DataFrame(novas)], ignore_index=True).to_csv(planilha, index=False, encoding="utf-8-sig")
    return len(novas)


def comparar(store: Store, planilha: Path = PLANILHA) -> dict:
    humanas = pd.read_csv(planilha, dtype=str, encoding="utf-8-sig")
    juiz = {p["id"]: (p.get("atual") or {}).get("juiz") or {} for p in store.listar()}
    por_criterio, aprov = {}, []
    for k in criterios():
        col = f"humano_{k}"
        if col not in humanas:
            continue
        pares = [(float(h), float(juiz[pid]["scores"][k])) for pid, h in zip(humanas["peca_id"], humanas[col])
                 if isinstance(h, str) and h.strip() and pid in juiz and k in (juiz[pid].get("scores") or {})]
        if len(pares) < 3:
            continue
        hs, js = pd.Series([x for x, _ in pares]), pd.Series([y for _, y in pares])
        rho = hs.rank().corr(js.rank()) if hs.nunique() > 1 and js.nunique() > 1 else None
        por_criterio[k] = {"n": len(pares), "erro_medio": round(float((hs - js).abs().mean()), 2),
                           "spearman": None if rho is None or pd.isna(rho) else round(float(rho), 2),
                           "ate_2_pontos": round(float(((hs - js).abs() <= 2).mean()), 2),
                           "vies_do_avaliador": round(float((js - hs).mean()), 2)}
    for pid, h in zip(humanas["peca_id"], humanas.get("humano_aprovaria", pd.Series(dtype=str))):
        if isinstance(h, str) and h.strip().lower() in ("sim", "nao", "não") and pid in juiz and "aprovado" in juiz[pid]:
            aprov.append((h.strip().lower() == "sim", bool(juiz[pid]["aprovado"])))
    return {"por_criterio": por_criterio,
            "aprovacao": {"n": len(aprov), "concordancia": round(sum(a == b for a, b in aprov) / len(aprov), 2)} if aprov else None}


def main() -> int:
    store = Store(Path(os.getenv("BOAPAUTA_DB", str(ROOT / "data" / "app" / "boapauta.sqlite"))))
    acao = sys.argv[1] if len(sys.argv) > 1 else "comparar"
    if acao == "preparar":
        n = preparar(store)
        print(f"{n} peça(s) nova(s) em {PLANILHA}. Preencha as colunas humano_* sem olhar a nota do avaliador.")
        return 0
    if not PLANILHA.exists():
        print("Planilha não encontrada. Rode antes: python scripts/calibrar_juiz.py preparar")
        return 1
    r = comparar(store)
    if not r["por_criterio"]:
        print("Ainda não há notas humanas suficientes (mínimo de 3 peças por critério).")
        return 1
    for k, v in r["por_criterio"].items():
        vies = v["vies_do_avaliador"]
        sinal = "mais generoso" if vies > 0.5 else ("mais rígido" if vies < -0.5 else "alinhado")
        print(f"{k:24} n={v['n']:2}  erro médio {v['erro_medio']:4.1f}  até 2 pontos {v['ate_2_pontos']:4.0%}  "
              f"Spearman {v['spearman'] if v['spearman'] is not None else '—':>5}  avaliador {sinal} ({vies:+.1f})")
    if r["aprovacao"]:
        print(f"Aprovaria × aprovado pelo avaliador: {r['aprovacao']['concordancia']:.0%} de concordância em {r['aprovacao']['n']} peças")
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
