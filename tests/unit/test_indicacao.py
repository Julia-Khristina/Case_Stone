"""Indicação para parceria e classificação em dois eixos (tipo e setor)."""
from __future__ import annotations

from src.analysis.indicacao import selecionar_indicados
from src.collection.discovery import classificar_perfil

CONFIG = {"transversais": 2, "setoriais": 3, "reservas_por_vaga": 1, "setores_prioritarios": [],
          "faixas_preferidas": ["micro", "medio"], "excluir_se": ["parceiro_atual", "publi_concorrente", "conta_de_marca"]}


def c(perfil, tipo, nota, setor=None, tema=None, faixa="micro", **extra):
    return {"perfil": perfil, "tipo": tipo, "nota": nota, "macrossetor": setor, "tema": tema, "faixa": faixa, **extra}


def test_classifica_transversal_setorial_e_nicho():
    contadora = classificar_perfil("Contadora. Ajudo MEI a organizar as finanças e pagar menos imposto")
    assert contadora["tipo"] == "transversal" and contadora["tema"] == "financas" and contadora["publico_mpe"]
    confeiteira = classificar_perfil("Confeitaria artesanal em BH 🎂 encomendas pelo direct · empreendedora")
    assert confeiteira["tipo"] == "setorial" and confeiteira["macrossetor"] == "alimentacao"
    assert confeiteira["nicho"] == "confeitaria"
    barbeiro = classificar_perfil("Barbearia do Zé · seu negócio de bairro")
    assert barbeiro["macrossetor"] == "beleza_estetica" and barbeiro["nicho"] == "barbearia"
    assert classificar_perfil("Viagens e fotos do meu dia a dia")["tipo"] is None


def test_composicao_2_transversais_e_3_setoriais_com_reservas():
    criadores = [
        c("fin1", "transversal", 90, tema="financas"), c("fin2", "transversal", 88, tema="financas"),
        c("mkt1", "transversal", 80, tema="marketing"),
        c("doce1", "setorial", 85, "alimentacao"), c("doce2", "setorial", 70, "alimentacao"),
        c("pet1", "setorial", 75, "pets"), c("casa1", "setorial", 72, "casa_reparos"),
        c("beleza1", "setorial", 95, "beleza_estetica"),
        c("ruth", "setorial", 99, "alimentacao", parceiro_atual=True),
        c("india", "setorial", 98, "beleza_estetica", parceiro_atual=True),
    ]
    r = selecionar_indicados(criadores, CONFIG)
    assert [x["perfil"] for x in r["transversais"]] == ["fin1", "mkt1"]          # varia o tema
    # setores sem parceiro atual vêm primeiro (pets, casa); alimentação e beleza já têm parceiro
    assert [x["perfil"] for x in r["setoriais"]] == ["pet1", "casa1", "beleza1"]
    assert {x["perfil"] for x in r["excluidos"]} == {"ruth", "india"}
    assert {(x["perfil"], x["reserva_de"]) for x in r["reservas"]} >= {("fin2", "fin1")}


def test_setores_prioritarios_da_stone_e_exclusoes():
    criadores = [c("doce1", "setorial", 60, "alimentacao"), c("pet1", "setorial", 99, "pets"),
                 c("moda1", "setorial", 70, "moda_acessorios", alertas=["publi_concorrente"]),
                 c("moda2", "setorial", 65, "moda_acessorios"), c("grande1", "setorial", 99, "alimentacao", faixa="grande")]
    r = selecionar_indicados(criadores, {**CONFIG, "setores_prioritarios": ["moda_acessorios", "alimentacao"]})
    perfis = [x["perfil"] for x in r["setoriais"]]
    assert perfis[:2] == ["moda2", "doce1"]          # micro/médio antes de grande; publi com concorrente fora
    assert "moda1" in {x["perfil"] for x in r["excluidos"]}
    assert r["motivo_setores"] == "setores priorizados pela Stone"


def test_mei_como_sobrenome_nao_conta_como_microempreendedor():
    bianca = classificar_perfil("Aqui você encontra conteúdo de Moda de qualidade, dicas de estudo e carreira.", "Bianca Mei")
    assert bianca["publico_mpe"] is False and bianca["tema"] != "financas"
    assert classificar_perfil("Dúvidas sobre seu MEI? Nós ajudamos!")["publico_mpe"] is True
    assert classificar_perfil("tudo sobre como abrir seu mei sem complicação")["publico_mpe"] is True


def test_nota_minima_e_reserva_sem_repeticao():
    criadores = [c("fin1", "transversal", 90, tema="financas"), c("mkt1", "transversal", 85, tema="marketing"),
                 c("ven1", "transversal", 80, tema="vendas"),
                 c("pet1", "setorial", 56, "pets"), c("art1", "setorial", 60, "artesanato_producao"),
                 c("doce1", "setorial", 78, "alimentacao"), c("bel1", "setorial", 72, "beleza_estetica"),
                 c("bel2", "setorial", 70, "beleza_estetica")]
    r = selecionar_indicados(criadores, {**CONFIG, "nota_minima": 65})
    assert {x["perfil"] for x in r["setoriais"]} == {"doce1", "bel1", "bel2"}     # pet e artesanato abaixo de 65
    reservas = [x["perfil"] for x in r["reservas"]]
    assert len(reservas) == len(set(reservas)) and reservas == ["ven1"]
