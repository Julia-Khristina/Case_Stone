"""Coleta oficial do YouTube pela Data API v3.

Caminho barato em cota, como o TAPI recomenda: channels (1 unidade) → playlist de uploads (playlistItems,
1 unidade por página) → videos em lotes de 50 (1 unidade por lote). Nunca usa search (100 unidades).

Shorts: a API não diz se o vídeo é vertical. Usamos a duração (até `shorts_max_s`, padrão 180 s) como
aproximação e registramos isso como limitação.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from src.collection.http import HttpError, get_json
from src.collection.models import Post, Profile
from src.shared.cache import VersionedCache

API = "https://www.googleapis.com/youtube/v3"
DURATION_RE = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$")


def parse_duration(value: str | None) -> float | None:
    """'PT1M5S' → 65.0. Devolve None para formato desconhecido."""
    match = DURATION_RE.fullmatch(value or "")
    if not match:
        return None
    days, hours, minutes, seconds = match.groups()
    return (int(days or 0) * 86400 + int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(seconds or 0))


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _int(value: Any) -> int | None:
    return int(value) if value not in (None, "") else None


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


class YouTubeCollector:
    def __init__(self, api_key: str | None = None, http: Callable[..., dict[str, Any]] = get_json,
                 cache: VersionedCache | None = None, shorts_max_s: float = 180) -> None:
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY", "")
        self.http = http
        self.cache = cache
        self.shorts_max_s = shorts_max_s
        if not self.api_key:
            raise RuntimeError("Defina YOUTUBE_API_KEY no .env (veja .env.example).")

    def _get(self, resource: str, params: dict[str, Any]) -> dict[str, Any]:
        return self.http(f"{API}/{resource}", {**params, "key": self.api_key}, cache=self.cache)

    def channel(self, handle_or_id: str) -> dict[str, Any]:
        selector = ({"id": handle_or_id} if handle_or_id.startswith("UC")
                    else {"forHandle": "@" + handle_or_id.lstrip("@")})
        items = self._get("channels", {"part": "snippet,statistics,contentDetails", **selector}).get("items") or []
        if not items:
            raise LookupError(f"Canal não encontrado no YouTube: {handle_or_id}")
        return items[0]

    def search_channels(self, query: str, max_results: int = 25) -> list[str]:
        """Busca canais por palavra-chave no Brasil. Custa 100 unidades de cota por chamada: usar com moderação."""
        data = self._get("search", {"part": "snippet", "type": "channel", "q": query, "maxResults": max_results,
                                    "regionCode": "BR", "relevanceLanguage": "pt"})
        return [i["id"]["channelId"] for i in data.get("items") or [] if (i.get("id") or {}).get("channelId")]

    def channels(self, ids: list[str]) -> list[dict[str, Any]]:
        """Detalhes de vários canais, 50 por chamada (1 unidade cada)."""
        out: list[dict[str, Any]] = []
        for batch in _chunks(list(dict.fromkeys(ids)), 50):
            out += self._get("channels", {"part": "snippet,statistics,contentDetails",
                                          "id": ",".join(batch)}).get("items") or []
        return out

    def recent_uploads(self, playlist_id: str, n: int = 20) -> list[str]:
        """Datas de publicação dos últimos n vídeos, do mais novo ao mais antigo (1 unidade de cota)."""
        try:
            items = self._get("playlistItems", {"part": "contentDetails", "playlistId": playlist_id,
                                                "maxResults": n}).get("items") or []
        except HttpError as exc:
            if exc.status == 404:      # canal sem vídeos não tem playlist de uploads
                return []
            raise
        datas = [(i.get("contentDetails") or {}).get("videoPublishedAt") for i in items]
        return sorted((d for d in datas if d), reverse=True)

    def upload_ids(self, playlist_id: str, since: datetime | None, max_items: int) -> list[str]:
        ids: list[str] = []
        token: str | None = None
        while len(ids) < max_items:
            params = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": 50}
            if token:
                params["pageToken"] = token
            data = self._get("playlistItems", params)
            for item in data.get("items") or []:
                details = item.get("contentDetails") or {}
                published = details.get("videoPublishedAt")
                if since and published and parse_time(published) < since:
                    return ids
                ids.append(details["videoId"])
                if len(ids) >= max_items:
                    return ids
            token = data.get("nextPageToken")
            if not token:
                break
        return ids

    def collect(self, handle_or_id: str, since: datetime | None = None, max_posts: int = 300
                ) -> tuple[Profile, list[Post], list[dict[str, Any]]]:
        collected_at = datetime.now(timezone.utc)
        channel = self.channel(handle_or_id)
        snippet, stats = channel.get("snippet") or {}, channel.get("statistics") or {}
        profile = Profile(plataforma="youtube", perfil_id=channel["id"],
                          username=(snippet.get("customUrl") or handle_or_id).lstrip("@"),
                          nome=snippet.get("title"),
                          seguidores=None if stats.get("hiddenSubscriberCount") else _int(stats.get("subscriberCount")),
                          total_posts=_int(stats.get("videoCount")), coletado_em=collected_at)
        uploads = channel["contentDetails"]["relatedPlaylists"]["uploads"]
        raw: list[dict[str, Any]] = [channel]
        posts: list[Post] = []
        for batch in _chunks(self.upload_ids(uploads, since, max_posts), 50):
            data = self._get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(batch)})
            raw.append(data)
            for video in data.get("items") or []:
                vs, vst = video.get("snippet") or {}, video.get("statistics") or {}
                duration = parse_duration((video.get("contentDetails") or {}).get("duration"))
                is_short = duration is not None and duration <= self.shorts_max_s
                thumbs = vs.get("thumbnails") or {}
                thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
                posts.append(Post(
                    plataforma="youtube", post_id=video["id"], perfil_id=profile.perfil_id,
                    username=profile.username, tipo="short" if is_short else "video",
                    legenda=vs.get("description") or "", titulo=vs.get("title"),
                    publicado_em=parse_time(vs["publishedAt"]), curtidas=_int(vst.get("likeCount")),
                    comentarios=_int(vst.get("commentCount")), visualizacoes=_int(vst.get("viewCount")),
                    duracao_s=duration,
                    link=(f"https://www.youtube.com/shorts/{video['id']}" if is_short
                          else f"https://www.youtube.com/watch?v={video['id']}"),
                    thumbnail_url=thumb, coletado_em=collected_at,
                ))
        return profile, posts, raw
