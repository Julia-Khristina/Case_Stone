"""Playbook de conteúdo para a Stone (entregável do TAPI, seção 10).

Sugestões de melhoria para o Instagram da @stone e do @impulsostone: cada conta é comparada com o que engaja no
nicho (55 perfis que falam com MPEs) e com ela mesma, e cada seção diz para qual conta é. Traz também o que engaja,
o que evitar, formatos, perfis em destaque, exemplos reais e os criativos aprovados prontos para produção. Sem modelo de linguagem: cada
número sai da base (src/agent/ferramentas.py) e cada criativo é uma peça aprovada no app. Gerar de novo depois de
uma coleta nova atualiza tudo.

Rodar: python scripts/gerar_playbook.py   (ou GET /api/playbook.html com o app no ar)
"""
from __future__ import annotations

import html
from functools import lru_cache
from pathlib import Path
from datetime import date, datetime
from typing import Callable, Optional

import pandas as pd
import yaml

from src.agent import ferramentas as fx

MINIMO_CRIATIVOS = 5          # o TAPI pede no mínimo cinco propostas prontas para produção

SEGMENTOS = {"alimentacao": "Alimentação", "artesanato_producao": "Artesanato e produção", "beleza_estetica": "Beleza e estética",
             "comercio_bairro": "Comércio de bairro", "moda_acessorios": "Moda e acessórios", "pets": "Pets",
             "transporte_entregas": "Transporte e entregas", "servicos": "Serviços", "financas": "Finanças", "vendas": "Vendas",
             "marketing": "Marketing", "gestao": "Gestão", "empreendedorismo": "Empreendedorismo", "geral": "Geral"}
FORMATOS = {"reels": "Reels", "carrossel": "Carrossel", "stories": "Stories", "short": "Short", "shorts": "Short",
            "video": "Vídeo longo", "imagem": "Imagem estática"}
PARTE = {"reels": "Cena", "short": "Cena", "shorts": "Cena", "carrossel": "Slide", "stories": "Tela"}
CONFERENCIAS = {"referencias_existem": "Baseado em posts reais da base", "caso_concreto": "Parte de um caso concreto",
                "sem_contas": "Sem contas nem fórmulas", "cta_presente": "Termina com um próximo passo claro",
                "sem_promessa_exagerada": "Sem promessas exageradas", "fiel_a_oferta": "Fiel ao que o Impulso oferece",
                "linguagem_simples": "Linguagem simples", "tamanho_do_formato": "Tamanho certo para o formato"}
COMPONENTES = {"consistencia": "Consistência", "conversa": "Conversa", "autenticidade": "Autenticidade",
               "marca": "Combina com a marca", "frequencia": "Frequência"}
DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
NOME_DIA = {"segunda": "Segunda", "terca": "Terça", "quarta": "Quarta", "quinta": "Quinta", "sexta": "Sexta",
            "sabado": "Sábado", "domingo": "Domingo"}
# Achado que engaja no orgânico, mas a Stone já testou em anúncio e não gerou clique: aparece, mas não vira recomendação
NAO_RECOMENDAR = {("mensagem_generica", "True")}


def _num(x: float, casas: int = 1) -> str:
    return "—" if x is None else f"{x:.{casas}f}".replace(".", ",")


def _vezes(lift: Optional[float], casas: int = 1) -> str:
    """'3,0×'; sem lift (0% no grupo de comparação) vira 'só no top'."""
    return "só no top" if lift is None else f"{_num(lift, casas)}×"


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _link_perfil(plataforma: str, perfil: str, username: Optional[str] = None) -> str:
    if plataforma == "instagram":
        return f"https://www.instagram.com/{username or perfil}/"
    return f"https://www.youtube.com/channel/{perfil}"


def _plataforma(p: str) -> str:
    return "YouTube" if p == "youtube" else "Instagram"


# ---------------------------------------------------------------- dados
def montar(base: fx.Base, pecas: list[dict], frase: Callable[[dict], str], contexto: Optional[dict] = None) -> dict:
    """Reúne tudo o que o playbook mostra. `frase` transforma um achado em frase simples (a mesma do app)."""
    contexto = contexto if contexto is not None else fx.load_stone_context()
    df = base.posts
    elegiveis = df[df["elegivel"].astype(bool)] if "elegivel" in df else df

    achados = []
    for f in fx.query_stats(base):
        if f.leitura not in ("mais no top", "menos no top"):
            continue
        a = f.model_dump()
        a["frase"] = frase(a)
        filtro = {f.caracteristica: f.valor}
        a["exemplos"] = [r.model_dump() for r in fx.search_posts(base, f.plataforma, filtros_rotulo=filtro, k=2, so_acionaveis=False)] \
            if f.leitura == "mais no top" else []
        a["recomendar"] = (f.caracteristica, f.valor) not in NAO_RECOMENDAR
        achados.append(a)
    # mesmo achado com sinal trocado entre as redes: avisar para tratar cada rede separadamente
    for a in achados:
        oposto = next((b for b in achados if b is not a and b["caracteristica"] == a["caracteristica"]
                       and b["valor"] == a["valor"] and b["leitura"] != a["leitura"]), None)
        a["oposto_em"] = _plataforma(oposto["plataforma"]) if oposto else None

    criadores, indicados = fx.creator_scorecard(base)
    for grupo in ("transversais", "setoriais", "reservas"):
        for c in indicados.get(grupo, []):
            c["link"] = _link_perfil(c["plataforma"], c["perfil"], c.get("username"))
    destaque = sorted([c for c in criadores if not c.get("parceiro_atual")], key=lambda c: -(c.get("nota") or 0))[:10]
    for c in destaque:
        c["link"] = _link_perfil(c["plataforma"], c["perfil"], c.get("username"))

    aprovadas = sorted([p for p in pecas if p.get("status") == "aprovada" and p.get("atual", {}).get("criativo")],
                       key=lambda p: (p.get("data_agenda") or "9999", p.get("atualizado_em") or ""))
    horarios = yaml.safe_load((fx.ROOT / "config" / "horarios.yaml").read_text(encoding="utf-8")) or {}

    datas = pd.to_datetime(elegiveis.get("publicado_em"), errors="coerce", utc=True).dropna()
    coletado = pd.to_datetime(df.get("coletado_em"), errors="coerce", utc=True).dropna()
    return {
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "base": {"posts": int(len(df)), "elegiveis": int(len(elegiveis)),
                 "perfis": int(df[["plataforma", "perfil_id"]].drop_duplicates().shape[0]),
                 "top": int((df["grupo"] == "top").sum()), "controle": int((df["grupo"] == "controle").sum()),
                 "de": datas.min().strftime("%d/%m/%Y") if len(datas) else "—",
                 "ate": datas.max().strftime("%d/%m/%Y") if len(datas) else "—",
                 "coletado_em": coletado.max().strftime("%d/%m/%Y") if len(coletado) else "—"},
        "usar": [a for a in achados if a["leitura"] == "mais no top"],
        "evitar": [a for a in achados if a["leitura"] == "menos no top"],
        "formatos": [t.model_dump() for t in fx.format_trends(base, "instagram")],
        "ads": contexto.get("aprendizados_ads", {}),
        "indicados": indicados, "destaque": destaque, "parceiros": contexto.get("parceiros_atuais", []),
        "exemplos": {p: [r.model_dump() for r in fx.search_posts(base, p, k=6)] for p in ("instagram", "youtube")},
        "criativos": aprovadas,
        "horarios": horarios,
        "contas": _contas(base, frase),
    }


# ---------------------------------------------------------------- contas da Stone
def _contas(base: fx.Base, frase: Callable[[dict], str]) -> list[dict]:
    """Diagnóstico de @stone e @impulsostone com as recomendações de cada uma (vazio se a coleta não rodou)."""
    from src.analysis import contas_stone as cs
    df = cs.carregar()
    if df is None or df.empty:
        return []
    contas = cs.diagnosticar(base, df, frase)
    achados_nicho = {(f.caracteristica, f.valor): f for f in fx.query_stats(base, "instagram") if f.leitura == "mais no top"}
    for c in contas:
        c["recomendacoes"] = _recomendacoes(base, c, achados_nicho)
    return contas


