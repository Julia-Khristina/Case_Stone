"""Contratos dos dados coletados. Campo desconhecido levanta erro (mesma regra do estado do Case Suno)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

Plataforma = Literal["instagram", "youtube"]
TipoPost = Literal["reels", "carrossel", "imagem", "video", "short"]


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plataforma: Plataforma
    perfil_id: str
    username: str
    nome: Optional[str] = None
    seguidores: Optional[int] = None
    total_posts: Optional[int] = None
    coletado_em: datetime


class Post(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plataforma: Plataforma
    post_id: str
    perfil_id: str
    username: str
    tipo: TipoPost
    legenda: str = ""
    titulo: Optional[str] = None
    publicado_em: datetime
    curtidas: Optional[int] = None        # None = curtidas ocultas pelo dono do perfil
    comentarios: Optional[int] = None
    visualizacoes: Optional[int] = None   # Instagram de terceiros não informa; YouTube informa
    duracao_s: Optional[float] = None
    link: Optional[str] = None
    media_url: Optional[str] = None       # expira em horas ou dias: renovar na passada 2
    thumbnail_url: Optional[str] = None
    coletado_em: datetime
