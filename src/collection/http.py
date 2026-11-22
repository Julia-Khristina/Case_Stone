"""GET de JSON com nova tentativa, espera crescente e cache em disco.

Segue o padrão do cliente de LLM do Case Suno: espera no limite de requisições (429 e os códigos de limite da
Graph API), espera crescente em falha de rede e cache por requisição para nunca gastar cota duas vezes.
Credenciais (access_token, key) nunca entram na chave do cache nem nas mensagens de erro.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from src.shared.cache import VersionedCache
from src.shared.logging import get_logger

logger = get_logger("collection.http")

SECRET_PARAMS = {"access_token", "key"}
# Códigos de limite de taxa da Graph API (devolvidos com HTTP 400 ou 403): 4, 17, 32, 613
GRAPH_RATE_LIMIT_CODES = {4, 17, 32, 613}


class HttpError(RuntimeError):
    def __init__(self, status: int, message: str, minutos_para_liberar: int | None = None) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.minutos_para_liberar = minutos_para_liberar


class TokenExpirado(HttpError):
    def __init__(self, detalhe: str) -> None:
        super().__init__(400, "O token da Meta expirou ou é inválido. Gere um novo no Graph API Explorer, estenda no "
                         "Depurador de token (vale cerca de 60 dias) e atualize META_ACCESS_TOKEN no .env. "
                         f"Detalhe da Meta: {detalhe}")


def minutos_para_liberar(headers: Any) -> int | None:
    """Lê o tempo de espera que a Meta informa no cabeçalho de uso (X-Business-Use-Case-Usage)."""
    if headers is None:
        return None
    # Limite da aplicação (modo de desenvolvimento: cerca de 200 chamadas/hora, janela móvel). A Meta não informa
    # o tempo; a janela leva até 60 minutos para esvaziar. Repetir só prolonga o bloqueio.
    try:
        if int(json.loads(headers.get("x-app-usage") or "{}").get("call_count") or 0) >= 100:
            return 60
    except (ValueError, AttributeError, TypeError):
        pass
    bruto = headers.get("x-business-use-case-usage")
    if not bruto:
        return None
    try:
        usos = [u for lista in json.loads(bruto).values() for u in lista]
    except (ValueError, AttributeError, TypeError):
        return None
    tempos = [int(u.get("estimated_time_to_regain_access") or 0) for u in usos]
    return max(tempos) if tempos else None


def _redact(params: dict[str, Any]) -> dict[str, Any]:
    return {k: ("***" if k in SECRET_PARAMS else v) for k, v in params.items()}


def _codigo_erro(body: str) -> int | None:
    try:
        return json.loads(body).get("error", {}).get("code")
    except (ValueError, AttributeError):
        return None


def _is_rate_limited(status: int, body: str) -> bool:
    return status == 429 or _codigo_erro(body) in GRAPH_RATE_LIMIT_CODES


def get_json(
    url: str,
    params: dict[str, Any],
    *,
    cache: VersionedCache | None = None,
    max_retries: int = 5,
    base_delay: float = 2.0,
    max_delay: float = 120.0,
    opener: Callable[..., Any] = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
    antes_da_rede: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """`antes_da_rede` é chamado antes de cada requisição real (não nas respostas do cache), por exemplo um limitador."""
    key = cache.build_key(url, _redact(params)) if cache else None
    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            return cached

    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(full_url, headers={"User-Agent": "CaseStoneCollector/1.0"})
    for attempt in range(max_retries):
        if antes_da_rede is not None:
            antes_da_rede()
        try:
            with opener(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            espera = minutos_para_liberar(exc.headers) if _is_rate_limited(exc.code, body) else None
            if espera:   # a Meta já disse quantos minutos faltam: repetir em segundos só gastaria tempo
                raise HttpError(exc.code, body[:500], minutos_para_liberar=espera) from None
            if _codigo_erro(body) == 190:   # token expirado ou inválido: mensagem clara em vez de erro técnico
                raise TokenExpirado(body[:300]) from None
            retryable = _is_rate_limited(exc.code, body) or exc.code >= 500
            if retryable and attempt < max_retries - 1:
                delay = min(max_delay, base_delay * (2 ** attempt))
                logger.warning("HTTP %s em %s; nova tentativa em %.0fs", exc.code, url, delay)
                sleep(delay)
                continue
            raise HttpError(exc.code, body[:500]) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt < max_retries - 1:
                sleep(min(max_delay, base_delay * (2 ** attempt)))
                continue
            raise HttpError(0, f"falha de conexão: {exc}") from None
    else:  # pragma: no cover - o laço sempre sai por break ou raise
        raise HttpError(0, "sem resposta")

    if cache is not None:
        cache.set(key, data)
    return data
