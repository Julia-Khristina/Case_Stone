"""Agente: ferramentas determinísticas, conferências e o laço de geração/reescrita, com o LLM falso."""
from __future__ import annotations

import pandas as pd

from src.agent.contrato import AgentInput, Creative
from src.agent.ferramentas import Base, format_trends, query_stats, search_posts
from src.agent.grafo import run_agent
from src.agent.verificador import conferir
from src.evaluation.thresholds import load_thresholds
from tests.fakes.llm import FakeLLMClient

LIMIARES = load_thresholds("config/limiares.yaml")


def base_falsa() -> Base:
    linhas = []
    for i in range(30):   # top: finanças com gancho de dor em 6 perfis; controle: marketing com promessa
        linhas.append({"plataforma": "instagram", "post_id": f"t{i}", "perfil_id": f"p{i % 6}", "username": f"perfil{i % 6}",
                       "tipo": "reels" if i % 3 else "carrossel", "grupo": "top", "faixa": "micro", "er": 0.1 + i / 1000,
                       "lift_perfil": 3 - i / 100, "titulo": None, "legenda": f"3 erros no caixa {i}", "link": f"https://ig/{i}",
                       "tema_principal": "financas", "tipo_hook": "dor", "tipo_cta": "comentar",
                       "convite_participacao": True, "mensagem_generica": False, "segmento_negocio": "alimentacao"})
        linhas.append({"plataforma": "instagram", "post_id": f"c{i}", "perfil_id": f"q{i % 8}", "username": f"outro{i % 8}",
                       "tipo": "imagem", "grupo": "controle", "faixa": "micro", "er": 0.01, "lift_perfil": 0.8,
                       "titulo": None, "legenda": "dicas", "link": None, "tema_principal": "marketing",
                       "tipo_hook": "promessa", "tipo_cta": "link", "convite_participacao": False,
                       "mensagem_generica": False, "segmento_negocio": "geral"})
    return Base(pd.DataFrame(linhas))


def criativo(**extra) -> dict:
    base = {"formato": "reels", "caso": "Dona de padaria tira do caixa para o mercado de casa e no fim do mês não sabe se lucrou",
            "titulo": "3 erros no caixa", "gancho": "Seu caixa perde dinheiro e você nem vê",
            "corpo": ["0-3s: gancho com rosto", "3-15s: erro 1, misturar contas", "15-30s: erro 2, não anotar o troco",
                      "30-40s: peça para comentar"],
            "texto_tela": ["3 erros no caixa"], "legenda": "Qual desses acontece aí? Conta pra gente.",
            "cta": "Comente CAIXA", "duracao_s": 40, "reference_post_ids": ["t1"],
            "justificativa": ["Finanças aparece mais no top", "Gancho de dor engaja"]}
    return {**base, **extra}


def test_ferramentas_trazem_padroes_e_referencias_da_base():
    base = base_falsa()
    achados = query_stats(base, "instagram")
    financas = next(f for f in achados if f.caracteristica == "tema_principal" and f.valor == "financas")
    assert financas.leitura == "mais no top" and financas.n_perfis == 6
    refs = search_posts(base, "instagram", "alimentacao", "reels", k=5)
    assert refs and all(r.formato == "reels" for r in refs)
    assert len({r.perfil for r in refs}) == len(refs)                 # uma referência por perfil
    assert any(t.valor == "reels" and t.leitura == "mais no top" for t in format_trends(base))


def test_verificador_aponta_cada_problema():
    ok, falhas = conferir(Creative(**criativo()), {"t1"}, LIMIARES)
    assert all(ok.values()) and falhas == []
    ruim = Creative(**criativo(cta="Clique aqui", reference_post_ids=["inventado"], legenda="Lucro garantido para você",
                               corpo=["um"]))
    ok, falhas = conferir(ruim, {"t1"}, LIMIARES)
    assert not ok["referencias_existem"] and not ok["cta_presente"] and not ok["sem_promessa_exagerada"]
    assert not ok["tamanho_do_formato"] and len(falhas) >= 4


