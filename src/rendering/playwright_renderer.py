"""Renderização do carrossel com Playwright, sem LLM (herdado do Case Suno, visual trocado para o Impulso).

- Template HTML/CSS em src/rendering/templates/carrossel.html, com tokens de config/tokens_visuais.yaml.
- Fontes carregadas dos arquivos do projeto (embutidas em base64); espera document.fonts.ready.
- Mede se o texto coube em cada campo (scrollHeight > max-height) e o contraste texto/fundo (WCAG).
- Um PNG 1080×1350 por slide, numerados, e ZIP para exportação.

Papéis de slide: "capa" (gancho), "corpo" (um passo ou ponto por slide) e "cta" (próximo passo).
"""
from __future__ import annotations

import base64
import html
import io
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from string import Template
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = Path(__file__).resolve().parent / "templates" / "carrossel.html"

# Texto que não coube: altura do conteúdo acima do limite do campo (max-height do CSS). Folga de 12 px para acentos.
FIT_SCRIPT = """() => Array.from(document.querySelectorAll('h1, h2, .apoio, .texto, .cta')).filter(el => {
  const limit = parseFloat(getComputedStyle(el).maxHeight);
  return !isNaN(limit) && el.scrollHeight > limit + 12;
}).map(el => (el.tagName.toLowerCase() + '.' + el.className.replace(/\\s*ajuste\\s*/, '')).replace(/\\.$/, ''))"""

# Fundo de cada papel; os slides de corpo alternam entre verde e escuro para dar ritmo ao carrossel.
BACKGROUNDS = {"capa": "lima", "cta": "lima"}
BODY_CYCLE = ("verde", "escuro")


@dataclass
class RenderResult:
    paths: list[Path] = field(default_factory=list)
    overflow: dict[int, list[str]] = field(default_factory=dict)   # slide -> campos em que o texto não coube
    contrast: dict[str, float] = field(default_factory=dict)        # par de cores -> razão de contraste

    @property
    def fits(self) -> bool:
        return not self.overflow


@lru_cache(maxsize=1)
def load_tokens(path: str = "config/tokens_visuais.yaml") -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8")) or {}


def _font_faces(tokens: dict) -> str:
    family = tokens["fonte"]["familia"]
    faces = []
    for weight, file in sorted((tokens["fonte"].get("arquivos") or {}).items()):
        data = base64.b64encode((ROOT / file).read_bytes()).decode()
        faces.append(f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;"
                     f"src:url(data:font/ttf;base64,{data}) format('truetype');}}")
    return "\n".join(faces)


def contrast_ratio(foreground: str, background: str) -> float:
    def luminance(hex_color: str) -> float:
        hex_color = hex_color.lstrip("#")
        channels = [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return round((high + 0.05) / (low + 0.05), 2)


def _field(slide: Any, name: str):
    return slide.get(name) if isinstance(slide, dict) else getattr(slide, name, None)


def background_for(role: str, index: int) -> str:
    if role in BACKGROUNDS:
        return BACKGROUNDS[role]
    return BODY_CYCLE[(index - 2) % len(BODY_CYCLE)]


def build_slide_html(slide: Any, index: int, total: int) -> str:
    tokens = load_tokens()
    colors = tokens["cores"]
    role = _field(slide, "role") or "corpo"
    title = html.escape(_field(slide, "title") or "")
    body = html.escape(_field(slide, "body") or "")
    highlight = html.escape(_field(slide, "highlight_data") or "")
    cta = html.escape(_field(slide, "cta") or "")
    background = background_for(role, index)
    if role == "capa":
        middle = f'<h1 class="ajuste">{title}</h1>' + (f'<p class="apoio ajuste">{body}</p>' if body else "")
    elif role == "cta":
        middle = (f'<h2 class="ajuste">{title}</h2>' + (f'<p class="texto ajuste">{body}</p>' if body else "")
                  + (f'<span class="cta ajuste">{cta}</span>' if cta else ""))
    else:
        number = highlight or f"{index - 1:02d}"
        middle = (f'<div class="numero">{number}</div><h2 class="ajuste">{title}</h2>'
                  + (f'<p class="texto ajuste">{body}</p>' if body else ""))
    values = {
        "font_faces": _font_faces(tokens), "familia": tokens["fonte"]["familia"],
        "lima": colors["lima"], "verde": colors["verde"], "escuro": colors["escuro"], "branco": colors["branco"],
        "tinta": colors["tinta"], "verde_texto": colors["verde_texto"],
        "margem": tokens["slides"]["margem_px"], "largura": tokens["slides"]["largura_px"],
        "altura": tokens["slides"]["altura_px"], "tipo": role, "fundo": background,
        "assinatura": html.escape(_field(slide, "assinatura") or tokens.get("assinatura", "impulso stone")).replace(" ", "<br>", 1),
        "pagina": f"{index}/{total}", "miolo": middle,
        "seguir": "" if index == total else '<span class="seguir">ARRASTE</span>',
    }
    return Template(TEMPLATE.read_text(encoding="utf-8")).substitute(values)


def contrast_report(colors: dict) -> dict[str, float]:
    return {
        "tinta_sobre_lima": contrast_ratio(colors["tinta"], colors["lima"]),
        "branco_sobre_verde": contrast_ratio(colors["branco"], colors["verde"]),
        "branco_sobre_escuro": contrast_ratio(colors["branco"], colors["escuro"]),
        "lima_sobre_escuro": contrast_ratio(colors["lima"], colors["escuro"]),
    }


class PlaywrightCarouselRenderer:
    def __init__(self, output_dir: str | Path = "data/exports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def render(self, carousel: Any, basename: str = "carrossel") -> RenderResult:
        from playwright.sync_api import sync_playwright

        slides = list(_field(carousel, "slides") or [])
        target = self.output_dir / basename
        target.mkdir(parents=True, exist_ok=True)
        tokens = load_tokens()
        width, height = tokens["slides"]["largura_px"], tokens["slides"]["altura_px"]
        result = RenderResult(contrast=contrast_report(tokens["cores"]))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            for index, slide in enumerate(slides, start=1):
                page.set_content(build_slide_html(slide, index, len(slides)), wait_until="load")
                page.evaluate("() => document.fonts.ready")
                overflow = page.evaluate(FIT_SCRIPT)
                if overflow:
                    result.overflow[index] = overflow
                path = target / f"slide_{index:02d}.png"
                page.screenshot(path=str(path), type="png")
                result.paths.append(path)
            browser.close()
        return result


def zip_slides(paths: list[Path]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, arcname=path.name)
    return buffer.getvalue()
