"""Agente de descoberta de perfis, sem rede."""
from __future__ import annotations

import csv
import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path

from src.collection.discovery import avaliar, classificar_bio, contar_mencoes, extrair_mencoes, info_perfil, propor
from src.collection.http import HttpError
from src.evaluation.thresholds import Thresholds

AGORA = datetime(2026, 11, 22, tzinfo=timezone.utc)
LIMIARES = Thresholds({"descoberta_seguidores_min": 1000, "descoberta_posts_min": 30,
                       "descoberta_dias_sem_postar_max": 60, "janela_momento_dias": 90,
                       "descoberta_posts_min_janela": {"instagram": 6, "youtube": 4}})
SEIS_RECENTES = [f"2026-11-{d:02d}T10:00:00+0000" for d in (15, 10, 5, 1)] + ["2026-10-20T10:00:00+0000",
                                                                              "2026-10-01T10:00:00+0000"]


def test_extrai_mencoes_sem_email_e_sem_ponto_final():
    texto = "Collab com @Doces.da.Vila e @chefrut. Fale em contato@loja.com ou com @chefrut de novo!"
    assert extrair_mencoes(texto) == ["doces.da.vila", "chefrut"]


def test_conta_mencoes_ignorando_autocitacao_e_perfis_conhecidos():
    posts = [{"username": "stone", "legenda": "Parabéns @novaloja e @stone e @chefrut"},
             {"username": "sebrae", "legenda": "Olha a @novaloja"}]
    contagem = contar_mencoes(posts, ignorar={"chefrut"})
    assert set(contagem) == {"novaloja"}
    assert contagem["novaloja"]["n_mencoes"] == 2 and contagem["novaloja"]["mencionado_por"] == {"stone", "sebrae"}


def test_classifica_bio_por_regras():
    publico, segmento, motivo = classificar_bio("Ajudo MEI e pequenos negócios a precificar e vender mais 💰")
    assert publico and segmento == "financas" and "mei" in motivo
    assert classificar_bio("Confeitaria artesanal · encomendas pelo direct", "Doces da Vila")[1] == "alimentacao"
    # "meio" e "meia" não podem contar como MEI
    assert classificar_bio("Corredora, meia maratona e meio ambiente")[0] is False


def test_avaliacao_recusa_revendedor_perfil_parado_e_bio_fora_do_publico():
    bom = {"seguidores": 8000, "total_posts": 400, "ultimo_post": "2026-11-15T10:00:00+0000",
           "datas_recentes": SEIS_RECENTES, "publico_mpe": True}
    assert avaliar(bom, AGORA, LIMIARES) == (True, [])
    # postou há 7 dias, mas só 2 vezes nos últimos 90: não contribui o bastante para a análise
    esporadico = {**bom, "datas_recentes": ["2026-11-15T10:00:00+0000", "2026-07-01T10:00:00+0000"]}
    assert avaliar(esporadico, AGORA, LIMIARES) == (False, ["só 1 post em 90 dias (mínimo 6)"])
    passou, motivos = avaliar({**bom, "seguidores": 7, "ultimo_post": "2026-04-07T10:00:00+0000",
                               "publico_mpe": False}, AGORA, LIMIARES)
    assert not passou and "poucos seguidores" in motivos and "bio não fala com empreendedores" in motivos
    assert any(m.startswith("parado há") for m in motivos)


def test_propoe_ate_completar_cada_faixa():
    cands = [{"perfil": f"m{i}", "faixa": "micro", "n_mencoes": 10 - i, "seguidores": 5000, "status": "passou"}
             for i in range(4)] + [{"perfil": "x", "faixa": "medio", "n_mencoes": 1, "status": "recusado"}]
    ordem = {c["perfil"]: c["status"] for c in propor(cands, {"micro": 13}, alvo_por_faixa=15)}
    assert [ordem[f"m{i}"] for i in range(4)] == ["proposto", "proposto", "passou (faixa cheia)", "passou (faixa cheia)"]
    assert ordem["x"] == "recusado"


