"""Atualização completa da base, na ordem certa, para rodar toda semana (Agendador de Tarefas do Windows ou cron).

    python scripts/atualizar_base.py                 # coleta nova + análises + contas da Stone + playbook
    python scripts/atualizar_base.py --sem-coleta    # só refaz as análises sobre a coleta mais recente
    python scripts/atualizar_base.py --agendar       # registra a tarefa semanal no Windows (segunda, 6h)

Etapas: coleta (APIs oficiais) → métricas (camada 0) → capas → rótulos de texto (camada 1, só posts novos) →
vídeo (camada 2, só posts novos, até o teto diário do Gemini) → contas da Stone → playbook.
Cada etapa que falha fica registrada e as seguintes continuam com o que já existe: uma cota esgotada no Gemini não
impede o playbook de sair. O log vai para data/processed/atualizacao.log. Custo: chamadas de API proporcionais aos
posts novos da semana (camadas 1 e 2 pulam o que já foi rotulado).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "processed" / "atualizacao.log"
TAREFA = "BoaPauta atualização semanal"


def coleta_mais_recente() -> Path:
    return max((p for p in (ROOT / "data" / "raw").iterdir() if p.is_dir() and p.name[:4].isdigit()), key=lambda p: p.name)


def etapas(sem_coleta: bool) -> list[tuple[str, list[str]]]:
    py = [sys.executable, "-u"]
    lista = [] if sem_coleta else [("coleta", py + ["scripts/coletar.py", "--esperar"])]
    coleta = "{coleta}"                                     # resolvida depois da coleta (a pasta nova é a do dia)
    return lista + [
        ("métricas (camada 0)", py + ["scripts/calcular_metricas.py", "--jsonl", coleta]),
        ("capas", py + ["scripts/baixar_capas.py", "--coleta", coleta]),
        ("rótulos de texto (camada 1)", py + ["scripts/camada1.py", "--coleta", coleta]),
        ("vídeo (camada 2)", py + ["scripts/camada2.py", "--coleta", coleta]),
        ("contas da Stone: coleta", py + ["scripts/contas_stone.py", "coletar"]),
        ("contas da Stone: Insights", py + ["scripts/contas_stone.py", "insights"]),
        ("contas da Stone: texto", py + ["scripts/contas_stone.py", "texto"]),
        ("contas da Stone: capas", py + ["scripts/contas_stone.py", "capas"]),
        ("radar de oportunidades", py + ["scripts/radar.py"]),
        ("playbook", py + ["scripts/gerar_playbook.py"]),
    ]


def rodar(sem_coleta: bool = False) -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    falhas = []
    with LOG.open("a", encoding="utf-8") as log:
        log.write(f"\n==== {datetime.now():%d/%m/%Y %H:%M} atualização {'sem coleta' if sem_coleta else 'completa'}\n")
        for nome, comando in etapas(sem_coleta):
            comando = [c.replace("{coleta}", str(coleta_mais_recente())) for c in comando]
            inicio = time.time()
            log.write(f"-- {nome}\n")
            log.flush()
            r = subprocess.run(comando, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                               env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
            situacao = "ok" if r.returncode == 0 else f"FALHOU (código {r.returncode})"
            log.write(f"-- {nome}: {situacao} em {time.time() - inicio:.0f}s\n")
            print(f"{nome:32} {situacao}", flush=True)
            if r.returncode != 0:
                falhas.append(nome)
        log.write(f"==== fim: {len(falhas)} etapa(s) com falha{': ' + ', '.join(falhas) if falhas else ''}\n")
    print(f"Log: {LOG}")
    return 1 if falhas else 0


def agendar() -> int:
    """Tarefa semanal no Windows: segunda às 6h; roda assim que o computador ligar se estava desligado na hora."""
    script = ROOT / "scripts" / "atualizar_base.py"
    ps = (f"$a = New-ScheduledTaskAction -Execute '{sys.executable}' -Argument '\"{script}\"' -WorkingDirectory '{ROOT}';"
          "$t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 6am;"
          "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 4);"
          f"Register-ScheduledTask -TaskName '{TAREFA}' -Action $a -Trigger $t -Settings $s -Force | Out-Null")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr.strip()[:400])
        return 1
    print(f"Tarefa '{TAREFA}' registrada: toda segunda às 6h (ou assim que o computador ligar).")
    print(f"Para remover: Unregister-ScheduledTask -TaskName '{TAREFA}' -Confirm:$false")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sem-coleta", action="store_true", help="não coleta; refaz as análises sobre a coleta mais recente")
    ap.add_argument("--agendar", action="store_true", help="registra a tarefa semanal no Agendador do Windows")
    args = ap.parse_args()
    return agendar() if args.agendar else rodar(args.sem_coleta)


if __name__ == "__main__":
    sys.exit(main())