def _recomendacoes(base: fx.Base, c: dict, achados_nicho: dict) -> list[dict]:
    """Regras simples e explícitas: cada recomendação diz de onde vem (nicho, própria conta ou os dois)."""
    recs = []
    fmt = {f["tipo"]: f for f in c["formatos"]}
    reels, carrossel, imagem = fmt.get("reels"), fmt.get("carrossel"), fmt.get("imagem")
    if reels and reels["pct_top"] and reels["pct_conta"] + 0.1 < reels["pct_top"] and (reels["lift_mediano_conta"] or 0) >= 1.1:
        recs.append({"acao": "fazer_mais", "titulo": "Reels",
                     "evidencia": f"Reels são {_pct(reels['pct_conta'])} dos posts da conta e {_pct(reels['pct_top'])} dos posts que mais engajam no nicho. "
                                  f"Na própria conta, Reels rendem {_num(reels['lift_mediano_conta'])}× a mediana.",
                     "fonte": "nicho e conta", "conta_pct": reels["pct_conta"], "nicho_pct": reels["pct_top"], "lift_conta": reels["lift_mediano_conta"],
                     "refs": [r.model_dump() for r in fx.search_posts(base, "instagram", formato="reels", k=3)]})
    if carrossel and carrossel["lift_mediano_conta"] is not None and carrossel["lift_mediano_conta"] <= 0.85:
        recs.append({"acao": "rever", "titulo": "Carrosséis",
                     "evidencia": f"Carrossel é {_pct(carrossel['pct_conta'])} dos posts da conta, mas rende {_num(carrossel['lift_mediano_conta'], 2)}× "
                                  f"a mediana da própria conta. No nicho, carrossel é {_pct(carrossel['pct_top'] or 0)} do top.",
                     "fonte": "conta", "conta_pct": carrossel["pct_conta"], "nicho_pct": carrossel["pct_top"], "lift_conta": carrossel["lift_mediano_conta"],
                     "refs": [r.model_dump() for r in fx.search_posts(base, "instagram", formato="carrossel", k=3)]})
    if imagem and imagem["leitura_nicho"] == "menos no top" and imagem["pct_conta"] > (imagem["pct_top"] or 0):
        recs.append({"acao": "fazer_menos", "titulo": "Imagem estática no orgânico",
                     "evidencia": f"Imagem é {_pct(imagem['pct_conta'])} dos posts da conta; no nicho aparece {_pct(imagem['pct_top'])} no top "
                                  f"e {_pct(imagem['pct_controle'])} no grupo de comparação.", "fonte": "nicho", "refs": [],
                     "conta_pct": imagem["pct_conta"], "nicho_pct": imagem["pct_top"], "lift_conta": imagem["lift_mediano_conta"]})
    for x in c["acima"]:
        if x["campo"] == "tipo" or x["valor"] == "motivacao":
            continue
        nicho = achados_nicho.get((x["campo"], x["valor"]))
        recs.append({"acao": "repetir", "titulo": f"Repetir: {x['frase']}",
                     "evidencia": f"{x['n']} posts da conta com isso rendem {_num(x['lift_mediano'])}× a mediana da própria conta"
                                  + (f", e o nicho confirma: aparece {_num(nicho.lift)}× mais nos posts que mais engajam." if nicho else "."),
                     "fonte": "conta e nicho" if nicho else "conta", "lift_conta": x["lift_mediano"], "n": x["n"],
                     "refs": [r.model_dump() for r in fx.search_posts(base, "instagram", filtros_rotulo={x["campo"]: x["valor"]}, k=3)]})
    menos_nicho = {(a["caracteristica"], a["valor"]): a for a in c["lacunas"] if a["leitura"] == "menos no top"}
    juntos = set()
    for x in c["abaixo"]:
        if x["campo"] == "tipo":
            continue
        nicho = menos_nicho.get((x["campo"], x["valor"]))
        evidencia = f"{x['n']} posts da conta com isso rendem {_num(x['lift_mediano'], 2)}× a mediana da própria conta"
        if nicho:
            juntos.add((x["campo"], x["valor"]))
            evidencia += (f", e o nicho confirma: está em {_pct(nicho['pct_conta'])} dos posts da conta, "
                          f"{_pct(nicho['pct_top'])} do top e {_pct(nicho['pct_controle'])} do grupo de comparação")
        recs.append({"acao": "fazer_menos" if nicho else "rever", "titulo": f"Rever: {x['frase']}", "evidencia": evidencia + ".",
                     "fonte": "conta e nicho" if nicho else "conta", "refs": [], "lift_conta": x["lift_mediano"], "n": x["n"],
                     "conta_pct": nicho["pct_conta"] if nicho else None, "nicho_pct": nicho["pct_top"] if nicho else None})
    for a in c["lacunas"]:
        if (a["caracteristica"], a["valor"]) in juntos:
            continue
        if a["acao"] == "fazer_mais":
            recs.append({"acao": "fazer_mais", "titulo": f"Usar mais: {_so_nome(a['frase'])}",
                         "evidencia": f"Está em {_pct(a['pct_conta'])} dos {a['n_conta']} posts da conta analisados e em {_pct(a['pct_top'])} dos posts que mais engajam no nicho "
                                      f"({_vezes(a['lift'])} o grupo de comparação, {a['n_perfis']} perfis).",
                         "fonte": "nicho", "refs": a.get("referencias", []), "conta_pct": a["pct_conta"], "nicho_pct": a["pct_top"]})
        elif a["acao"] == "fazer_menos":
            recs.append({"acao": "fazer_menos", "titulo": f"Usar menos: {_so_nome(a['frase'])}",
                         "evidencia": f"Está em {_pct(a['pct_conta'])} dos {a['n_conta']} posts da conta analisados; no nicho aparece {_pct(a['pct_top'])} no top "
                                      f"e {_pct(a['pct_controle'])} no grupo de comparação.", "fonte": "nicho", "refs": [],
                         "conta_pct": a["pct_conta"], "nicho_pct": a["pct_top"]})
    ordem = {"fazer_mais": 0, "repetir": 1, "rever": 2, "fazer_menos": 3}
    return sorted(recs, key=lambda r: ordem[r["acao"]])


# ---------------------------------------------------------------- HTML
def _e(t) -> str:
    return html.escape(str(t if t is not None else ""))



def _milhar(n) -> str:
    return f"{int(n or 0):,}".replace(",", ".")



def _sem_prefixo(t: str) -> str:
    import re
    return re.sub(r"^\s*((slide|tela|cena)\s*\d+\s*[:\-–]\s*|\d+[.)]\s*)+", "", str(t), flags=re.I).strip()



PARA = {"impulsostone": ("Para @impulsostone", "p-impulso"), "stone": ("Para @stone", "p-stone"), "ambas": ("Para as duas contas", "p-ambas")}
ACAO = {"fazer_mais": "Fazer mais", "repetir": "Repetir", "rever": "Rever", "fazer_menos": "Fazer menos"}
ICONE_ACAO = {"fazer_mais": "M12 5v14M5 12h14", "repetir": "M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3M18 3v4h-4M6 21v-4h4",
              "rever": "M12 8v5M12 16.5v.5M10.3 3.9 2.5 17.5A2 2 0 0 0 4.2 20.5h15.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
              "fazer_menos": "M5 12h14"}


# ---------------------------------------------------------------- imagens embutidas (o HTML abre offline)
@lru_cache(maxsize=512)
def _img(caminho: str, largura: int = 320) -> Optional[str]:
    """Imagem reduzida em JPEG base64; None se o arquivo não existe."""
    import base64
    import io
    from PIL import Image
    p = Path(caminho)
    if not p.exists():
        return None
    try:
        im = Image.open(p).convert("RGB")
        im.thumbnail((largura, int(largura * 1.7)))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=70, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001 - imagem corrompida não derruba o playbook
        return None


def _capa_nicho(post_id) -> Optional[str]:
    return _img(str(fx.ROOT / "data" / "capas" / f"{post_id}.jpg"))


def _capa_conta(post_id) -> Optional[str]:
    return _img(str(fx.ROOT / "data" / "contas_stone" / "capas" / f"{post_id}.jpg"))


def _foto(c: dict) -> Optional[str]:
    nome = f"{c['plataforma']}_{(c.get('username') or c['perfil']).lower() if c['plataforma'] == 'instagram' else c['perfil']}.jpg"
    return _img(str(fx.ROOT / "data" / "fotos" / nome), 120)


def _para(chave: str) -> str:
    rotulo, cls = PARA[chave]
    return f"<span class='para {cls}'>{rotulo}</span>"


def _so_nome(frase: str) -> str:
    """'Tema “finanças” aparece 6,6 vezes mais…' → 'Tema “finanças”'."""
    from src.analysis.contas_stone import nome_caracteristica
    return nome_caracteristica(frase)


def _icone(caminho: str, cls: str = "ic") -> str:
    return f"<svg class='{cls}' viewBox='0 0 24 24' aria-hidden='true'><path d='{caminho}'/></svg>"


# ---------------------------------------------------------------- peças visuais
def _barras(conta: Optional[float], nicho: Optional[float]) -> str:
    """Duas barras: quanto a conta usa × quanto aparece no top do nicho."""
    if conta is None or nicho is None:
        return ""
    return (f"<div class='barras'><div><span>Na conta</span><i><b class='b-conta' style='width:{max(2, round(conta * 100))}%'></b></i><em>{_pct(conta)}</em></div>"
            f"<div><span>No top do nicho</span><i><b class='b-nicho' style='width:{max(2, round(nicho * 100))}%'></b></i><em>{_pct(nicho)}</em></div></div>")


def _rende(lift: Optional[float]) -> str:
    """'Rende 1,8×' com uma régua onde 1,0× é o post típico da conta."""
    if lift is None:
        return ""
    pos = max(3, min(97, lift / 2.5 * 100))
    tom = "alto" if lift >= 1.1 else ("baixo" if lift <= 0.9 else "")
    return (f"<div class='rende {tom}'><b>{_num(lift)}×</b><span>a mediana da conta</span>"
            f"<div class='regua'><i class='meio'></i><i class='ponto' style='left:{pos:.0f}%'></i></div></div>")


def _miniaturas(refs: list[dict], n: int = 3) -> str:
    itens = []
    for r in (refs or [])[:n]:
        if not r.get("link"):
            continue
        capa = _capa_nicho(r.get("post_id"))
        fundo = f"<img src='{capa}' alt='' loading='lazy'>" if capa else "<span class='sem-capa'>▶</span>"
        lift = f"<em>{_num(r['lift_perfil'])}×</em>" if r.get("lift_perfil") else ""
        itens.append(f"<a class='mini' href='{_e(r['link'])}' target='_blank' rel='noreferrer'>{fundo}{lift}<small>@{_e(r.get('perfil'))}</small></a>")
    return f"<div class='minis'>{''.join(itens)}</div>" if itens else ""


