"""Conferências determinísticas de cada criativo, antes do juiz e da revisão humana.

Mesma ideia do avaliador do Case Suno: o código decide o que é objetivo (referências existem, CTA presente, sem
promessa exagerada, linguagem simples, tamanho do formato); cada falha vira feedback numérico para a reescrita.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from src.agent.contrato import Creative
from src.evaluation.flesch_ptbr import clareza_ok

ROOT = Path(__file__).resolve().parents[2]
# Tipos de negócio que tornam um caso concreto (o verificador exige pelo menos um no caso ou no roteiro)
NEGOCIOS = ["padaria", "salão", "salao", "mercadinho", "mercado", "loja", "lanchonete", "restaurante", "oficina", "ateliê",
            "atelie", "barbearia", "doceria", "confeitaria", "pet shop", "petshop", "food truck", "açougue", "acougue",
            "brechó", "brecho", "hamburgueria", "pizzaria", "sorveteria", "papelaria", "manicure", "cabeleireir",
            "costureira", "marmita", "quitanda", "feira", "ambulante", "entregador", "motorista", "motoboy", "borracharia",
            "lava-jato", "lava jato", "consultório", "academia", "bar ", "distribuidora", "floricultura", "marcenaria",
            "delivery", "ótica", "otica", "bolo", "brigadeiro", "doces", "salgados", "costura", "estética", "estetica",
            "clínica", "clinica", "mecânic", "mecanic", "vendedor", "vendedora", "artesã", "artesa", "sacolão", "empório"]
LIMITES_CORPO = {"reels": (3, 6), "short": (3, 6), "carrossel": (5, 7), "estatico": (1, 2), "stories": (3, 5)}
DURACAO_MAX = {"reels": 60, "short": 60}


@lru_cache(maxsize=1)
def _config() -> tuple[list[str], list[str], list[str]]:
    verbos = yaml.safe_load((ROOT / "config" / "verbos_acao.yaml").read_text(encoding="utf-8"))
    proibidos = yaml.safe_load((ROOT / "config" / "termos_proibidos.yaml").read_text(encoding="utf-8"))
    imperativos = [i.lower() for lista in (verbos.get("imperativos") or {}).values() for i in lista]
    return imperativos, [t.lower() for t in proibidos.get("termos") or []], list(proibidos.get("padroes") or [])


def verbos_permitidos() -> list[str]:
    return _config()[0]


def _sem_acento(texto: str) -> str:
    import unicodedata
    base = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in base if not unicodedata.combining(c))


@lru_cache(maxsize=1)
def _afirmacoes_proibidas() -> list[str]:
    contexto = yaml.safe_load((ROOT / "config" / "stone_context.yaml").read_text(encoding="utf-8")) or {}
    return [a.lower() for a in contexto.get("afirmacoes_proibidas") or []]


def conferir(criativo: Creative, ids_referencia: set[str], limiares) -> tuple[dict[str, bool], list[str]]:
    """Devolve (conferências, falhas). Cada falha é uma instrução objetiva de correção."""
    imperativos, termos, padroes = _config()
    texto = " ".join([criativo.titulo, criativo.gancho, *criativo.corpo, *criativo.texto_tela, criativo.legenda, criativo.cta])
    texto_min = texto.lower()
    falhas: list[str] = []

    refs_ok = bool(criativo.reference_post_ids) and set(criativo.reference_post_ids) <= ids_referencia
    if not refs_ok:
        falhas.append("reference_post_ids precisa ter só ids da lista de posts de referência, e pelo menos um")

    cta = criativo.cta.strip().lower()
    cta_ok = any(cta.startswith(v) or re.search(rf"\b{re.escape(v)}\b", cta) for v in imperativos)
    if not cta_ok:
        falhas.append(f"cta precisa começar com um verbo da lista (ex.: {', '.join(imperativos[:4])}); veio: '{criativo.cta}'")

    achados = [t for t in termos if t in texto_min] + [p for p in padroes if re.search(p, texto_min)]
    sem_promessa = not achados
    if achados:
        falhas.append(f"retire promessas ou termos proibidos: {achados[:3]}")

    # Fidelidade à oferta: o Impulso é um programa de educação; não faz pagamento nem garante crédito
    sem_acento = _sem_acento(texto_min)
    indevidas = [a for a in _afirmacoes_proibidas() if a in sem_acento]
    fiel_a_oferta = not indevidas
    if indevidas:
        falhas.append(f"o Impulso Stone é um programa de educação e mentoria; retire afirmações sobre o que ele não "
                      f"oferece: {indevidas[:3]}")

    passou_clareza, valor = clareza_ok(" ".join([criativo.legenda, *criativo.corpo]), limiares)
    if not passou_clareza:
        falhas.append(f"clareza={valor} abaixo de {limiares.req('clareza_flesch_min')}: use frases mais curtas e palavras simples")

    minimo, maximo = LIMITES_CORPO.get(criativo.formato, (1, 10))
    tamanho_ok = minimo <= len(criativo.corpo) <= maximo
    if not tamanho_ok:
        falhas.append(f"'corpo' precisa ter de {minimo} a {maximo} itens para {criativo.formato}; veio {len(criativo.corpo)}")
    if criativo.formato in DURACAO_MAX and (criativo.duracao_s or 0) > DURACAO_MAX[criativo.formato]:
        tamanho_ok = False
        falhas.append(f"duracao_s precisa ser no máximo {DURACAO_MAX[criativo.formato]}")

    caso = (criativo.caso or "").strip()
    texto_caso = (caso + " " + texto_min).lower()
    caso_ok = len(caso) >= 40 and any(n in texto_caso for n in NEGOCIOS)
    if not caso_ok:
        falhas.append("falta um caso concreto: em 'caso', descreva um pequeno negócio real (ex.: padaria, salão, "
                      "mercadinho), a dor específica e o que acontece se nada mudar; e construa as cenas ou slides "
                      "em cima desse caso")

    contas = [m.group(0) for p in CONTAS for m in [re.search(p, texto_min)] if m]
    sem_contas = not contas
    if contas:
        falhas.append(f"retire as contas e fórmulas (um erro de conta numa peça da Stone é grave): {contas[:2]}; "
                      "mostre o passo sem calcular, ex.: 'anote todos os custos antes de definir o preço'")

    conferencias = {"referencias_existem": refs_ok, "caso_concreto": caso_ok, "cta_presente": cta_ok, "sem_promessa_exagerada": sem_promessa,
                    "fiel_a_oferta": fiel_a_oferta, "sem_contas": sem_contas,
                    "linguagem_simples": passou_clareza, "tamanho_do_formato": tamanho_ok}
    return conferencias, falhas


# Instruções de conta que o gerador não pode ensinar (o juiz deu 10 para "multiplique por 1,2 para 20% de margem")
CONTAS = [
    r"\b(custo|pre[çc]o|valor)\s*[+×x*]\s*\d",                              # "custo + 30%", "preço x 2"
    r"\bmultipli\w+\s+(o|a|os|as|por|pelo|pela)\b",                        # "multiplique por 1,2"
    r"\b(some|adicione|acrescente|coloque|aplique)\s+(mais\s+)?\d+\s*%",   # "adicione 30%"
    r"\b(divida|divide)\s+(o|a|por)\b",
    r"\d+\s*%\s*(de\s+)?(margem|lucro|markup|sobre o custo)",             # "30% de margem"
    r"\b(margem|markup|lucro)\s+de\s+\d+\s*%",
]


def conferir_texto(texto: str, limiares, chave_clareza: str = "clareza_guia_min") -> list[str]:
    """Conferências de um texto livre (guia detalhado): promessas e termos proibidos, fidelidade à oferta e clareza."""
    _, termos, padroes = _config()
    minusculo = texto.lower()
    falhas = []
    achados = [t for t in termos if t in minusculo] + [p for p in padroes if re.search(p, minusculo)]
    if achados:
        falhas.append(f"retire promessas ou termos proibidos: {achados[:3]}")
    indevidas = [a for a in _afirmacoes_proibidas() if a in _sem_acento(minusculo)]
    if indevidas:
        falhas.append(f"o Impulso Stone é um programa de educação e mentoria; retire: {indevidas[:3]}")
    from src.evaluation.flesch_ptbr import flesch_reading_ease_pt
    minimo = float(limiares.req(chave_clareza))
    valor = round(flesch_reading_ease_pt(texto), 1)
    if valor < minimo:
        from src.evaluation.flesch_ptbr import count_syllables
        longas = sorted({w for w in re.findall(r"[a-záéíóúâêôãõàüç]+", texto.lower()) if count_syllables(w) >= 4},
                        key=lambda w: -count_syllables(w))[:10]
        falhas.append(f"clareza={valor} abaixo de {minimo:g}: frases de até 12 palavras e troque palavras longas por "
                      f"curtas (ex.: 'usar' e não 'utilizar'). Palavras longas no texto: {', '.join(longas)}")
    return falhas
