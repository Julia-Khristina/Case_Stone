"""Radar de oportunidades (src/analysis/radar.py): leitura do feed, filtro barato e travas depois da IA."""
from __future__ import annotations

from datetime import date

from src.analysis import radar

RSS = """<rss><channel>
<item><title>Comitê Gestor do Simples Nacional publica novas regras para o MEI</title><link>https://gov.br/a</link>
<pubDate>Tue, 24 Nov 2026 19:08:53 +0000</pubDate><description><![CDATA[<p>As regras valem a partir de 1º de dezembro.</p>]]></description></item>
<item><title>Receita apreende ouro na aduana</title><link>https://gov.br/b</link><dc:date>2026-11-20T10:00:00Z</dc:date>
<description>Operação de fraude em exportação.</description></item>
<item><title>Sem data</title><link>https://gov.br/c</link></item>
<item><title>Notícia antiga sobre o MEI</title><link>https://gov.br/d</link><pubDate>Mon, 01 Sep 2026 10:00:00 +0000</pubDate></item>
</channel></rss>"""


def test_feed_exige_link_e_data_e_limpa_html():
    itens = radar.ler_feed(RSS, "Receita")
    assert [i["link"] for i in itens] == ["https://gov.br/a", "https://gov.br/b", "https://gov.br/d"]   # sem data: fora
    assert itens[0]["resumo"] == "As regras valem a partir de 1º de dezembro."


def test_candidatos_respeitam_validade():
    itens = radar.candidatos(radar.ler_feed(RSS, "Receita"), date(2026, 11, 25))
    assert "https://gov.br/d" not in [i["link"] for i in itens]                     # mais de 30 dias


def test_data_precisa_estar_na_fonte():
    assert radar.data_na_fonte("2026-12-01", "As regras valem a partir de 1º de dezembro.")
    assert radar.data_na_fonte("2026-12-16", "começa em 16/12")
    assert not radar.data_na_fonte("2026-12-20", "As regras valem a partir de 1º de dezembro.")


def test_travas_descartam_data_inventada_alerta_fora_e_concorrente():
    fontes = radar.ler_feed(RSS, "Receita")[:2]
    base = {"pilar": "Gestão e vendas", "tema_post": "t", "por_que_importa": "p", "o_que_muda": "m", "titulo_curto": "x"}
    ex = [radar.ItemRadar(id="0", tipo="regra_nova", data_chave="2026-12-01", **base),
          radar.ItemRadar(id="1", tipo="alerta", **base)]
    aceitos, fora = radar.aplicar_travas(fontes, ex, ["PagBank"])
    assert len(aceitos) == 1 and aceitos[0]["link"] == "https://gov.br/a" and aceitos[0]["fonte"] == "Receita"
    assert fora[0]["motivo"] == "alerta de crime fora do pequeno negócio"
    ex2 = [radar.ItemRadar(id="0", tipo="regra_nova", data_chave="2026-12-20", **base)]
    assert radar.aplicar_travas(fontes, ex2, [])[1][0]["motivo"].startswith("data 2026-12-20")
    ex3 = [radar.ItemRadar(id="0", tipo="ferramenta", **{**base, "tema_post": "Use o PagBank"})]
    assert radar.aplicar_travas(fontes, ex3, ["PagBank"])[1][0]["motivo"] == "cita concorrente da Stone"
    ex4 = [radar.ItemRadar(id="0", tipo="regra_nova", data_chave="2026-11-24", **base)]   # data da notícia: só some a data
    a4, _ = radar.aplicar_travas(fontes, ex4, [])
    assert a4[0]["data_chave"] is None
