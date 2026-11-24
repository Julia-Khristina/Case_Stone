"""Montagem dos slides do carrossel a partir do texto da peça (sem abrir navegador)."""
from src.rendering.carrossel_da_peca import montar_slides


def test_tela_vira_titulo_prefixos_saem_e_a_capa_nao_se_repete():
    criativo = {"titulo": "Separe seu dinheiro", "gancho": "Você ainda mistura as contas?", "cta": "Comente QUERO",
                "corpo": ["Capa: Você ainda mistura as contas? (na tela: “Capa: Você ainda mistura as contas?”)",
                          "Abra uma conta só para a loja e use só ela (na tela: “1. Conta separada”)",
                          "Slide 3: Anote toda saída do caixa. Assim você vê para onde vai o dinheiro.",
                          "Quer aprender mais? (na tela: “Quer saber mais?”)"]}
    slides = montar_slides(criativo)
    assert [s["role"] for s in slides] == ["capa", "corpo", "corpo", "cta"]
    assert slides[1] == {"role": "corpo", "title": "Conta separada", "body": "Abra uma conta só para a loja e use só ela"}
    assert slides[2]["title"] == "Anote toda saída do caixa." and slides[2]["body"].startswith("Assim")
    assert slides[3]["title"] == "Quer saber mais?" and slides[3]["cta"] == "Comente QUERO"
    assert not any("na tela" in (s.get("title", "") + s.get("body", "")) for s in slides)
