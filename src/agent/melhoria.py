"""Ciclo de melhora pelo juiz: quando o avaliador independente aponta critérios fracos, o agente reescreve
usando o retorno dele, o juiz avalia de novo e fica a versão com a nota maior.

Antes, o juiz só dava a nota final: a reescrita automática acontecia apenas nas conferências determinísticas.
Gatilho (config/limiares.yaml): peça reprovada pelo juiz ou algum critério abaixo de juiz_nota_alvo_criterio.
Limite: reescritas_pelo_juiz (cada uma custa uma geração e uma avaliação). Antes e depois ficam registrados
na peça e em data/processed/agent_runs.jsonl, para medir se o retorno do juiz melhora os criativos.
"""
from __future__ import annotations

from typing import Callable, Optional

from src.agent.verificador import conferir
from src.evaluation.judge import JudgeResult, avaliar_com_seguranca
from src.shared.llm_client import InvalidLLMOutput


def precisa_melhorar(avaliacao: Optional[dict], nota_alvo: float) -> list[str]:
    """Critérios abaixo do alvo (ou todos os reprovados); vazio quando não há o que melhorar ou o juiz falhou."""
    if not avaliacao or avaliacao.get("erro") or not avaliacao.get("scores"):
        return []
    fracos = [k for k, v in avaliacao["scores"].items() if v < nota_alvo]
    if not avaliacao.get("aprovado") and not fracos:
        fracos = list(avaliacao.get("criterios_abaixo_do_minimo") or [])
    return fracos


def texto_para_juiz(criativo) -> str:
    return "\n".join([f"Caso: {criativo.caso}", criativo.gancho, *criativo.corpo, criativo.legenda, criativo.cta])


def melhorar_com_juiz(criativo, avaliacao: dict, *, gerar_versao: Callable[[str, int], object], ids_referencia: set,
                      juiz, limiares, juiz_kwargs: dict, avisar: Callable = lambda tipo, dados: None) -> tuple:
    """Devolve (criativo, conferencias, avaliacao, registro). `gerar_versao(feedback, tentativa)` chama o gerador."""
    nota_alvo = float(limiares.get("juiz_nota_alvo_criterio") or 7)
    rodadas = int(limiares.get("reescritas_pelo_juiz") or 1)
    media_minima = float(limiares.req("juiz_media_minima"))
    melhor, melhor_av, melhor_conf = criativo, avaliacao, None
    registro = {"antes": avaliacao.get("media_ponderada"), "criterios_antes": dict(avaliacao.get("scores") or {}),
                "rodadas": [], "mantida": "original"}
    for r in range(rodadas):
        fracos = precisa_melhorar(melhor_av, nota_alvo)
        if not fracos:
            break
        retorno = JudgeResult(**melhor_av).feedback(media_minima, nota_alvo)
        feedback = ("O avaliador independente leu a versão anterior e apontou o que melhorar. Mantenha o que está bom "
                    f"e melhore principalmente: {', '.join(fracos)}.\n{retorno}\nVersão anterior: {melhor.model_dump_json()}")
        avisar("feedback_juiz", {"nota": melhor_av.get("media_ponderada"), "criterios": fracos})
        avisar("escrevendo", {"tentativa": f"juiz {r + 1}"})
        try:
            nova = gerar_versao(feedback, 100 + r)
        except (InvalidLLMOutput, RuntimeError) as exc:   # saída fora do formato ou cota do modelo: fica a versão atual
            registro["rodadas"].append({"erro": str(exc)[:200]})
            break
        avisar("rascunho", {"tentativa": f"juiz {r + 1}", "criativo": nova.model_dump()})
        conferencias, falhas = conferir(nova, ids_referencia, limiares)
        avisar("conferencias", {"tentativa": f"juiz {r + 1}", "conferencias": conferencias, "falhas": falhas})
        if falhas:                                    # a versão nova quebrou uma regra: fica a anterior
            registro["rodadas"].append({"descartada": "não passou nas conferências", "falhas": falhas})
            continue
        avisar("avaliando", {})
        nova_av = avaliar_com_seguranca(juiz, texto_para_juiz(nova), **juiz_kwargs)
        avisar("juiz", {"juiz": nova_av})
        if nova_av.get("erro"):                          # o juiz não conseguiu avaliar: sem nota, não dá para comparar
            registro["rodadas"].append({"descartada": "o avaliador não conseguiu dar nota", "erro": nova_av["erro"][:200]})
            break
        depois = nova_av.get("media_ponderada")
        antes_sc, novo_sc = melhor_av.get("scores") or {}, nova_av.get("scores") or {}
        # não troca um problema por outro: a reescrita não pode criar um critério fraco que antes estava bom
        novos_fracos = [k for k, v in novo_sc.items() if v < nota_alvo and antes_sc.get(k, 0) >= nota_alvo]
        registro["rodadas"].append({"nota": depois, "criterios": dict(novo_sc),
                                    **({"descartada": f"criou critério fraco: {', '.join(novos_fracos)}"} if novos_fracos else {})})
        if depois is not None and depois > (melhor_av.get("media_ponderada") or 0) and not novos_fracos:
            melhor, melhor_av, melhor_conf = nova, nova_av, conferencias
            registro["mantida"] = f"reescrita {r + 1}"
    registro["depois"] = melhor_av.get("media_ponderada")
    return melhor, melhor_conf, melhor_av, registro
