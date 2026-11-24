"""Da peça de carrossel aprovada (texto) aos slides em PNG no visual Impulso.

O roteiro do modelo vem em frases ("Crie uma conta só para a empresa (na tela: “1. Conta separada”)"). Aqui cada
item vira um slide com título curto em destaque (o texto de tela, quando existe) e a frase de apoio menor. Prefixos
que o template já mostra ("Slide 2:", "1.", "Capa:") saem, e um item que só repete a capa é pulado. Se o texto não
couber no slide, ele é refeito só com o título: nada sai cortado no meio da frase.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from src.rendering.playwright_renderer import PlaywrightCarouselRenderer

ROOT = Path(__file__).resolve().parents[2]
PASTA = ROOT / "data" / "exports"
TELA = re.compile(r"\s*\(na tela:\s*[“\"](.+?)[”\"]\)\s*", re.I)
PREFIXO = re.compile(r"^\s*((capa|slide|tela|cena)\s*\d*\s*[:\-–]\s*|\d+\s*[-–]\s*\d+\s*s\s*:\s*|\d+[.)]\s*"
                     r"|[0-9#*]️?⃣\s*|🔟\s*)+", re.I)   # inclui emojis numéricos (1️⃣, 🔟)
MAX_TITULO = 90


def _limpo(texto: str) -> str:
    return PREFIXO.sub("", str(texto or "")).strip().strip("“”\"").strip()


def _parecidos(a: str, b: str) -> bool:
    a, b = re.sub(r"\W+", " ", a.lower()).strip(), re.sub(r"\W+", " ", b.lower()).strip()
    return bool(a) and bool(b) and (a in b or b in a)


def _titulo_e_apoio(item: str, tela: str = "") -> tuple[str, str]:
    achado = TELA.search(item)
    if achado and not tela:
        tela = achado.group(1)
    fala = _limpo(TELA.sub(" ", item))
    tela = _limpo(tela)
    if tela and len(tela) <= MAX_TITULO:
        return tela, ("" if _parecidos(tela, fala) else fala)
    frases = re.split(r"(?<=[.!?])\s+", fala, maxsplit=1)
    if len(frases) == 2 and len(frases[0]) <= MAX_TITULO:
        return frases[0], frases[1]
    return fala, ""


def montar_slides(criativo: dict) -> list[dict]:
    corpo = list(criativo.get("corpo") or [])
    telas = list(criativo.get("texto_tela") or [])
    slides = [{"role": "capa", "title": _limpo(criativo.get("titulo", "")), "body": _limpo(criativo.get("gancho", ""))}]
    itens = []
    for i, item in enumerate(corpo):
        bruto = str(item)
        if re.match(r"^\s*capa\b", bruto, re.I) or _parecidos(_limpo(TELA.sub(" ", bruto)), criativo.get("gancho", "")):
            continue                                       # repete a capa
        titulo, apoio = _titulo_e_apoio(bruto, telas[i] if i < len(telas) else "")
        if titulo:
            itens.append((titulo, apoio))
    for titulo, apoio in itens[:-1]:
        slides.append({"role": "corpo", "title": titulo, "body": apoio})
    if itens:
        titulo, apoio = itens[-1]
        slides.append({"role": "cta", "title": titulo, "body": apoio, "cta": criativo.get("cta", "")})
    else:
        slides.append({"role": "cta", "title": _limpo(criativo.get("titulo", "")), "cta": criativo.get("cta", "")})
    return slides


def renderizar_peca(peca: dict) -> list[Path]:
    """PNGs da versão atual da peça (cache por versão: uma nova versão gera slides novos)."""
    versao = hashlib.sha1(f"{peca['id']}|{peca['atualizado_em']}".encode()).hexdigest()[:8]
    destino = PASTA / f"peca_{peca['id']}_{versao}"
    prontos = sorted(destino.glob("slide_*.png")) if destino.exists() else []
    if prontos:
        return prontos
    slides = montar_slides(peca["atual"]["criativo"])
    if peca["atual"].get("conta") == "stone":              # peça da marca Stone: assina como stone, não como Impulso
        slides = [{**s, "assinatura": "stone"} for s in slides]
    renderizador = PlaywrightCarouselRenderer(PASTA)
    resultado = renderizador.render({"slides": slides}, basename=destino.name)
    if resultado.overflow:                                 # não coube: refaz esses slides só com o título
        for indice in resultado.overflow:
            slides[indice - 1] = {**slides[indice - 1], "body": ""}
        resultado = renderizador.render({"slides": slides}, basename=destino.name)
    return resultado.paths
