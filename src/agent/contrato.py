"""Contrato mínimo do agente (TAPI, seção 7), validado com Pydantic."""
from __future__ import annotations

import re

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Modo = Literal["analisar", "recomendar", "gerar_criativo", "gerar_pacote", "buscar_embaixador"]
Formato = Literal["reels", "carrossel", "estatico", "stories", "short"]


class Filtros(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plataforma: Optional[Literal["instagram", "youtube"]] = None
    faixa: Optional[Literal["micro", "medio", "grande"]] = None


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Modo
    query: str = Field(description="pergunta ou objetivo, ex.: 'atrair donos de restaurante'")
    segment: Optional[str] = Field(default=None, description="macrossetor (ex.: alimentacao) ou None para todos")
    filters: Filtros = Field(default_factory=Filtros)
    formatos: Optional[list[Formato]] = None
    usar_juiz: bool = False
    conta: Literal["impulsostone", "stone"] = Field(default="impulsostone", description="conta para a qual a peça é escrita")


class Finding(BaseModel):
    plataforma: str
    caracteristica: str
    valor: str
    pct_top: float
    pct_controle: float
    lift: Optional[float]
    ic: tuple[float, float]
    n_top: int
    n_perfis: int
    leitura: str


class RefPost(BaseModel):
    post_id: str
    plataforma: str
    perfil: str
    formato: str
    link: Optional[str]
    titulo_ou_trecho: str
    conteudo: str = ""          # legenda completa + o que se vê e se ouve (camada 2), para o gerador ver a substância
    capa: Optional[str] = None  # endereço da capa guardada em data/capas/ (scripts/baixar_capas.py)
    er: Optional[float]
    lift_perfil: Optional[float]
    categorias: dict[str, str] = Field(default_factory=dict)


CHAVE_DE_CENA = re.compile(r"^(\d+(\.\d+)?\s*(-|–|a)\s*\d+(\.\d+)?\s*s?|\d+\s*s|(cena|slide|tela)\s*\d+)$", re.I)


def _como_textos(valor):
    """Aceita cenas e slides como texto ou como {"0-3s": "texto"} (o modelo às vezes devolve assim) e normaliza."""
    if isinstance(valor, dict):
        valor = [valor]
    if not isinstance(valor, list):
        return valor
    saida = []
    for item in valor:
        if isinstance(item, dict) and len(item) > 1 and all(CHAVE_DE_CENA.match(str(k).strip()) for k in item):
            saida.extend(f"{k}: {v}" for k, v in item.items())   # {"0-3s": ..., "3-8s": ...}: cada chave é uma cena
        elif isinstance(item, dict):
            saida.append(_cena_em_texto(item))      # uma cena (ou slide) vira um item, nunca vários
        else:
            saida.append(item if isinstance(item, str) else str(item))
    return saida


CHAVES_TEXTO = ("texto", "fala", "descricao", "cena", "conteudo", "slide", "titulo")
CHAVES_TEMPO = ("tempo", "intervalo", "duracao_s", "duracao", "inicio")


CHAVES_TELA = ("texto_tela", "texto_na_tela", "tela", "on_screen_text")


def _cena_em_texto(item: dict) -> str:
    """{"duracao_s": 3, "texto": "..."} → "3s: ..."; {"0-3s": "..."} → "0-3s: ..."; outros → "k: v · k: v".

    O texto de tela, quando vem dentro da cena, vira "(na tela: “...”)" em vez do nome técnico do campo.
    """
    tela = next((str(item[k]) for k in CHAVES_TELA if item.get(k)), None)
    if tela is not None:
        resto = {k: v for k, v in item.items() if k not in CHAVES_TELA}
        base = _cena_em_texto(resto) if resto else ""
        return f"{base} (na tela: “{tela}”)".strip()
    texto = next((str(item[k]) for k in CHAVES_TEXTO if k in item), None)
    if texto is not None:
        tempo = next((item[k] for k in CHAVES_TEMPO if k in item), None)
        if tempo is None:
            return texto
        return f"{tempo}s: {texto}" if isinstance(tempo, (int, float)) else f"{tempo}: {texto}"
    if len(item) == 1:
        (k, v), = item.items()
        return f"{k}: {v}"
    return " · ".join(f"{k}: {v}" for k, v in item.items())


class Creative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("corpo", "texto_tela", "reference_post_ids", "justificativa", mode="before")
    @classmethod
    def _normalizar_listas(cls, valor):
        return _como_textos(valor)

    formato: Formato
    caso: str = Field(default="", description="situação concreta de um pequeno negócio em que a peça se apoia: "
                                               "tipo de negócio, a dor específica e o que acontece se nada mudar")
    titulo: str
    gancho: str
    corpo: list[str] = Field(description="cenas do roteiro, slides do carrossel ou telas dos stories")
    texto_tela: list[str] = Field(default_factory=list)
    legenda: str
    cta: str
    duracao_s: Optional[int] = None
    reference_post_ids: list[str]
    justificativa: list[str] = Field(description="por que este criativo, em frases curtas ligadas aos padrões")


class CreativeAvaliado(BaseModel):
    criativo: Creative
    conferencias: dict[str, bool]
    falhas: list[str]
    tentativas: int
    juiz: Optional[dict] = None
    aprovado_automatico: bool
    melhoria_juiz: Optional[dict] = None   # nota antes e depois da reescrita guiada pelo juiz (src/agent/melhoria.py)


class AgentOutput(BaseModel):
    findings: list[Finding]
    reference_posts: list[RefPost]
    creatives: list[CreativeAvaliado] = Field(default_factory=list)
    format_trends: list[Finding] = Field(default_factory=list)
    confidence_flag: bool
    explanation: str
    erros: list[str] = Field(default_factory=list, description="formatos que não saíram e por quê")
    creators: list[dict] = Field(default_factory=list, description="scorecard dos criadores (modo buscar_embaixador)")
    indicados: dict = Field(default_factory=dict, description="transversais, setoriais e reservas indicados")
