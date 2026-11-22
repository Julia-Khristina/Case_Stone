"""Radar semanal de oportunidades (src/analysis/radar.py): lê as fontes oficiais e grava data/processed/radar.json.

    python scripts/radar.py

O arquivo traz, para cada novidade aceita: tipo (prazo, regra nova, oportunidade de venda, ferramenta, alerta,
data), o que muda, data-chave (só se estiver na fonte), pilar, tema de post sugerido, por que importa, fonte, link e
data de publicação. Também lista as descartadas e o motivo, e o estado de cada fonte. A agenda e o app leem esse
arquivo; sem ele, tudo funciona como antes.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)
except ImportError:
    pass

from src.agent.ferramentas import load_stone_context  # noqa: E402
from src.analysis import radar  # noqa: E402
from src.shared.llm_client import InvalidLLMOutput, LLMClient  # noqa: E402

SAIDA = ROOT / "data" / "processed" / "radar.json"


def main() -> int:
    hoje = date.today()
    estado, todos = [], []
    for f in radar.FONTES:
        try:
            itens = radar.ler_feed(radar.baixar(f["url"]), f["nome"])
            estado.append({**f, "ok": True, "itens": len(itens)})
            todos += itens
        except Exception as exc:  # noqa: BLE001 - uma fonte fora do ar não derruba o radar
            estado.append({**f, "ok": False, "erro": str(exc)[:160]})
    cand = radar.candidatos(todos, hoje)
    print(f"{len(todos)} notícias lidas de {sum(e['ok'] for e in estado)} fontes; {len(cand)} candidatas nos últimos "
          f"{radar.VALIDADE_DIAS} dias")
    client = LLMClient()
    aceitos, fora = [], []
    concorrentes = load_stone_context().get("concorrentes", [])
    for i in range(0, len(cand), 12):
        lote = cand[i:i + 12]
        for tentativa in range(3):
            try:
                a, d = radar.aplicar_travas(lote, radar.extrair(client, lote, tentativa), concorrentes)
                aceitos += a
                fora += d
                break
            except InvalidLLMOutput:
                continue
    # acumula semana a semana: cada feed traz só as últimas notícias; o que ainda está na validade continua
    if SAIDA.exists():
        limite = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=radar.VALIDADE_DIAS)).isoformat()
        novos = {x["link"] for x in aceitos + fora}
        anteriores = json.loads(SAIDA.read_text(encoding="utf-8")).get("itens", [])
        aceitos += [x for x in anteriores if x["link"] not in novos and x["publicado_em"] >= limite]
    aceitos.sort(key=lambda x: x["publicado_em"], reverse=True)
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps({"gerado_em": datetime.now(timezone.utc).isoformat(), "validade_dias": radar.VALIDADE_DIAS,
                                 "fontes": estado, "itens": aceitos, "descartados": fora}, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    print(f"{len(aceitos)} novidades aceitas, {len(fora)} descartadas → {SAIDA}")
    for x in aceitos:
        print(f"  [{x['tipo']}] {x['titulo_curto']}{' · ' + x['data_chave'] if x.get('data_chave') else ''} ({x['fonte']})")
    motivos = {}
    for x in fora:
        motivos[x["motivo"]] = motivos.get(x["motivo"], 0) + 1
    print("Descartes:", motivos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