class FakeCollector:
    base_url, access_token, cache = "https://g", "tok", None

    def __init__(self, resposta):
        self.resposta = resposta

    def http(self, url, params, cache=None):
        if isinstance(self.resposta, Exception):
            raise self.resposta
        return self.resposta


def test_info_perfil_devolve_none_para_conta_pessoal_ou_inexistente():
    erro = HttpError(400, '{"error":{"message":"Invalid user id","code":110}}')
    assert info_perfil(FakeCollector(erro), "pessoal") is None
    ok = {"business_discovery": {"username": "Loja", "followers_count": 5000, "media_count": 90, "biography": "MEI",
                                 "media": {"data": [{"timestamp": "2026-11-20T10:00:00+0000"}]}}}
    info = info_perfil(FakeCollector(ok), "loja")
    assert info["perfil"] == "loja" and info["ultimo_post"].startswith("2026-11-20")


def _carregar_aprovar():
    caminho = Path(__file__).resolve().parents[2] / "scripts" / "aprovar_perfis.py"
    spec = importlib.util.spec_from_file_location("aprovar_perfis", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.aprovar


def test_aprovar_leva_so_os_marcados_com_origem_e_sem_duplicar(tmp_path):
    perfis = tmp_path / "perfis.csv"
    perfis.write_text("plataforma,perfil,origem,segmento,parceiro_atual,justificativa,data_entrada\n"
                      "instagram,chefrut,parceiro_stone,gastronomia,sim,x,2026-11-21\n", encoding="utf-8")
    cands = tmp_path / "candidatos.csv"
    with cands.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["aprovar", "perfil", "mencionado_por", "segmento_sugerido", "motivo",
                                          "seguidores", "faixa"])
        w.writeheader()
        w.writerow({"aprovar": "sim", "perfil": "novaloja", "mencionado_por": "@stone", "segmento_sugerido": "moda",
                    "motivo": "bio cita mei", "seguidores": "8000", "faixa": "micro"})
        w.writerow({"aprovar": "", "perfil": "outra", "mencionado_por": "@sebrae"})
        w.writerow({"aprovar": "Sim", "perfil": "ChefRut", "mencionado_por": "@stone"})
    assert _carregar_aprovar()(cands, perfis, hoje=date(2026, 11, 22)) == ["novaloja"]
    linhas = list(csv.DictReader(perfis.open(encoding="utf-8")))
    assert linhas[-1]["origem"] == "descoberta: mencionado por @stone" and linhas[-1]["data_entrada"] == "2026-11-22"


# ------------------------------------------------------------------ fonte YouTube
from src.collection.discovery import info_canal, instagram_no_texto  # noqa: E402


def test_acha_instagram_na_descricao_do_canal():
    descricao = ("Dicas para MEI toda semana!\nInsta: @Doces.Da.Vila\nhttps://www.instagram.com/lojadamaria/ "
                 "· veja também instagram.com/reel/abc e meu email contato@x.com")
    assert instagram_no_texto(descricao) == ["lojadamaria", "doces.da.vila"]


def test_canal_do_youtube_vira_info_avaliavel():
    canal = {"id": "UCabc", "snippet": {"title": "Canal MEI", "description": "Ajudo MEI a vender mais",
                                        "customUrl": "@CanalMEI"},
             "statistics": {"subscriberCount": "52000", "videoCount": "310"}}
    info = info_canal(canal, ["2026-11-18T12:00:00Z", "2026-11-04T12:00:00Z", "2026-10-21T12:00:00Z",
                              "2026-10-07T12:00:00Z"])
    assert info["perfil"] == "UCabc" and info["seguidores"] == 52000 and info["handle_youtube"] == "canalmei"
    info["publico_mpe"] = classificar_bio(info["bio"])[0]
    assert avaliar(info, AGORA, LIMIARES, "youtube") == (True, [])   # 4 vídeos em 90 dias; data com "Z" aceita
    escondido = info_canal({**canal, "statistics": {"hiddenSubscriberCount": True, "videoCount": "10"}}, [])
    assert escondido["seguidores"] is None


