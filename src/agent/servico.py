"""Serviços do app sobre o agente: proposta (sem LLM), criar peça (com LLM), pedir ajuste e aprovar.

A proposta mostra o que o agente vai fazer (formato, padrões, referências, horário) usando só a base: o modelo de
linguagem só entra quando alguém clica em "Criar este post". Isso evita gastar tokens com ideias descartadas.
"""
from __future__ import annotations

from typing import Optional

from src.agent import ferramentas as fx
from src.agent.contrato import AgentInput, Creative, Filtros
from src.agent.gerador import gerar
from src.agent.grafo import FORMATO_DO_TIPO, PLATAFORMA_DO_FORMATO, TIPO_NA_BASE, _padroes_relevantes, run_agent
from src.agent.melhoria import melhorar_com_juiz, precisa_melhorar
from src.agent.verificador import conferir, verbos_permitidos
from src.app_store import Store
from src.evaluation.judge import LLMJudge, avaliar_com_seguranca
from src.evaluation.thresholds import load_thresholds
from src.shared.llm_client import InvalidLLMOutput, LLMClient

LIMIARES_CAMINHO = fx.ROOT / "config" / "limiares.yaml"


def formato_sugerido(base: fx.Base, segmento: Optional[str]) -> str:
    em_alta = [FORMATO_DO_TIPO[t.valor] for t in fx.format_trends(base, "instagram", segmento)
               if t.leitura == "mais no top" and t.valor in FORMATO_DO_TIPO]
    return em_alta[0] if em_alta else "reels"


def proposta(base: fx.Base, objetivo: str, segmento: Optional[str] = None, formato: Optional[str] = None) -> dict:
    """O que o agente faria, sem chamar o LLM."""
    formato = formato or formato_sugerido(base, segmento)
    plataforma = PLATAFORMA_DO_FORMATO[formato]
    achados, refs, reserva = fx.evidencia_com_reserva(base, plataforma, segmento, TIPO_NA_BASE[formato])
    padroes = _padroes_relevantes(achados, plataforma)
    return {"objetivo": objetivo, "segmento": segmento, "formato": formato, "plataforma": plataforma,
            "padroes": [p.model_dump() for p in padroes], "referencias": [r.model_dump() for r in refs],
            "reserva_geral": reserva,
            "pouca_evidencia": len(refs) < 3 or not any(p.leitura == "mais no top" for p in padroes)}


def criar_peca(store: Store, base: fx.Base, objetivo: str, formato: str, segmento: Optional[str] = None,
               data_agenda: Optional[str] = None, horario: Optional[str] = None, client=None, ao_evento=None,
               conta: str = "impulsostone") -> dict:
    """Gera a peça com o agente (geração, conferências, reescrita e juiz) e guarda para revisão."""
    saida = run_agent(AgentInput(mode="gerar_criativo", query=objetivo, segment=segmento,
                                 filters=Filtros(plataforma=PLATAFORMA_DO_FORMATO[formato]), formatos=[formato],
                                 usar_juiz=True, conta=conta), base=base, client=client, ao_evento=ao_evento)
    if not saida.creatives:
        atual = {"erros": saida.erros, "referencias": [r.model_dump() for r in saida.reference_posts], "conta": conta}
        return store.criar(formato, objetivo, atual, segmento, data_agenda, horario, status="falhou")
    c = saida.creatives[0]
    ids = set(c.criativo.reference_post_ids)
    atual = {**c.model_dump(), "conta": conta, "referencias": [r.model_dump() for r in saida.reference_posts if r.post_id in ids],
             "padroes": [f.model_dump() for f in _padroes_relevantes(saida.findings, PLATAFORMA_DO_FORMATO[formato])][:6]}
    return store.criar(formato, objetivo, atual, segmento, data_agenda, horario)


def aprovar(store: Store, peca_id: str, quem: str = "equipe Stone") -> dict:
    return store.registrar(peca_id, "aprovada", {"acao": "aprovar", "quem": quem})


