"""Agente de descoberta de perfis: mantém a lista de perfis atualizada por bola de neve, só com a API oficial.

Fluxo (a decisão final é sempre humana):
1. lê os posts recentes das sementes e dos perfis já aprovados;
2. extrai os @ mencionados nas legendas (parcerias, collabs, indicações);
3. consulta cada @ novo no Business Discovery: conta profissional, seguidores, número de posts, bio, último post;
4. classifica a bio (fala com MPE? qual segmento?) por regras de palavras-chave;
5. aplica os critérios do TAPI (ativo, público MPE) e equilibra as faixas micro / médio / grande;
6. grava os candidatos num CSV para a pessoa aprovar (scripts/aprovar_perfis.py).

Por que não busca por hashtag: a Graph API devolve os posts de uma hashtag sem o @ do autor.
Viés conhecido: a bola de neve encontra perfis parecidos com as sementes. Mitigação: sementes variadas e
equilíbrio de faixas. Cada candidato guarda quem o mencionou (origem auditável).
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml

from src.collection.http import HttpError

MENTION_RE = re.compile(r"(?<![\w@.])@([A-Za-z0-9._]{2,30})")
IG_LINK_RE = re.compile(r"instagram\.com/([A-Za-z0-9._]{2,30})", re.IGNORECASE)
IG_LABEL_RE = re.compile(r"\b(?:instagram|insta|ig)\b\s*[:\-–—|]?\s*@([A-Za-z0-9._]{2,30})", re.IGNORECASE)
IG_RESERVADOS = {"p", "reel", "reels", "stories", "explore", "accounts", "tv", "direct", "about"}

# Expressões regulares sobre o texto sem acento. Sinais curtos têm limite de palavra dos dois lados
# ("mei" não pode casar com "meio").
SINAIS_MPE = [r"\bempreend", r"\bmei\b", r"\bmicroempreend", r"\bpequenos? negocios?\b", r"\bpequenas? empresas?\b",
              r"\blojistas?\b", r"\bempresari", r"\bautonom", r"\bcomercio\b", r"\bnegocios?\b", r"\bvender mais\b",
              r"\bvendas\b", r"\blojas?\b", r"\bfaturar\b", r"\bclientes\b",
              # Acrescentados na revisão de 22/11/2026: perfis bons de setores novos eram recusados por falta delas
              r"\bdon[oa]s? d[eoa]s?\b", r"\bviver d[eao]\b", r"\bganhar dinheiro\b", r"\blucrativ",
              r"\bmotoristas? de (app|aplicativo)\b", r"\bmercadinhos?\b", r"\bbarbeir[oa]s?\b", r"\bartesa(o|s)?\b",
              r"\bfaca e venda\b", r"\bpara vender\b"]
# Quem ensina para outros empreendedores tende a ser transversal, mesmo citando um setor
SINAIS_EDUCADOR = [r"\bajudo\b", r"\bensino\b", r"\bdicas\b", r"\baprenda\b", r"\bmentor", r"\bcursos?\b",
                   r"\bpara empreendedor", r"\bpara (o )?mei\b", r"\bpara pequenos negocios\b", r"\bconsultor"]
TAXONOMIA_PADRAO = Path(__file__).resolve().parents[2] / "config" / "segmentos.yaml"


@lru_cache(maxsize=4)
def carregar_taxonomia(caminho: str = str(TAXONOMIA_PADRAO)) -> dict:
    return yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}


def _norm(text: str) -> str:
    base = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in base if not unicodedata.combining(c))


def extrair_mencoes(texto: str) -> list[str]:
    """@ mencionados, em minúsculas, sem repetição e sem o ponto final de frase. Ignora e-mails."""
    vistos: list[str] = []
    for bruto in MENTION_RE.findall(texto or ""):
        handle = bruto.rstrip(".").lower()
        if len(handle) >= 2 and handle not in vistos:
            vistos.append(handle)
    return vistos


def instagram_no_texto(texto: str) -> list[str]:
    """@ do Instagram citados num texto (descrição de canal, página web): links instagram.com/... e "Insta: @..."."""
    achados: list[str] = []
    for regex in (IG_LINK_RE, IG_LABEL_RE):
        for bruto in regex.findall(texto or ""):
            handle = bruto.rstrip(".").lower()
            if handle not in IG_RESERVADOS and handle not in achados:
                achados.append(handle)
    return achados


def info_canal(canal: dict[str, Any], datas_uploads: list[str]) -> dict[str, Any]:
    """Converte um canal do YouTube no mesmo formato de info_perfil, para passar pelos mesmos filtros."""
    snippet, stats = canal.get("snippet") or {}, canal.get("statistics") or {}
    seguidores = None if stats.get("hiddenSubscriberCount") else int(stats.get("subscriberCount") or 0)
    return {"perfil": canal["id"], "nome": snippet.get("title"), "seguidores": seguidores,
            "total_posts": int(stats.get("videoCount") or 0), "bio": snippet.get("description") or "",
            "ultimo_post": datas_uploads[0] if datas_uploads else None, "datas_recentes": list(datas_uploads),
            "handle_youtube": (snippet.get("customUrl") or "").lstrip("@").lower()}


def contar_mencoes(posts: Iterable[dict], ignorar: set[str]) -> dict[str, dict[str, Any]]:
    """Para cada @ mencionado: quantas vezes e por quais perfis. Ignora autocitação e perfis já conhecidos."""
    contagem: dict[str, dict[str, Any]] = defaultdict(lambda: {"n_mencoes": 0, "mencionado_por": set()})
    for post in posts:
        autor = (post.get("username") or "").lower()
        for handle in extrair_mencoes(post.get("legenda") or post.get("caption") or ""):
            if handle == autor or handle in ignorar:
                continue
            contagem[handle]["n_mencoes"] += 1
            contagem[handle]["mencionado_por"].add(autor)
    return dict(contagem)


def _pontuar(texto: str, grupos: dict[str, list[str]]) -> tuple[str | None, int, str | None]:
    """Grupo com mais palavras-chave no texto, quantas casaram e a primeira palavra inteira que casou."""
    melhor, pontos, palavra = None, 0, None
    for nome, chaves in grupos.items():
        achadas = [c for c in chaves if re.search(rf"\b{c}", texto)]   # chave é fragmento de regex
        if len(achadas) > pontos:
            melhor, pontos = nome, len(achadas)
            m = re.search(rf"\b\w*{achadas[0]}\w*", texto)
            palavra = m.group(0) if m else achadas[0]
    return melhor, pontos, palavra


CONTEXTO_MEI = re.compile(r"\b(o|do|da|no|seu|sua|meu|minha|para|pra|pro|de|como|ser|virar|abrir|ajudo|todo)\s+mei\b")


def _mei_e_sigla(original: str, normalizado: str) -> bool:
    """"MEI" conta como microempreendedor individual só em caixa alta ou com contexto ("seu mei", "para mei").

    Na primeira rodada, "Bianca Mei" (sobrenome) passou no filtro como canal de finanças para MEI.
    """
    return bool(re.search(r"\bMEIs?\b", original) or CONTEXTO_MEI.search(normalizado))


def classificar_perfil(bio: str, nome: str = "", taxonomia: dict | None = None) -> dict[str, Any]:
    """Rascunho por palavras-chave, refinado depois pela IA na camada 1.

    Devolve publico_mpe (fala com empreendedores?), tipo (transversal | setorial | None), macrossetor,
    tema (para transversais), nicho (palavra que casou) e motivo legível.
    """
    tax = taxonomia or carregar_taxonomia()
    original = f"{nome} {bio}"
    texto = _norm(original)
    if not _mei_e_sigla(original, texto):
        texto = re.sub(r"\bmei\b", " ", texto)   # "Bianca Mei" é sobrenome, não microempreendedor individual
    sinais = [m.group(0) for s in SINAIS_MPE if (m := re.search(s, texto))]
    setor, pts_setor, nicho = _pontuar(texto, tax.get("macrossetores") or {})
    tema, pts_tema, _ = _pontuar(texto, tax.get("temas_transversais") or {})
    educador = any(re.search(s, texto) for s in SINAIS_EDUCADOR)
    if pts_tema and (pts_tema > pts_setor or educador or not pts_setor):
        tipo = "transversal"
    elif pts_setor:
        tipo = "setorial"
    else:
        tipo = None
    motivo = f"bio cita {', '.join(sinais[:3])}" if sinais else "bio não fala com empreendedores"
    return {"publico_mpe": bool(sinais), "tipo": tipo, "macrossetor": setor if tipo == "setorial" else None,
            "tema": tema if tipo == "transversal" else None, "nicho": nicho if tipo == "setorial" else tema,
            "motivo": motivo}


def classificar_bio(bio: str, nome: str = "") -> tuple[bool, str | None, str]:
    """Compatibilidade: (fala com MPE?, macrossetor ou tema, motivo)."""
    c = classificar_perfil(bio, nome)
    return c["publico_mpe"], c["macrossetor"] or c["tema"], c["motivo"]


def limite_atingido(exc: Exception) -> bool:
    """Erro de limite de chamadas da Graph API (códigos 4, 17, 32, 613)."""
    if not isinstance(exc, HttpError):
        return False
    if getattr(exc, "minutos_para_liberar", None):
        return True
    return bool(re.search(r'"code"\s*:\s*(4|17|32|613)\b', str(exc)))


def info_perfil(collector, username: str) -> dict[str, Any] | None:
    """Dados públicos do perfil, ou None se não existir ou não for conta profissional."""
    # 12 posts recentes na mesma chamada: dá para contar quantos caem na janela de análise sem custo extra
    fields = (f"business_discovery.username({username}){{username,name,followers_count,media_count,biography,"
              "media.limit(12){timestamp}}")
    # A resposta negativa também vai para o cache: sem isso, cada rodada consultava de novo os mesmos perfis
    # pessoais ou inexistentes e gastava o limite da API à toa.
    cache = collector.cache
    chave_negativa = cache.build_key("nao_profissional", username.lower()) if cache else None
    if chave_negativa and cache.get(chave_negativa):
        return None
    try:
        data = collector.http(collector.base_url, {"fields": fields, "access_token": collector.access_token},
                              cache=cache)
    except HttpError as exc:
        if exc.status == 400 and ('"code":110' in str(exc) or '"code":100' in str(exc) or "Invalid user" in str(exc)):
            if chave_negativa:
                cache.set(chave_negativa, True)
            return None
        raise
    bd = data.get("business_discovery") or {}
    datas = [m["timestamp"] for m in (bd.get("media") or {}).get("data") or [] if m.get("timestamp")]
    return {"perfil": (bd.get("username") or username).lower(), "nome": bd.get("name"),
            "seguidores": bd.get("followers_count"), "total_posts": bd.get("media_count"),
            "bio": bd.get("biography") or "", "ultimo_post": datas[0] if datas else None, "datas_recentes": datas}


def _data(valor: str) -> datetime:
    # Instagram: "2026-11-20T10:00:00+0000"; YouTube: "2026-11-20T10:00:00Z"
    return datetime.strptime(valor.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")


def avaliar(info: dict[str, Any], agora: datetime, limiares, plataforma: str = "instagram") -> tuple[bool, list[str]]:
    """Critérios do TAPI para entrar na amostra. Devolve (passou, motivos de recusa)."""
    motivos = []
    if (info.get("seguidores") or 0) < int(limiares.req("descoberta_seguidores_min")):
        motivos.append("poucos seguidores")
    if (info.get("total_posts") or 0) < int(limiares.req("descoberta_posts_min")):
        motivos.append("poucos posts")
    ultimo = info.get("ultimo_post")
    if not ultimo:
        motivos.append("sem posts")
    else:
        dias = (agora - _data(ultimo)).days
        if dias > int(limiares.req("descoberta_dias_sem_postar_max")):
            motivos.append(f"parado há {dias} dias")
        else:
            # Quantos posts caem na janela de análise: um perfil com um post solto em meses não contribui
            janela = int(limiares.req("janela_momento_dias"))
            minimo = int(limiares.req("descoberta_posts_min_janela")[plataforma])
            recentes = sum(1 for d in info.get("datas_recentes") or [ultimo] if (agora - _data(d)).days <= janela)
            if recentes < minimo:
                motivos.append(f"só {recentes} post{'s' if recentes != 1 else ''} em {janela} dias (mínimo {minimo})")
    if not info.get("publico_mpe"):
        motivos.append("bio não fala com empreendedores")
    return not motivos, motivos


def propor(candidatos: list[dict[str, Any]], faixas_atuais: dict[str, int], alvo_por_faixa: int) -> list[dict]:
    """Marca como 'proposto' os melhores aprovados de cada faixa até completar o alvo, para equilibrar a amostra."""
    vagas = {f: max(0, alvo_por_faixa - faixas_atuais.get(f, 0)) for f in ("micro", "medio", "grande")}
    ordem = sorted(candidatos, key=lambda c: (-c["n_mencoes"], -(c.get("seguidores") or 0)))
    for c in ordem:
        if c["status"] != "passou":
            continue
        if vagas.get(c["faixa"], 0) > 0:
            c["status"] = "proposto"
            vagas[c["faixa"]] -= 1
        else:
            c["status"] = "passou (faixa cheia)"
    return ordem