def _cartao_rec(r: dict, grande: bool, n: int = 0) -> str:
    titulo = _e(r["titulo"].split(": ", 1)[-1])
    corpo = (_barras(r.get("conta_pct"), r.get("nicho_pct")) + _rende(r.get("lift_conta"))) if grande else ""
    refs = _miniaturas(r.get("refs")) if grande else ""
    return (f"<article class='rec rec-{r['acao']} {'grande' if grande else ''}'>{f'<span class=rec-n>{n}</span>' if n else ''}"
            f"<header><span class='acao'>{_icone(ICONE_ACAO[r['acao']])}{ACAO[r['acao']]}</span><span class='fonte'>base: {_e(r['fonte'])}</span></header>"
            f"<h4>{titulo}</h4>{corpo}<p>{_e(r['evidencia'])}</p>"
            + (f"<div class='refs-titulo'>Referências do nicho</div>{refs}" if refs else "") + "</article>")


def _medidor(c: dict) -> str:
    """Engajamento da conta × mediana dos perfis do nicho na mesma faixa."""
    maior = max(c["er_conta"], c["er_nicho"] or 0) * 1.15 or 1
    razao = c["er_conta"] / c["er_nicho"] if c["er_nicho"] else None
    if razao is None:
        leitura, tom = "—", ""
    elif 0.85 <= razao <= 1.15:
        leitura, tom = "no mesmo nível do nicho", "igual"
    elif razao < 1:
        leitura, tom = f"{_num(1 / razao)}× abaixo do nicho", "abaixo"
    else:
        leitura, tom = f"{_num(razao)}× acima do nicho", "acima"
    return (f"<div class='kpi kpi-largo {tom}'><small>Engajamento mediano por post</small><b>{_num(c['er_conta'] * 100, 2)}%</b>"
            f"<strong>{leitura}</strong>"
            f"<div class='medidor'><div><span>@{_e(c['username'])}</span><i><b class='b-conta' style='width:{c['er_conta'] / maior * 100:.0f}%'></b></i><em>{_num(c['er_conta'] * 100, 2)}%</em></div>"
            f"<div><span>Nicho, mesma faixa</span><i><b class='b-nicho' style='width:{(c['er_nicho'] or 0) / maior * 100:.0f}%'></b></i><em>{_num((c['er_nicho'] or 0) * 100, 2)}%</em></div></div></div>")


def _formatos_empilhados(c: dict) -> str:
    cores = {"reels": "f-reels", "carrossel": "f-carrossel", "imagem": "f-imagem"}

    def linha(rotulo: str, chave: str) -> str:
        partes = "".join(f"<b class='{cores[f['tipo']]}' style='width:{(f[chave] or 0) * 100:.1f}%'>{_pct(f[chave] or 0) if (f[chave] or 0) >= 0.08 else ''}</b>"
                         for f in c["formatos"])
        return f"<div class='pilha'><span>{rotulo}</span><i>{partes}</i></div>"

    rende = "".join(f"<span class='chip-rende'>{_e(FORMATOS.get(f['tipo'], f['tipo']))}: "
                    f"{(_num(f['lift_mediano_conta'], 2) + '× na conta') if f['lift_mediano_conta'] is not None else 'poucos posts'}</span>"
                    for f in c["formatos"])
    legenda = "".join(f"<span><i class='{cores[f['tipo']]}'></i>{_e(FORMATOS.get(f['tipo'], f['tipo']))}</span>" for f in c["formatos"])
    return (f"<div class='caixa'>{linha('@' + _e(c['username']), 'pct_conta')}{linha('Top do nicho', 'pct_top')}"
            f"<div class='legenda-f'>{legenda}</div><div class='rendes'>{rende}</div></div>")


def _melhores(c: dict) -> str:
    itens = []
    for m in c["melhores"]:
        capa = _capa_conta(m.get("post_id"))
        fundo = f"<img src='{capa}' alt='' loading='lazy'>" if capa else ""
        itens.append(f"<a class='post-conta' href='{_e(m['link'])}' target='_blank' rel='noreferrer'><div class='pc-capa'>{fundo}"
                     f"<em>{_num(m['lift'])}×</em></div><p>{_e(m['trecho'][:120])}{'…' if len(m['trecho']) > 120 else ''}</p></a>")
    return f"<div class='posts-conta'>{''.join(itens)}</div>"


def _criativo_celular(i: int, p: dict) -> str:
    a = p["atual"]
    c = a["criativo"]
    juiz = (a.get("juiz") or {}).get("media_ponderada")
    tela = ""
    if p["formato"] == "carrossel":
        try:
            from src.rendering.carrossel_da_peca import renderizar_peca
            slides = [s for s in (_img(str(x), 300) for x in renderizar_peca(p)) if s]
        except Exception:  # noqa: BLE001 - sem Playwright, mostra o roteiro em texto
            slides = []
        if slides:
            tela = "<div class='slides'>" + "".join(f"<img src='{s}' alt='Slide {n}'>" for n, s in enumerate(slides, 1)) + "</div>"
    if not tela:
        cenas = "".join(f"<li><span>{PARTE.get(p['formato'], 'Parte')} {n}</span>{_e(_sem_prefixo(t))}</li>"
                        for n, t in enumerate(c.get("corpo", []), 1))
        tela = f"<div class='roteiro'><p class='gancho-cel'>{_e(c.get('gancho'))}</p><ol>{cenas}</ol><p class='cta-cel'>{_e(c.get('cta'))}</p></div>"
    refs = "".join(f"<a href='{_e(r.get('link'))}' target='_blank' rel='noreferrer'>@{_e(r.get('perfil'))}</a>" for r in a.get("referencias", []) if r.get("link"))
    formato = _e(FORMATOS.get(p['formato'], p['formato']))
    return (f"<article class='criativo-cel'><div class='celular'><div class='cel-topo'><b>{_e(a.get('conta') or 'impulsostone')}</b><span>{formato}</span></div>{tela}</div>"
            f"<div class='cel-info'><div class='cel-cab'><span class='cel-n'>{i:02d}</span><small>{formato} · {_e(SEGMENTOS.get(p.get('segmento'), 'Todos os segmentos'))}</small></div>"
            f"<h4>{_e(c.get('titulo'))}</h4>"
            f"<div class='cel-meta'>{('<span class=nota>Nota ' + _num(juiz) + '</span>') if juiz is not None else ''}<span class='ok'>✓ aprovada</span></div>"
            + (f"<div class='caso-cel'><b>O caso</b><p>{_e(c['caso'])}</p></div>" if c.get("caso") else "")
            + (f"<div class='cel-refs'><b>Baseado em</b>{refs}</div>" if refs else "")
            + f"<details><summary>Ver legenda</summary><p>{_e(c.get('legenda'))}</p></details></div></article>")


def _vaga(i: int) -> str:
    """Lugar reservado para um criativo que ainda falta aprovar (o TAPI pede no mínimo cinco)."""
    return (f"<article class='criativo-vaga'><span class='cel-n'>{i:02d}</span><div class='vaga-cel'><svg viewBox='0 0 24 24'><path d='M12 5v14M5 12h14'/></svg></div>"
            "<div><b>Aguardando aprovação</b><small>Aprove uma peça em Peças e gere o playbook de novo.</small></div></article>")


def _ctr_motivacional() -> str:
    """' (x,xx%)' a partir dos dados internos; vazio quando eles não estão na máquina."""
    for x in fx.load_stone_context().get("aprendizados_ads", {}).get("nao_funcionou", []):
        if "motivacional" in x.get("padrao", "").lower() and x.get("ctr"):
            return f" ({_num(x['ctr'] * 100, 2)}%)"
    return ""


def _painel_conta(c: dict, extra: str = "") -> str:
    recs = c["recomendacoes"]
    principais = "".join(_cartao_rec(r, True, i) for i, r in enumerate(recs[:3], 1)) or "<p class='m'>Nenhuma diferença forte nesta coleta.</p>"
    resto = recs[3:]
    resto_html = (f"<details class='mais'><summary>Ver todas as recomendações ({len(recs)})</summary><div class='recs-lista'>"
                  + "".join(_cartao_rec(r, False) for r in resto) + "</div></details>") if resto else ""
    avisos = []
    if c["perfis_nicho_faixa"] < 5:
        avisos.append(f"Só {c['perfis_nicho_faixa']} perfis do nicho têm esse tamanho: a comparação de engajamento é um sinal, não uma meta.")
    if not c["tem_visual"]:
        avisos.append("A análise de vídeo desta conta ainda não rodou: as recomendações usam formato e texto.")
    elif c["n_visual"] < c["n_posts"]:
        avisos.append(f"Vídeo analisado em {c['n_visual']} dos {c['n_posts']} posts (o Instagram não entregou parte dos Reels): cenário, texto na tela e quem aparece são sinais.")
    motivacao = [x for x in c["acima"] if x["valor"] == "motivacao"]
    if motivacao:
        avisos.append(f"Motivação rende {_num(motivacao[0]['lift_mediano'])}× na conta, mas teve o menor CTR nos anúncios do Impulso{_ctr_motivacional()}: use como apoio, não como mensagem principal.")
    mantem = [a for a in c["lacunas"] if a["acao"] == "manter"]
    if mantem:
        avisos.append("Já no nível do nicho: " + "; ".join(_so_nome(a["frase"]) for a in mantem) + ".")
    avisos_html = "".join(f"<li>{_e(a)}</li>" for a in avisos)
    cls = PARA.get(c["username"], ("", "p-stone"))[1].replace("p-", "cb-")
    inicial = "IS" if c["username"] == "impulsostone" else c["username"][:1].upper()
    return f"""
<div class="conta-banner {cls}">
  <div class="cb-id"><span class="monograma">{inicial}</span>
    <div>{_para(c['username'])}<h2>@{_e(c['username'])}</h2><p>{_e(c['papel'])}</p></div></div>
  <div class="kpis">
    {_medidor(c)}
    <div class="kpi"><small>Seguidores</small><b>{_milhar(c['seguidores'])}</b><strong>{c['n_posts']} posts nos últimos 90 dias</strong></div>
    <div class="kpi"><small>Posts por semana</small><b>{_num(c['posts_semana'])}</b><strong>nicho na mesma faixa: {_num(c['posts_semana_nicho'])}</strong></div>
  </div>
</div>
<h3 class="titulo-bloco">Os 3 movimentos principais</h3>
<div class="recs-grandes">{principais}</div>
{resto_html}
<section class="faixa escura"><div class="duas">
  <div><h3 class="titulo-bloco">Formatos: a conta × o nicho</h3>{_formatos_empilhados(c)}</div>
  <div><h3 class="titulo-bloco">Posts da conta que mais renderam</h3>{_melhores(c)}</div>
</div></section>
{f'<div class="antes"><h4>{_icone("M12 8v5M12 16.5v.5M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z")}Antes de usar</h4><ul class="notas">{avisos_html}</ul></div>' if avisos else ''}
{extra}"""


