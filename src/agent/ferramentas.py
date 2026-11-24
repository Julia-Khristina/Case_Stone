"""Ferramentas determinísticas do agente: leem a base processada e devolvem números e posts reais.

O LLM nunca calcula nada: ele recebe o que estas funções devolvem e só redige. É o que garante a regra do TAPI
"os dados apresentados provêm sempre da base coletada".
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml

from src.agent.contrato import Finding, RefPost
from src.analysis.padroes import comparar
from src.collection.storage import read_jsonl

ROOT = Path(__file__).resolve().parents[2]
CAPAS = ROOT / "data" / "capas"
CAMPOS_PADRAO = ["tema_principal", "tipo_hook", "tipo_cta", "convite_participacao", "mensagem_generica",
                 # camada 2 (Gemini): o que se vê e se ouve
                 "quem_aparece", "gancho_visual", "cenario", "rosto_nos_3s", "fala_nos_3s",
                 "texto_na_tela_inicio", "legendas_queimadas", "cta_no_final",
                 # camada 2 v3: áudio (música, volume, tom e ritmo da fala, qualidade, efeitos)
                 "musica_fundo", "tipo_musica", "volume_musica", "tom_fala", "ritmo_fala", "qualidade_audio", "efeitos_sonoros"]
# producao, tom_de_voz e mostra_ferramenta ficam fora: instáveis na concordância (config/limiares.yaml)


@dataclass
class Base:
    """Posts com métricas, grupo (top/controle), rótulos de texto (camada 1) e visuais (camada 2)."""
    posts: pd.DataFrame

    @classmethod
    def carregar(cls, coleta: Path, processados: Path = ROOT / "data" / "processed") -> "Base":
        scores = pd.read_csv(processados / "scores.csv")
        rotulos = pd.DataFrame(read_jsonl(processados / "rotulos_texto.jsonl"))
        perfis = pd.DataFrame(read_jsonl(Path(coleta) / "perfis.jsonl"))
        df = scores.drop(columns=["titulo", "legenda", "link"], errors="ignore").merge(
            pd.DataFrame(read_jsonl(Path(coleta) / "posts.jsonl"))[["plataforma", "post_id", "titulo", "legenda", "link"]],
            on=["plataforma", "post_id"], how="left")
        if not rotulos.empty:
            rotulos = rotulos.drop_duplicates("post_id", keep="last").drop(columns=["modelo", "prompt_versao"], errors="ignore")
            df = df.merge(rotulos, on="post_id", how="left")
        visuais = pd.DataFrame(read_jsonl(processados / "rotulos_visuais.jsonl"))
        if not visuais.empty:
            from src.analysis.camada2 import VERSOES_ACEITAS
            visuais = visuais[visuais.get("prompt_versao").isin(VERSOES_ACEITAS)]
            visuais = visuais.assign(_v=visuais["prompt_versao"].map(VERSOES_ACEITAS.index)).sort_values("_v").drop(columns="_v")
        if not visuais.empty:
            visuais = visuais.drop_duplicates("post_id", keep="last").drop(
                columns=["plataforma", "modelo", "prompt_versao", "posts_no_pedido"], errors="ignore").rename(columns={"resumo": "resumo_visual"})
            visuais["post_id"] = visuais["post_id"].astype(str)
            df["post_id"] = df["post_id"].astype(str)
            df = df.merge(visuais, on="post_id", how="left")
        if not perfis.empty and "segmento" in perfis:
            df = df.merge(perfis[["plataforma", "perfil_id", "segmento"]].rename(columns={"segmento": "segmento_perfil"}),
                          on=["plataforma", "perfil_id"], how="left")
        return cls(df)

    def recorte(self, plataforma: Optional[str] = None, segmento: Optional[str] = None,
                faixa: Optional[str] = None) -> pd.DataFrame:
        df = self.posts
        if plataforma:
            df = df[df["plataforma"] == plataforma]
        if faixa:
            df = df[df["faixa"] == faixa]
        if segmento:
            por_rotulo = df.get("segmento_negocio", pd.Series(index=df.index, dtype=object)) == segmento
            por_perfil = df.get("segmento_perfil", pd.Series(index=df.index, dtype=object)) == segmento
            df = df[por_rotulo | por_perfil]
        return df


def query_stats(base: Base, plataforma: Optional[str] = None, segmento: Optional[str] = None,
                faixa: Optional[str] = None, campos: list[str] = CAMPOS_PADRAO) -> list[Finding]:
    """Padrões top × controle de cada campo, por plataforma (as plataformas nunca são misturadas)."""
    achados = []
    plataformas = [plataforma] if plataforma else sorted(base.posts["plataforma"].dropna().unique())
    for plat in plataformas:
        df = base.recorte(plat, segmento, faixa)
        df = df[df["grupo"].isin(["top", "controle"])]
        if df.empty:
            continue
        for campo in campos:
            if campo not in df or df[campo].isna().all():
                continue
            tabela = comparar(df.dropna(subset=[campo]), campo)
            for valor, r in tabela.iterrows():
                if str(valor) in ("False", "—"):   # sim/não: o lado "não" só repete o "sim" ao contrário
                    continue
                achados.append(Finding(plataforma=plat, caracteristica=campo, valor=str(valor), pct_top=round(r.pct_top, 3),
                                       pct_controle=round(r.pct_controle, 3),
                                       lift=None if pd.isna(r.lift) else round(float(r.lift), 2),
                                       ic=(round(float(r.ic_baixo), 2), round(float(min(r.ic_alto, 999)), 2)),
                                       n_top=int(r.n_top), n_perfis=int(r.n_perfis_top), leitura=r.leitura))
    ordem = {"mais no top": 0, "menos no top": 1, "concentrado em poucos perfis": 2, "inconclusivo": 3}
    return sorted(achados, key=lambda f: (ordem.get(f.leitura, 9), -(f.lift or 0)))


def format_trends(base: Base, plataforma: str = "instagram", segmento: Optional[str] = None) -> list[Finding]:
    """Formatos que aparecem mais no top. Só no Instagram: no YouTube, Short e vídeo longo são ranqueados à parte."""
    if plataforma != "instagram":
        return []
    df = base.recorte(plataforma, segmento)
    df = df[df["grupo"].isin(["top", "controle"])]
    if df.empty:
        return []
    return [f for f in query_stats(Base(df), plataforma, campos=["tipo"])]


MEIA_VIDA_DIAS = 45   # peso da recência na escolha das referências


def search_posts(base: Base, plataforma: Optional[str] = None, segmento: Optional[str] = None,
                 formato: Optional[str] = None, filtros_rotulo: Optional[dict[str, str]] = None, k: int = 5,
                 so_acionaveis: bool = True) -> list[RefPost]:
    """Posts de referência: só do top, ordenados pelo quanto superaram a média do próprio perfil (lift).

    `so_acionaveis=False` mostra também posts motivacionais ou fora do tema: serve para provar um achado
    ("Ver exemplos"), não para inspirar um criativo.
    """
    df = base.recorte(plataforma, segmento)
    df = df[df["grupo"] == "top"]
    if so_acionaveis and "tema_principal" in df:
        # Só temas acionáveis servem de inspiração. Posts virais fora do tema (opinião sobre eleição, luto) e
        # motivacionais engajam, mas não ensinam a fazer um criativo para a Stone (e o Ads da Stone mostra que
        # frase motivacional não gera clique).
        df = df[~df["tema_principal"].astype(str).isin(["outro", "motivacao", "receita_ou_tecnica"])]
    if formato:
        df = df[df["tipo"] == formato]
    for campo, valor in (filtros_rotulo or {}).items():
        if campo in df:
            df = df[df[campo].astype(str) == str(valor)]
    # Recência pesa: o que engaja muda rápido, então entre posts fortes o mais novo vem antes (meia-vida de 45 dias).
    idade = pd.to_numeric(df.get("idade_dias"), errors="coerce").fillna(90) if "idade_dias" in df else 90
    df = df.assign(_forca=df["lift_perfil"].fillna(0) * (0.5 ** (idade / MEIA_VIDA_DIAS)))
    df = df.sort_values(["_forca", "er"], ascending=False).drop_duplicates("username").head(k)   # 1 por perfil
    refs = []
    for _, r in df.iterrows():
        trecho = (r.get("titulo") if isinstance(r.get("titulo"), str) and r.get("titulo") else
                  " ".join(str(r.get("legenda") or "").split())[:160])
        categorias = {c: str(r[c]) for c in ("tema_principal", "tipo_hook", "tipo_cta", "tom") if c in r and pd.notna(r[c])}
        partes = [" ".join(str(r.get("legenda") or "").split())[:600]]
        if isinstance(r.get("resumo_visual"), str) and r.get("resumo_visual"):
            partes.append(f"No vídeo: {r['resumo_visual']}")
        if isinstance(r.get("fala_inicial"), str) and r.get("fala_inicial"):
            partes.append(f"Primeiras falas: {r['fala_inicial']}")
        refs.append(RefPost(post_id=str(r["post_id"]), plataforma=r["plataforma"], perfil=str(r.get("username")),
                            formato=str(r.get("tipo")), link=r.get("link") if isinstance(r.get("link"), str) else None,
                            titulo_ou_trecho=trecho or "", conteudo=" | ".join(x for x in partes if x),
                            capa=f"/api/capas/{r['post_id']}.jpg" if (CAPAS / f"{r['post_id']}.jpg").exists() else None, er=None if pd.isna(r.get("er")) else float(r["er"]),
                            lift_perfil=None if pd.isna(r.get("lift_perfil")) else float(r["lift_perfil"]),
                            categorias=categorias))
    return refs


def creator_scorecard(base: Base, segmento: Optional[str] = None, pesos: Optional[dict] = None,
                      setores_prioritarios: Optional[list[str]] = None, transversais: Optional[int] = None,
                      setoriais: Optional[int] = None) -> tuple[list[dict], dict]:
    """Scorecard de todos os criadores da amostra e a indicação para parceria (config/segmentos.yaml)."""
    import csv

    from src.analysis.indicacao import selecionar_indicados
    from src.analysis.scorecard import calcular
    from src.evaluation.thresholds import load_thresholds

    with (ROOT / "config" / "perfis.csv").open(encoding="utf-8") as f:
        lista = pd.DataFrame(list(csv.DictReader(f)))
    contexto = load_stone_context()
    pesos = pesos or dict(load_thresholds(ROOT / "config" / "limiares.yaml").get("scorecard_pesos") or {}) or None
    tabela = calcular(base.posts, lista, contexto.get("concorrentes", []), pesos)
    if segmento:
        tabela = tabela[(tabela["segmento"] == segmento)]
    colunas = ["plataforma", "perfil", "nome", "username", "faixa", "seguidores", "tipo", "macrossetor", "tema",
               "segmento", "nota", "consistencia", "conversa", "autenticidade", "marca", "frequencia", "alertas",
               "posts_elegiveis", "posts_rotulados", "posts_vistos", "autenticidade_fonte", "parceiro_atual"]
    criadores = tabela[[c for c in colunas if c in tabela]].replace({np.nan: None}).to_dict("records")
    config = (yaml.safe_load((ROOT / "config" / "segmentos.yaml").read_text(encoding="utf-8")) or {}).get("indicacao", {})
    if setores_prioritarios:
        config = {**config, "setores_prioritarios": setores_prioritarios}
    if transversais is not None:
        config = {**config, "transversais": transversais}
    if setoriais is not None:
        config = {**config, "setoriais": setoriais}
    for c in criadores:
        c["parceiro_atual"] = str(c.get("parceiro_atual")).lower() in {"sim", "true", "1"}
    indicados = selecionar_indicados(criadores, config)
    return criadores, indicados


def load_stone_context(caminho: Path = ROOT / "config" / "stone_context.yaml",
                       interno: Optional[Path] = None) -> dict:
    """Contexto da Stone (tom, pilares, parceiros) + dados internos (persona, aprendizados do Ads).

    Os internos ficam em config/stone_interno.yaml, fora do git; sem o arquivo, o contexto vem sem eles.
    """
    contexto = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    interno = interno or caminho.with_name("stone_interno.yaml")
    if interno.exists():
        contexto.update(yaml.safe_load(interno.read_text(encoding="utf-8")) or {})
    return contexto


CONTAS = {"impulsostone": "Impulso Stone", "stone": "Stone"}


def contexto_da_conta(conta: str = "impulsostone") -> dict:
    """Contexto com a oferta da conta escolhida: o Impulso (educação, mentoria) ou a marca Stone (produtos)."""
    contexto = load_stone_context()
    if conta == "stone" and contexto.get("oferta_stone"):
        contexto["oferta"] = contexto["oferta_stone"]
    contexto["conta"], contexto["marca"] = conta, CONTAS.get(conta, "Impulso Stone")
    return contexto


def evidencia_com_reserva(base: Base, plataforma: str, segmento: Optional[str], formato_na_base: Optional[str],
                          minimo_refs: int = 3) -> tuple[list, list[RefPost], bool]:
    """Padrões e referências do segmento; quando o recorte tem pouca evidência, completa com os gerais.

    Devolve (achados, referências, usou_reserva). O app e o agente avisam quando a reserva foi usada.
    """
    achados = query_stats(base, plataforma, segmento)
    refs = search_posts(base, plataforma, segmento, formato_na_base, k=5) or search_posts(base, plataforma, segmento, k=5)
    fortes = [f for f in achados if f.leitura in ("mais no top", "menos no top")]
    usou = False
    if segmento and not fortes:
        achados, usou = query_stats(base, plataforma, None), True
    if segmento and len(refs) < minimo_refs:
        ids = {r.post_id for r in refs}
        gerais = search_posts(base, plataforma, None, formato_na_base, k=5) or search_posts(base, plataforma, None, k=5)
        refs = refs + [r for r in gerais if r.post_id not in ids][: 5 - len(refs)]
        usou = True
    return achados, refs, usou
