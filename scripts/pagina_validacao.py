"""Página para preencher a validação humana no navegador, sem editar CSV na mão.

    python scripts/pagina_validacao.py        → data/validacao/validacao.html (abra no navegador)

Duas abas: "Rótulos dos posts" (data/validacao/rotulagem_manual.csv, camada 3) e "Notas das peças"
(data/validacao/notas_humanas.csv, calibração do avaliador; gere antes com scripts/calibrar_juiz.py preparar).
O progresso fica salvo no navegador. No fim, "Baixar CSV" gera a planilha preenchida: salve-a por cima da original
em data/validacao/ e rode scripts/validar_rotulos.py e scripts/calibrar_juiz.py comparar.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PASTA = ROOT / "data" / "validacao"

OPCOES = {
    "tema_principal": ["vendas", "financas", "marketing", "atendimento", "gestao", "motivacao", "ferramentas",
                       "historia_de_empreendedor", "receita_ou_tecnica", "outro"],
    "tipo_hook": ["pergunta", "promessa", "dor", "numero", "polemica", "curiosidade", "historia", "nenhum"],
    "tipo_cta": ["comentar", "salvar", "compartilhar", "link", "dm", "seguir", "comprar", "nenhum"],
    "convite_participacao": ["sim", "nao"], "mensagem_generica": ["sim", "nao"], "patrocinado": ["sim", "nao"],
    "humano_aprovaria": ["sim", "nao"],
}

HTML = r"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Validação humana</title>
<style>
:root{--sher:#004132;--lima:#C7F93C;--fundo:#f3f4f0;--m:#5b6b61}
body{margin:0;background:var(--fundo);font:15px/1.45 system-ui,Arial,sans-serif;color:#13231c}
header{background:var(--sher);color:#fff;padding:20px 24px;position:sticky;top:0;z-index:2}
header h1{margin:0 0 4px;font-size:22px}header p{margin:0;color:#cfe3da;font-size:13.5px}
nav{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}nav button,.baixar{border:0;border-radius:999px;padding:8px 14px;font:600 14px system-ui;cursor:pointer}
nav button{background:rgba(255,255,255,.14);color:#fff}nav button.on{background:var(--lima);color:var(--sher)}
.baixar{background:#fff;color:var(--sher)}main{max-width:900px;margin:0 auto;padding:18px 16px 60px}
.barra{height:8px;background:rgba(255,255,255,.2);border-radius:999px;margin-top:10px;overflow:hidden}.barra i{display:block;height:100%;background:var(--lima)}
.item{background:#fff;border-radius:16px;padding:16px 18px;margin:0 0 12px;box-shadow:0 3px 12px rgba(0,40,30,.06)}
.item.feito{border-left:6px solid var(--lima)}.item h3{margin:0 0 4px;font-size:16px}.item a{color:var(--sher)}
.texto{white-space:pre-wrap;font-size:13.5px;color:#34443b;max-height:9em;overflow:auto;background:#f6f7f4;border-radius:10px;padding:8px 10px;margin:8px 0}
.campos{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}
label{display:grid;gap:3px;font-size:12.5px;color:var(--m)}select,input{font:14px system-ui;padding:6px 8px;border:1px solid #cfd8d0;border-radius:8px;background:#fff}
.vazio{color:var(--m);padding:30px;text-align:center}
.cab{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.fora{border:1px solid #e0b4a0;background:#fff;color:#9a3a12;border-radius:999px;padding:5px 12px;font:600 12.5px system-ui;cursor:pointer;white-space:nowrap}
.item.excluido{opacity:.55;border-left:6px solid #e8590c}.item.excluido .campos{display:none}.item.excluido .fora{background:#e8590c;color:#fff;border-color:#e8590c}
</style></head><body>
<header><h1>Validação humana</h1><p>Responda sem olhar a resposta da IA. O progresso fica salvo neste navegador.</p>
<nav id="abas"></nav><div class="barra"><i id="prog"></i></div></header>
<main id="lista"></main>
<script>
const DADOS = __DADOS__;
const OPCOES = __OPCOES__;
let aba = Object.keys(DADOS).find(k => DADOS[k].linhas.length) || Object.keys(DADOS)[0];
const chave = k => "validacao." + k;
const carregar = k => { try { return JSON.parse(localStorage.getItem(chave(k))) || {}; } catch { return {}; } };
const salvar = (k, v) => { try { localStorage.setItem(chave(k), JSON.stringify(v)); } catch {} };
function valor(k, linha, col) { const r = carregar(k)[linha[DADOS[k].id]]; return (r && r[col] != null) ? r[col] : (linha[col] || ""); }
function excluido(k, linha) { return DADOS[k].exclui && String(valor(k, linha, "fora_do_tema")).toLowerCase() === "sim"; }
function feito(k, linha) { return excluido(k, linha) || DADOS[k].campos.every(c => String(valor(k, linha, c)).trim() !== ""); }
function render() {
  const d = DADOS[aba];
  document.getElementById("abas").innerHTML = Object.entries(DADOS).map(([k, v]) =>
    `<button class="${k === aba ? "on" : ""}" data-k="${k}">${v.nome} (${v.linhas.filter(l => feito(k, l)).length}/${v.linhas.length})</button>`).join("")
    + `<button class="baixar" id="baixar">Baixar CSV</button>`;
  document.querySelectorAll("#abas [data-k]").forEach(b => b.onclick = () => { aba = b.dataset.k; render(); scrollTo(0, 0); });
  document.getElementById("baixar").onclick = baixar;
  const prontos = d.linhas.filter(l => feito(aba, l)).length;
  document.getElementById("prog").style.width = (d.linhas.length ? prontos / d.linhas.length * 100 : 0) + "%";
  if (!d.linhas.length) { document.getElementById("lista").innerHTML = `<p class="vazio">${d.vazio}</p>`; return; }
  document.getElementById("lista").innerHTML = d.linhas.map((l, i) => `
    <article class="item ${feito(aba, l) ? "feito" : ""} ${excluido(aba, l) ? "excluido" : ""}" data-i="${i}">
      <div class="cab"><h3>${i + 1}. ${esc(l[d.titulo] || "(sem título)")}</h3>
        ${d.exclui ? `<button class="fora" type="button" title="Tira o post desta validação e da análise">${excluido(aba, l) ? "Excluído: desfazer" : "Fora do tema"}</button>` : ""}</div>
      ${l.link ? `<a href="${esc(l.link)}" target="_blank" rel="noreferrer">Abrir o post</a>` : ""}
      <div class="texto">${esc(l[d.texto] || "")}</div>
      <div class="campos">${d.campos.map(c => campo(aba, l, c)).join("")}</div>
    </article>`).join("");
  document.querySelectorAll("#lista .fora").forEach(b => b.onclick = () => {
    const l = d.linhas[+b.closest(".item").dataset.i], todos = carregar(aba);
    todos[l[d.id]] = { ...(todos[l[d.id]] || {}), fora_do_tema: excluido(aba, l) ? "" : "sim" }; salvar(aba, todos);
    const y = scrollY; render(); scrollTo(0, y);
  });
  document.querySelectorAll("#lista select, #lista input").forEach(el => el.onchange = () => {
    const l = d.linhas[+el.closest(".item").dataset.i], todos = carregar(aba);
    todos[l[d.id]] = { ...(todos[l[d.id]] || {}), [el.name]: el.value }; salvar(aba, todos);
    el.closest(".item").classList.toggle("feito", feito(aba, l));
    const n = d.linhas.filter(x => feito(aba, x)).length;
    document.getElementById("prog").style.width = n / d.linhas.length * 100 + "%";
    document.querySelector(`#abas [data-k="${aba}"]`).textContent = `${d.nome} (${n}/${d.linhas.length})`;
  });
}
function campo(k, l, c) {
  const v = valor(k, l, c), nome = c.replace(/^humano_/, "").replace(/_/g, " ");
  if (OPCOES[c]) return `<label>${nome}<select name="${c}"><option value=""></option>${OPCOES[c].map(o => `<option ${o === v ? "selected" : ""}>${o}</option>`).join("")}</select></label>`;
  return `<label>${nome} (0 a 10)<input name="${c}" type="number" min="0" max="10" step="0.5" value="${esc(v)}"></label>`;
}
function esc(t) { return String(t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]); }
function baixar() {
  const d = DADOS[aba];
  const csv = [d.colunas.join(","), ...d.linhas.map(l => d.colunas.map(c => {
    const v = String(d.campos.includes(c) || c === "fora_do_tema" ? valor(aba, l, c) : (l[c] ?? ""));
    return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v; }).join(","))].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
  a.download = d.arquivo; a.click();
}
render();
</script></body></html>"""