def _painel_nicho(d: dict) -> str:
    usar = sorted(d["usar"], key=lambda a: not a["recomendar"])      # o achado que não recomendamos vai para o fim
    cards = []
    for a in usar:
        minis = _miniaturas(a.get("exemplos"), 2)
        avisos = []
        if not a["recomendar"]:
            avisos.append("não usar como mensagem principal: menor CTR nos anúncios do Impulso")
        if a.get("oposto_em"):
            avisos.append(f"no {a['oposto_em']} é o contrário")
        cards.append(f"<article class='achado-card {'nao' if not a['recomendar'] else ''}'><div class='lift{" so" if a["lift"] is None else ""}'><b>{_vezes(a['lift'])}</b><small>{'no top' if a['lift'] is not None else '0% nos demais'}</small></div>"
                     f"<div><span class='rede'>{_plataforma(a['plataforma'])} · {a['n_perfis']} perfis</span><h4>{_e(_so_nome(a['frase']))}</h4>"
                     f"<p>{_pct(a['pct_top'])} dos posts que mais engajam × {_pct(a['pct_controle'])} dos demais</p>"
                     + "".join(f"<div class='aviso'>{_e(x)}</div>" for x in avisos) + f"</div>{minis}</article>")
    evitar = "".join(f"<li><i class='menos'>−</i><div><b>{_e(_so_nome(a['frase']))}</b> <span>{_plataforma(a['plataforma'])} · {_pct(a['pct_top'])} no top × {_pct(a['pct_controle'])} nos demais</span></div></li>"
                     for a in d["evitar"])
    ind = d["indicados"]
    criadores = "".join(
        f"<a class='criador-card' href='{_e(c['link'])}' target='_blank' rel='noreferrer'>"
        + (f"<img src='{f}' alt=''>" if (f := _foto(c)) else "<span class='sem-foto'></span>")
        + f"<div><b>{_e(c.get('nome') or c['perfil'])}</b><small>{papel} · {_plataforma(c['plataforma'])} · {_milhar(c.get('seguidores'))}</small>"
          f"<small>{_e(SEGMENTOS.get(c.get('segmento'), c.get('segmento') or ''))}</small></div><em>{c.get('nota')}</em></a>"
        for papel, grupo in (("Transversal", "transversais"), ("Setorial", "setoriais")) for c in ind.get(grupo, []))
    exemplos = ""
    for plat, lista in d["exemplos"].items():
        exemplos += f"<h4 class='sub'>{_plataforma(plat)}</h4>" + _miniaturas(lista, 6)
    horas = d["horarios"].get("dias", {})
    semana = "".join(f"<div class='dia f-{_e(v.get('forca'))}'><b>{NOME_DIA[k][:3]}</b><span>{_e(v.get('principal'))}</span><small>{_e(v.get('forca'))}</small></div>"
                     for k in DIAS if (v := horas.get(k)))
    return f"""
<div class="conta-banner cb-ambas"><div class="cb-id"><span class="monograma"><svg viewBox="0 0 24 24"><path d="M12 2.5v19M2.5 12h19M5.3 5.3l13.4 13.4M18.7 5.3 5.3 18.7"/></svg></span>
  <div>{_para('ambas')}<h2>O que engaja no nicho</h2><p>55 perfis públicos que falam com micro e pequenos empreendedores. No ranking entram só posts dentro do escopo: orientam o empreendedor, têm 150 curtidas ou mais e não tratam de política, raça, gênero, religião ou polêmica. Vale para as duas contas.</p></div></div>
  <div class="cb-numeros"><div><b>{len(d['usar'])}</b><span>padrões que mais aparecem no top</span></div><div><b>{len(d['evitar'])}</b><span>que aparecem menos</span></div>
  <div><b>{sum(len(ind.get(g, [])) for g in ('transversais', 'setoriais'))}</b><span>perfis para parceria</span></div></div></div>
<h3 class="titulo-bloco">O que aparece mais nos posts que mais engajam</h3>
<div class="achados">{''.join(cards)}</div>
<div class="duas">
  <div><h3 class="titulo-bloco">O que aparece menos</h3><ul class="evitar">{evitar}</ul></div>
  <div><h3 class="titulo-bloco">Quando publicar</h3><div class="semana">{semana}</div><p class="m">Pesquisas públicas (Opinion Box, Buffer, Sprout Social 2026), não dados da Stone.</p></div>
</div>
<h3 class="titulo-bloco">Perfis para parceria</h3><div class="criadores">{criadores}</div>
<section class="faixa escura"><h3 class="titulo-bloco">Posts que mais superaram a média do próprio perfil</h3>{exemplos}</section>"""


