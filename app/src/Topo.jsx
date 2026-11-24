import { useEffect, useState } from "react";
import { api } from "./api.js";
import { usePerfilLocal } from "./Configuracoes.jsx";

/* Barra do topo: busca de verdade (filtra a página), sino = peças pra revisar, avatar = configurações. */
export default function BarraTopo({ busca, setBusca, placeholder }) {
  const [perfil] = usePerfilLocal();
  const [revisar, setRevisar] = useState(0);
  useEffect(() => {
    api.pecas().then((l) => setRevisar(l.filter((p) => p.status === "revisar" || p.status === "ajuste").length)).catch(() => {});
  }, []);
  const iniciais = (perfil.nome || "").trim().split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
  return (
    <div className="barra-topo">
      <label className="busca">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></svg>
        <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder={placeholder} aria-label={placeholder} />
        {busca && <button type="button" className="busca-limpar" onClick={() => setBusca("")} aria-label="Limpar busca">×</button>}
      </label>
      <span className="topo-divisor" aria-hidden="true" />
      <a className="sino" href="#/pecas" title={revisar ? `${revisar} ${revisar === 1 ? "peça" : "peças"} pra revisar` : "Nada pra revisar"}
        aria-label={`${revisar} peças pra revisar`}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15zM10 20.5a2.2 2.2 0 0 0 4 0" /></svg>
        {revisar > 0 && <i />}
      </a>
      <a className="topo-avatar" href="#/configuracoes" title="Configurações">{iniciais || "?"}</a>
    </div>
  );
}

// texto contém a busca, sem diferenciar acento nem maiúscula ("13º" vira "13o")
const sem = (t) => String(t || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
// sinônimos: o que a pessoa digita → como o termo aparece na agenda e nas peças (só nesse sentido)
const SINONIMOS = {
  "decimo": ["13o"], "13 salario": ["13o"], "13o": ["decimo terceiro"],
  "imposto": ["das do mei", "dasn"], "guia do mei": ["das do mei"], "boleto do mei": ["das do mei"],
  "declaracao": ["dasn"], "zap": ["whatsapp"], "video": ["reels", "short"],
  "promocao": ["liquidacao", "oferta", "black friday", "cyber monday"],
  "desconto": ["liquidacao", "oferta", "black friday", "cyber monday"],
};
const termos = (busca) => {
  const q = sem(busca.trim());
  return [q, ...Object.entries(SINONIMOS).filter(([k]) => q.includes(k)).flatMap(([, v]) => v)];
};
export const casa = (busca, ...campos) => {
  if (!busca.trim()) return true;
  const ts = termos(busca);
  return campos.some((c) => { const t = sem(c); return ts.some((q) => t.includes(q)); });
};
