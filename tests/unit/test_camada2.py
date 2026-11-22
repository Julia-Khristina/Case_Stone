"""Camada 2 sem rede: protocolo de trechos, contrato do rótulo, lote com resposta incompleta e efeito na autenticidade."""
from __future__ import annotations

import json

import pandas as pd
import pytest
from pydantic import ValidationError

from src.analysis import camada2
from src.analysis.camada2 import AnalisadorVisual, RotuloVisual, partes_video, segundos, trechos
from src.analysis.scorecard import calcular

ROTULO = {"quem_aparece": "dono_do_negocio", "rosto_nos_3s": True, "fala_nos_3s": True, "texto_na_tela_inicio": False,
          "gancho_visual": "rosto_falando", "cenario": "negocio_real", "producao": "caseira", "legendas_queimadas": True,
          "cta_no_final": "falado", "mostra_ferramenta": False, "tom_de_voz": "conversa_informal", "musica_fundo": True, "tipo_musica": "instrumental_calma", "volume_musica": "baixo_sob_a_fala", "tom_fala": "calmo_acolhedor", "ritmo_fala": "medio", "qualidade_audio": "limpo", "efeitos_sonoros": False,
          "resumo": "Dona da padaria mostra o balcão", "fala_inicial": "Oi, gente"}


def test_mesmo_protocolo_para_qualquer_duracao():
    assert trechos(10) is None                                         # curto: vai inteiro
    assert trechos(60) == [(0, 5), (28, 33), (55, 60)]                 # Short ou Reels
    assert trechos(1200) == [(0, 5), (598, 603), (1195, 1200)]         # vídeo longo
    assert segundos("12.5s") == 12.5 and segundos(None) == 0.0


def test_partes_do_video_usam_o_mesmo_link_em_tres_trechos():
    from google.genai import types
    partes, descr = partes_video(types, "https://youtu.be/x", 600)
    assert [(p.video_metadata.start_offset, p.video_metadata.end_offset) for p in partes] == \
        [("0s", "5s"), ("298s", "303s"), ("595s", "600s")]
    assert all(p.file_data.file_uri == "https://youtu.be/x" for p in partes) and "meio" in descr
    inteiro, _ = partes_video(types, "https://youtu.be/s", 12)
    assert len(inteiro) == 1 and inteiro[0].video_metadata is None


def test_rotulo_visual_aceita_so_valores_da_lista():
    assert RotuloVisual.model_validate(ROTULO).cenario == "negocio_real"
    with pytest.raises(ValidationError):
        RotuloVisual.model_validate({**ROTULO, "cenario": "praia"})


def test_lote_aproveita_os_rotulos_certos_e_deixa_pendentes_os_outros(tmp_path, monkeypatch):
    monkeypatch.setattr(camada2, "CACHE", tmp_path)
    analisador = AnalisadorVisual.__new__(AnalisadorVisual)          # sem cliente real: mídia e modelo substituídos
    analisador.pedidos, analisador.tokens, analisador.pausa_s = 0, 0, 0
    analisador.partes_do_post = lambda post, enviados: (["<mídia>"], "imagem do Instagram")
    resposta = {"posts": [{**ROTULO, "post_id": "1"}, {**ROTULO, "post_id": "2", "cenario": "praia"}]}
    analisador._gerar = lambda conteudo: (resposta, "gemini-teste")
    analisador.cliente = None
    posts = [{"post_id": p, "plataforma": "instagram", "tipo": "imagem", "legenda": "x"} for p in ("1", "2", "3")]
    prontos, erros = analisador.analisar_lote(posts)
    assert [r["post_id"] for r in prontos] == ["1"] and prontos[0]["posts_no_pedido"] == 3
    assert set(erros) == {"2", "3"} and "fora do formato" in erros["2"]
    # o post 1 fica no cache: na próxima execução não vai de novo ao modelo
    analisador._gerar = lambda conteudo: pytest.fail("chamou o modelo para um post já rotulado")
    prontos2, _ = analisador.analisar_lote(posts[:1])
    assert prontos2[0]["post_id"] == "1" and json.loads(next(tmp_path.iterdir()).read_text(encoding="utf-8"))["modelo"]


def test_autenticidade_usa_o_video_quando_ha_posts_vistos():
    linhas = []
    for perfil, quem in (("a", "dono_do_negocio"), ("b", "ator_ou_modelo")):
        for _ in range(4):
            linhas.append({"plataforma": "instagram", "perfil_id": perfil, "username": perfil, "faixa": "micro",
                           "seguidores": 5000, "elegivel": True, "er": 0.05, "comment_ratio": 0.1, "janela": "momento",
                           "tema_principal": "vendas", "mensagem_generica": False, "patrocinado": False,
                           "quem_aparece": quem, "cenario": "estudio"})
    lista = pd.DataFrame([{"plataforma": "instagram", "perfil": p, "nome": p, "tipo": "transversal", "segmento": "vendas",
                           "parceiro_atual": "nao"} for p in ("a", "b")])
    t = calcular(pd.DataFrame(linhas), lista, []).set_index("perfil")
    assert (t["autenticidade_fonte"] == "video").all()
    assert t.loc["a", "autenticidade"] > t.loc["b", "autenticidade"]