CSS = """
:root{--sher:#004132;--escuro:#0b3d2c;--lima:#C7F93C;--roxo:#A780FF;--laranja:#ff9a3d;--tinta:#13231c;--m:#5b6b61;--linha:#e3e8e2;--papel:#fff;--fundo:#f3f4f0}
*{box-sizing:border-box}body{margin:0;background:var(--fundo);color:var(--tinta);font:15px/1.5 'Hanken Grotesk',Arial,sans-serif}
a{color:inherit}h2,h3,h4{margin:0;letter-spacing:-.02em}.m{color:var(--m);font-size:13px}
.topo{position:relative;overflow:hidden;color:#fff;padding:34px 0 0;
 background:radial-gradient(circle at 92% -20%,rgba(84,176,70,.75) 0 190px,transparent 191px),radial-gradient(circle at 80% 130%,rgba(70,160,64,.55) 0 170px,transparent 171px),linear-gradient(100deg,#082d21,#0b3d2c 55%,#11553a)}
.topo .in,.corpo{max-width:1120px;margin:0 auto;padding:0 28px}
.marca{display:flex;align-items:center;gap:10px;font-weight:700;font-size:18px}.marca svg{width:22px;height:22px;stroke:var(--lima);stroke-width:2.8;stroke-linecap:round;fill:none}
.marca b{color:var(--lima)}.topo h1{font-size:46px;letter-spacing:-.035em;line-height:1.02;margin:18px 0 8px}
.topo p{color:#cfe3da;max-width:640px;margin:0}.topo .meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.topo .meta span{background:rgba(255,255,255,.1);border-radius:999px;padding:5px 12px;font-size:13px}.topo .meta b{color:var(--lima)}
.abas{display:flex;gap:6px;margin-top:26px}.abas button{border:0;background:rgba(255,255,255,.1);color:#fff;font:600 15px 'Hanken Grotesk',Arial;padding:13px 22px;border-radius:16px 16px 0 0;cursor:pointer}
.abas button.on{background:var(--fundo);color:var(--tinta)}.abas button small{display:block;font-weight:400;font-size:11.5px;opacity:.75}
.painel{display:none;padding:30px 0 10px}.painel.on{display:block}
.para{display:inline-block;font-size:12px;font-weight:700;padding:4px 11px;border-radius:999px}
.p-impulso{background:#efe8ff;color:#5b34c4}.p-stone{background:#dff3e8;color:#004132}.p-ambas{background:#eef9cf;color:#3d6b00}
.conta-topo h2{font-size:36px;margin:8px 0 2px}.conta-topo p{color:var(--m);margin:0}
.kpis{display:grid;grid-template-columns:2fr 1fr 1fr;gap:14px;margin:22px 0 8px}
.kpi{background:var(--papel);border-radius:22px;padding:18px 20px;box-shadow:0 6px 22px rgba(0,40,30,.07)}
.kpi small{color:var(--m);font-size:13px}.kpi b{display:block;font-size:40px;letter-spacing:-.03em;line-height:1.1}.kpi strong{font-weight:600;font-size:14px}
.kpi-largo{display:grid;grid-template-columns:auto 1fr;column-gap:22px;align-items:center}.kpi-largo small,.kpi-largo b,.kpi-largo strong{grid-column:1}
.kpi-largo .medidor{grid-column:2;grid-row:1/4}.kpi.igual strong{color:#2f7d1e}.kpi.abaixo strong{color:#b4530a}.kpi.acima strong{color:#2f7d1e}
.medidor div,.barras div{display:grid;grid-template-columns:120px 1fr 52px;align-items:center;gap:10px;font-size:13px;margin:6px 0}
.medidor i,.barras i{display:block;height:12px;background:#eef1ec;border-radius:999px;overflow:hidden}
.medidor b,.barras b{display:block;height:100%;border-radius:999px}.b-conta{background:var(--sher)}.b-nicho{background:var(--lima)}
.medidor em,.barras em{font-style:normal;font-weight:700;text-align:right}.medidor span,.barras span{color:var(--m)}
.titulo-bloco{font-size:20px;margin:30px 0 12px}
.recs-grandes{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.rec{background:var(--papel);border-radius:22px;padding:18px 20px;box-shadow:0 6px 22px rgba(0,40,30,.07);border-top:6px solid var(--lima)}
.rec-repetir{border-top-color:#2f9e44}.rec-rever{border-top-color:var(--laranja)}.rec-fazer_menos{border-top-color:#e8590c}
.rec header{display:flex;justify-content:space-between;align-items:center;gap:8px}
.acao{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;font-weight:700;padding:4px 10px 4px 7px;border-radius:999px;background:#eef9cf;color:#2d5a00}
.rec-repetir .acao{background:#e3f6e7;color:#1d6b2e}.rec-rever .acao{background:#fff1e3;color:#9a4a00}.rec-fazer_menos .acao{background:#ffe8dc;color:#a43c00}
.ic{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round}
.fonte{font-size:11.5px;color:var(--m)}.rec h4{font-size:21px;margin:12px 0 6px;line-height:1.15}.rec p{font-size:13.5px;color:var(--m);margin:8px 0 0}
.rec .barras div{grid-template-columns:96px 1fr 40px}
.rende{display:grid;grid-template-columns:auto 1fr;column-gap:8px;align-items:baseline;margin-top:8px}.rende b{font-size:26px;letter-spacing:-.02em}
.rende span{font-size:12.5px;color:var(--m)}.rende.alto b{color:#2f7d1e}.rende.baixo b{color:#b4530a}
.regua{grid-column:1/-1;position:relative;height:8px;background:linear-gradient(90deg,#ffd8b8,#eef1ec 40%,#eef1ec 60%,#d6f58a);border-radius:999px;margin-top:6px}
.regua .meio{position:absolute;left:40%;top:-3px;bottom:-3px;width:2px;background:var(--m)}.regua .ponto{position:absolute;top:50%;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;background:var(--sher);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.25)}
.refs-titulo{font-size:12px;color:var(--m);margin:14px 0 6px}
.minis{display:flex;gap:8px;flex-wrap:wrap}.mini{position:relative;width:96px;height:120px;border-radius:12px;overflow:hidden;background:#dfe7df;text-decoration:none;flex:none}
.mini img{width:100%;height:100%;object-fit:cover;display:block}.mini em{position:absolute;top:6px;left:6px;background:var(--lima);color:var(--sher);font:700 11px Arial;padding:2px 6px;border-radius:999px;font-style:normal}
.mini small{position:absolute;left:0;right:0;bottom:0;padding:14px 6px 5px;font-size:10.5px;color:#fff;background:linear-gradient(transparent,rgba(0,20,14,.85));white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sem-capa{display:grid;place-items:center;height:100%;color:var(--sher);font-size:22px}
details.mais{margin-top:12px}details summary{cursor:pointer;font-weight:600;color:var(--sher);padding:8px 0}
.recs-lista{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:6px}.recs-lista .rec{padding:14px 16px;border-top-width:4px}.recs-lista .rec h4{font-size:16px;margin:8px 0 2px}
.duas{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.caixa{background:var(--papel);border-radius:22px;padding:18px 20px;box-shadow:0 6px 22px rgba(0,40,30,.07)}
.pilha{display:grid;grid-template-columns:110px 1fr;align-items:center;gap:10px;margin:8px 0;font-size:13px}.pilha span{color:var(--m)}
.pilha i{display:flex;height:30px;border-radius:10px;overflow:hidden}.pilha b{display:grid;place-items:center;color:#fff;font-size:12px}
.f-reels{background:var(--sher)}.f-carrossel{background:#5aa63a}.f-imagem{background:#b9d99a;color:var(--tinta)!important}
.legenda-f{display:flex;gap:14px;font-size:12.5px;color:var(--m);margin-top:6px}.legenda-f i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px}
.rendes{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.chip-rende{background:#eef1ec;border-radius:999px;padding:4px 10px;font-size:12.5px}
.posts-conta{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.post-conta{text-decoration:none;background:var(--papel);border-radius:16px;overflow:hidden;box-shadow:0 4px 16px rgba(0,40,30,.07)}
.pc-capa{position:relative;aspect-ratio:4/5;background:#dfe7df}.pc-capa img{width:100%;height:100%;object-fit:cover;display:block}
.pc-capa em{position:absolute;top:8px;left:8px;background:var(--lima);color:var(--sher);font:700 13px Arial;padding:3px 8px;border-radius:999px;font-style:normal}
.post-conta p{font-size:12px;color:var(--m);margin:0;padding:8px 10px 10px}
.notas{margin:18px 0 0;padding:14px 18px 14px 34px;background:#f4efff;border-radius:16px;font-size:13px;color:#4a2fa8;display:grid;gap:4px}
.criativos{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:18px}
.criativo-cel{display:grid;grid-template-columns:150px minmax(0,1fr);gap:16px;background:var(--papel);border-radius:22px;padding:16px;box-shadow:0 6px 22px rgba(0,40,30,.07)}
.celular{border:6px solid #12241c;border-radius:24px;overflow:hidden;background:#fff;height:300px;display:flex;flex-direction:column}
.cel-topo{display:flex;justify-content:space-between;font-size:10.5px;padding:6px 8px;border-bottom:1px solid var(--linha)}.cel-topo span{color:var(--m)}
.slides{display:flex;align-items:center;overflow-x:auto;scroll-snap-type:x mandatory;flex:1;background:#eef1ec}.slides img{width:100%;height:auto;flex:none;object-fit:contain;scroll-snap-align:start}
.roteiro{padding:8px;overflow-y:auto;font-size:11px;flex:1}.gancho-cel{font-weight:700;font-size:12.5px;margin:0 0 6px}.roteiro ol{list-style:none;padding:0;margin:0;display:grid;gap:5px}
.roteiro li{background:#f3f4f0;border-radius:8px;padding:5px 7px}.roteiro li span{display:block;font-size:9.5px;color:var(--m)}.cta-cel{background:var(--lima);border-radius:8px;padding:5px 7px;font-weight:700;margin:6px 0 0}
.cel-info{min-width:0;overflow-wrap:anywhere}.cel-info small{color:var(--m);font-size:12px}.cel-info h4{font-size:18px;margin:4px 0 6px}.caso-cel{font-size:13px;background:#f4efff;border-radius:10px;padding:8px 10px;margin:0 0 8px}
.cel-meta{display:flex;flex-wrap:wrap;gap:6px}.cel-meta span{font-size:12px;font-weight:700;padding:3px 9px;border-radius:999px;white-space:nowrap}.nota{background:var(--lima);color:var(--sher)}.ok{background:#e3f6e7;color:#1d6b2e}
.cel-refs{font-size:12.5px;margin-top:8px;color:var(--m)}.cel-refs a{margin-right:8px;color:var(--sher)}.cel-info details p{font-size:13px;white-space:pre-wrap;margin:4px 0 0}
.falta{background:#f4efff;border:1px dashed var(--roxo);border-radius:16px;padding:14px 18px;font-size:14px;margin-bottom:14px}
.ads{display:grid;grid-template-columns:1fr 1fr;gap:12px}.ads ul{margin:6px 0 0;padding-left:18px;font-size:13.5px}.ads li b{white-space:nowrap}
.achados{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.achado-card{display:grid;grid-template-columns:86px 1fr auto;gap:14px;align-items:center;background:var(--papel);border-radius:20px;padding:14px 16px;box-shadow:0 4px 16px rgba(0,40,30,.06)}
.achado-card .lift{font-size:30px;font-weight:700;letter-spacing:-.03em;background:linear-gradient(transparent 58%,var(--lima) 58%);justify-self:start}
.achado-card.nao .lift{background:linear-gradient(transparent 58%,#e6dcff 58%)}.achado-card h4{font-size:16px;margin:2px 0}.achado-card p{font-size:12.5px;color:var(--m);margin:0}
.achado-card .minis .mini{width:62px;height:78px}.rede{font-size:11.5px;color:var(--m)}.aviso{font-size:12px;color:#5b34c4;margin-top:4px}
.evitar{list-style:none;padding:0;margin:0;display:grid;gap:8px}.evitar li{background:var(--papel);border-radius:14px;padding:10px 14px;border-left:5px solid var(--laranja);box-shadow:0 2px 10px rgba(0,40,30,.05)}
.evitar span{display:block;font-size:12.5px;color:var(--m)}
.semana{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}.dia{background:var(--papel);border-radius:14px;padding:10px 6px;text-align:center;box-shadow:0 2px 10px rgba(0,40,30,.05)}
.dia b{display:block}.dia span{display:block;font-size:12px;margin:4px 0}.dia small{font-size:11px;color:var(--m)}.f-forte{background:#e9f9c4}.f-fraco{opacity:.7}
.criadores{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px}
.criador-card{display:grid;grid-template-columns:52px 1fr auto;gap:12px;align-items:center;background:var(--papel);border-radius:18px;padding:12px 14px;text-decoration:none;box-shadow:0 4px 16px rgba(0,40,30,.06)}
.criador-card img,.sem-foto{width:52px;height:52px;border-radius:50%;object-fit:cover;background:#dfe7df}.criador-card small{display:block;font-size:12px;color:var(--m)}
.criador-card em{font-style:normal;font-weight:700;font-size:18px;background:var(--lima);color:var(--sher);width:44px;height:44px;border-radius:50%;display:grid;place-items:center}
h4.sub{font-size:14px;color:var(--m);margin:16px 0 8px}
.apendice{margin:44px 0 20px;background:var(--papel);border-radius:22px;padding:6px 22px;box-shadow:0 6px 22px rgba(0,40,30,.05)}
.apendice details{border-top:1px solid var(--linha)}.apendice details:first-child{border-top:0}.apendice summary{padding:14px 0}
.apendice .dentro{padding:0 0 16px;font-size:14px}.apendice table{width:100%;border-collapse:collapse;font-size:13px}.apendice th{text-align:left;color:var(--m);font-weight:600;padding:6px 8px;background:#f3f4f0}
.apendice td{padding:8px;border-top:1px solid var(--linha);vertical-align:top}.apendice td.n{white-space:nowrap}
footer{color:var(--m);font-size:12.5px;padding:10px 0 40px}
/* ===== camada visual v2: ritmo de faixas, cor por conta, números grandes ===== */
body{overflow-x:hidden}
.topo{padding:40px 0 0;background:radial-gradient(circle at 88% -10%,rgba(199,249,60,.22) 0 230px,transparent 231px),radial-gradient(circle at 70% 120%,rgba(167,128,255,.30) 0 200px,transparent 201px),linear-gradient(110deg,#062a1f,#0b3d2c 50%,#11553a)}
.topo::after{content:"";position:absolute;right:-60px;top:40px;width:340px;height:340px;opacity:.10;pointer-events:none;
 background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 2.5v19M2.5 12h19M5.3 5.3l13.4 13.4M18.7 5.3 5.3 18.7' stroke='%23C7F93C' stroke-width='2.6' stroke-linecap='round' fill='none'/%3E%3C/svg%3E") no-repeat center/contain}
.capa{display:grid;grid-template-columns:1.35fr 1fr;gap:36px;align-items:end;margin-top:22px;position:relative;z-index:1}
.sobre{display:inline-block;font-size:12.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--lima);font-weight:700}
.topo h1{font-size:64px;line-height:.98;margin:12px 0 14px}.topo h1 em{font-style:normal;color:var(--lima)}
.topo p{font-size:16.5px}
.capa-numeros{display:grid;gap:10px}
.capa-numeros div{display:flex;align-items:baseline;gap:14px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);border-radius:18px;padding:12px 18px}
.capa-numeros b{font-size:34px;letter-spacing:-.03em;color:var(--lima);min-width:110px}.capa-numeros span{color:#cfe3da;font-size:14px}
.abas{margin-top:34px;gap:8px}.abas button{border-radius:18px 18px 0 0;padding:14px 26px;font-size:16px}
.abas button:not(.on):hover{background:rgba(255,255,255,.18)}
.painel{counter-reset:bloco;padding-top:34px}
.conta-banner{border-radius:28px;padding:28px 30px;color:#fff;position:relative;overflow:hidden;box-shadow:0 14px 40px rgba(0,40,30,.16)}
.conta-banner::after{content:"";position:absolute;right:-70px;top:-70px;width:240px;height:240px;border-radius:50%;background:rgba(255,255,255,.08)}
.cb-impulso{background:linear-gradient(120deg,#5b34c4,#8a5cf0 60%,#A780FF)}
.cb-stone{background:linear-gradient(120deg,#002a20,#004132 55%,#0f6a4a)}
.cb-ambas{background:linear-gradient(120deg,#0b3d2c,#2c6b1c 70%,#5d9a1a)}
.cb-id{display:flex;gap:18px;align-items:center;position:relative;z-index:1}
.monograma{width:74px;height:74px;border-radius:22px;display:grid;place-items:center;font-weight:700;font-size:26px;flex:none;background:var(--lima);color:var(--sher)}
.monograma svg{width:38px;height:38px;stroke:var(--sher);stroke-width:2.6;stroke-linecap:round;fill:none}
.cb-impulso .monograma{background:#fff;color:#5b34c4}
.conta-banner h2{font-size:40px;margin:6px 0 2px;color:#fff}.conta-banner p{color:rgba(255,255,255,.82);margin:0}
.conta-banner .para{background:rgba(255,255,255,.16);color:#fff}
.conta-banner .kpis{position:relative;z-index:1;margin:22px 0 0}
.conta-banner .kpi{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.16);box-shadow:none;color:#fff;backdrop-filter:blur(2px)}
.conta-banner .kpi small,.conta-banner .medidor span{color:rgba(255,255,255,.78)}
.conta-banner .kpi.igual strong,.conta-banner .kpi.acima strong{color:var(--lima)}.conta-banner .kpi.abaixo strong{color:#ffc58a}
.conta-banner .medidor i{background:rgba(255,255,255,.16)}.conta-banner .b-conta{background:#fff}
.cb-numeros{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:22px;position:relative;z-index:1}
.cb-numeros div{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.16);border-radius:20px;padding:14px 18px}
.cb-numeros b{display:block;font-size:40px;letter-spacing:-.03em;color:var(--lima);line-height:1.05}.cb-numeros span{font-size:13.5px;color:rgba(255,255,255,.82)}
.titulo-bloco{counter-increment:bloco;display:flex;align-items:center;gap:12px;font-size:25px;margin:44px 0 16px}
.titulo-bloco::before{content:counter(bloco,decimal-leading-zero);font-size:13px;font-weight:700;letter-spacing:.02em;background:var(--sher);color:var(--lima);border-radius:999px;padding:5px 10px}
.duas .titulo-bloco{font-size:21px}
.rec{position:relative;border-top:0;border-radius:24px;padding:22px 22px 20px;overflow:hidden}
.rec.grande{background:linear-gradient(180deg,#f3fde0,#fff 46%)}
.rec-repetir.grande{background:linear-gradient(180deg,#e3f6e7,#fff 46%)}.rec-rever.grande{background:linear-gradient(180deg,#fff0e0,#fff 46%)}
.rec-fazer_menos.grande{background:linear-gradient(180deg,#ffe6d8,#fff 46%)}
.rec .minis{flex-wrap:nowrap;gap:6px}.rec .mini{width:calc((100% - 12px)/3);max-width:110px;height:auto;aspect-ratio:4/5}
.topo{background:radial-gradient(circle at 88% -10%,rgba(199,249,60,.22) 0 230px,transparent 231px),radial-gradient(circle at 70% 125%,rgba(199,249,60,.12) 0 200px,transparent 201px),linear-gradient(110deg,#062a1f,#0b3d2c 50%,#11553a)}
.topo::after{right:-150px;top:-40px;opacity:.07}
.rec-n{position:absolute;right:14px;bottom:-14px;font-size:92px;font-weight:700;letter-spacing:-.06em;line-height:1;color:rgba(0,65,50,.07);pointer-events:none}
.rec.grande h4{font-size:24px;position:relative}
.recs-lista .rec{border-left:5px solid var(--lima);border-radius:18px}.recs-lista .rec-repetir{border-left-color:#2f9e44}
.recs-lista .rec-rever{border-left-color:var(--laranja)}.recs-lista .rec-fazer_menos{border-left-color:#e8590c}
.faixa{margin:48px calc(50% - 50vw) 0;padding:6px calc(50vw - 50%) 40px}
.faixa.escura{background:linear-gradient(115deg,#062a1f,#0b3d2c 60%,#0f4a33);color:#fff}
.faixa.escura .titulo-bloco{color:#fff}.faixa.escura .titulo-bloco::before{background:var(--lima);color:var(--sher)}
.faixa.escura h4.sub{color:var(--lima)}.faixa.escura .post-conta,.faixa.escura .caixa{color:var(--tinta)}
.faixa.escura .mini{width:118px;height:148px;border-radius:14px;box-shadow:0 8px 22px rgba(0,0,0,.25)}
.faixa.lilas{background:linear-gradient(180deg,#efe8ff,#f7f3ff)}
.faixa.lilas .titulo-bloco::before{background:#5b34c4;color:#fff}
.faixa.lilas .criativo-cel{box-shadow:0 10px 30px rgba(91,52,196,.12)}
.faixa + .antes,.faixa + details.mais{margin-top:28px}
.antes{margin-top:30px;background:#fff;border-radius:22px;padding:18px 22px;box-shadow:0 6px 22px rgba(0,40,30,.06);border-left:6px solid var(--roxo)}
.antes h4{display:flex;align-items:center;gap:8px;font-size:16px;color:#4a2fa8;margin-bottom:8px}.antes .ic{width:20px;height:20px}
.antes .notas{background:none;padding:0 0 0 20px;margin:0;color:var(--tinta);font-size:14px;gap:6px}
.achado-card{grid-template-columns:96px 1fr auto;border-radius:22px;padding:14px}
.achado-card .lift{background:var(--lima);color:var(--sher);border-radius:18px;padding:12px 6px;text-align:center;justify-self:stretch}
.achado-card .lift b{display:block;font-size:28px;letter-spacing:-.03em;line-height:1}.achado-card .lift small{font-size:11px;font-weight:600}
.achado-card.nao .lift{background:#e6dcff;color:#4a2fa8}
.achado-card .lift.so b{font-size:19px;line-height:1.05}
.achado-card.nao{background:repeating-linear-gradient(135deg,#fff 0 14px,#faf7ff 14px 28px)}
.evitar li{display:flex;gap:12px;align-items:center;border-left:0;border-radius:16px}
.menos{flex:none;width:30px;height:30px;border-radius:50%;background:#ffe6d8;color:#c2410c;display:grid;place-items:center;font-style:normal;font-weight:700;font-size:20px}
.dia{border-radius:16px;padding:14px 6px}.dia.f-forte{background:var(--sher);color:#fff}.dia.f-forte small{color:var(--lima);font-weight:700}
.dia.f-moderado{background:#eef9d2}.dia.f-fraco{background:#fff;opacity:.6}
.criador-card{border-radius:20px;transition:transform .15s}.criador-card:hover,.post-conta:hover,.mini:hover{transform:translateY(-3px)}
.criador-card em{background:var(--sher);color:var(--lima);box-shadow:0 0 0 4px #eef9d2}
.post-conta,.mini{transition:transform .15s}
.apendice{margin-top:56px}
@media (max-width:900px){.capa,.cb-numeros{grid-template-columns:1fr}.topo h1{font-size:42px}.conta-banner{padding:22px 18px}.conta-banner h2{font-size:30px}
 .monograma{width:56px;height:56px;font-size:20px}.achado-card{grid-template-columns:80px 1fr}}
/* ===== criativos, anúncios e metodologia (v2) ===== */
.criativos{grid-template-columns:repeat(auto-fill,minmax(460px,1fr));gap:20px}
.criativo-cel{grid-template-columns:200px minmax(0,1fr);gap:22px;padding:18px;border-radius:26px;align-items:start}
.celular{height:auto;border-width:7px;border-radius:28px;box-shadow:0 12px 28px rgba(19,35,28,.18)}
.slides{background:#fff;flex:none}.slides img{width:100%;height:auto;display:block}
.roteiro{max-height:330px}
.cel-cab{display:flex;align-items:center;gap:10px}
.cel-n{display:inline-grid;place-items:center;min-width:34px;height:34px;border-radius:12px;background:#5b34c4;color:#fff;font-weight:700;font-size:13px}
.cel-info h4{font-size:22px;line-height:1.15;margin:12px 0 10px}
.cel-meta{margin-bottom:14px}
.caso-cel{background:#f6f2ff;border-radius:14px;padding:10px 12px;margin:0 0 12px}
.caso-cel b{font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;color:#5b34c4}
.caso-cel p{margin:4px 0 0;font-size:13.5px;line-height:1.45;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
.cel-refs{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:0 0 6px}.cel-refs b{font-size:12px;color:var(--m);font-weight:600;margin-right:2px}
.cel-refs a{margin:0;text-decoration:none;background:#eef1ec;border-radius:999px;padding:3px 10px;font-size:12.5px;color:var(--sher)}
.cel-info details summary{font-size:14px}
.criativo-vaga{border:2px dashed #c9b6ff;border-radius:26px;padding:22px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:8px;min-height:240px;background:rgba(255,255,255,.45);position:relative}
.criativo-vaga .cel-n{position:absolute;top:18px;left:18px;background:#e6dcff;color:#5b34c4}
.vaga-cel{width:64px;height:96px;border:3px solid #c9b6ff;border-radius:14px;display:grid;place-items:center}
.vaga-cel svg{width:26px;height:26px;stroke:#a78bfa;stroke-width:2.4;stroke-linecap:round;fill:none}
.criativo-vaga b{color:#4a2fa8}.criativo-vaga small{color:var(--m);max-width:240px}
.progresso-criativos{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:-4px 0 18px;font-size:14px}
.progresso-criativos b{color:#4a2fa8}.progresso-criativos span:last-child{color:var(--m)}
.pc-barra{width:160px;height:10px;border-radius:999px;background:#fff;overflow:hidden;box-shadow:inset 0 0 0 1px #d9ccff}
.pc-barra i{display:block;height:100%;background:linear-gradient(90deg,#7b52e8,#A780FF);border-radius:999px}
.rodape-secao{margin-top:16px}
.ads{gap:16px}
.ads-card{background:#fff;border-radius:22px;padding:18px 20px;box-shadow:0 6px 22px rgba(0,40,30,.07);border-top:6px solid #2f9e44}
.ads-card.ruim{border-top-color:#e8590c}
.ads-card h4{display:flex;align-items:center;gap:8px;font-size:18px}.ads-card h4 .ic{width:22px;height:22px;padding:3px;border-radius:50%;background:#e3f6e7;color:#1d6b2e}
.ads-card.ruim h4 .ic{background:#ffe6d8;color:#c2410c}.ads-card small{color:var(--m);font-size:12.5px}
.ads-card ul{list-style:none;padding:0;margin:12px 0 0;display:grid;gap:10px}
.ads-card li{display:grid;grid-template-columns:minmax(0,1fr) 90px 50px;gap:10px;align-items:center;font-size:13.5px}
.ads-card li i{display:block;height:10px;border-radius:999px;background:#eef1ec;overflow:hidden}.ads-card li i b{display:block;height:100%;background:#2f9e44;border-radius:999px}
.ads-card.ruim li i b{background:#e8590c}.ads-card li em{font-style:normal;font-weight:700;text-align:right}
.ads + .m{margin-top:10px}
.apendice{padding:22px 26px 8px}
.apendice-cab{display:flex;gap:14px;align-items:center;padding-bottom:12px}
.ap-icone{width:46px;height:46px;border-radius:14px;background:var(--sher);display:grid;place-items:center;flex:none}
.ap-icone svg{width:24px;height:24px;stroke:var(--lima);stroke-width:2;fill:none;stroke-linejoin:round}
.apendice-cab h3{font-size:20px}.apendice-cab p{margin:2px 0 0;color:var(--m);font-size:13.5px}
.apendice details:first-of-type{border-top:1px solid var(--linha)}
.apendice summary{list-style:none;display:flex;justify-content:space-between;align-items:center;font-weight:600}
.apendice summary::-webkit-details-marker{display:none}
.apendice summary::after{content:"+";font-size:22px;font-weight:400;color:var(--sher);width:30px;height:30px;border-radius:50%;background:#eef1ec;display:grid;place-items:center}
.apendice details[open] summary::after{content:"−";background:var(--lima)}
.apendice summary:hover{color:var(--sher)}
footer{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:18px 0 48px}
.rod-marca{display:inline-flex;align-items:center;gap:0;font-weight:700;color:var(--tinta);font-size:14px}.rod-marca b{color:var(--sher)}
.rod-marca svg{margin-right:6px;width:16px;height:16px;stroke:var(--sher);stroke-width:2.8;stroke-linecap:round;fill:none}
.vagas{grid-column:1/-1;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.vagas .criativo-vaga{flex-direction:row;justify-content:flex-start;text-align:left;min-height:0;padding:14px 16px;gap:14px;border-radius:20px}
.vagas .criativo-vaga .cel-n{position:static;flex:none}
.vagas .vaga-cel{width:34px;height:50px;border-radius:9px;border-width:2px;flex:none}.vagas .vaga-cel svg{width:16px;height:16px}
.vagas .criativo-vaga b{display:block;font-size:14px}.vagas .criativo-vaga small{font-size:12px}
@media (max-width:900px){.criativos{grid-template-columns:1fr}.criativo-cel{grid-template-columns:1fr}.celular{max-width:240px}.ads-card li{grid-template-columns:1fr 70px 44px}}
@media print{.faixa{margin:24px 0 0;padding:6px 16px 20px;-webkit-print-color-adjust:exact;print-color-adjust:exact}.conta-banner{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
@media (max-width:900px){.kpis,.recs-grandes,.duas,.achados,.recs-lista,.ads{grid-template-columns:1fr}.kpi-largo{grid-template-columns:1fr}.kpi-largo .medidor{grid-column:1;grid-row:auto}
 .topo h1{font-size:34px}.abas{overflow-x:auto}.abas button{padding:10px 14px;white-space:nowrap}.posts-conta{grid-template-columns:repeat(3,1fr)}.criativo-cel{grid-template-columns:1fr}.celular{max-width:220px}
 .achado-card{grid-template-columns:70px 1fr}.achado-card .minis{grid-column:1/-1}.semana{grid-template-columns:repeat(4,1fr)}}
@media print{.abas{display:none}.painel{display:block!important;break-before:page}.topo{-webkit-print-color-adjust:exact;print-color-adjust:exact}
 details{display:block}details>*{display:block}.rec,.kpi,.caixa{box-shadow:none;border:1px solid var(--linha)}}
"""

