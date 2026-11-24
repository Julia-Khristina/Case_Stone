"""Servidor MCP do BoaPauta: expõe o agente para qualquer cliente MCP (ex.: um assistente de IA no computador do time).

Rodar:   python -m src.servidor_mcp
Config de um cliente MCP (stdio):
    {"mcpServers": {"boapauta": {"command": "python", "args": ["-m", "src.servidor_mcp"], "cwd": "<pasta do projeto>"}}}

Todas as ferramentas chamam o mesmo código da função Python (src.agent.grafo.run_agent e src.agent.ferramentas):
o que o cliente MCP recebe é exatamente o que a API e o app mostram.

Canva: `pecas_aprovadas` entrega o texto de cada peça aprovada separado por slide ou cena (e os PNGs dos carrosséis).
Um assistente conectado ao mesmo tempo a este servidor e ao conector do Canva consegue montar o design no Canva a
partir dessas peças (passo a passo no README, seção "Levar as peças para o Canva").
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from fastmcp import FastMCP

from src.agent import ferramentas as fx
from src.agent.contrato import AgentInput, Filtros
from src.agent.grafo import run_agent as _run_agent
from src.app_store import Store

ROOT = Path(__file__).resolve().parents[1]
mcp = FastMCP("BoaPauta", instructions=(
    "Agente do BoaPauta: descobre o que engaja micro e pequenos empreendedores no Instagram e no YouTube e gera "
    "criativos para o Impulso Stone. Toda resposta traz os posts reais em que se apoia."))


@lru_cache(maxsize=1)
def _base() -> fx.Base:
    coleta = max((p for p in (ROOT / "data" / "raw").iterdir() if p.is_dir() and p.name[:4].isdigit()), key=lambda p: p.name)
    return fx.Base.carregar(coleta)


@mcp.tool
def run_agent(mode: Literal["analisar", "recomendar", "gerar_criativo", "gerar_pacote"], query: str,
              segment: Optional[str] = None, plataforma: Optional[Literal["instagram", "youtube"]] = None,
              faixa: Optional[Literal["micro", "medio", "grande"]] = None,
              formatos: Optional[list[Literal["reels", "carrossel", "estatico", "stories", "short"]]] = None,
              usar_juiz: bool = False, conta: Literal["impulsostone", "stone"] = "impulsostone") -> dict:
    """Contrato do agente (TAPI): analisar o que engaja, recomendar, gerar um criativo ou um pacote de criativos.

    Devolve findings (padrões top × controle com intervalo de confiança), reference_posts (posts reais),
    creatives (com conferências e nota do juiz), confidence_flag e explanation.
    """
    entrada = AgentInput(mode=mode, query=query, segment=segment, filters=Filtros(plataforma=plataforma, faixa=faixa),
                         formatos=formatos, usar_juiz=usar_juiz, conta=conta)
    return _run_agent(entrada, base=_base()).model_dump()


@mcp.tool
def padroes(plataforma: Optional[Literal["instagram", "youtube"]] = None, segment: Optional[str] = None,
            so_confiaveis: bool = True) -> list[dict]:
    """O que aparece mais (ou menos) nos posts que mais engajam do que no grupo controle, por plataforma."""
    achados = fx.query_stats(_base(), plataforma, segment)
    if so_confiaveis:
        achados = [a for a in achados if a.leitura in ("mais no top", "menos no top")]
    return [a.model_dump() for a in achados]


@mcp.tool
def posts_de_referencia(plataforma: Optional[Literal["instagram", "youtube"]] = None, segment: Optional[str] = None,
                        formato: Optional[str] = None, k: int = 5) -> list[dict]:
    """Posts reais do top (um por perfil), ordenados pelo quanto superaram a média do próprio perfil."""
    return [r.model_dump() for r in fx.search_posts(_base(), plataforma, segment, formato, k=k)]


def _store() -> Store:
    import os
    return Store(Path(os.getenv("BOAPAUTA_DB", str(ROOT / "data" / "app" / "boapauta.sqlite"))))


@mcp.tool
def pecas_aprovadas(conta: Optional[Literal["impulsostone", "stone"]] = None, limite: int = 10,
                    com_slides: bool = True) -> list[dict]:
    """Peças aprovadas pela equipe, prontas para produção (ex.: montar o design no Canva).

    Cada peça traz título, caso, partes (um item por slide ou cena, com o texto de tela), legenda, chamada para ação,
    nota do avaliador e quem aprovou. Com com_slides, os carrosséis trazem também os caminhos dos PNGs já no visual
    da marca, para subir no Canva como imagem.
    """
    pecas = [p for p in _store().listar() if p.get("status") == "aprovada" and (p.get("atual") or {}).get("criativo")]
    if conta:
        pecas = [p for p in pecas if (p["atual"].get("conta") or "impulsostone") == conta]
    saida = []
    for p in sorted(pecas, key=lambda x: x.get("atualizado_em") or "", reverse=True)[:max(1, limite)]:
        c, a = p["atual"]["criativo"], p["atual"]
        telas = c.get("texto_tela") or []
        item = {"id": p["id"], "conta": a.get("conta") or "impulsostone", "formato": p["formato"],
                "data_agenda": p.get("data_agenda"), "horario": p.get("horario"), "titulo": c.get("titulo"),
                "caso": c.get("caso"), "gancho": c.get("gancho"),
                "partes": [{"n": i, "texto": t, "texto_tela": telas[i - 1] if i <= len(telas) else None}
                           for i, t in enumerate(c.get("corpo") or [], 1)],
                "legenda": c.get("legenda"), "cta": c.get("cta"),
                "nota_avaliador": (a.get("juiz") or {}).get("media_ponderada"),
                "aprovado_por": next((h.get("quem") for h in reversed(p.get("historico") or []) if h.get("acao") == "aprovar"), None),
                "referencias": [r.get("link") for r in a.get("referencias", []) if r.get("link")]}
        if com_slides and p["formato"] == "carrossel":
            try:
                from src.rendering.carrossel_da_peca import renderizar_peca
                item["slides_png"] = [str(x) for x in renderizar_peca(p)]
            except Exception as exc:  # noqa: BLE001 - sem Playwright, a peça vai só com o texto
                item["slides_png"], item["aviso"] = [], f"slides não gerados: {str(exc)[:120]}"
        saida.append(item)
    return saida


if __name__ == "__main__":
    mcp.run()
