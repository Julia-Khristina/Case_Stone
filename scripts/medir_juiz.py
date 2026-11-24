"""Mede se o retorno do juiz melhora os criativos, a partir de data/processed/agent_runs.jsonl.

    python scripts/medir_juiz.py              # resume o que já está registrado
    python scripts/medir_juiz.py --rodar 8    # gera 8 peças reais (temas da agenda) e depois resume

Para cada criativo que passou pela reescrita guiada pelo juiz (src/agent/melhoria.py): nota antes e depois,
quantos melhoraram, quantas reescritas foram descartadas e a variação média por critério da rubrica.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRO = ROOT / "data" / "processed" / "agent_runs.jsonl"


def resumir(linhas: list[dict]) -> dict:
    avaliados, melhorias = [], []
    for run in linhas:
        for c in run.get("juiz") or []:
            if c.get("nota") is not None:
                avaliados.append(c)
            if c.get("melhoria"):
                melhorias.append(c["melhoria"])
    reescritos = [m for m in melhorias if m.get("antes") is not None]
    trocados = [m for m in reescritos if m.get("mantida") != "original"]
    variacao: dict[str, list[float]] = {}
    for m in trocados:
        final = next((r["criterios"] for r in reversed(m["rodadas"]) if r.get("criterios")), {})
        for k, antes in (m.get("criterios_antes") or {}).items():
            if k in final:
                variacao.setdefault(k, []).append(final[k] - antes)
    media = lambda xs: round(sum(xs) / len(xs), 2) if xs else None   # noqa: E731
    return {
        "criativos_avaliados": len(avaliados),
        "precisaram_de_reescrita": len(reescritos),
        "reescrita_aproveitada": len(trocados),
        "reescrita_descartada": len(reescritos) - len(trocados),
        "nota_media_antes": media([m["antes"] for m in reescritos]),
        "nota_media_depois": media([m["depois"] for m in reescritos]),
        "variacao_por_criterio": {k: media(v) for k, v in sorted(variacao.items())},
    }


def rodar_lote(n: int) -> None:
    """Gera n peças com o agente real (Groq), com objetivos variados dos temas de orientação da agenda.

    Cada peça custa de 2 a 6 chamadas ao modelo (geração, conferências, avaliador e, se preciso, a reescrita guiada).
    Tudo vai para o registro normal, então o resumo abaixo já inclui o lote.
    """
    import yaml
    sys.path.insert(0, str(ROOT))
    from src.agent import ferramentas as fx
    from src.agent.contrato import AgentInput, Filtros
    from src.agent.grafo import run_agent
    temas = [o["tema"] for o in yaml.safe_load((ROOT / "config" / "orientacoes.yaml").read_text(encoding="utf-8"))["orientacoes"]]
    coleta = max((p for p in (ROOT / "data" / "raw").iterdir() if p.is_dir() and p.name[:4].isdigit()), key=lambda p: p.name)
    base = fx.Base.carregar(coleta)
    for i in range(n):
        formato = ("carrossel", "reels")[i % 2]
        entrada = AgentInput(mode="gerar_criativo", query=temas[i % len(temas)], formatos=[formato], usar_juiz=True,
                             filters=Filtros(plataforma="instagram"), conta=("impulsostone", "stone")[i % 4 == 3])
        try:
            saida = run_agent(entrada, base=base)
            c = saida.creatives[0] if saida.creatives else None
            nota = (c.juiz or {}).get("media_ponderada") if c else None
            print(f"{i + 1}/{n} {formato:9} nota {nota if nota is not None else '—'}"
                  f"{' · reescrita pelo avaliador' if c and c.melhoria_juiz else ''} · {temas[i % len(temas)][:60]}", flush=True)
        except Exception as exc:  # noqa: BLE001 - cota esgotada etc.: para o lote e resume o que saiu
            print(f"{i + 1}/{n} parou: {str(exc)[:160]}")
            break


def main() -> int:
    if "--rodar" in sys.argv:
        rodar_lote(int(sys.argv[sys.argv.index("--rodar") + 1]))
    if not REGISTRO.exists():
        print("Ainda não há execuções registradas.")
        return 0
    linhas = [json.loads(l) for l in REGISTRO.read_text(encoding="utf-8").splitlines() if l.strip()]
    r = resumir(linhas)
    print(f"Criativos avaliados pelo juiz: {r['criativos_avaliados']}")
    print(f"Precisaram de reescrita guiada pelo juiz: {r['precisaram_de_reescrita']} "
          f"(aproveitada: {r['reescrita_aproveitada']}, descartada por não superar a original: {r['reescrita_descartada']})")
    if r["precisaram_de_reescrita"]:
        print(f"Nota média: {r['nota_media_antes']} antes → {r['nota_media_depois']} depois (fica sempre a melhor versão)")
        for k, v in r["variacao_por_criterio"].items():
            print(f"  {k:24} {v:+.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
