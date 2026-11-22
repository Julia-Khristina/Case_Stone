"""Agenda de posts com as configurações reais (datas, horários e pilares do projeto)."""
from __future__ import annotations

from datetime import date

from src.analysis.agenda import datas_ativas, gerar_agenda

SEGMENTOS = ["alimentacao", "beleza_estetica", "comercio_bairro"]


def test_black_friday_entra_com_antecedencia_e_no_proprio_dia():
    ativas = datas_ativas(date(2026, 11, 23), [{"nome": "Black Friday", "data": "2026-11-27", "antecedencia_dias": 21,
                                                "segmentos": ["todos"], "pilar": "Gestão e vendas"}])
    assert ativas and ativas[0]["dias_para_data"] == 4
    agenda = gerar_agenda(date(2026, 11, 23), 14, SEGMENTOS, ["reels", "carrossel"])
    por_data = {s["data"]: s for s in agenda}
    assert "2026-11-27" in por_data                                   # sexta é dia fraco, mas é a própria data
    assert por_data["2026-11-27"]["data_comemorativa"] == "Black Friday"
    assert "se preparar" not in por_data["2026-11-27"]["tema"]        # no próprio dia não se fala em preparação


def test_regras_de_rotacao_e_dias_fracos():
    agenda = gerar_agenda(date(2026, 11, 23), 14, SEGMENTOS, ["reels", "carrossel"])
    segmentos = [s["segmento"] for s in agenda]
    assert all(a != b for a, b in zip(segmentos, segmentos[1:]))     # segmento nunca repete em dias seguidos
    sabados = [s for s in agenda if s["dia"] == "sáb"]
    assert not sabados                                                # sábado é fraco e não tem data nessas semanas
    semana1 = [s for s in agenda if s["data"] <= "2026-11-29"]
    assert len(semana1) <= 6 and len({s["pilar"] for s in semana1}) >= 4
    assert all(s["horario"] and s["fontes_horario"] for s in agenda)


def test_mesma_data_nao_domina_a_semana():
    agenda = gerar_agenda(date(2026, 11, 23), 7, SEGMENTOS, ["reels"])
    black = [s for s in agenda if s["data_comemorativa"] == "Black Friday"]
    assert 1 <= len(black) <= 3          # até 2 de preparação + o próprio dia


def test_datas_que_competem_na_mesma_semana_todas_aparecem():
    agenda = gerar_agenda(date(2026, 11, 23), 7, SEGMENTOS, ["reels"])
    datas = {s["data_comemorativa"] for s in agenda}
    assert "13º salário (1ª parcela)" in datas            # antes sumia atrás de Black Friday e Cyber Monday
    assert "Black Friday" in datas


def test_temporada_no_proprio_dia_agradece_em_vez_de_vender():
    agenda = gerar_agenda(date(2026, 12, 21), 7, SEGMENTOS, ["reels"])
    natal = next(s for s in agenda if s["data"] == "2026-12-25")
    assert natal["fase"] == "no_dia_agradecer" and "agradeça" in natal["tema"]
    assert any(s["fase"] == "vespera_feriado" for s in agenda)          # aviso do feriado antes do dia


def test_feriado_sem_post_de_venda_e_aviso_uma_vez_so():
    agenda = gerar_agenda(date(2027, 4, 12), 14, SEGMENTOS, ["reels"])
    assert not any(s["data"] == "2027-04-21" for s in agenda)            # Tiradentes: sem post no dia
    avisos = [s for s in agenda if s["data_comemorativa"] == "Feriado de Tiradentes"]
    assert len(avisos) == 1


def test_mesma_data_nao_repete_o_texto_e_das_entra_todo_mes():
    agenda = gerar_agenda(date(2026, 11, 23), 35, SEGMENTOS, ["reels", "carrossel"])
    temas = [s["tema"] for s in agenda]
    assert len(temas) == len(set(temas))
    jan = gerar_agenda(date(2027, 1, 11), 14, SEGMENTOS, ["reels"])
    assert any(s["data"] == "2027-01-20" and s["data_comemorativa"] == "Vencimento do DAS do MEI" for s in jan)


def test_dia_sem_data_tem_ferramenta_da_semana_e_orientacao_pratica():
    agenda = gerar_agenda(date(2027, 6, 28), 28, SEGMENTOS, ["reels"])      # julho: poucas datas
    for i in range(4):
        semana = [s for s in agenda if date(2027, 6, 28).toordinal() + 7 * i <= date.fromisoformat(s["data"]).toordinal() < date(2027, 6, 28).toordinal() + 7 * (i + 1)]
        ferramentas = [s for s in semana if s["tipo_data"] == "ferramenta"]
        if any(s["data_comemorativa"] is None for s in semana):
            assert len(ferramentas) == 1                                       # uma ferramenta por semana
            assert any("site oficial" in m for m in ferramentas[0]["motivos"])  # com custo e fonte para conferir
    assert any(s["tipo_data"] == "orientacao" for s in agenda)