def pedir_ajuste(store: Store, base: fx.Base, peca_id: str, motivo: str, categoria: str = "", client=None,
                 quem: str = "equipe Stone", ao_evento=None) -> dict:
    """Gera uma nova versão seguindo o pedido da pessoa; a versão anterior e o motivo ficam no histórico."""
    peca = store.obter(peca_id)
    if peca is None:
        raise KeyError(peca_id)
    limiares = load_thresholds(LIMIARES_CAMINHO)
    client = client or LLMClient()
    formato = peca["formato"]
    plataforma = PLATAFORMA_DO_FORMATO[formato]
    refs = [fx.RefPost(**r) for r in peca["atual"].get("referencias", [])] or fx.search_posts(base, plataforma, peca["segmento"], k=5)
    padroes = _padroes_relevantes(fx.query_stats(base, plataforma, peca["segmento"]), plataforma)
    anterior = peca["atual"].get("criativo")
    conta = peca["atual"].get("conta", "impulsostone")
    contexto = fx.contexto_da_conta(conta)
    feedback = f"Pedido da equipe da Stone ({categoria or 'ajuste'}): {motivo}. Versão anterior: {anterior}"
    tentativa_base = 10 + len(peca["historico"])          # tentativas novas não reaproveitam o cache das antigas
    criativo, conferencias, falhas = None, {}, []
    avisar = ao_evento or (lambda tipo, dados: None)
    avisar("dados", {"formato": formato, "plataforma": plataforma, "padroes": [p.model_dump() for p in padroes],
                     "referencias": [r.model_dump() for r in refs]})
    for t in range(int(limiares.req("reescritas_maximas")) + 1):
        avisar("escrevendo", {"tentativa": t + 1, "formato": formato})
        try:
            criativo = gerar(client, peca["objetivo"], formato, peca["segmento"], padroes, refs,
                             contexto, verbos_permitidos(), feedback, tentativa_base + t)
        except InvalidLLMOutput as exc:
            falhas = [str(exc)[:200]]
            continue
        avisar("rascunho", {"tentativa": t + 1, "criativo": criativo.model_dump()})
        conferencias, falhas = conferir(criativo, {r.post_id for r in refs}, limiares)
        avisar("conferencias", {"tentativa": t + 1, "conferencias": conferencias, "falhas": falhas})
        if not falhas:
            break
        feedback = f"Pedido da equipe: {motivo}. Corrija também: {'; '.join(falhas)}"
    decisao = {"acao": "pedir_ajuste", "motivo": motivo, "categoria": categoria, "quem": quem}
    if criativo is None:
        return store.registrar(peca_id, "ajuste", {**decisao, "erro": "; ".join(falhas)})
    juiz, melhoria = None, None
    if not falhas:
        texto = "\n".join([f"Caso: {criativo.caso}", criativo.gancho, *criativo.corpo, criativo.legenda, criativo.cta])
        avisar("avaliando", {})
        avaliador = LLMJudge(llm_client=client, thresholds=limiares)
        juiz_kwargs = {"level": peca["segmento"] or "geral", "formato": formato}
        juiz = avaliar_com_seguranca(avaliador, texto, **juiz_kwargs)
        avisar("juiz", {"juiz": juiz})
        if precisa_melhorar(juiz, float(limiares.get("juiz_nota_alvo_criterio") or 7)):
            antes = criativo
            criativo, conf_nova, juiz, melhoria = melhorar_com_juiz(
                criativo, juiz, ids_referencia={r.post_id for r in refs}, juiz=avaliador, limiares=limiares,
                juiz_kwargs=juiz_kwargs, avisar=avisar,
                gerar_versao=lambda fb, tt: gerar(client, peca["objetivo"], formato, peca["segmento"], padroes, refs,
                                                  contexto, verbos_permitidos(),
                                                  f"Pedido da equipe: {motivo}. {fb}", tentativa_base + tt))
            if criativo is not antes and conf_nova is not None:
                conferencias = conf_nova
    nova = {"criativo": criativo.model_dump(), "conferencias": conferencias, "falhas": falhas, "tentativas": t + 1,
            "juiz": juiz, "aprovado_automatico": not falhas and bool(juiz and juiz.get("aprovado")), "melhoria_juiz": melhoria,
            "conta": conta,
            "referencias": [r.model_dump() for r in refs if r.post_id in set(criativo.reference_post_ids)] or
            peca["atual"].get("referencias", []), "padroes": [f.model_dump() for f in padroes][:6]}   # regra atual
    return store.registrar(peca_id, "revisar", decisao, nova_versao=nova)
