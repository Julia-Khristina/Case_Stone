import { useEffect, useState } from "react";
import { api } from "./api.js";
import Planejamento from "./Planejamento.jsx";
import Pecas from "./Pecas.jsx";
import Inicio from "./Inicio.jsx";
import Criadores, { Perfil } from "./Criadores.jsx";
import Configuracoes, { usePerfilLocal } from "./Configuracoes.jsx";

/* Organização pelo trabalho da equipe:
   Planejamento (o que postar e quando; criar e revisar no painel) · Peças (fila de trabalho e guia detalhado)
   · Insights (o que engaja) · Criadores (parcerias). Configurações fica no perfil. */

// Endereços antigos continuam funcionando
const REDIRECIONA = [[/^#\/?(inicio|agenda)?$/, "#/planejamento"], [/^#\/agenda\/peca\//, "#/planejamento/peca/"], [/^#\/achados/, "#/insights"]];

function useRota() {
  const ler = () => {
    let h = window.location.hash || "#/planejamento";
    if (!window.location.hash) window.history.replaceState(null, "", h);
    for (const [re, novo] of REDIRECIONA) if (re.test(h)) { h = h.replace(re, novo); window.history.replaceState(null, "", h); }
    return h.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  };
  const [rota, setRota] = useState(ler);
  useEffect(() => {
    const f = () => { setRota(ler()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return rota;
}

export const ir = (caminho) => (window.location.hash = `#/${caminho}`);

const ICONE = {
  planejamento: <path d="M4 6h16v14H4zM4 10.5h16M8.5 3.5v4M15.5 3.5v4M9 15l2 2 4-4" />,
  pecas: <path d="M4 5h7v7H4zM13 5h7v7h-7zM4 14h7v6H4zM13 14h7v6h-7z" />,
  insights: <path d="M5 20v-7M10 20V5M15 20v-9M20 20V8" />,
  criadores: <path d="M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5M16 4.3a3.5 3.5 0 0 1 0 6.4M18 14.8c1.9.6 3.1 2.4 3.5 5.2" />,
};
const MENU = [
  ["planejamento", "Planejamento", "o que postar e quando"],
  ["pecas", "Peças", "revisar e publicar"],
  ["insights", "Insights", "o que engaja"],
  ["criadores", "Criadores", "parcerias"],
];

export default function App() {
  const [pagina, ...resto] = useRota();
  const [perfil] = usePerfilLocal();
  const [revisar, setRevisar] = useState(0);
  useEffect(() => {
    api.pecas().then((l) => setRevisar(l.filter((p) => p.status === "revisar" || p.status === "ajuste").length)).catch(() => {});
  }, [pagina, resto.join("/")]);

  let conteudo;
  if (pagina === "pecas") conteudo = <Pecas />;
  else if (pagina === "insights") conteudo = <Inicio />;
  else if (pagina === "criadores" && resto.length === 2) conteudo = <Perfil plataforma={resto[0]} perfil={resto[1]} />;
  else if (pagina === "criadores") conteudo = <Criadores />;
  else if (pagina === "configuracoes") conteudo = <Configuracoes />;
  else conteudo = <Planejamento pecaId={resto[0] === "peca" ? resto[1] : null} />;

  const ativa = MENU.some(([id]) => id === pagina) ? pagina : pagina === "configuracoes" ? "" : "planejamento";
  const iniciais = (perfil.nome || "").trim().split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
  return (
    <div className="casca">
      <aside className="lateral">
        <a className="marca" href="#/planejamento">
          <span className="marca-nome">
            <svg className="marca-simbolo" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5v19M2.5 12h19M5.3 5.3l13.4 13.4M18.7 5.3 5.3 18.7" /></svg>
            <span>Boa<b>Pauta</b></span>
          </span>
          <small>para o Impulso Stone</small>
        </a>
        <nav>
          {MENU.map(([id, nome, dica]) => (
            <a key={id} href={`#/${id}`} className={ativa === id ? "ativa" : ""}>
              <svg viewBox="0 0 24 24" aria-hidden="true">{ICONE[id]}</svg>
              <span className="menu-texto"><b>{nome}</b><small>{dica}</small></span>
              {id === "pecas" && revisar > 0 && <i className="menu-badge" title={`${revisar} pra revisar`}>{revisar}</i>}
            </a>
          ))}
        </nav>
        <div className="lateral-rodape">
          <a className={`lateral-config ${pagina === "configuracoes" ? "ativo" : ""}`} href="#/configuracoes">
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></svg>
            <span>Configurações</span>
          </a>
          <a className="lateral-perfil" href="#/configuracoes" title="Seu nome fica só neste navegador">
            <span className="lateral-avatar">{iniciais || "?"}</span>
            <span>{perfil.nome || "Seu nome"}</span>
            <svg className="perfil-seta" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
          </a>
        </div>
      </aside>
      <main className="pagina">{conteudo}</main>
    </div>
  );
}