def test_orientacao_do_dia_nao_muda_conforme_a_janela():
    mes = {s["data"]: s["tema"] for s in gerar_agenda(date(2027, 7, 5), 35, SEGMENTOS, ["reels"]) if s["tipo_data"] == "orientacao"}
    semana = {s["data"]: s["tema"] for s in gerar_agenda(date(2027, 7, 12), 7, SEGMENTOS, ["reels"]) if s["tipo_data"] == "orientacao"}
    assert semana and all(mes[d] == t for d, t in semana.items() if d in mes)


def test_radar_de_ferramentas_sem_concorrentes_da_stone():
    import yaml
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[2] / "config"
    concorrentes = [c.lower() for c in yaml.safe_load((raiz / "stone_context.yaml").read_text(encoding="utf-8"))["concorrentes"]]
    ferramentas = yaml.safe_load((raiz / "orientacoes.yaml").read_text(encoding="utf-8"))["ferramentas"]
    texto = " ".join(f"{f['nome']} {f['tema']} {f['fonte']}" for f in ferramentas).lower()
    assert not [c for c in concorrentes if c in texto]
    assert all(f.get("fonte") and f.get("custo") for f in ferramentas)


def test_datas_moveis_sao_calculadas_para_qualquer_ano():
    from datetime import date
    from src.analysis.agenda import data_no_ano, pascoa
    assert pascoa(2027) == date(2027, 3, 28) and pascoa(2028) == date(2028, 4, 16) and pascoa(2030) == date(2030, 4, 21)
    assert data_no_ano({"pascoa": -47}, 2027) == date(2027, 2, 9)                       # terça de Carnaval
    assert data_no_ano({"pascoa": 60}, 2027) == date(2027, 5, 27)                       # Corpus Christi
    assert data_no_ano({"domingo": {"mes": 5, "n": 2}}, 2028) == date(2028, 5, 14)      # Dia das Mães
    assert data_no_ano({"quinta": {"mes": 11, "n": 4}, "deslocamento": 1}, 2026) == date(2026, 11, 27)   # Black Friday
    assert data_no_ano({"quinta": {"mes": 11, "n": 4}, "deslocamento": 1}, 2028) == date(2028, 11, 24)
    assert data_no_ano({"dia": "12-25"}, 2031) == date(2031, 12, 25)


def test_config_de_datas_nao_tem_ano_fixo():
    import yaml
    from pathlib import Path
    cfg = yaml.safe_load((Path(__file__).resolve().parents[2] / "config" / "datas_comemorativas.yaml").read_text(encoding="utf-8"))
    assert all("data" not in d for d in cfg["datas"])                                # nada vence no fim do ano


def test_radar_entra_em_dia_sem_data_com_fonte_e_prioridade():
    from datetime import date
    from src.analysis.agenda import gerar_agenda
    base = {"pilar": "Educação financeira", "tema_post": "t", "o_que_muda": "m", "por_que_importa": "p", "titulo_fonte": "f",
            "fonte": "Receita Federal"}
    radar = [{**base, "tipo": "data", "titulo_curto": "Velha", "link": "a", "publicado_em": "2026-12-01T00:00:00+00:00"},
             {**base, "tipo": "regra_nova", "titulo_curto": "Regra", "link": "b", "publicado_em": "2026-12-02T00:00:00+00:00"},
             {**base, "tipo": "prazo", "titulo_curto": "Prazo", "link": "c", "publicado_em": "2026-11-20T00:00:00+00:00",
              "data_chave": "2027-01-10"}]                                        # fora da janela de 10 dias antes
    s = gerar_agenda(date(2026, 12, 7), 7, ["alimentacao"], ["reels"], radar=radar)
    rad = [x for x in s if x["tipo_data"] == "radar"]
    assert 1 <= len(rad) <= 2 and rad[0]["radar"]["link"] == "b"            # a regra nova antes da data genérica
    assert rad[0]["radar"]["fonte"] == "Receita Federal" and rad[0]["motivos"][0].startswith("Novidade da semana")
    assert all(x["radar"]["link"] != "c" for x in rad)
    assert not any(x["tipo_data"] == "radar" and x["data_comemorativa"] for x in s)   # nunca no lugar de uma data
