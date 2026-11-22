"""Indicação de criadores para parceria (embaixadores). Roda depois da análise, sobre os criadores da amostra.

Composição em config/segmentos.yaml (padrão: 2 transversais + 3 setoriais + 1 reserva por vaga), o mesmo formato
dos parceiros atuais da Stone. Os indicados saem da amostra já analisada: primeiro o sistema aprende o que engaja,
depois aponta quem já faz isso bem. A decisão de contatar é sempre da Stone.

Cada criador é um dict com: perfil, nome, tipo, macrossetor, tema, faixa, nota (0–100, do scorecard),
parceiro_atual (bool) e alertas (lista com, por exemplo, "publi_concorrente" ou "conta_de_marca").
"""
from __future__ import annotations

from typing import Any


def _excluido(c: dict[str, Any], regras: list[str]) -> str | None:
    if "parceiro_atual" in regras and c.get("parceiro_atual"):
        return "já é parceiro"
    for alerta in c.get("alertas") or []:
        if alerta in regras:
            return alerta.replace("_", " ")
    return None


def selecionar_indicados(criadores: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    regras = list(config.get("excluir_se") or [])
    preferidas = list(config.get("faixas_preferidas") or [])
    n_trans, n_set = int(config.get("transversais", 2)), int(config.get("setoriais", 3))
    reservas_por_vaga = int(config.get("reservas_por_vaga", 1))

    nota_minima = float(config.get("nota_minima", 0))
    elegiveis, excluidos = [], []
    for c in criadores:
        motivo = _excluido(c, regras)
        if not motivo and (c.get("nota") or 0) < nota_minima:
            motivo = f"nota abaixo de {nota_minima:.0f}"
        (excluidos.append({**c, "motivo_exclusao": motivo}) if motivo else elegiveis.append(c))
    ordenar = lambda lista: sorted(lista, key=lambda c: (c.get("faixa") not in preferidas, -(c.get("nota") or 0)))  # noqa: E731

    # Transversais: os melhores, variando o tema quando possível
    trans = ordenar([c for c in elegiveis if c.get("tipo") == "transversal"])
    escolhidos_t, temas = [], set()
    for c in trans:
        if len(escolhidos_t) < n_trans and c.get("tema") not in temas:
            escolhidos_t.append(c)
            temas.add(c.get("tema"))
    for c in trans:
        if len(escolhidos_t) < n_trans and c not in escolhidos_t:
            escolhidos_t.append(c)

    # Setoriais: um por setor; setores prioritários da Stone ou, se não houver, setores sem parceiro atual
    setoriais = ordenar([c for c in elegiveis if c.get("tipo") == "setorial"])
    cobertos = {c.get("macrossetor") for c in criadores if c.get("parceiro_atual")}
    prioritarios = list(config.get("setores_prioritarios") or [])
    if prioritarios:
        setores = prioritarios
        motivo_setores = "setores priorizados pela Stone"
    else:
        melhor_por_setor: dict[str, float] = {}
        for c in setoriais:
            melhor_por_setor.setdefault(c["macrossetor"], c.get("nota") or 0)
        setores = sorted(melhor_por_setor, key=lambda s: (s in cobertos, -melhor_por_setor[s]))
        motivo_setores = "setores sem parceiro atual primeiro, depois os de criadores com nota mais alta"
    escolhidos_s = []
    for setor in setores:
        melhor = next((c for c in setoriais if c.get("macrossetor") == setor and c not in escolhidos_s), None)
        if melhor and len(escolhidos_s) < n_set:
            escolhidos_s.append(melhor)
    for c in setoriais:                         # menos setores que vagas: completa com os melhores restantes
        if len(escolhidos_s) < n_set and c not in escolhidos_s:
            escolhidos_s.append(c)

    # Reservas: para cada vaga, o próximo melhor do mesmo tipo (e do mesmo setor, nos setoriais)
    usados = escolhidos_t + escolhidos_s
    ocupados = {(c.get("plataforma"), c["perfil"]) for c in usados}   # ninguém é reserva de duas vagas
    reservas = []
    for vaga in usados:
        mesmo = [c for c in (trans if vaga in escolhidos_t else setoriais)
                 if (c.get("plataforma"), c["perfil"]) not in ocupados
                 and (vaga in escolhidos_t or c.get("macrossetor") == vaga.get("macrossetor"))]
        for c in mesmo[:reservas_por_vaga]:
            reservas.append({**c, "reserva_de": vaga["perfil"]})
            ocupados.add((c.get("plataforma"), c["perfil"]))
    return {"transversais": escolhidos_t, "setoriais": escolhidos_s, "reservas": reservas,
            "excluidos": excluidos, "motivo_setores": motivo_setores}