JS = """
const abas=[...document.querySelectorAll('.abas button')],paineis=[...document.querySelectorAll('.painel')];
function abrir(id){abas.forEach(b=>b.classList.toggle('on',b.dataset.aba===id));paineis.forEach(p=>p.classList.toggle('on',p.id===id));
 try{history.replaceState(null,'','#'+id)}catch(e){}}
abas.forEach(b=>b.addEventListener('click',()=>{abrir(b.dataset.aba);window.scrollTo({top:0,behavior:'smooth'})}));
const ini=location.hash.slice(1);abrir(paineis.some(p=>p.id===ini)?ini:paineis[0].id);
window.addEventListener('beforeprint',()=>document.querySelectorAll('details').forEach(d=>d.open=true));
"""


def renderizar(d: dict, frase: Callable[[dict], str]) -> str:
    b = d["base"]
    contas = {c["username"]: c for c in d["contas"]}
    ads = d["ads"]
    maior_ctr = max([x["ctr"] for x in ads.get("funcionou", []) + ads.get("nao_funcionou", [])] or [1]) or 1

    def _linhas_ads(lista: list) -> str:
        return "".join(f"<li><span>{_e(x['padrao'])}</span><i><b style='width:{x['ctr'] / maior_ctr * 100:.0f}%'></b></i><em>{_num(x['ctr'] * 100, 2)}%</em></li>" for x in lista)
    ads_bloco = ("<h3 class='titulo-bloco'>O que os anúncios do Impulso já mostraram</h3><div class='ads'>"
                 f"<div class='ads-card bom'><h4>{_icone('m6 12.5 4 4 8-9')}Funcionou</h4><small>CTR por padrão de anúncio</small><ul>{_linhas_ads(ads.get('funcionou', []))}</ul></div>"
                 f"<div class='ads-card ruim'><h4>{_icone('M6 6l12 12M18 6 6 18')}Não funcionou</h4><small>CTR por padrão de anúncio</small><ul>{_linhas_ads(ads.get('nao_funcionou', []))}</ul></div>"
                 "</div><p class='m'>Fonte interna: histórico de campanhas, fev a out/2026. Quando anúncio e orgânico discordam, o playbook segue o anúncio.</p>")
    faltam = MINIMO_CRIATIVOS - len(d["criativos"])
    n_ok = len(d["criativos"])
    aviso = (f"<div class='progresso-criativos'><span class='pc-barra'><i style='width:{n_ok / MINIMO_CRIATIVOS * 100:.0f}%'></i></span>"
             f"<b>{n_ok} de {MINIMO_CRIATIVOS} aprovados</b><span>Faltam {faltam} criativo(s) para o mínimo pedido.</span></div>"
             if faltam > 0 else "")
    vagas = "".join(_vaga(i) for i in range(n_ok + 1, MINIMO_CRIATIVOS + 1))
    vagas = f"<div class='vagas'>{vagas}</div>" if vagas else ""
    da_stone = [p for p in d["criativos"] if p["atual"].get("conta") == "stone"]
    do_impulso = [p for p in d["criativos"] if p["atual"].get("conta") != "stone"]
    criativos = (f"<section class='faixa lilas'><h3 class='titulo-bloco'>Criativos prontos para produção</h3>{aviso}"
                 f"<div class='criativos'>{''.join(_criativo_celular(i, p) for i, p in enumerate(do_impulso, 1))}{vagas}</div>"
                 "<p class='m rodape-secao'>Escritos pelo agente com a oferta do Impulso, conferidos automaticamente, avaliados por um modelo independente e aprovados pela equipe."
                 + (f" O mínimo de {MINIMO_CRIATIVOS} soma as peças das duas contas." if da_stone else "") + "</p></section>")
    criativos_stone = (
        "<section class='faixa lilas'><h3 class='titulo-bloco'>Criativos prontos para produção</h3>"
        f"<div class='criativos'>{''.join(_criativo_celular(i, p) for i, p in enumerate(da_stone, 1))}</div>"
        "<p class='m rodape-secao'>Escritos pelo agente com a oferta da marca Stone (maquininha, conta, link de pagamento e crédito), sem taxas nem condições: "
        "a equipe confere os detalhes do plano antes de publicar.</p></section>") if da_stone else (
        "<ul class='notas'><li>Ainda não há criativos aprovados para a @stone. No app, na proposta de um post, escolha "
        "<b>Fazer para o @stone</b>: o agente escreve com a oferta da marca (maquininha, conta, link de pagamento e crédito).</li></ul>")
    sem = "<div class='falta'>Conta ainda não coletada. Rode <code>python scripts/contas_stone.py coletar</code> e <code>texto</code>.</div>"
    painel_impulso = _painel_conta(contas["impulsostone"], criativos + ads_bloco) if "impulsostone" in contas else sem + criativos
    painel_stone = _painel_conta(contas["stone"], criativos_stone) if "stone" in contas else sem + criativos_stone

    tabela_achados = "".join(
        f"<tr><td>{_e(_so_nome(a['frase']))}</td><td>{_plataforma(a['plataforma'])}</td><td class=n>{_pct(a['pct_top'])} × {_pct(a['pct_controle'])}</td>"
        f"<td class=n>{_vezes(a['lift'], 2)} ({_num(a['ic'][0], 2)} a {_num(a['ic'][1], 2)})</td><td class=n>{a['n_perfis']}</td></tr>" for a in d["usar"] + d["evitar"])
    destaque = "".join(f"<tr><td>{_e(c.get('nome') or c['perfil'])}</td><td>{_plataforma(c['plataforma'])}</td><td>{_e(SEGMENTOS.get(c.get('segmento'), ''))}</td>"
                       f"<td class=n>{_milhar(c.get('seguidores'))}</td><td class=n>{c.get('nota')}</td></tr>" for c in d["destaque"])
    n_contas = sum(c["n_posts"] for c in d["contas"])

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Playbook de conteúdo · Stone e Impulso Stone</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<header class="topo"><div class="in">
  <div class="marca"><svg viewBox="0 0 24 24"><path d="M12 2.5v19M2.5 12h19M5.3 5.3l13.4 13.4M18.7 5.3 5.3 18.7"/></svg><span>Boa<b>Pauta</b></span></div>
  <div class="capa">
    <div><span class="sobre">Stone · Impulso Stone · coleta de {b['coletado_em']}</span>
      <h1>Playbook de <em>conteúdo</em></h1>
      <p>O que mudar no Instagram da @stone e do @impulsostone, comparando o que cada conta publica com o que engaja em perfis que falam com pequenos empreendedores.</p></div>
    <div class="capa-numeros">
      <div><b>{_milhar(b['posts'])}</b><span>posts do nicho analisados</span></div>
      <div><b>{b['perfis']}</b><span>perfis de referência</span></div>
      <div><b>{n_contas}</b><span>posts das contas da Stone</span></div>
    </div>
  </div>
  <nav class="abas">
    <button data-aba="impulso">@impulsostone<small>equipe do Impulso</small></button>
    <button data-aba="stone">@stone<small>equipe da marca</small></button>
    <button data-aba="nicho">Nicho<small>as duas contas</small></button>
  </nav>
