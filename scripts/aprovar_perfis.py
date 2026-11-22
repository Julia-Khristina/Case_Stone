"""Leva para config/perfis.csv os candidatos marcados com "sim" na coluna aprovar.

Uso: python scripts/aprovar_perfis.py data/descoberta/candidatos_2026-11-22.csv

Cada perfil entra com a origem (quem o mencionou) e a data de entrada, para a seleção ficar auditável.
Perfis que já estão na lista são ignorados.

Exclusões: candidatos cuja observação começa com "Excluído" vão para config/perfis_recusados.csv e não voltam
nas próximas rodadas do agente de descoberta. "Não aprovado" (ex.: "já há três perfis do setor") não é registrado,
porque depende do contexto e pode mudar.
"""
from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERFIS = ROOT / "config" / "perfis.csv"
RECUSADOS = ROOT / "config" / "perfis_recusados.csv"
CAMPOS_RECUSADOS = ["plataforma", "perfil", "nome", "motivo", "data"]
SIM = {"sim", "s", "x", "1", "yes", "y"}


def chave(plataforma: str, perfil: str) -> tuple[str, str]:
    # @ do Instagram não diferencia maiúsculas; o ID de canal do YouTube (UC...) diferencia
    return plataforma, perfil.lower() if plataforma == "instagram" else perfil


def _ler(caminho: Path) -> tuple[list[str], list[dict]]:
    if not caminho.exists():
        return [], []
    with caminho.open(encoding="utf-8") as file:
        reader = csv.DictReader(file)
        return list(reader.fieldnames or []), list(reader)


def registrar_exclusoes(candidatos: list[dict], recusados_csv: Path, hoje: date) -> list[str]:
    _, atuais = _ler(recusados_csv)
    existentes = {chave(r["plataforma"], r["perfil"]) for r in atuais}
    novos = []
    for c in candidatos:
        obs = (c.get("observacao") or "").strip()
        plataforma = c.get("plataforma") or "instagram"
        if obs.startswith("Excluído") and chave(plataforma, c["perfil"]) not in existentes:
            existentes.add(chave(plataforma, c["perfil"]))
            novos.append({"plataforma": plataforma, "perfil": c["perfil"], "nome": c.get("nome") or "",
                          "motivo": obs, "data": hoje.isoformat()})
    if novos:
        novo_arquivo = not recusados_csv.exists()
        with recusados_csv.open("a", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=CAMPOS_RECUSADOS)
            if novo_arquivo:
                writer.writeheader()
            writer.writerows(novos)
    return [n["perfil"] for n in novos]


def aprovar(candidatos_csv: Path, perfis_csv: Path = PERFIS, hoje: date | None = None,
            recusados_csv: Path | None = None) -> list[str]:
    hoje = hoje or date.today()
    campos, atuais = _ler(perfis_csv)
    existentes = {chave(r["plataforma"], r["perfil"]) for r in atuais}
    with candidatos_csv.open(encoding="utf-8-sig") as file:
        candidatos = list(csv.DictReader(file))
    marcados = [r for r in candidatos if (r.get("aprovar") or "").strip().lower() in SIM]
    novos = []
    for c in marcados:
        plataforma = c.get("plataforma") or "instagram"
        if chave(plataforma, c["perfil"]) in existentes:
            continue
        existentes.add(chave(plataforma, c["perfil"]))
        # A observação de quem revisou (ex.: "Resgatado: ...") vale mais que o motivo automático do filtro
        obs = (c.get("observacao") or "").strip()
        motivo = obs or c.get("motivo", "")
        tipo = "marca" if obs.startswith("Marca do setor") else (c.get("tipo") or "")
        novos.append({"plataforma": plataforma, "perfil": c["perfil"], "nome": c.get("nome") or "",
                      "origem": f"descoberta: mencionado por {c.get('mencionado_por', '')}",
                      "segmento": c.get("macrossetor") or c.get("tema") or c.get("segmento_sugerido") or "",
                      "tipo": tipo, "nicho": c.get("nicho") or "", "parceiro_atual": "nao",
                      "justificativa": f"{motivo}; {c.get('seguidores', '')} seguidores ({c.get('faixa', '')})",
                      "data_entrada": hoje.isoformat()})
    if novos:
        with perfis_csv.open("a", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=campos, extrasaction="ignore")
            writer.writerows(novos)
    registrar_exclusoes(candidatos, recusados_csv or perfis_csv.with_name("perfis_recusados.csv"), hoje)
    return [n["perfil"] for n in novos]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    adicionados = aprovar(Path(sys.argv[1]))
    _, recusados = _ler(RECUSADOS)
    print(f"{len(adicionados)} perfis adicionados a config/perfis.csv: {', '.join('@' + a for a in adicionados) or '-'}")
    print(f"{len(recusados)} perfis na lista de exclusões (config/perfis_recusados.csv)")
