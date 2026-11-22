"""Agenda de posts: sugere o que postar, quando e para quem, sem usar o LLM.

Regras (config/datas_comemorativas.yaml, config/horarios.yaml, config/stone_context.yaml → pilares):
- cada data tem um TIPO, e cada tipo tem fases no tempo:
    venda_no_dia  planejar → divulgar → véspera → o próprio dia (a venda acontece no dia)
    temporada     planejar → divulgar → última hora → agradecimento no dia → pós-venda nos dias seguintes
                  (a venda acontece antes: no Natal ou no Dia das Mães o comércio já vendeu)
    obrigacao     organizar antes do prazo → último dia (DAS, 13º, declaração do MEI)
    comunidade    preparar → homenagem no dia (Dia da Mulher, Dia da MPE)
    feriado       aviso na véspera; no próprio dia não há post de venda
- cada fase tem ângulos com pilares diferentes: a mesma data não repete o mesmo texto e os pilares variam na semana;
- revezamento justo: entre as datas ativas, ganha a que teve menos posts na semana (depois, a de maior peso);
  o próprio dia de uma venda, obrigação ou comunidade sempre entra;
- dias fracos ficam sem sugestão, salvo o próprio dia de uma data; feriados ficam sem post de venda;
- o mesmo segmento não aparece em dias seguidos; o formato vem dos formatos em alta; o horário é orientação, com a fonte.
O criativo só é gerado (pelo agente) quando alguém escolhe uma sugestão.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).resolve().parents[2]
DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
ROTULO_DIA = {"segunda": "seg", "terca": "ter", "quarta": "qua", "quinta": "qui", "sexta": "sex", "sabado": "sáb",
              "domingo": "dom"}
NOME_DIA = {"segunda": "segunda", "terca": "terça", "quarta": "quarta", "quinta": "quinta", "sexta": "sexta",
            "sabado": "sábado", "domingo": "domingo"}
FORCA = {"forte": 0, "moderado": 1, "fraco": 2}

EF, GV, HR, ESP, COM = "Educação financeira", "Gestão e vendas", "Histórias reais", "Especialistas", "Comunidade"
# fase → ângulos (pilar, tema, rótulo curto para o calendário). {nome} é a data; {dia} é o dia da semana do feriado.
ANGULOS = {
    "planejar": [(EF, "{nome}: calcule preço e custo antes de montar a promoção", "preço e custo"),
                 (EF, "{nome}: quanto estoque comprar sem apertar o caixa", "estoque e caixa"),
                 (ESP, "{nome}: o que um especialista faria para se preparar", "dica de especialista")],
    "divulgar": [(GV, "{nome}: como divulgar no WhatsApp e no Instagram do negócio", "divulgação"),
                 (GV, "{nome}: combos e kits que vendem mais", "combos e kits"),
                 (HR, "{nome}: como um pequeno negócio real se preparou", "história real")],
    "vespera_venda": [(GV, "{nome} chegando: atendimento, estoque e formas de pagamento prontos", "reta final"),
                      (ESP, "{nome} chegando: checklist de especialista para os últimos dias", "checklist"),
                      (EF, "{nome} chegando: desconto que cabe na margem", "desconto e margem")],
    "no_dia_venda": [(GV, "{nome} é hoje: atendimento rápido e oferta clara", "é hoje"),
                     (COM, "{nome} é hoje: conte nos comentários como estão as vendas", "é hoje")],
    "ultima_hora": [(GV, "{nome}: vendas de última hora sem perder o controle", "última hora"),
                    (GV, "{nome}: entrega e retirada para quem deixou para depois", "entrega e retirada"),
                    (HR, "{nome}: o que funcionou para quem vende na reta final", "história real")],
    "no_dia_agradecer": [(COM, "{nome}: agradeça quem comprou e convide para voltar", "agradecer")],
    "depois": [(GV, "Pós-{nome}: trocas e pós-venda que fazem o cliente voltar", "trocas e pós-venda"),
               (EF, "Pós-{nome}: confira as contas e o lucro da temporada", "contas da temporada")],
    "organizar": [(EF, "{nome}: organize o dinheiro e o prazo com antecedência", "organizar o dinheiro"),
                  (EF, "{nome}: o passo a passo para ficar em dia", "passo a passo"),
                  (ESP, "{nome}: dúvidas comuns respondidas por um especialista", "dúvidas comuns")],
    "ultimo_dia": [(EF, "{nome}: hoje é o último dia para ficar em dia", "último dia")],
    "preparar_comunidade": [(HR, "{nome}: a história de quem empreende de verdade", "história real"),
                            (COM, "{nome}: convide a comunidade a se apresentar", "convite")],
    "no_dia_comunidade": [(COM, "{nome}: homenagem e convite para a comunidade do Impulso", "homenagem"),
                          (HR, "{nome}: a história de quem empreende de verdade", "história real")],
    "vespera_feriado": [(GV, "{nome} na {dia}: avise o horário e organize estoque e atendimento", "aviso de horário")],
}
EXPLICA_FASE = {
    "planejar": "fase de planejamento: preço, custo e estoque", "divulgar": "fase de divulgação",
    "vespera_venda": "reta final antes do dia de venda", "no_dia_venda": "a venda acontece no próprio dia",
    "ultima_hora": "compras de última hora", "no_dia_agradecer": "a venda já aconteceu: dia de agradecer e convidar a voltar",
    "depois": "dias seguintes: trocas e pós-venda", "organizar": "prazo de pagamento ou declaração chegando",
    "ultimo_dia": "último dia do prazo", "preparar_comunidade": "data do público do Impulso chegando",
    "no_dia_comunidade": "data do público do Impulso", "vespera_feriado": "feriado: o comércio muda o horário",
}
NO_DIA = {"no_dia_venda", "ultimo_dia", "no_dia_comunidade", "no_dia_agradecer"}   # entram sempre, sem limite semanal


def _yaml(nome: str) -> dict:
    return yaml.safe_load((ROOT / "config" / nome).read_text(encoding="utf-8")) or {}


def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mes = (h + l_ - 7 * m + 114) // 31
    return date(ano, mes, (h + l_ - 7 * m + 114) % 31 + 1)


def _enesimo(ano: int, mes: int, n: int, dia_semana: int) -> date:
    """n-ésimo dia da semana do mês (dia_semana: 0 = segunda ... 6 = domingo)."""
    primeiro = date(ano, mes, 1)
    return primeiro + timedelta(days=(dia_semana - primeiro.weekday()) % 7 + 7 * (n - 1))


def data_no_ano(d: dict, ano: int) -> Optional[date]:
    """Aplica a regra da data (dia, pascoa, domingo, quinta) ao ano; None se a data não tem regra."""
    if "dia" in d:
        mes, dia = (int(x) for x in str(d["dia"]).split("-"))
        return date(ano, mes, dia)
    if "pascoa" in d:
        return pascoa(ano) + timedelta(days=int(d["pascoa"]))
    if "domingo" in d:
        return _enesimo(ano, int(d["domingo"]["mes"]), int(d["domingo"]["n"]), 6)
    if "quinta" in d:
        return _enesimo(ano, int(d["quinta"]["mes"]), int(d["quinta"]["n"]), 3) + timedelta(days=int(d.get("deslocamento", 0)))
    return None


REGRAS_DE_DATA = ("dia", "pascoa", "domingo", "quinta", "deslocamento")


def expandir_datas(datas_cfg: dict, inicio: date, fim: date) -> list[dict]:
    """Datas por regra (qualquer ano), datas fixas e recorrentes mensais (ex.: DAS do MEI no dia 20) perto da janela."""
    datas = []
    for d in datas_cfg.get("datas", []):
        base = dict(d, tipo=d.get("tipo", "temporada"), peso=int(d.get("peso", 2)))
        if "data" in d:
            datas.append(base)
            continue
        for ano in range(inicio.year - 1, fim.year + 2):
            alvo = data_no_ano(d, ano)
            if alvo and inicio - timedelta(days=7) <= alvo <= fim + timedelta(days=int(d.get("antecedencia_dias", 0)) + 1):
                datas.append({k: v for k, v in base.items() if k not in REGRAS_DE_DATA} | {"data": alvo.isoformat()})
    for r in datas_cfg.get("recorrentes", []):
        ano, mes = inicio.year, inicio.month
        while date(ano, mes, 1) <= fim + timedelta(days=31):
            alvo = date(ano, mes, int(r["dia_do_mes"]))
            if inicio - timedelta(days=7) <= alvo <= fim + timedelta(days=int(r["antecedencia_dias"])):
                datas.append({k: v for k, v in r.items() if k != "dia_do_mes"} | {"data": alvo.isoformat(), "peso": int(r.get("peso", 2))})
            ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return datas


def fase_de(d: dict, dias_para: int, dias_depois: int = 3) -> Optional[str]:
    """Em que fase a data está naquele dia (None = a data não gera post nesse dia)."""
    tipo, antecedencia = d["tipo"], int(d["antecedencia_dias"])
    if dias_para < 0:
        return "depois" if tipo == "temporada" and -dias_para <= dias_depois else None
    if dias_para > antecedencia:
        return None
    if dias_para == 0:
        return {"venda_no_dia": "no_dia_venda", "temporada": "no_dia_agradecer", "obrigacao": "ultimo_dia",
                "comunidade": "no_dia_comunidade"}.get(tipo)
    if tipo == "venda_no_dia":
        return "vespera_venda" if dias_para <= 3 else ("planejar" if dias_para > antecedencia * 0.5 else "divulgar")
    if tipo == "temporada":
        return "ultima_hora" if dias_para <= 5 else ("planejar" if dias_para > antecedencia * 0.6 else "divulgar")
    if tipo == "obrigacao":
        return "organizar"
    if tipo == "comunidade":
        return "preparar_comunidade"
    if tipo == "feriado":
        return "vespera_feriado" if dias_para <= 3 else None
    return None


def datas_ativas(dia: date, datas: list[dict], dias_depois: int = 3) -> list[dict]:
    """Datas que geram post no dia, com a fase e quantos dias faltam (negativo = já passou)."""
    ativas = []
    for d in datas:
        d = dict(d, tipo=d.get("tipo", "temporada"), peso=int(d.get("peso", 2)))
        dias_para = (date.fromisoformat(d["data"]) - dia).days
        fase = fase_de(d, dias_para, dias_depois)
        if fase:
            ativas.append({**d, "dias_para_data": dias_para, "fase": fase})
    return sorted(ativas, key=lambda d: (d["fase"] not in NO_DIA, -d["peso"], abs(d["dias_para_data"])))


PRIORIDADE_RADAR = {"prazo": 0, "alerta": 0, "regra_nova": 1, "ferramenta": 2, "oportunidade_de_venda": 3, "data": 4}
RADAR_POR_SEMANA = 2            # novidades do radar por semana, nos dias sem data (não tiram o lugar de datas)
RADAR_FRESCOR_DIAS = 14         # novidade sem data-chave vale por duas semanas a partir da publicação
RADAR_ANTES_DA_DATA = 10        # novidade com data-chave entra nos 10 dias antes dela
ANTECIPACAO_NICHO_DIAS = 14     # quando o nicho já fala de uma data, a preparação começa duas semanas antes


def _sem_acento(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", str(t or "")) if not unicodedata.combining(c)).lower()


def _janela_radar(item: dict) -> tuple[date, date]:
    publicado = date.fromisoformat(item["publicado_em"][:10])
    if item.get("data_chave"):
        alvo = date.fromisoformat(item["data_chave"])
        return max(publicado, alvo - timedelta(days=RADAR_ANTES_DA_DATA)), alvo
    return publicado, publicado + timedelta(days=RADAR_FRESCOR_DIAS)


def gerar_agenda(inicio: date, dias: int, segmentos: list[str], formatos: list[str],
                 horarios: Optional[dict] = None, datas_cfg: Optional[dict] = None,
                 pilares: Optional[list[str]] = None, radar: Optional[list[dict]] = None,
                 sinal_nicho: Optional[dict[str, int]] = None) -> list[dict]:
    """`segmentos`: em ordem de prioridade (ex.: os com mais posts no top); "todos" entra alternado.
    `formatos`: em ordem (formatos em alta primeiro). Devolve uma sugestão por dia escolhido.

    `radar`: novidades de fontes oficiais (data/processed/radar.json); entram nos dias sem data, no máximo
    RADAR_POR_SEMANA por semana, com a fonte. `sinal_nicho`: {data sazonal: posts do top recente que já falam dela};
    essas datas ganham ANTECIPACAO_NICHO_DIAS a mais de preparação."""
    horarios = horarios or _yaml("horarios.yaml")
    datas_cfg = datas_cfg or _yaml("datas_comemorativas.yaml")
    contexto = _yaml("stone_context.yaml")
    pilares = pilares or [p["nome"] for p in contexto.get("pilares", [])]
    regras = datas_cfg.get("regras", {})
    por_semana = int(regras.get("sugestoes_por_semana", 5))
    max_por_data = int(regras.get("max_posts_por_data_na_semana", 2))
    dias_depois = int(regras.get("dias_depois_temporada", 3))
    fontes = {f["id"]: f["nome"] for f in horarios.get("fontes", [])}
    rotacao_segmentos = [s for par in zip(segmentos, ["todos"] * len(segmentos)) for s in par] or ["todos"]
    datas = expandir_datas(datas_cfg, inicio, inicio + timedelta(days=dias + ANTECIPACAO_NICHO_DIAS))
    for d in datas:                               # o nicho já está falando da data: a preparação começa antes
        nome = _sem_acento(d["nome"])
        n = max((v for k, v in (sinal_nicho or {}).items() if k and (k in nome or nome in k)), default=0)
        if n and d["tipo"] in ("temporada", "venda_no_dia", "comunidade"):
            d["antecedencia_dias"] = int(d["antecedencia_dias"]) + ANTECIPACAO_NICHO_DIAS
            d["sinal_nicho"] = n
    feriados = {d["data"] for d in datas if d["tipo"] == "feriado"}
    radar_usados: set[str] = set()

    sugestoes: list[dict] = []
    ultimo_segmento, idx_seg, idx_fmt = None, 0, 0
    usos_angulo: dict[tuple, int] = {}            # (data, fase) → quantas vezes já saiu, para variar o texto
    textos_usados: dict[str, set] = {}            # data → textos já usados (a mesma data não repete o texto)
    feriados_avisados: set[str] = set()           # um aviso por feriado no período todo
    orient = _yaml("orientacoes.yaml")
    ferramentas = orient.get("ferramentas", [])
    # orientações intercaladas por pilar (finanças, vendas, especialista, história...): dias seguidos não repetem o pilar
    por_pilar: dict[str, list] = {}
    for o in orient.get("orientacoes", []):
        por_pilar.setdefault(o["pilar"], []).append(o)
    # distribuição uniforme: cada pilar fica espalhado pela sequência, mesmo os que têm mais temas
    orientacoes = [o for _, _, o in sorted(((i + 0.5) / len(g), n, o) for n, g in enumerate(por_pilar.values()) for i, o in enumerate(g))]
    for semana_inicio in range(0, dias, 7):
        semana = [inicio + timedelta(days=semana_inicio + i) for i in range(min(7, dias - semana_inicio))]
        info = {d: horarios["dias"][DIAS[d.weekday()]] for d in semana}
        ativas_dia = {d: datas_ativas(d, datas, dias_depois) for d in semana}
        proprio_dia = {d: any(a["fase"] in NO_DIA for a in ativas_dia[d]) for d in semana}

        def pode(d: date) -> bool:
            if d.isoformat() in feriados and not proprio_dia[d]:
                return False                       # feriado: comércio fechado, sem post de venda
            return info[d]["forca"] != "fraco" or proprio_dia[d] or not regras.get("pular_dias_fracos", True)

        candidatos = [d for d in semana if pode(d)]
        escolhidos = sorted(sorted(candidatos, key=lambda d: (not proprio_dia[d], FORCA[info[d]["forca"]]))[:por_semana])
        pilares_usados: set[str] = set()
        usos_data: dict[str, int] = {}
        ferramenta_na_semana = False
        radar_na_semana = 0
        for dia in escolhidos:
            ativas = ativas_dia[dia]
            foco = next((a for a in ativas if a["fase"] in NO_DIA), None)
            if foco is None:
                # feriado: um aviso só, e ele passa na frente (o comércio precisa avisar o horário antes)
                def disponivel(a: dict) -> bool:
                    if a["tipo"] == "feriado":
                        return a["nome"] not in feriados_avisados
                    return usos_data.get(a["nome"], 0) < max_por_data

                livres = [a for a in ativas if disponivel(a)]
                livres.sort(key=lambda a: (a["tipo"] != "feriado", usos_data.get(a["nome"], 0), -a["peso"], abs(a["dias_para_data"])))
                foco = livres[0] if livres else None

            if foco:
                usos_data[foco["nome"]] = usos_data.get(foco["nome"], 0) + 1
                if foco["tipo"] == "feriado":
                    feriados_avisados.add(foco["nome"])
                opcoes = ANGULOS[foco["fase"]]
                chave = (foco["nome"], foco["fase"])
                n = usos_angulo.get(chave, 0)
                ordem = opcoes[n % len(opcoes):] + opcoes[:n % len(opcoes)]
                ja_usados = textos_usados.setdefault(foco["nome"], set())
                pilar, modelo, curto = min(ordem, key=lambda o: (o[1] in ja_usados, o[0] in pilares_usados))
                ja_usados.add(modelo)
                usos_angulo[chave] = n + 1
                dia_alvo = date.fromisoformat(foco["data"])
                tema = modelo.format(nome=foco["nome"], dia=NOME_DIA[DIAS[dia_alvo.weekday()]])
                rotulo = f"{foco['nome']} · {curto}"
            # Dia sem data: uma ferramenta por semana (radar de ferramentas) e, nos outros, orientação prática.
            # A escolha depende da semana do calendário, não da janela pedida: o mesmo dia mostra o mesmo tema
            # na vista de mês, na de semana e no resumo.
            extra = None
            novidade = None
            if not foco and radar and radar_na_semana < RADAR_POR_SEMANA:
                cabem = [it for it in radar if it["link"] not in radar_usados
                         and _janela_radar(it)[0] <= dia <= _janela_radar(it)[1]]
                # primeiro o que tem prazo (mais perto antes), depois o tipo mais urgente, depois o mais recente
                cabem.sort(key=lambda it: (it.get("data_chave") is None, it.get("data_chave") or "",
                                           PRIORIDADE_RADAR.get(it.get("tipo"), 9), -date.fromisoformat(it["publicado_em"][:10]).toordinal()))
                novidade = cabem[0] if cabem else None
            if novidade:
                radar_usados.add(novidade["link"])
                radar_na_semana += 1
                extra = dict(novidade, tipo="radar")
                pilar, tema, rotulo = novidade["pilar"], novidade["tema_post"], f"Radar · {novidade['titulo_curto']}"
            if not foco and not novidade:
                semana_num = (dia.toordinal() - 1) // 7
                if ferramentas and not ferramenta_na_semana:
                    extra = dict(ferramentas[semana_num % len(ferramentas)], tipo="ferramenta")
                    ferramenta_na_semana = True
                    pilar, tema, rotulo = extra["pilar"], extra["tema"], f"Ferramenta · {extra['nome']}"
                elif orientacoes:
                    # cada dia do calendário tem a sua orientação: o tema não muda conforme a tela que pede a agenda
                    extra = dict(orientacoes[dia.toordinal() % len(orientacoes)], tipo="orientacao")
                    pilar, tema, rotulo = extra["pilar"], extra["tema"], f"Orientação · {extra['rotulo']}"
                else:
                    pilar = next((p for p in pilares if p not in pilares_usados), pilares[0])
                    tema, rotulo = f"{pilar} para o pequeno negócio", pilar
            pilares_usados.add(pilar)

            # segmento: o da data (se não for "todos"), senão a rotação, nunca repetindo o dia anterior
            segmento = None
            preferidos = (foco or extra or {}).get("segmentos") or ["todos"]
            if preferidos != ["todos"]:
                segmento = next((s for s in preferidos if s != ultimo_segmento and s != "todos"), None)
            if segmento is None:
                for _ in range(len(rotacao_segmentos)):
                    candidato = rotacao_segmentos[idx_seg % len(rotacao_segmentos)]
                    idx_seg += 1
                    if candidato != ultimo_segmento:
                        segmento = candidato
                        break
            formato = formatos[idx_fmt % len(formatos)] if formatos else "reels"
            idx_fmt += 1
            h = info[dia]
            motivos = []
            if foco:
                quando = ("hoje" if foco["dias_para_data"] == 0 else
                          f"em {foco['dias_para_data']} dias" if foco["dias_para_data"] > 0 else f"foi há {-foco['dias_para_data']} dias")
                motivos.append(f"{foco['nome']} {quando}: {EXPLICA_FASE[foco['fase']]}")
                if foco.get("nota"):
                    motivos.append(foco["nota"])
                if foco.get("sinal_nicho"):
                    motivos.append(f"O nicho já está falando disso: {foco['sinal_nicho']} posts do top recente; "
                                   "a preparação começou mais cedo")
            elif extra and extra["tipo"] == "radar":
                pub = date.fromisoformat(extra["publicado_em"][:10])
                motivos.append(f"Novidade da semana ({extra['fonte']}, {pub:%d/%m}): {extra['o_que_muda']}")
                motivos.append(f"Por que importa: {extra['por_que_importa']}")
                if extra.get("data_chave"):
                    motivos.append(f"Data na fonte: {date.fromisoformat(extra['data_chave']):%d/%m}")
            elif extra and extra["tipo"] == "ferramenta":
                motivos.append(f"Radar de ferramentas: {extra['resolve']}")
                motivos.append(f"Custo: {extra['custo']} · site oficial: {extra['fonte']} (confira antes de publicar)")
                if extra.get("nota"):
                    motivos.append(extra["nota"])
            elif extra:
                motivos.append("Dia sem data comemorativa: orientação prática para o empreendedor aplicar no mesmo dia")
            motivos.append(f"pilar {pilar}")
            if segmento != "todos":
                motivos.append(f"segmento {segmento} não repete o dia anterior")
            motivos.append(f"formato {formato} entre os que mais engajam")
            sugestoes.append({
                "data": dia.isoformat(), "dia": ROTULO_DIA[DIAS[dia.weekday()]], "forca_do_dia": h["forca"],
                "horario": h["principal"], "horario_alternativo": h.get("alternativa"),
                "fontes_horario": [fontes.get(f, f) for f in h.get("base", [])],
                "data_comemorativa": foco["nome"] if foco else None,
                "tipo_data": foco["tipo"] if foco else (extra["tipo"] if extra else None), "fase": foco["fase"] if foco else None,
                "rotulo": rotulo, "segmento": segmento, "pilar": pilar, "formato": formato, "tema": tema, "motivos": motivos,
                "radar": ({k: extra.get(k) for k in ("tipo", "fonte", "link", "titulo_fonte", "publicado_em", "data_chave")}
                          | {"tipo_novidade": novidade["tipo"]}) if novidade else None,
            })
            ultimo_segmento = segmento
    return sugestoes