</div></header>
<main class="corpo">
<section class="painel" id="impulso">{painel_impulso}</section>
<section class="painel" id="stone">{painel_stone}</section>
<section class="painel" id="nicho">{_painel_nicho(d)}</section>

<section class="apendice">
<div class="apendice-cab"><span class="ap-icone"><svg viewBox="0 0 24 24"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5zM4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5"/></svg></span>
<div><h3>Como os números foram feitos</h3><p>Método, tabelas completas e limites. Abra quando precisar conferir.</p></div></div>
<details><summary>Como ler os números</summary><div class="dentro">
<p><b>Nicho</b>: 55 perfis públicos que falam com MPEs. <b>Top</b>: os 10% de posts de cada rede e faixa de seguidores que mais superaram a média do próprio perfil; <b>demais</b>: o mesmo número de posts sorteados entre os outros. <b>3,0×</b> = três vezes mais frequente no top.</p>
<p><b>Nas contas da Stone</b>, cada post é comparado com a mediana da própria conta: <b>1,8×</b> quer dizer que posts com aquela característica tiveram, no meio, 80% a mais de engajamento que o post típico da conta (só grupos com 4 posts ou mais). Engajamento = (curtidas + comentários) ÷ seguidores.</p>
<p class="m">Cada conta é um perfil só, com algumas dezenas de posts em 90 dias: trate as recomendações como hipóteses para testar, não como prova de causa.</p></div></details>
<details><summary>Todos os achados do nicho (com intervalo de confiança)</summary><div class="dentro"><table><thead><tr><th>Característica</th><th>Rede</th><th>Top × demais</th><th>Lift (IC 90%)</th><th>Perfis</th></tr></thead><tbody>{tabela_achados}</tbody></table></div></details>
<details><summary>Os 10 perfis com nota mais alta</summary><div class="dentro"><table><thead><tr><th>Perfil</th><th>Rede</th><th>Segmento</th><th>Seguidores</th><th>Nota</th></tr></thead><tbody>{destaque}</tbody></table></div></details>
<details><summary>Limites desta análise</summary><div class="dentro"><ul>
<li>Amostra de {b['perfis']} perfis públicos escolhidos por falar com MPEs; associação, não causa.</li>
<li>As contas da Stone ficam fora do cálculo do top: são comparadas com o nicho, não fazem parte dele.</li>
<li>Rótulos feitos por modelos de linguagem e conferidos por amostra; campos instáveis ficam fora.</li>
<li>Reels com música licenciada ou cujo arquivo o Instagram não entrega ficam fora da análise de vídeo.</li>
<li>Alcance, salvamentos e compartilhamentos das contas da Stone só viriam com acesso aos Insights delas.</li></ul></div></details>
</section>
<footer><span class="rod-marca"><svg viewBox="0 0 24 24"><path d="M12 2.5v19M2.5 12h19M5.3 5.3l13.4 13.4M18.7 5.3 5.3 18.7"/></svg>Boa<b>Pauta</b></span>Gerado em {d['gerado_em']}. Nenhum número foi escrito por modelo de linguagem; gere de novo depois de cada coleta.</footer>
</main>
<script>{JS}</script>
</body></html>"""


def gerar(base: fx.Base, pecas: list[dict], frase: Callable[[dict], str]) -> str:
    return renderizar(montar(base, pecas, frase), frase)