def test_agente_gera_reescreve_quando_reprovado_e_registra(tmp_path):
    fake = FakeLLMClient({"criativo": [criativo(cta="Clique aqui"), criativo()]})
    saida = run_agent(AgentInput(mode="gerar_criativo", query="atrair donos de restaurante", segment="alimentacao"),
                      base=base_falsa(), client=fake, registro=tmp_path / "runs.jsonl")
    assert len(saida.creatives) == 1
    c = saida.creatives[0]
    assert c.tentativas == 2 and c.falhas == [] and c.aprovado_automatico
    assert "Corrija" in fake.prompts[1]["prompt"]                       # a reescrita recebeu o relatório de falhas
    assert set(c.criativo.reference_post_ids) <= {r.post_id for r in saida.reference_posts}
    assert not saida.confidence_flag and "financas" in saida.explanation
    assert (tmp_path / "runs.jsonl").read_text(encoding="utf-8").count("run_id") == 1


def test_modo_analisar_nao_chama_o_llm(tmp_path):
    saida = run_agent(AgentInput(mode="analisar", query="o que engaja?"), base=base_falsa(), client=None,
                      registro=tmp_path / "runs.jsonl")
    assert saida.creatives == [] and saida.findings and saida.reference_posts


def test_pacote_usa_os_formatos_em_alta():
    fake = FakeLLMClient({"criativo": [criativo()]})
    saida = run_agent(AgentInput(mode="gerar_pacote", query="pacote da semana"), base=base_falsa(), client=fake, registro=None)
    assert [c.criativo.formato for c in saida.creatives] == ["reels"]    # reels está em alta na base falsa


def test_referencias_excluem_posts_fora_do_tema():
    base = base_falsa()
    base.posts.loc[base.posts["post_id"] == "t1", ["tema_principal", "lift_perfil"]] = ["outro", 999]
    refs = search_posts(base, "instagram", formato="reels", k=10)
    assert "t1" not in {r.post_id for r in refs}


def test_cenas_como_dicionario_sao_aceitas_e_falha_total_fica_registrada():
    c = Creative(**criativo(corpo=[{"0-3s": "gancho"}, {"3-15s": "erro 1"}, {"15-30s": "erro 2"}]))
    assert c.corpo == ["0-3s: gancho", "3-15s: erro 1", "15-30s: erro 2"]
    from src.shared.llm_client import InvalidLLMOutput
    fake = FakeLLMClient({"criativo": [InvalidLLMOutput("JSON quebrado")]})
    saida = run_agent(AgentInput(mode="gerar_criativo", query="x"), base=base_falsa(), client=fake, registro=None)
    assert saida.creatives == [] and saida.erros and "reels" in saida.erros[0]


def test_cena_com_tempo_e_texto_vira_um_item_so():
    c = Creative(**criativo(corpo=[{"duracao_s": 3, "texto": "gancho"}, {"duracao_s": 5, "texto": "erro 1"},
                                   {"tempo": "8-12s", "fala": "erro 2"}]))
    assert c.corpo == ["3s: gancho", "5s: erro 1", "8-12s: erro 2"]


def test_verificador_barra_o_que_o_impulso_nao_oferece():
    c = Creative(**criativo(corpo=["0-3s: gancho", "3-10s: Com o Impulso, pagamento instantâneo", "10-20s: dinheiro na conta"]))
    ok, falhas = conferir(c, {"t1"}, LIMIARES)
    assert ok["fiel_a_oferta"] is False and any("programa de educação" in f for f in falhas)


def test_cenas_num_unico_objeto_com_tempos_viram_itens_separados():
    from src.agent.contrato import _como_textos
    corpo = _como_textos({"0-3s": "abre", "3-8s": "mostra", "8-13s": "explica"})
    assert corpo == ["0-3s: abre", "3-8s: mostra", "8-13s: explica"]
    assert _como_textos([{"Cena 1": "a", "Cena 2": "b"}]) == ["Cena 1: a", "Cena 2: b"]
    assert len(_como_textos([{"duracao_s": 3, "texto": "x"}])) == 1      # uma cena descrita por campos continua um item