def _ler(nome: str) -> pd.DataFrame:
    p = PASTA / nome
    return pd.read_csv(p, dtype=str, encoding="utf-8-sig").fillna("") if p.exists() else pd.DataFrame()


def montar() -> str:
    rot, notas = _ler("rotulagem_manual.csv"), _ler("notas_humanas.csv")
    dados = {
        "rotulos": {"nome": "Rótulos dos posts", "arquivo": "rotulagem_manual.csv", "id": "post_id", "titulo": "titulo",
                    "texto": "texto", "exclui": True,
                    "colunas": list(rot.columns) + ([] if "fora_do_tema" in rot.columns or rot.empty else ["fora_do_tema"]),
                    "linhas": rot.to_dict("records"),
                    "campos": [c for c in OPCOES if c in rot.columns],
                    "vazio": "Planilha não encontrada: rode scripts/preparar_validacao.py."},
        "notas": {"nome": "Notas das peças", "arquivo": "notas_humanas.csv", "id": "peca_id", "titulo": "titulo",
                  "texto": "texto", "colunas": list(notas.columns), "linhas": notas.to_dict("records"),
                  "campos": [c for c in notas.columns if c.startswith("humano_")],
                  "vazio": "Ainda não há peças avaliadas: rode scripts/calibrar_juiz.py preparar."},
    }
    return (HTML.replace("__DADOS__", json.dumps(dados, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__OPCOES__", json.dumps(OPCOES, ensure_ascii=False)))


def main() -> int:
    PASTA.mkdir(parents=True, exist_ok=True)
    saida = PASTA / "validacao.html"
    saida.write_text(montar(), encoding="utf-8")
    print(f"Abra no navegador: {saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
