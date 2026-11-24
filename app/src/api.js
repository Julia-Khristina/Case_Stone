// Cliente da API do BoaPauta (FastAPI). Tudo vem da base real e do agente; nada é simulado no front.
// Cabeçalhos: senha de acesso (se o servidor pedir) e o nome de quem usa, que vai para o histórico das peças.
function cabecalhos() {
  let perfil = {};
  try { perfil = JSON.parse(localStorage.getItem("boapauta.perfil")) || {}; } catch {}
  const h = { "Content-Type": "application/json" };
  if (perfil.token) h["X-BoaPauta-Token"] = perfil.token;
  if (perfil.nome) h["X-BoaPauta-Quem"] = encodeURIComponent(perfil.nome);
  return h;
}

async function pedir(caminho, opcoes = {}) {
  const r = await fetch(caminho, {
    headers: cabecalhos(),
    ...opcoes,
    body: opcoes.body ? JSON.stringify(opcoes.body) : undefined,
  });
  if (!r.ok) {
    let msg = `${r.status}`;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {}
    throw new Error(msg);
  }
  return r.json();
}

const qs = (o) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => v !== undefined && v !== null && v !== "" && p.set(k, v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

// Eventos ao vivo do agente (text/event-stream via POST): chama aoEvento(tipo, dados) a cada etapa.
async function aoVivo(caminho, corpo, aoEvento) {
  const r = await fetch(caminho, { method: "POST", headers: cabecalhos(), body: JSON.stringify(corpo) });
  if (!r.ok) {
    let msg = `${r.status}`;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new Error(msg);
  }
  const leitor = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await leitor.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const bloco = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const tipo = (bloco.match(/^event: (.*)$/m) || [])[1];
      const dados = (bloco.match(/^data: (.*)$/m) || [])[1];
      if (tipo) aoEvento(tipo, dados ? JSON.parse(dados) : {});
    }
  }
}

export const api = {
  criarAoVivo: (corpo, aoEvento) => aoVivo("/api/pecas/ao-vivo", corpo, aoEvento),
  ajusteAoVivo: (id, motivo, aoEvento) => aoVivo(`/api/pecas/${id}/ajuste/ao-vivo`, { motivo, categoria: "" }, aoEvento),
  panorama: (segmento) => pedir(`/api/panorama${qs({ segmento })}`),
  segmentos: () => pedir("/api/segmentos"),
  acesso: () => pedir("/api/acesso"),
  radar: () => pedir("/api/radar"),
  metricasAgente: () => pedir("/api/agente/metricas"),
  exemplos: (a, segmento) =>
    pedir(`/api/exemplos${qs({ plataforma: a.plataforma, caracteristica: a.caracteristica, valor: a.valor, segmento })}`),
  post: (id) => pedir(`/api/posts/${id}`),
  proposta: (corpo) => pedir("/api/proposta", { method: "POST", body: corpo }),
  criarPeca: (corpo) => pedir("/api/pecas", { method: "POST", body: corpo }),
  pecas: () => pedir("/api/pecas"),
  peca: (id) => pedir(`/api/pecas/${id}`),
  aprovar: (id) => pedir(`/api/pecas/${id}/aprovar`, { method: "POST" }),
  ajuste: (id, motivo, categoria) => pedir(`/api/pecas/${id}/ajuste`, { method: "POST", body: { motivo, categoria } }),
  agenda: (inicio, segmento, dias = 14) => pedir(`/api/agenda${qs({ inicio, segmento, dias })}`),
  criadores: (o = {}) => pedir(`/api/criadores${qs(o)}`),
  criador: (plataforma, perfil) => pedir(`/api/criadores/${plataforma}/${encodeURIComponent(perfil)}`),
  convidar: (c) => pedir("/api/convites", { method: "POST", body: { plataforma: c.plataforma, perfil: c.perfil, nome: c.nome, nota: c.nota } }),
  convites: () => pedir("/api/convites"),
  slidesUrl: (id) => `/api/pecas/${id}/slides.zip`,
  slides: (id) => pedir(`/api/pecas/${id}/slides`),
  semanaGuia: (inicio) => pedir(`/api/guia/semana${qs({ inicio })}`),
  gerarGuia: (inicio) => pedir("/api/guia", { method: "POST", body: { inicio } }),
  guias: () => pedir("/api/guia"),
  guiaUrl: (id) => `/api/guia/${id}.html`,
};