def test_aprovar_canal_do_youtube_mantem_maiusculas_do_id(tmp_path):
    perfis = tmp_path / "perfis.csv"
    perfis.write_text("plataforma,perfil,origem,segmento,parceiro_atual,justificativa,data_entrada\n", encoding="utf-8")
    cands = tmp_path / "c.csv"
    cands.write_text("aprovar,plataforma,perfil,mencionado_por\nsim,youtube,UCAbC123,busca: dicas para MEI\n"
                     "sim,youtube,UCAbC123,busca: repetida\n", encoding="utf-8-sig")
    assert _carregar_aprovar()(cands, perfis, hoje=date(2026, 11, 22)) == ["UCAbC123"]


def test_resposta_negativa_fica_no_cache_e_limite_e_reconhecido(tmp_path):
    from src.collection.discovery import limite_atingido
    from src.shared.cache import VersionedCache

    chamadas = []

    class Coletor(FakeCollector):
        cache = VersionedCache(tmp_path)

        def http(self, url, params, cache=None):
            chamadas.append(params["fields"])
            raise HttpError(400, '{"error":{"message":"Invalid user id","code":110}}')

    coletor = Coletor(None)
    assert info_perfil(coletor, "pessoal") is None and info_perfil(coletor, "Pessoal") is None
    assert len(chamadas) == 1                       # a segunda consulta veio do cache
    assert limite_atingido(HttpError(403, '{"error":{"message":"(#4) Application request limit reached","code":4,"type":"x"}}'))
    assert not limite_atingido(HttpError(400, '{"error":{"code":110,"message":"x"}}'))


def test_filtro_reconhece_setores_novos():
    for bio in ["Ajudo donos de mercadinhos a vender mais", "Sou barbeiro e vivo da barbearia",
                "A real do motorista de app: quanto entra e quanto sobra", "Artesã há 20 anos, ensino a viver de artesanato",
                "Dicas de faça e venda para quem quer renda"]:
        assert classificar_bio(bio)[0], bio
    assert classificar_bio("Eu sussurro no microfone, sons satisfatórios")[0] is False


def test_exclusoes_ficam_registradas_e_nao_aprovado_nao(tmp_path):
    perfis = tmp_path / "perfis.csv"
    perfis.write_text("plataforma,perfil,nome,origem,segmento,parceiro_atual,justificativa,data_entrada,tipo,nicho\n",
                      encoding="utf-8")
    cands = tmp_path / "c.csv"
    with cands.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["aprovar", "plataforma", "perfil", "nome", "observacao"])
        w.writeheader()
        w.writerow({"aprovar": "", "plataforma": "youtube", "perfil": "UCprimo", "nome": "Primo",
                    "observacao": "Excluído: finanças pessoais"})
        w.writerow({"aprovar": "", "plataforma": "youtube", "perfil": "UCpet", "nome": "Pet",
                    "observacao": "Não aprovado: já há um médio do setor"})
        w.writerow({"aprovar": "sim", "plataforma": "instagram", "perfil": "graces", "nome": "Graces",
                    "observacao": "Marca do setor (ferramenta de gestão): ..."})
    aprovar = _carregar_aprovar()
    assert aprovar(cands, perfis, hoje=date(2026, 11, 22)) == ["graces"]
    recusados = list(csv.DictReader((tmp_path / "perfis_recusados.csv").open(encoding="utf-8")))
    assert [r["perfil"] for r in recusados] == ["UCprimo"]
    assert list(csv.DictReader(perfis.open(encoding="utf-8")))[-1]["tipo"] == "marca"
    aprovar(cands, perfis, hoje=date(2026, 11, 23))                       # rodar de novo não duplica
    assert len(list(csv.DictReader((tmp_path / "perfis_recusados.csv").open(encoding="utf-8")))) == 1