def test_juiz_fora_do_contrato_nao_derruba_a_geracao():
    from src.evaluation.judge import avaliar_com_seguranca
    from src.shared.llm_client import InvalidLLMOutput

    class JuizQuebrado:
        chamadas = 0

        def evaluate(self, *a, **k):
            JuizQuebrado.chamadas += 1
            raise InvalidLLMOutput("evidencias vazias")

    r = avaliar_com_seguranca(JuizQuebrado(), "texto")
    assert r["aprovado"] is False and "indisponível" in r["erro"] and JuizQuebrado.chamadas == 2


def test_texto_de_tela_dentro_da_cena_vira_parentese_legivel():
    from src.agent.contrato import _como_textos
    assert _como_textos([{"0-3s": "Você no balcão", "texto_tela": "Calcule sem dor"}]) == \
        ["0-3s: Você no balcão (na tela: “Calcule sem dor”)"]


def test_sem_caso_concreto_a_conferencia_reprova_e_explica():
    from src.agent.contrato import Creative
    from src.agent.verificador import conferir
    from src.evaluation.thresholds import load_thresholds
    lim = load_thresholds(ROOT / "config" / "limiares.yaml") if "ROOT" in globals() else None
    generico = Creative.model_validate(criativo(caso="", corpo=["0-3s: separe as contas", "3-10s: defina metas",
                                                                "10-20s: planeje o estoque"]))
    ok, falhas = conferir(generico, {"t1"}, lim or _limiares())
    assert not ok["caso_concreto"] and any("caso concreto" in f for f in falhas)


def _limiares():
    from pathlib import Path
    from src.evaluation.thresholds import load_thresholds
    return load_thresholds(Path(__file__).resolve().parents[2] / "config" / "limiares.yaml")


def test_conta_ensinada_na_peca_reprova_mesmo_com_caso_concreto():
    from src.agent.contrato import Creative
    from src.agent.verificador import conferir
    peca = Creative.model_validate(criativo(corpo=["0-3s: Ana na padaria", "3-10s: Defina o preço: custo + 30%",
                                                   "10-20s: anote cada venda no caderno"]))
    ok, falhas = conferir(peca, {"t1"}, _limiares())
    assert not ok["sem_contas"] and any("contas e fórmulas" in f for f in falhas)
    limpa = Creative.model_validate(criativo())
    assert conferir(limpa, {"t1"}, _limiares())[0]["sem_contas"]


def _juiz(**notas) -> dict:
    """Resposta do juiz com nota 9 em tudo, menos nos critérios passados."""
    import yaml
    nomes = [c["nome"] for c in yaml.safe_load(open("src/evaluation/rubric_criativo.yaml", encoding="utf-8"))["criterios"]]
    return {"criterios": [{"nome": n, "nota": notas.get(n, 9), "justificativa": f"avaliação de {n}", "evidencias": ["trecho"]}
                          for n in nomes], "resumo": "ok"}


def test_retorno_do_juiz_gera_reescrita_e_fica_a_versao_melhor(tmp_path):
    melhor = criativo(caso="Dona de padaria anota o troco num caderno às 18h e descobre que perdia R$ 200 por semana")
    fake = FakeLLMClient({"criativo": [criativo(), melhor], "judge": [_juiz(profundidade=4), _juiz(profundidade=8)]})
    saida = run_agent(AgentInput(mode="gerar_criativo", query="caixa da padaria", segment="alimentacao", usar_juiz=True),
                      base=base_falsa(), client=fake, registro=tmp_path / "runs.jsonl")
    c = saida.creatives[0]
    assert c.melhoria_juiz["antes"] < c.melhoria_juiz["depois"] and c.melhoria_juiz["mantida"] == "reescrita 1"
    assert c.criativo.caso == melhor["caso"]
    reescrita = [p for p in fake.prompts if p["schema"] == "criativo"][1]["prompt"]
    assert "avaliador independente" in reescrita and "profundidade" in reescrita        # o retorno do juiz chegou ao gerador
    assert '"melhoria"' in (tmp_path / "runs.jsonl").read_text(encoding="utf-8")       # antes e depois ficam registrados


def test_reescrita_pior_que_a_original_e_descartada():
    fake = FakeLLMClient({"criativo": [criativo(), criativo(titulo="Outra versão")],
                          "judge": [_juiz(profundidade=6), _juiz(profundidade=3, concretude=4)]})
    saida = run_agent(AgentInput(mode="gerar_criativo", query="caixa", segment="alimentacao", usar_juiz=True),
                      base=base_falsa(), client=fake, registro=None)
    c = saida.creatives[0]
    assert c.melhoria_juiz["mantida"] == "original" and c.criativo.titulo == "3 erros no caixa"


