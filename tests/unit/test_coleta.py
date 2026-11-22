"""Coletores oficiais, testados com respostas falsas (sem rede)."""
from __future__ import annotations

import io
import json
import urllib.error
from datetime import datetime, timezone

import pytest

from src.collection.http import HttpError, get_json
from src.collection.instagram_graph import InstagramGraphCollector, tipo_instagram
from src.collection.storage import append_jsonl, read_jsonl
from src.collection.youtube import YouTubeCollector, parse_duration
from src.shared.cache import VersionedCache


# ------------------------------------------------------------------ http
class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code: int, body: dict) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("u", code, "erro", {}, io.BytesIO(json.dumps(body).encode()))


def test_http_espera_no_limite_da_graph_api_e_tenta_de_novo():
    calls, sleeps = [], []

    def opener(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise http_error(400, {"error": {"code": 4, "message": "Application request limit reached"}})
        return FakeResponse(b'{"ok": 1}')

    assert get_json("https://x", {"a": 1}, opener=opener, sleep=sleeps.append) == {"ok": 1}
    assert len(calls) == 2 and sleeps == [2.0]


def test_http_nao_repete_erro_de_permissao_e_nao_vaza_token():
    def opener(request, timeout):
        raise http_error(400, {"error": {"code": 190, "message": "Invalid OAuth access token"}})

    with pytest.raises(HttpError) as exc:
        get_json("https://x", {"access_token": "SEGREDO"}, opener=opener, sleep=lambda s: None)
    assert "SEGREDO" not in str(exc.value)


def test_cache_nao_guarda_o_token_na_chave(tmp_path):
    cache = VersionedCache(tmp_path)
    get_json("https://x", {"access_token": "SEGREDO", "f": 1}, cache=cache,
             opener=lambda r, timeout: FakeResponse(b'{"v": 1}'))
    # mesma requisição com outro token vem do cache, sem chamar a rede
    assert get_json("https://x", {"access_token": "OUTRO", "f": 1}, cache=cache,
                    opener=lambda r, timeout: pytest.fail("não deveria chamar a rede")) == {"v": 1}
    assert all("SEGREDO" not in p.read_text() for p in tmp_path.iterdir())


# ------------------------------------------------------------------ instagram
def ig_page(items: list[dict], after: str | None) -> dict:
    paging = {"cursors": {"after": after}, "next": "https://next"} if after else {"cursors": {}}
    return {"business_discovery": {"id": "17841", "username": "chefrut", "name": "Chef Ruth",
                                   "followers_count": 12000, "media_count": 300,
                                   "media": {"data": items, "paging": paging}}}


def ig_item(i: int, ts: str, **extra) -> dict:
    return {"id": str(i), "caption": f"post {i}", "like_count": 100, "comments_count": 9, "media_type": "VIDEO",
            "media_product_type": "REELS", "timestamp": ts, "permalink": f"https://instagram.com/p/{i}", **extra}


def test_instagram_pagina_e_para_na_data_limite():
    pages = [ig_page([ig_item(1, "2026-11-01T10:00:00+0000"), ig_item(2, "2026-10-01T10:00:00+0000")], "C1"),
             ig_page([ig_item(3, "2026-09-01T10:00:00+0000"), ig_item(4, "2026-03-01T10:00:00+0000")], "C2")]
    requested = []

    def http(url, params, cache=None):
        requested.append(params["fields"])
        return pages[len(requested) - 1]

    collector = InstagramGraphCollector("me", "tok", http=http)
    profile, posts, raw = collector.collect("chefrut", since=datetime(2026, 5, 1, tzinfo=timezone.utc))
    assert profile.seguidores == 12000 and profile.username == "chefrut"
    assert [p.post_id for p in posts] == ["1", "2", "3"]           # o post de março ficou fora
    assert "media.after(C1)" in requested[1] and len(raw) == 2


def test_instagram_curtida_oculta_vira_none_e_tipos_sao_mapeados():
    item = ig_item(1, "2026-11-01T10:00:00+0000")
    del item["like_count"]
    collector = InstagramGraphCollector("me", "tok", http=lambda url, params, cache=None: ig_page([item], None))
    _, posts, _ = collector.collect("chefrut")
    assert posts[0].curtidas is None and posts[0].tipo == "reels"
    assert tipo_instagram("CAROUSEL_ALBUM", "FEED") == "carrossel"
    assert tipo_instagram("IMAGE", "FEED") == "imagem"


def test_instagram_exige_credenciais(monkeypatch):
    monkeypatch.delenv("META_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("META_IG_USER_ID", raising=False)
    with pytest.raises(RuntimeError, match="META_IG_USER_ID"):
        InstagramGraphCollector()


# ------------------------------------------------------------------ youtube
def test_duracao_iso8601():
    assert parse_duration("PT45S") == 45 and parse_duration("PT1M5S") == 65
    assert parse_duration("PT1H2M3S") == 3723 and parse_duration("xyz") is None


def test_youtube_usa_playlist_de_uploads_e_separa_shorts():
    def http(url, params, cache=None):
        resource = url.rsplit("/", 1)[1]
        if resource == "channels":
            assert params["forHandle"] == "@canalmei"
            return {"items": [{"id": "UC1", "snippet": {"title": "Canal MEI", "customUrl": "@canalmei"},
                               "statistics": {"subscriberCount": "5000", "videoCount": "80"},
                               "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}
        if resource == "playlistItems":
            return {"items": [{"contentDetails": {"videoId": "a", "videoPublishedAt": "2026-11-01T00:00:00Z"}},
                              {"contentDetails": {"videoId": "b", "videoPublishedAt": "2026-10-01T00:00:00Z"}},
                              {"contentDetails": {"videoId": "c", "videoPublishedAt": "2026-01-01T00:00:00Z"}}]}
        assert resource == "videos" and params["id"] == "a,b"
        return {"items": [
            {"id": "a", "snippet": {"title": "Dica", "publishedAt": "2026-11-01T00:00:00Z"},
             "statistics": {"viewCount": "900", "likeCount": "50"}, "contentDetails": {"duration": "PT40S"}},
            {"id": "b", "snippet": {"title": "Aula", "publishedAt": "2026-10-01T00:00:00Z"},
             "statistics": {"viewCount": "300"}, "contentDetails": {"duration": "PT12M"}}]}

    profile, posts, _ = YouTubeCollector("k", http=http).collect("canalmei",
                                                                  since=datetime(2026, 5, 1, tzinfo=timezone.utc))
    assert profile.seguidores == 5000 and profile.username == "canalmei"
    assert [(p.post_id, p.tipo) for p in posts] == [("a", "short"), ("b", "video")]
    assert posts[0].link.endswith("/shorts/a") and posts[1].curtidas is None


# ------------------------------------------------------------------ storage
def test_jsonl_ida_e_volta(tmp_path):
    path = tmp_path / "x" / "posts.jsonl"
    assert append_jsonl(path, [{"a": 1}, {"a": 2}]) == 2
    assert read_jsonl(path) == [{"a": 1}, {"a": 2}]


def test_limite_com_tempo_informado_pela_meta_nao_fica_repetindo():
    sleeps = []

    def opener(request, timeout):
        erro = http_error(403, {"error": {"code": 4, "message": "Application request limit reached"}})
        erro.headers = {"x-business-use-case-usage":
                        '{"123":[{"type":"instagram","call_count":100,"estimated_time_to_regain_access":37}]}'}
        raise erro

    with pytest.raises(HttpError) as exc:
        get_json("https://x", {"a": 1}, opener=opener, sleep=sleeps.append)
    assert exc.value.minutos_para_liberar == 37 and sleeps == []


def test_limite_da_aplicacao_para_na_hora():
    sleeps = []

    def opener(request, timeout):
        erro = http_error(403, {"error": {"code": 4, "message": "Application request limit reached"}})
        erro.headers = {"x-app-usage": '{"call_count":100,"total_cputime":0,"total_time":32}'}
        raise erro

    with pytest.raises(HttpError) as exc:
        get_json("https://x", {"a": 1}, opener=opener, sleep=sleeps.append)
    assert exc.value.minutos_para_liberar == 60 and sleeps == []


def test_token_expirado_vira_mensagem_clara():
    from src.collection.http import TokenExpirado

    def opener(request, timeout):
        raise http_error(400, {"error": {"message": "Session has expired", "code": 190, "error_subcode": 463}})

    with pytest.raises(TokenExpirado, match="Depurador de token"):
        get_json("https://x", {"access_token": "SEGREDO"}, opener=opener, sleep=lambda s: None)


def test_instagram_pagina_so_com_cursor_after_como_a_api_real():
    """A resposta real do Business Discovery não tem "next" na paginação, só cursors.after."""
    def pagina(items, after):
        return {"business_discovery": {"id": "1", "username": "chefrut", "followers_count": 6878, "media_count": 1423,
                                       "media": {"data": items, "paging": {"cursors": {"after": after}}}}}
    paginas = [pagina([ig_item(1, "2026-11-01T10:00:00+0000")], "C1"),
               pagina([ig_item(2, "2026-08-01T10:00:00+0000")], "C2"),
               pagina([ig_item(3, "2026-04-01T10:00:00+0000")], "C3")]
    pedidas = []

    def http(url, params, cache=None):
        pedidas.append(params["fields"])
        return paginas[len(pedidas) - 1]

    _, posts, _ = InstagramGraphCollector("me", "tok", http=http).collect(
        "chefrut", since=datetime(2026, 5, 26, tzinfo=timezone.utc))
    assert [p.post_id for p in posts] == ["1", "2"] and len(pedidas) == 3     # leu até passar da data limite


def test_instagram_para_se_o_cursor_se_repete():
    repetida = {"business_discovery": {"id": "1", "username": "x", "media": {
        "data": [ig_item(1, "2026-11-01T10:00:00+0000")], "paging": {"cursors": {"after": "MESMO"}}}}}
    chamadas = []

    def http(url, params, cache=None):
        chamadas.append(1)
        if len(chamadas) > 5:
            raise AssertionError("laço infinito")
        return repetida

    InstagramGraphCollector("me", "tok", http=http).collect("x")
    assert len(chamadas) == 2


def test_insights_da_midia_le_as_metricas_da_graph_api():
    from src.collection.instagram_graph import insights_da_midia
    chamadas = []

    def http(url, params, **_):
        chamadas.append((url, params))
        return {"data": [{"name": "reach", "values": [{"value": 1200}]}, {"name": "saved", "values": [{"value": 35}]},
                         {"name": "shares", "values": [{"value": 12}]}]}
    r = insights_da_midia("123", "tok", version="v27.0", http=http)
    assert r == {"reach": 1200, "saved": 35, "shares": 12, "total_interactions": None}   # métrica ausente vira None
    assert chamadas[0][0].endswith("/v27.0/123/insights") and "reach" in chamadas[0][1]["metric"]
