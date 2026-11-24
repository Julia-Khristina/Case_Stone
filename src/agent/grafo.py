"""Agente em LangGraph: dados (ferramentas determinísticas) → roteamento pelo modo → geração com conferência e
reescrita → explicação. Cada execução fica registrada em data/processed/agent_runs.jsonl.

    run_agent(AgentInput(mode="gerar_criativo", query="atrair donos de restaurante", segment="alimentacao"))
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from src.evaluation.judge import avaliar_com_seguranca
from src.agent import ferramentas as fx
from src.agent.contrato import AgentInput, AgentOutput, CreativeAvaliado, Finding, RefPost
from src.agent.gerador import gerar
from src.agent.melhoria import melhorar_com_juiz, precisa_melhorar
from src.agent.verificador import conferir, verbos_permitidos
from src.collection.storage import append_jsonl
from src.evaluation.thresholds import load_thresholds
from src.shared.llm_client import InvalidLLMOutput

ROOT = Path(__file__).resolve().parents[2]
PLATAFORMA_DO_FORMATO = {"reels": "instagram", "carrossel": "instagram", "estatico": "instagram",
                         "stories": "instagram", "short": "youtube"}
TIPO_NA_BASE = {"reels": "reels", "carrossel": "carrossel", "estatico": "imagem", "short": "short", "stories": None}
FORMATO_DO_TIPO = {"reels": "reels", "carrossel": "carrossel", "imagem": "estatico"}


class Estado(TypedDict, total=False):
    entrada: AgentInput
    contexto: dict
    findings: list[Finding]
    trends: list[Finding]
    refs: list[RefPost]
    criativos: list[CreativeAvaliado]
    erros: list[str]
    creators: list[dict]
    indicados: dict
    explanation: str
    confidence_flag: bool
    registro: dict


def escolher_formatos(entrada: AgentInput, trends: list[Finding]) -> list[str]:
    if entrada.formatos:
        return list(entrada.formatos)
    if entrada.mode == "gerar_criativo":
        return ["reels"]
    em_alta = [FORMATO_DO_TIPO[t.valor] for t in trends if t.leitura == "mais no top" and t.valor in FORMATO_DO_TIPO]
    return (em_alta or ["reels", "carrossel"])[:3]


CARACTERISTICAS_FORA_DA_GERACAO = {"mensagem_generica"}


def _padroes_relevantes(findings: list[Finding], plataforma: str) -> list[Finding]:
    # A frase motivacional genérica engaja no orgânico, mas o histórico de anúncios da Stone mostra que não gera clique
    # e o gerador a proíbe: ela aparece no Início como achado, mas não orienta a criação.
    fortes = [f for f in findings if f.plataforma == plataforma and f.leitura in ("mais no top", "menos no top")
              and f.caracteristica not in CARACTERISTICAS_FORA_DA_GERACAO]
    return fortes[:8]


def construir_grafo(base: fx.Base, client, limiares, juiz=None, ao_evento=None):
    """`ao_evento(tipo, dados)` recebe cada etapa enquanto acontece (o painel ao vivo do app usa isso)."""
    avisar = ao_evento or (lambda tipo, dados: None)

    def dados(estado: Estado) -> Estado:
        e = estado["entrada"]
        plat, faixa = e.filters.plataforma, e.filters.faixa
        findings = fx.query_stats(base, plat, e.segment, faixa)
        trends = fx.format_trends(base, "instagram", e.segment) if plat in (None, "instagram") else []
        refs = fx.search_posts(base, plat, e.segment, k=5)
        registro = {"ferramentas": ["query_stats", "format_trends", "search_posts", "load_stone_context"]}
        return {"contexto": fx.contexto_da_conta(e.conta), "findings": findings, "trends": trends, "refs": refs,
                "registro": registro}

    def gerar_no(estado: Estado) -> Estado:
        e, criativos, erros, refs_todas = estado["entrada"], [], [], list(estado["refs"])
        reescritas = int(limiares.req("reescritas_maximas"))
        for formato in escolher_formatos(e, estado["trends"]):
            plataforma = PLATAFORMA_DO_FORMATO[formato]
            achados, refs, reserva = fx.evidencia_com_reserva(base, plataforma, e.segment, TIPO_NA_BASE[formato])
            refs_todas += [r for r in refs if r.post_id not in {x.post_id for x in refs_todas}]
            padroes = _padroes_relevantes(achados if reserva else estado["findings"], plataforma)
            avisar("dados", {"formato": formato, "plataforma": plataforma, "reserva_geral": reserva,
                             "padroes": [p.model_dump() for p in padroes], "referencias": [r.model_dump() for r in refs]})
            feedback, criativo, conferencias, falhas = None, None, {}, []
            for tentativa in range(reescritas + 1):
                avisar("escrevendo", {"tentativa": tentativa + 1, "formato": formato})
                try:
                    criativo = gerar(client, e.query, formato, e.segment, padroes, refs, estado["contexto"],
                                     verbos_permitidos(), feedback, tentativa)
                except InvalidLLMOutput as exc:
                    falhas, feedback = [str(exc)[:200]], "responda exatamente no formato JSON pedido"
                    avisar("conferencias", {"tentativa": tentativa + 1, "conferencias": {}, "falhas": falhas})
                    continue
                avisar("rascunho", {"tentativa": tentativa + 1, "criativo": criativo.model_dump()})
                conferencias, falhas = conferir(criativo, {r.post_id for r in refs}, limiares)
                avisar("conferencias", {"tentativa": tentativa + 1, "conferencias": conferencias, "falhas": falhas})
                if not falhas:
                    break
                feedback = "; ".join(falhas)
            if criativo is None:   # nenhuma tentativa produziu JSON válido: registra o motivo em vez de sumir
                erros.append(f"{formato}: não saiu depois de {reescritas + 1} tentativas ({'; '.join(falhas)[:300]})")
                continue
            avaliacao = None
            if juiz is not None and not falhas:
                oferta, marca = estado["contexto"].get("oferta", {}), estado["contexto"].get("marca", "Impulso Stone").upper()
                bloco = "\n".join([f"O QUE A {marca} OFERECE: {'; '.join(oferta.get('oferece', []))}",
                                   f"O QUE A {marca} NÃO OFERECE: {'; '.join(oferta.get('nao_oferece', []))}"] +
                                  [f"- {p.caracteristica}={p.valor}: {p.leitura}" for p in padroes] +
                                  [f"- post {r.post_id}: {r.titulo_ou_trecho}" for r in refs])
                texto = "\n".join([f"Caso: {criativo.caso}", criativo.gancho, *criativo.corpo, criativo.legenda, criativo.cta])
                avisar("avaliando", {})
                juiz_kwargs = {"level": e.segment or "geral", "formato": formato, "assertions_block": bloco}
                avaliacao = avaliar_com_seguranca(juiz, texto, **juiz_kwargs)
                avisar("juiz", {"juiz": avaliacao})
            melhoria = None
            if avaliacao is not None and precisa_melhorar(avaliacao, float(limiares.get("juiz_nota_alvo_criterio") or 7)):
                criativo_antes = criativo
                criativo, conf_nova, avaliacao, melhoria = melhorar_com_juiz(
                    criativo, avaliacao, ids_referencia={r.post_id for r in refs}, juiz=juiz, limiares=limiares,
                    juiz_kwargs=juiz_kwargs, avisar=avisar,
                    gerar_versao=lambda fb, t: gerar(client, e.query, formato, e.segment, padroes, refs, estado["contexto"],
                                                     verbos_permitidos(), fb, t))
                if criativo is not criativo_antes and conf_nova is not None:
                    conferencias = conf_nova
                tentativa += len(melhoria["rodadas"])
            criativos.append(CreativeAvaliado(
                criativo=criativo, conferencias=conferencias, falhas=falhas, tentativas=tentativa + 1, juiz=avaliacao,
                aprovado_automatico=not falhas and (avaliacao is None or avaliacao.get("aprovado", False)),
                melhoria_juiz=melhoria))
        return {"criativos": criativos, "erros": erros, "refs": refs_todas}

    def embaixador(estado: Estado) -> Estado:
        e = estado["entrada"]
        criadores, indicados = fx.creator_scorecard(base, e.segment)
        return {"creators": criadores, "indicados": indicados}

    def explicar(estado: Estado) -> Estado:
        e = estado["entrada"]
        fortes = [f for f in estado["findings"] if f.leitura in ("mais no top", "menos no top")]
        frases = []
        for f in fortes[:5]:
            sentido = "aparece mais" if f.leitura == "mais no top" else "aparece menos"
            frases.append(f"No {f.plataforma.capitalize()}, {f.caracteristica.replace('_', ' ')} = {f.valor} {sentido} "
                          f"nos posts que mais engajam ({f.pct_top:.0%} contra {f.pct_controle:.0%} no grupo controle, "
                          f"em {f.n_perfis} perfis).")
        if not frases:
            frases.append("Nenhum padrão se sustenta com segurança neste recorte: os resultados ainda são inconclusivos.")
        refs_ok = len(estado["refs"]) >= 3
        confianca_baixa = not any(f.leitura == "mais no top" for f in fortes) or not refs_ok
        if confianca_baixa:
            frases.append("Atenção: poucos posts sustentam as conclusões deste recorte (confidence_flag).")
        if e.segment:
            frases.insert(0, f"Recorte: segmento {e.segment}.")
        return {"explanation": " ".join(frases), "confidence_flag": confianca_baixa}

    g = StateGraph(Estado)
    g.add_node("dados", dados)
    g.add_node("gerar", gerar_no)
    g.add_node("explicar", explicar)
    g.add_node("embaixador", embaixador)
    g.add_edge(START, "dados")

    def rota(s: Estado) -> str:
        if s["entrada"].mode in ("gerar_criativo", "gerar_pacote"):
            return "gerar"
        return "embaixador" if s["entrada"].mode == "buscar_embaixador" else "explicar"
    g.add_conditional_edges("dados", rota, {"gerar": "gerar", "embaixador": "embaixador", "explicar": "explicar"})
    g.add_edge("gerar", "explicar")
    g.add_edge("embaixador", "explicar")
    g.add_edge("explicar", END)
    return g.compile()


def run_agent(entrada: AgentInput, base: Optional[fx.Base] = None, client=None, coleta: Optional[Path] = None,
              registro: Optional[Path] | str = "padrao", ao_evento=None) -> AgentOutput:
    """Função Python do agente (entregável do TAPI); o servidor MCP chama esta mesma função."""
    from src.evaluation.judge import LLMJudge
    from src.shared.llm_client import LLMClient

    limiares = load_thresholds(ROOT / "config" / "limiares.yaml")
    if registro == "padrao":  # None = não registrar; BOAPAUTA_RUNS permite aos testes gravar fora do registro real
        registro = Path(os.getenv("BOAPAUTA_RUNS") or ROOT / "data" / "processed" / "agent_runs.jsonl")
    if base is None:
        coleta = coleta or max((p for p in (ROOT / "data" / "raw").iterdir() if p.is_dir() and p.name[:4].isdigit()), key=lambda p: p.name)
        base = fx.Base.carregar(coleta)
    if client is None and entrada.mode in ("gerar_criativo", "gerar_pacote"):
        client = LLMClient()
    juiz = LLMJudge(llm_client=client, thresholds=limiares) if entrada.usar_juiz and client is not None else None
    inicio = time.time()
    estado = construir_grafo(base, client, limiares, juiz, ao_evento).invoke({"entrada": entrada})
    saida = AgentOutput(findings=estado["findings"], reference_posts=estado["refs"],
                        creatives=estado.get("criativos", []), format_trends=estado.get("trends", []),
                        confidence_flag=estado["confidence_flag"], explanation=estado["explanation"],
                        erros=estado.get("erros", []), creators=estado.get("creators", []),
                        indicados=estado.get("indicados", {}))
    if registro is not None:
        append_jsonl(registro, [{
            "run_id": uuid.uuid4().hex[:12], "momento": time.strftime("%Y-%m-%dT%H:%M:%S"), "entrada": entrada.model_dump(),
            "ferramentas": estado.get("registro", {}).get("ferramentas", []),
            "post_ids": [r.post_id for r in saida.reference_posts], "criativos": len(saida.creatives),
            "tentativas": [c.tentativas for c in saida.creatives], "latencia_s": round(time.time() - inicio, 2),
            "juiz": [{"nota": (c.juiz or {}).get("media_ponderada"), "melhoria": c.melhoria_juiz} for c in saida.creatives],
            "chamadas_llm": len(getattr(client, "calls", []) or []) if client is not None else 0}])
    return saida