def test_juiz_satisfeito_nao_gasta_reescrita():
    fake = FakeLLMClient({"criativo": [criativo()], "judge": [_juiz()]})
    saida = run_agent(AgentInput(mode="gerar_criativo", query="caixa", segment="alimentacao", usar_juiz=True),
                      base=base_falsa(), client=fake, registro=None)
    assert saida.creatives[0].melhoria_juiz is None
    assert len([p for p in fake.prompts if p["schema"] == "criativo"]) == 1


def test_medicao_resume_antes_e_depois():
    import importlib.util
    spec = importlib.util.spec_from_file_location("medir_juiz", "scripts/medir_juiz.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    linhas = [{"juiz": [{"nota": 8.5, "melhoria": {"antes": 7.0, "depois": 8.5, "mantida": "reescrita 1",
                                                     "criterios_antes": {"profundidade": 4},
                                                     "rodadas": [{"nota": 8.5, "criterios": {"profundidade": 8}}]}}]},
              {"juiz": [{"nota": 9.0, "melhoria": None}]}]
    r = m.resumir(linhas)
    assert r["precisaram_de_reescrita"] == 1 and r["nota_media_depois"] == 8.5
    assert r["variacao_por_criterio"]["profundidade"] == 4


def test_cota_estourada_na_reescrita_mantem_a_original():
    erro = RuntimeError("Groq request failed (429): rate_limit_exceeded")
    fake = FakeLLMClient({"criativo": [criativo(), criativo()], "judge": [_juiz(profundidade=5), erro]})
    saida = run_agent(AgentInput(mode="gerar_criativo", query="caixa", segment="alimentacao", usar_juiz=True),
                      base=base_falsa(), client=fake, registro=None)
    c = saida.creatives[0]
    assert c.melhoria_juiz["mantida"] == "original" and c.juiz["media_ponderada"] is not None   # nota da original preservada
    assert "avaliador" in c.melhoria_juiz["rodadas"][0]["descartada"]


def test_reescrita_que_cria_outro_criterio_fraco_e_descartada():
    # profundidade melhora (5 → 9) e a média sobe, mas "segue o que engaja" cai de 9 para 5: fica a original
    fake = FakeLLMClient({"criativo": [criativo(), criativo(titulo="Outra")],
                          "judge": [_juiz(profundidade=5), _juiz(profundidade=10, concretude=10, aderencia_aos_padroes=5)]})
    saida = run_agent(AgentInput(mode="gerar_criativo", query="caixa", segment="alimentacao", usar_juiz=True),
                      base=base_falsa(), client=fake, registro=None)
    c = saida.creatives[0]
    assert c.melhoria_juiz["mantida"] == "original" and "aderencia_aos_padroes" in c.melhoria_juiz["rodadas"][0]["descartada"]


def test_peca_para_a_stone_usa_a_oferta_da_marca():
    fake = FakeLLMClient({"criativo": [criativo()]})
    run_agent(AgentInput(mode="gerar_criativo", query="vender pelo WhatsApp", conta="stone"), base=base_falsa(), client=fake, registro=None)
    chamada = [p for p in fake.prompts if p["schema"] == "criativo"][0]
    assert "a Stone, marca de maquininha" in chamada["system"] and "Nunca cite taxa" in chamada["system"]
    assert "link de pagamento" in chamada["prompt"]                       # oferta da Stone no lugar da do Impulso
    assert "mentoria profissional" not in chamada["prompt"]


def test_peca_do_impulso_continua_com_a_oferta_do_programa():
    fake = FakeLLMClient({"criativo": [criativo()]})
    run_agent(AgentInput(mode="gerar_criativo", query="organizar o caixa"), base=base_falsa(), client=fake, registro=None)
    chamada = [p for p in fake.prompts if p["schema"] == "criativo"][0]
    assert "Impulso Stone é um PROGRAMA" in chamada["system"] and "mentoria profissional" in chamada["prompt"]
