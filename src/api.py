"""API do BoaPauta (FastAPI): o app React conversa só com ela, e ela só chama o agente e a base real.

Rodar:  python -m src.api            → http://localhost:8000  (serve também o app React já construído, se existir)
Docs:   http://localhost:8000/docs
"""
from __future__ import annotations

import csv
import os
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.agent import ferramentas as fx
from src.agent import servico
from src.analysis.agenda import gerar_agenda
from src.app_store import Store

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "app" / "dist"
app = FastAPI(title="BoaPauta", description="O que engaja o empreendedor vira criativo do Impulso Stone.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])

# ---------------------------------------------------------------- acesso e limite de uso
# BOAPAUTA_TOKEN (opcional): quando definido, toda ação que muda dados ou gasta cota (POST) exige o cabeçalho
# X-BoaPauta-Token. Leitura (GET) continua aberta. Vazio = uso local sem senha, como antes.
# BOAPAUTA_GERACOES_POR_MINUTO: teto de gerações com modelo de linguagem por minuto (padrão 6), para um
# clique repetido ou um robô não esgotar a cota do Groq.
ROTAS_QUE_GERAM = ("/api/pecas", "/api/proposta", "/api/guia")
_geracoes: list[float] = []


def _gera_conteudo(metodo: str, caminho: str) -> bool:
    return metodo == "POST" and (caminho in ROTAS_QUE_GERAM or caminho.endswith("/ao-vivo") or caminho.endswith("/ajuste"))


@app.middleware("http")
async def _acesso(request, chamar):
    import hmac
    import time as _time
    from fastapi.responses import JSONResponse
    metodo, caminho = request.method, request.url.path
    if metodo == "POST" and caminho.startswith("/api/"):
        token = os.getenv("BOAPAUTA_TOKEN", "")
        if token and not hmac.compare_digest(request.headers.get("x-boapauta-token", ""), token):
            return JSONResponse(status_code=401, content={"detail": "Senha de acesso necessária: informe em Configurações."})
        if _gera_conteudo(metodo, caminho):
            agora, teto = _time.time(), int(os.getenv("BOAPAUTA_GERACOES_POR_MINUTO", "6") or 6)
            _geracoes[:] = [t for t in _geracoes if agora - t < 60]
            if len(_geracoes) >= teto:
                return JSONResponse(status_code=429, content={"detail": f"Muitas gerações seguidas (limite de {teto} por minuto). Espere um minuto e tente de novo."})
            _geracoes.append(agora)
    return await chamar(request)


def _quem(request) -> str:
    """Nome de quem usa o app (Configurações), enviado no cabeçalho X-BoaPauta-Quem; vai para o histórico da peça."""
    from urllib.parse import unquote
    nome = unquote(request.headers.get("x-boapauta-quem", "")).strip()[:40]
    return nome or "equipe Stone"


@app.get("/api/acesso")
def acesso() -> dict:
    """O app usa para saber se precisa pedir a senha."""
    return {"protegido": bool(os.getenv("BOAPAUTA_TOKEN"))}

@app.exception_handler(RuntimeError)
def _cota_esgotada(request, exc: RuntimeError):
    """Cota do provedor de LLM esgotada vira mensagem clara no app (e não erro 500 genérico)."""
    from fastapi.responses import JSONResponse
    import re as _re
    msg = str(exc)
    if "429" in msg or "rate limit" in msg.lower():
        espera = _re.search(r"try again in ([0-9hms.]+)", msg)
        detalhe = "A cota diária do modelo de linguagem acabou. " + (
            f"Tente de novo em cerca de {espera.group(1).split('.')[0].replace('m', ' min ').replace('h', ' h ')}s."
            if espera else "Tente de novo mais tarde.")
        return JSONResponse(status_code=503, content={"detail": detalhe})
    return JSONResponse(status_code=500, content={"detail": f"erro interno: {msg[:200]}"})


ROTULOS = {
    "tema_principal": "Tema", "tipo_hook": "Gancho", "tipo_cta": "Chamada para ação", "convite_participacao": "Convite a participar",
    "mensagem_generica": "Frase motivacional genérica", "tipo": "Formato",
    "quem_aparece": "Quem aparece", "gancho_visual": "Começo do vídeo", "cenario": "Cenário", "producao": "Produção",
    "rosto_nos_3s": "Rosto nos 3 primeiros segundos", "fala_nos_3s": "Alguém falando nos 3 primeiros segundos",
    "texto_na_tela_inicio": "Texto na tela logo no início", "legendas_queimadas": "Legenda da fala escrita na tela",
    "ritmo": "Ritmo de cortes", "cta_no_final": "Chamada no final", "mostra_ferramenta": "Ferramenta aparecendo na tela",
    "tom_de_voz": "Tom de voz",
    "musica_fundo": "Música de fundo", "tipo_musica": "Música", "volume_musica": "Volume da música",
    "tom_fala": "Tom da fala", "ritmo_fala": "Ritmo da fala", "qualidade_audio": "Áudio da fala", "efeitos_sonoros": "Efeitos sonoros",
}
SIM_NAO = {"convite_participacao", "mensagem_generica", "rosto_nos_3s", "fala_nos_3s", "texto_na_tela_inicio",
           "legendas_queimadas", "mostra_ferramenta", "musica_fundo", "efeitos_sonoros"}
VALORES = {"financas": "finanças", "dor": "dor do cliente", "historia_de_empreendedor": "história de empreendedor",
           "motivacao": "motivação", "historia": "história", "gestao": "gestão", "numero": "número", "comentar": "pedir para comentar",
           "salvar": "pedir para salvar", "compartilhar": "pedir para compartilhar",
           "receita_ou_tecnica": "ensinar a fazer", "promessa": "promessa", "seguir": "pedir para seguir",
           "link": "mandar para um link", "marketing": "marketing", "True": "sim", "imagem": "imagem estática",
           "carrossel": "carrossel", "reels": "Reels",
           "dono_do_negocio": "dono do negócio", "especialista_educador": "especialista ou educador", "cliente": "cliente",
           "ator_ou_modelo": "ator ou modelo", "ninguem": "ninguém", "rosto_falando": "rosto falando",
           "texto_grande": "texto grande", "produto": "produto", "bastidor_do_negocio": "bastidor do negócio",
           "antes_depois": "antes e depois", "tela_ou_print": "tela ou print", "cena_encenada": "cena encenada",
           "negocio_real": "negócio de verdade", "estudio": "estúdio", "casa": "casa", "rua": "rua", "tela": "tela",
           "caseira": "caseira", "semi_profissional": "semiprofissional", "profissional": "profissional",
           "rapido": "rápido", "medio": "médio", "lento": "lento", "falado": "falada", "escrito": "escrita",
           "ambos": "falada e escrita", "conversa_informal": "conversa informal", "aula_didatica": "aula",
           "energico_vendedor": "vendedor enérgico", "humor": "humor", "sem_fala": "sem fala",
           "sem_musica": "sem música", "instrumental_calma": "instrumental calma", "instrumental_animada": "instrumental animada",
           "musica_com_letra": "música com letra", "trend_viral": "áudio de tendência", "baixo_sob_a_fala": "baixa, por baixo da fala",
           "equilibrado": "equilibrada com a fala", "alto_compete_com_a_fala": "alta, competindo com a fala", "so_musica": "só música",
           "calmo_acolhedor": "calmo e acolhedor", "animado_energico": "animado e enérgico", "serio_direto": "sério e direto",
           "urgente_alarmista": "urgente e alarmista", "bem_humorado": "bem-humorado", "lento": "lento", "rapido": "rápido",
           "limpo": "limpo", "ruido_ambiente": "com ruído ambiente", "eco_ou_baixo": "com eco ou baixo"}


def base() -> fx.Base:
    """Base da coleta mais recente; recarrega sozinha quando a atualização semanal traz coleta ou análise nova."""
    coleta = Path(os.getenv("BOAPAUTA_COLETA", "")) if os.getenv("BOAPAUTA_COLETA") else \
        max((p for p in (ROOT / "data" / "raw").iterdir() if p.is_dir() and p.name[:4].isdigit()), key=lambda p: p.name)
    processados = ROOT / "data" / "processed"
    versao = tuple(int(a.stat().st_mtime) if a.exists() else 0
                   for a in (processados / "scores.csv", processados / "rotulos_texto.jsonl", processados / "rotulos_visuais.jsonl"))
    return _base_da_versao(str(coleta), versao)


@lru_cache(maxsize=2)
def _base_da_versao(coleta: str, versao: tuple) -> fx.Base:
    return fx.Base.carregar(Path(coleta))


@lru_cache(maxsize=1)
def store() -> Store:
    return Store(Path(os.getenv("BOAPAUTA_DB", str(ROOT / "data" / "app" / "boapauta.sqlite"))))


def frase(f: dict) -> str:
    """Achado em frase simples: o que aparece mais (ou menos) nos posts que mais engajam."""
    nome = ROTULOS.get(f["caracteristica"], f["caracteristica"])
    valor = VALORES.get(f["valor"], f["valor"].replace("_", " "))
    vezes = f.get("lift")                     # mesmo número do achado (lift suavizado), não a razão bruta
    if vezes is None and f.get("leitura") == "mais no top":   # 0% no grupo de comparação: não há razão a calcular
        sujeito = f"{nome}:" if f["caracteristica"] in SIM_NAO else f"{nome} “{valor}”"
        return f"{sujeito} aparece só nos posts que mais engajam, nunca nos outros."
    quanto = (f"{vezes:.1f}".replace(".", ",") + " vezes mais") if vezes and vezes >= 1 else "menos"
    if f["caracteristica"] in SIM_NAO:
        return f"{nome}: aparece {quanto} nos posts que mais engajam do que nos outros."
    return f"{nome} “{valor}” aparece {quanto} nos posts que mais engajam do que nos outros."


# ---------------------------------------------------------------- Início
@app.get("/api/panorama")
def panorama(segmento: Optional[str] = None) -> dict:
    df = base().posts
    achados = [f.model_dump() for f in fx.query_stats(base(), None, segmento) if f.leitura in ("mais no top", "menos no top")]
    from src.analysis.contas_stone import nome_caracteristica
    for a in achados:
        a["frase"] = frase(a)
        a["nome"] = nome_caracteristica(a["frase"])
        # engaja no orgânico, mas a Stone já testou em anúncio e não gerou clique: aparece, mas não vira recomendação
        a["recomendado"] = (a["caracteristica"], a["valor"]) != ("mensagem_generica", "True")
        a["exemplos"] = [r.model_dump() for r in fx.search_posts(base(), a["plataforma"], segmento, filtros_rotulo={a["caracteristica"]: a["valor"]},
                                                                 k=3, so_acionaveis=False)] if a["leitura"] == "mais no top" else []
    trends = [t.model_dump() for t in fx.format_trends(base(), "instagram", segmento)]
    return {
        "kpis": {"posts": int(len(df)), "perfis": int(df[["plataforma", "perfil_id"]].drop_duplicates().shape[0]),
                 "top": int((df["grupo"] == "top").sum()), "rotulados": int(df.get("tema_principal", pd.Series()).notna().sum()),
                 "coletado_em": str(pd.to_datetime(df["coletado_em"]).max().date()) if "coletado_em" in df else None},
        "achados": achados, "formatos": trends,
    }


@app.get("/api/exemplos")
def exemplos(plataforma: str, caracteristica: str, valor: str, segmento: Optional[str] = None, k: int = 6) -> list[dict]:
    """Posts reais do top que têm a característica do achado (para "Ver exemplos")."""
    filtro = {caracteristica: ("True" if valor == "True" else valor)}
    if caracteristica == "tipo":
        return [r.model_dump() for r in fx.search_posts(base(), plataforma, segmento, formato=valor, k=k, so_acionaveis=False)]
    return [r.model_dump() for r in fx.search_posts(base(), plataforma, segmento, filtros_rotulo=filtro, k=k,
                                                     so_acionaveis=False)]


@app.get("/api/posts/{post_id}")
def post(post_id: str) -> dict:
    df = base().posts
    linha = df[df["post_id"].astype(str) == post_id]
    if linha.empty:
        raise HTTPException(404, "post não encontrado")
    r = linha.iloc[0].replace({float("nan"): None}).to_dict()
    campos = ["post_id", "plataforma", "username", "tipo", "titulo", "legenda", "link", "publicado_em", "curtidas",
              "comentarios", "visualizacoes", "er", "lift_perfil", "grupo", "faixa", "tema_principal", "tipo_hook",
              "tipo_cta", "tom", "convite_participacao", "ferramentas_mencionadas", "thumbnail_url"]
    return {c: r.get(c) for c in campos}


class PedidoProposta(BaseModel):
    objetivo: str
    segmento: Optional[str] = None
    formato: Optional[str] = None


@app.post("/api/proposta")
def proposta(p: PedidoProposta) -> dict:
    return servico.proposta(base(), p.objetivo, p.segmento, p.formato)


# ---------------------------------------------------------------- Peças
class PedidoCriar(BaseModel):
    objetivo: str
    formato: str
    conta: Literal["impulsostone", "stone"] = "impulsostone"
    segmento: Optional[str] = None
    data_agenda: Optional[str] = None
    horario: Optional[str] = None


@app.post("/api/pecas")
def criar_peca(p: PedidoCriar) -> dict:
    return servico.criar_peca(store(), base(), p.objetivo, p.formato, p.segmento, p.data_agenda, p.horario, conta=p.conta)


class PedidoAjuste(BaseModel):
    motivo: str
    categoria: str = ""


def _mensagem_de_erro(exc: Exception) -> str:
    import re as _re
    msg = str(exc)
    if "429" in msg or "rate limit" in msg.lower():
        espera = _re.search(r"try again in ([0-9hms.]+)", msg)
        return "A cota diária do modelo de linguagem acabou. " + (
            f"Tente de novo em cerca de {espera.group(1).split('.')[0].replace('m', ' min ').replace('h', ' h ')}s."
            if espera else "Tente de novo mais tarde.")
    return f"Não deu certo: {msg[:200]}"


def _ao_vivo(trabalho):
    """Roda `trabalho(ao_evento)` numa thread e transmite cada etapa como evento (text/event-stream).

    O último evento é "pronto" (com a peça) ou "erro" (com a mensagem). O app monta o painel ao vivo com isso.
    """
    import json as _json
    import queue
    import threading

    from fastapi.responses import StreamingResponse

    fila: "queue.Queue" = queue.Queue()

    def rodar():
        try:
            peca = trabalho(lambda tipo, dados: fila.put((tipo, dados)))
            fila.put(("pronto", {"peca": peca}))
        except Exception as exc:  # noqa: BLE001 - o erro vira evento para o app, não 500
            fila.put(("erro", {"mensagem": _mensagem_de_erro(exc)}))
        fila.put(None)

    threading.Thread(target=rodar, daemon=True).start()

    def fluxo():
        while True:
            item = fila.get()
            if item is None:
                break
            tipo, dados = item
            corpo = _json.dumps(dados, ensure_ascii=False, default=str)
            yield f"event: {tipo}\ndata: {corpo}\n\n"

    return StreamingResponse(fluxo(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/api/pecas/ao-vivo")
def criar_peca_ao_vivo(p: PedidoCriar):
    """Mesmo que POST /api/pecas, mas transmitindo cada etapa do agente enquanto acontece."""
    return _ao_vivo(lambda avisar: servico.criar_peca(store(), base(), p.objetivo, p.formato, p.segmento,
                                                       p.data_agenda, p.horario, ao_evento=avisar, conta=p.conta))


@app.post("/api/pecas/{peca_id}/ajuste/ao-vivo")
def ajuste_ao_vivo(peca_id: str, p: PedidoAjuste, request: Request):
    if not p.motivo.strip():
        raise HTTPException(422, "explique o que precisa mudar")
    quem = _quem(request)
    return _ao_vivo(lambda avisar: servico.pedir_ajuste(store(), base(), peca_id, p.motivo, p.categoria, quem=quem, ao_evento=avisar))


@app.get("/api/pecas")
def listar_pecas() -> list[dict]:
    return store().listar()


@app.get("/api/pecas/{peca_id}")
def obter_peca(peca_id: str) -> dict:
    peca = store().obter(peca_id)
    if peca is None:
        raise HTTPException(404, "peça não encontrada")
    return peca


@app.post("/api/pecas/{peca_id}/aprovar")
def aprovar(peca_id: str, request: Request) -> dict:
    if store().obter(peca_id) is None:
        raise HTTPException(404, "peça não encontrada")
    return servico.aprovar(store(), peca_id, quem=_quem(request))


@app.post("/api/pecas/{peca_id}/ajuste")
def ajuste(peca_id: str, p: PedidoAjuste, request: Request) -> dict:
    if not p.motivo.strip():
        raise HTTPException(422, "explique o que precisa mudar")
    return servico.pedir_ajuste(store(), base(), peca_id, p.motivo, p.categoria, quem=_quem(request))


def _radar_itens() -> list[dict]:
    import json as _json
    caminho = ROOT / "data" / "processed" / "radar.json"
    return _json.loads(caminho.read_text(encoding="utf-8")).get("itens", []) if caminho.exists() else []


def _sinal_nicho() -> dict[str, int]:
    """Datas sazonais que os posts do top recente (até 60 dias) já citam: {data: quantos posts}."""
    df = base().posts
    if "data_sazonal" not in df:
        return {}
    top = df[(df["grupo"] == "top") & df["data_sazonal"].notna() & (pd.to_numeric(df["idade_dias"], errors="coerce") <= 60)]
    import unicodedata
    norm = top["data_sazonal"].astype(str).map(
        lambda t: "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)).lower().strip())
    return {k: int(v) for k, v in norm.value_counts().items() if k and k not in ("none", "nan") and v >= 2}


COMO_FAZER = {"musica_fundo", "volume_musica", "tom_fala", "ritmo_fala", "cenario", "quem_aparece", "gancho_visual",
              "rosto_nos_3s", "cta_no_final", "tipo_cta", "tipo_hook"}
TEMAS_AFINS = {"Educação financeira": ["financas", "gestao"], "Gestão e vendas": ["vendas", "gestao", "atendimento", "marketing", "financas"],
               "Especialistas": ["gestao", "financas", "ferramentas"], "Histórias reais": ["historia_de_empreendedor"],
               "Comunidade": ["historia_de_empreendedor", "vendas"]}
TEMA_DO_PILAR = {"Educação financeira": "financas", "Gestão e vendas": "vendas", "Histórias reais": "historia_de_empreendedor",
                 "Especialistas": "gestao", "Comunidade": None}


def _justificar(sugestoes: list[dict]) -> None:
    """Acrescenta a cada sugestão o "por que este post neste dia": quando, o quê (com o que a base mostra) e um
    post real do top como exemplo. Tudo vem da base e das regras; nada é escrito por modelo de linguagem."""
    from src.agent.grafo import PLATAFORMA_DO_FORMATO, TIPO_NA_BASE
    b = base()
    achados = {(a.plataforma, a.caracteristica, a.valor): a for a in fx.query_stats(b) if a.leitura == "mais no top"}
    from src.collection.storage import read_jsonl
    from src.analysis.escopo import PROMPT_VERSAO as VERSAO_ESCOPO
    orienta = {str(r["post_id"]) for r in read_jsonl(ROOT / "data" / "processed" / "rotulos_escopo.jsonl")
               if r.get("orienta_empreendedor") == "sim" and r.get("prompt_versao") == VERSAO_ESCOPO}
    for s in sugestoes:
        plat = PLATAFORMA_DO_FORMATO.get(s["formato"], "instagram")
        o_que = []
        f = achados.get((plat, "tipo", TIPO_NA_BASE.get(s["formato"]) or ""))
        if f:
            o_que.append(frase(f.model_dump()))
        tema = TEMA_DO_PILAR.get(s["pilar"])
        t = next((a for (p, c, v), a in achados.items() if c == "tema_principal" and v == tema), None) if tema else None
        if t:
            o_que.append(f"No {t.plataforma.capitalize()}: " + frase(t.model_dump()))
        # como fazer: os achados mais fortes da plataforma sobre o jeito do post (vídeo, áudio, gancho, chamada)
        if s["formato"] in ("reels", "short", "stories"):
            como = sorted((a for (p, c, v), a in achados.items() if p == plat and c in COMO_FAZER),
                          key=lambda a: (-(a.n_perfis or 0), -(a.lift or 99)))[:2]
        else:
            como = sorted((a for (p, c, v), a in achados.items() if p == plat and c in ("tipo_hook", "tipo_cta", "convite_participacao")),
                          key=lambda a: -(a.lift or 99))[:1]
        o_que += [frase(a.model_dump()) for a in como]
        if not o_que:
            o_que.append(f"{nomes_formato(s['formato'])} e o pilar {s['pilar']} entram no rodízio da semana: a agenda varia "
                         "formato, pilar e segmento para o perfil não ficar repetitivo.")
        # exemplo: post do top sobre o mesmo assunto, que a IA de escopo marcou como "orienta o empreendedor: sim";
        # varia entre os melhores conforme o dia, para a agenda não repetir o mesmo exemplo
        refs = []
        for t_ in TEMAS_AFINS.get(s["pilar"], []):
            for p_ in (plat, "youtube" if plat == "instagram" else "instagram"):
                refs = [r for r in fx.search_posts(b, p_, None, filtros_rotulo={"tema_principal": t_}, k=6) if r.post_id in orienta]
                if refs:
                    break
            if refs:
                break
        refs = refs or [r for r in fx.search_posts(b, plat, None, TIPO_NA_BASE.get(s["formato"]), k=6) if r.post_id in orienta]
        escolhido = refs[date.fromisoformat(s["data"]).toordinal() % len(refs)] if refs else None
        exemplo = escolhido.model_dump(include={"perfil", "link", "titulo_ou_trecho", "lift_perfil", "capa"}) if escolhido else None
        s["justificativa"] = {"quando": s["motivos"][0] if s["motivos"] else "", "o_que": o_que, "exemplo": exemplo}


def nomes_formato(f: str) -> str:
    return {"reels": "Reels", "carrossel": "Carrossel", "stories": "Stories", "short": "Short", "estatico": "Post estático"}.get(f, f)


# ---------------------------------------------------------------- radar de oportunidades (fontes oficiais)
@app.get("/api/radar")
def radar_semana() -> dict:
    """Novidades da semana em fontes oficiais (scripts/radar.py). Sem o arquivo, devolve lista vazia."""
    import json as _json
    caminho = ROOT / "data" / "processed" / "radar.json"
    if not caminho.exists():
        return {"gerado_em": None, "itens": [], "fontes": []}
    dados = _json.loads(caminho.read_text(encoding="utf-8"))
    return {"gerado_em": dados.get("gerado_em"), "itens": dados.get("itens", []),
            "fontes": [{"nome": f["nome"], "ok": f.get("ok")} for f in dados.get("fontes", [])]}


# ---------------------------------------------------------------- desempenho do agente
@app.get("/api/agente/metricas")
def metricas_agente() -> dict:
    """Tempo, tentativas, notas do avaliador e efeito da reescrita guiada por ele (data/processed/agent_runs.jsonl)."""
    import json as _json
    import statistics
    from scripts.medir_juiz import resumir
    caminho = Path(os.getenv("BOAPAUTA_RUNS", str(ROOT / "data" / "processed" / "agent_runs.jsonl")))
    linhas = [_json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()] if caminho.exists() else []
    lat = sorted(x["latencia_s"] for x in linhas if x.get("latencia_s") is not None)
    tent = [t for x in linhas for t in (x.get("tentativas") or [])]
    notas = [j["nota"] for x in linhas for j in (x.get("juiz") or []) if j.get("nota") is not None]
    p90 = lat[min(len(lat) - 1, int(round(0.9 * (len(lat) - 1))))] if lat else None
    return {"execucoes": len(linhas), "criativos": sum(x.get("criativos") or 0 for x in linhas),
            "latencia_mediana_s": round(statistics.median(lat), 1) if lat else None, "latencia_p90_s": round(p90, 1) if p90 else None,
            "chamadas_llm": sum(x.get("chamadas_llm") or 0 for x in linhas),
            "tentativas_media": round(sum(tent) / len(tent), 2) if tent else None,
            "primeira_tentativa_pct": round(sum(1 for t in tent if t == 1) / len(tent), 3) if tent else None,
            "nota_media_juiz": round(sum(notas) / len(notas), 2) if notas else None,
            "juiz": resumir(linhas), "ultima": linhas[-1]["momento"] if linhas else None}


# ---------------------------------------------------------------- Agenda
@app.get("/api/agenda")
def agenda(inicio: Optional[str] = None, dias: int = 14, segmento: Optional[str] = None) -> dict:
    hoje = date.fromisoformat(inicio) if inicio else date.today()
    dias = max(1, min(dias, 400))            # a busca do Planejamento pede 6 meses; mais que um ano não faz sentido
    # semana atual; no fim de semana a equipe já planeja a próxima, então começa na segunda seguinte
    segunda = hoje + timedelta(days=7 - hoje.weekday()) if not inicio and hoje.weekday() >= 5 else hoje - timedelta(days=hoje.weekday())
    top = base().posts[base().posts["grupo"] == "top"]
    contagem = top.get("segmento_perfil", pd.Series(dtype=object)).value_counts()
    segmentos = [segmento] if segmento else [s for s in contagem.index if s and s not in ("geral", "empreendedorismo")][:6]
    formatos = [f for f in [servico.formato_sugerido(base(), segmento), "carrossel", "reels"]]
    formatos = list(dict.fromkeys(formatos))
    sugestoes = gerar_agenda(segunda, dias, segmentos, formatos, radar=_radar_itens(), sinal_nicho=_sinal_nicho())
    _justificar(sugestoes)
    pecas = store().listar()
    return {"inicio": segunda.isoformat(), "hoje": hoje.isoformat(), "sugestoes": sugestoes, "pecas": pecas}


# ---------------------------------------------------------------- Playbook de conteúdo para a Stone (entregável)
@app.get("/api/playbook.html", include_in_schema=False)
def playbook_stone(baixar: bool = False):
    """Playbook gerado na hora a partir da base e das peças aprovadas (sem modelo de linguagem)."""
    from fastapi.responses import HTMLResponse
    from src.playbook import gerar
    cab = {"Content-Disposition": 'attachment; filename="playbook_impulso_stone.html"'} if baixar else {}
    return HTMLResponse(gerar(base(), store().listar(), frase), headers=cab)


# ---------------------------------------------------------------- Guia detalhado da semana (e-mail ao empreendedor)
class PedidoGuia(BaseModel):
    inicio: Optional[str] = None        # qualquer dia da semana; padrão: semana atual


@app.post("/api/guia")
def gerar_guia(p: PedidoGuia) -> dict:
    """Gera o guia detalhado da semana com as peças aprovadas (chama o modelo de linguagem)."""
    from src.guia import gerar_guia as gerar, semana_de
    from src.shared.llm_client import LLMClient
    dia = date.fromisoformat(p.inicio) if p.inicio else date.today()
    ini, fim = semana_de(dia)
    proxima = [s for s in agenda(inicio=(ini + timedelta(days=7)).isoformat(), dias=7)["sugestoes"]]
    try:
        pb = gerar(LLMClient(), base(), store().listar(), ini, proxima)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return store().salvar_guia(pb)


@app.get("/api/guia")
def listar_guias() -> list[dict]:
    return [{k: v for k, v in pb.items() if k != "html"} for pb in store().guias()]


@app.get("/api/guia/semana")
def resumo_semana(inicio: Optional[str] = None) -> dict:
    """Quantas peças aprovadas entram no guia desta semana (sem chamar o modelo)."""
    from src.guia import pecas_da_semana, semana_de
    ini, fim = semana_de(date.fromisoformat(inicio) if inicio else date.today())
    pecas = pecas_da_semana(store().listar(), ini, fim)
    return {"inicio": ini.isoformat(), "fim": fim.isoformat(),
            "pecas": [{"id": x["id"], "titulo": x["atual"]["criativo"]["titulo"], "formato": x["formato"]} for x in pecas]}


@app.get("/api/guia/{pb_id}.html", include_in_schema=False)
def guia_html(pb_id: str):
    from fastapi.responses import HTMLResponse
    pb = store().guia(pb_id)
    if pb is None:
        raise HTTPException(404, "guia não encontrado")
    return HTMLResponse(pb["html"])


# ---------------------------------------------------------------- Criadores
FOTOS = ROOT / "data" / "fotos"


def foto_url(plataforma: str, perfil: str) -> Optional[str]:
    """Foto de perfil baixada por scripts/baixar_fotos.py (APIs oficiais); None quando não há."""
    nome = f"{plataforma}_{perfil.lower() if plataforma == 'instagram' else perfil}.jpg"
    return f"/api/fotos/{nome}" if (FOTOS / nome).exists() else None


@app.get("/api/capas/{nome}", include_in_schema=False)
def capa(nome: str):
    """Capa de um post do top ou do grupo de comparação (scripts/baixar_capas.py)."""
    pasta = (ROOT / "data" / "capas").resolve()
    arquivo = (pasta / nome).resolve()
    if arquivo.parent != pasta or not arquivo.exists():
        raise HTTPException(404, "capa não encontrada")
    return FileResponse(arquivo, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@app.get("/api/fotos/{nome}", include_in_schema=False)
def foto(nome: str):
    arquivo = (FOTOS / nome).resolve()
    if arquivo.parent != FOTOS.resolve() or not arquivo.exists():   # só arquivos da pasta de fotos
        raise HTTPException(404, "foto não encontrada")
    return FileResponse(arquivo, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@app.get("/api/criadores")
def criadores(segmento: Optional[str] = None, transversais: Optional[int] = None, setoriais: Optional[int] = None,
              setores: Optional[str] = None) -> dict:
    prioritarios = [s for s in (setores or "").split(",") if s]
    lista, indicados = fx.creator_scorecard(base(), segmento, setores_prioritarios=prioritarios or None,
                                            transversais=transversais, setoriais=setoriais)
    convidados = {(c["plataforma"], c["perfil"]) for c in store().convites()}
    for c in lista:
        c["convidado"] = (c["plataforma"], c["perfil"]) in convidados
        c["foto"] = foto_url(c["plataforma"], c["perfil"])
    for grupo in ("transversais", "setoriais", "reservas", "excluidos"):
        for c in indicados.get(grupo, []):
            c["foto"] = foto_url(c["plataforma"], c["perfil"])
    return {"criadores": lista, "indicados": indicados,
            "nota_metodologica": "Autenticidade vem da análise de vídeo (camada 2, Gemini) quando há 3 ou mais posts "
                                 "do perfil analisados: fração em que aparece o dono do negócio ou o negócio de verdade. "
                                 "Sem isso, é aproximada pelo tipo de perfil. Alertas ficam fora da nota."}


@app.get("/api/criadores/{plataforma}/{perfil}")
def criador(plataforma: str, perfil: str) -> dict:
    lista, _ = fx.creator_scorecard(base())
    achado = next((c for c in lista if c["plataforma"] == plataforma and c["perfil"] == perfil), None)
    if achado is None:
        raise HTTPException(404, "criador não encontrado")
    df = base().posts
    chave = df["username"].astype(str).str.lower() == perfil.lower() if plataforma == "instagram" else df["perfil_id"] == perfil
    seus = df[(df["plataforma"] == plataforma) & chave & df["elegivel"].astype(bool)]
    melhores = seus.sort_values("lift_perfil", ascending=False).head(3)
    posts = [{"post_id": str(r["post_id"]), "formato": r["tipo"], "link": r.get("link"),
              "trecho": (r.get("titulo") if isinstance(r.get("titulo"), str) and r.get("titulo")
                         else " ".join(str(r.get("legenda") or "").split())[:140]),
              "lift_perfil": None if pd.isna(r["lift_perfil"]) else float(r["lift_perfil"])} for _, r in melhores.iterrows()]
    convidado = (plataforma, perfil) in {(c["plataforma"], c["perfil"]) for c in store().convites()}
    return {**achado, "melhores_posts": posts, "foto": foto_url(plataforma, perfil), "convidado": convidado}


class PedidoConvite(BaseModel):
    plataforma: str
    perfil: str
    nome: str = ""
    nota: Optional[int] = None


@app.post("/api/convites")
def convidar(p: PedidoConvite) -> list[dict]:
    store().convidar(p.plataforma, p.perfil, p.nome, p.nota)
    return store().convites()


@app.get("/api/convites")
def convites() -> list[dict]:
    return store().convites()


def _carrossel(peca_id: str) -> tuple[dict, list[Path]]:
    from src.rendering.carrossel_da_peca import renderizar_peca
    peca = store().obter(peca_id)
    if peca is None or peca["formato"] != "carrossel" or "criativo" not in peca["atual"]:
        raise HTTPException(404, "só peças de carrossel geradas têm slides")
    return peca, renderizar_peca(peca)


@app.get("/api/pecas/{peca_id}/slides")
def slides_da_peca(peca_id: str) -> list[str]:
    """Endereços dos slides em PNG (1080×1350, visual Impulso) da versão atual; renderiza na primeira vez."""
    peca, caminhos = _carrossel(peca_id)
    return [f"/api/pecas/{peca_id}/slides/{i}.png?v={peca['atualizado_em']}" for i in range(1, len(caminhos) + 1)]


@app.get("/api/pecas/{peca_id}/slides/{n}.png")
def slide_png(peca_id: str, n: int):
    _, caminhos = _carrossel(peca_id)
    if not 1 <= n <= len(caminhos):
        raise HTTPException(404, "slide não existe")
    return FileResponse(caminhos[n - 1], media_type="image/png")


@app.get("/api/pecas/{peca_id}/slides.zip")
def slides(peca_id: str):
    """Carrossel em PNG 1080×1350 no visual Impulso, num ZIP (renderizador do Case Suno, Playwright)."""
    from fastapi.responses import Response

    from src.rendering.playwright_renderer import zip_slides
    _, caminhos = _carrossel(peca_id)
    return Response(zip_slides(caminhos), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="carrossel_{peca_id}.zip"'})


@app.get("/api/segmentos")
def segmentos() -> list[str]:
    with (ROOT / "config" / "perfis.csv").open(encoding="utf-8") as f:
        return sorted({r["segmento"] for r in csv.DictReader(f) if r.get("tipo") == "setorial" and r.get("segmento")})


# ---------------------------------------------------------------- App React (build)
if FRONT.exists():
    app.mount("/assets", StaticFiles(directory=FRONT / "assets"), name="assets")

    @app.get("/{caminho:path}", include_in_schema=False)
    def spa(caminho: str):
        if caminho.startswith("api/"):            # rota de API inexistente não vira a página do app
            raise HTTPException(404, "rota não encontrada")
        return FileResponse(FRONT / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api:app", host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
