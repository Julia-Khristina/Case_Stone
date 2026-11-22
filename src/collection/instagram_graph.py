"""Coleta oficial do Instagram pela Graph API (Business Discovery).

Uma conta profissional própria, ligada a uma página do Facebook e a um app da Meta, consulta os dados públicos
de outras contas profissionais pelo @. Não exige a conta da Stone.

Limitações conhecidas (registradas no README):
- só funciona com contas profissionais (criador ou empresa);
- não traz o texto dos comentários de terceiros, só a contagem;
- curtidas ocultas pelo dono chegam sem like_count (viram None);
- media_url expira: a passada 2 pede URLs novas só para o top e o grupo controle.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable

from src.collection.http import get_json
from src.collection.models import Post, Profile
from src.shared.cache import VersionedCache

MEDIA_FIELDS = ("id,caption,like_count,comments_count,media_type,media_product_type,timestamp,permalink,"
                "media_url,thumbnail_url")
PROFILE_FIELDS = "id,username,name,followers_count,media_count"


def tipo_instagram(media_type: str | None, product_type: str | None) -> str:
    if (product_type or "").upper() == "REELS":
        return "reels"
    media_type = (media_type or "").upper()
    if media_type == "CAROUSEL_ALBUM":
        return "carrossel"
    if media_type == "VIDEO":
        return "video"
    return "imagem"


def parse_timestamp(value: str) -> datetime:
    # A Graph API devolve "2026-08-21T14:03:11+0000"
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")


class InstagramGraphCollector:
    def __init__(
        self,
        ig_user_id: str | None = None,
        access_token: str | None = None,
        version: str | None = None,
        page_size: int = 50,
        http: Callable[..., dict[str, Any]] = get_json,
        cache: VersionedCache | None = None,
    ) -> None:
        self.ig_user_id = ig_user_id or os.getenv("META_IG_USER_ID", "")
        self.access_token = access_token or os.getenv("META_ACCESS_TOKEN", "")
        self.version = version or os.getenv("META_GRAPH_VERSION", "v27.0")
        self.page_size = page_size
        self.http = http
        self.cache = cache
        if not self.ig_user_id or not self.access_token:
            raise RuntimeError("Defina META_IG_USER_ID e META_ACCESS_TOKEN no .env (veja .env.example).")

    @property
    def base_url(self) -> str:
        return f"https://graph.facebook.com/{self.version}/{self.ig_user_id}"

    def discovery_page(self, username: str, after: str | None = None, limit: int | None = None) -> dict[str, Any]:
        cursor = f".after({after})" if after else ""
        fields = (f"business_discovery.username({username}){{{PROFILE_FIELDS},"
                  f"media{cursor}.limit({limit or self.page_size}){{{MEDIA_FIELDS}}}}}")
        data = self.http(self.base_url, {"fields": fields, "access_token": self.access_token}, cache=self.cache)
        return data.get("business_discovery") or {}

    def collect(self, username: str, since: datetime | None = None, max_posts: int = 600
                ) -> tuple[Profile, list[Post], list[dict[str, Any]]]:
        """Pagina do post mais novo para o mais antigo e para no primeiro post anterior a `since`."""
        collected_at = datetime.now(timezone.utc)
        raw_pages: list[dict[str, Any]] = []
        posts: list[Post] = []
        profile: Profile | None = None
        after: str | None = None
        while True:
            page = self.discovery_page(username, after)
            raw_pages.append(page)
            if profile is None:
                profile = Profile(plataforma="instagram", perfil_id=str(page.get("id", username)),
                                  username=page.get("username", username), nome=page.get("name"),
                                  seguidores=page.get("followers_count"), total_posts=page.get("media_count"),
                                  coletado_em=collected_at)
            media = page.get("media") or {}
            reached_since = False
            for item in media.get("data") or []:
                published = parse_timestamp(item["timestamp"])
                if since and published < since:
                    reached_since = True
                    break
                posts.append(Post(
                    plataforma="instagram", post_id=str(item["id"]), perfil_id=profile.perfil_id,
                    username=profile.username,
                    tipo=tipo_instagram(item.get("media_type"), item.get("media_product_type")),
                    legenda=item.get("caption") or "", publicado_em=published,
                    curtidas=item.get("like_count"), comentarios=item.get("comments_count"),
                    link=item.get("permalink"), media_url=item.get("media_url"),
                    thumbnail_url=item.get("thumbnail_url"), coletado_em=collected_at,
                ))
                if len(posts) >= max_posts:
                    reached_since = True
                    break
            # No Business Discovery a paginação traz só o cursor "after", sem o campo "next" (confirmado em
            # 22/11/2026). Para quando: chegou à data limite, a página veio vazia ou o cursor não mudou.
            proximo = ((media.get("paging") or {}).get("cursors") or {}).get("after")
            if reached_since or not media.get("data") or not proximo or proximo == after:
                break
            after = proximo
        return profile, posts, raw_pages


# ---------------------------------------------------------------- Insights (só das contas da própria Stone)
METRICAS_INSIGHTS = ("reach", "saved", "shares", "total_interactions")


def insights_da_midia(media_id: str, access_token: str, version: str | None = None,
                      http: Callable[..., dict[str, Any]] = get_json) -> dict[str, int | None]:
    """Alcance, salvamentos, compartilhamentos e interações de UM post da própria conta.

    Exige um token de quem administra a conta (permissão instagram_manage_insights): o Business Discovery, usado
    para o nicho, não entrega esses números de contas de terceiros. Métrica que a API não devolve vira None.
    """
    url = f"https://graph.facebook.com/{version or os.getenv('META_GRAPH_VERSION', 'v27.0')}/{media_id}/insights"
    dados = http(url, {"metric": ",".join(METRICAS_INSIGHTS), "access_token": access_token})
    valores = {m["name"]: (m.get("values") or [{}])[0].get("value") for m in dados.get("data") or []}
    return {m: valores.get(m) for m in METRICAS_INSIGHTS}
