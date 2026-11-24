import { useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import { STATUS, nomeFormato, nomeSegmento } from "./util.js";
import { casa } from "./Topo.jsx";

/* O único calendário do app: sugestões da agenda e peças criadas. Tocar abre o painel lateral. */
/* ---------- datas e janela do calendário ---------- */
export function hojeIso() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}
export function somarDias(iso, n) {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}
export function segundaDe(iso) {
  const d = new Date(iso + "T12:00:00");
  return somarDias(iso, -((d.getDay() + 6) % 7));
}
// "Mês" mostra a semana de referência e as 4 seguintes (cruza a virada do mês): semanas já passadas não ocupam a tela.
export function janelaDaVista(v) {
  return { inicio: segundaDe(v.ref), dias: v.tipo === "semana" ? 7 : 35 };
}

const DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
const ICONE_FORMATO = {
  reels: <path d="M8 5v14l11-7z" />,
  short: <path d="M8 5v14l11-7z" />,
  carrossel: <path d="M4 5h16v14H4zM4 15l5-5 4 4 3-3 4 4" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinejoin="round" />,
  stories: <path d="M7 3h10v18H7zM10 18h4" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinejoin="round" />,
};

export default function Calendario({ agenda, vista, setVista, onSugestao, onPeca, onNovo, busca = "" }) {
  const [segmentos, setSegmentos] = useState([]);
  useEffect(() => { api.segmentos().then(setSegmentos).catch(() => {}); }, []);
  const { inicio, dias: n } = janelaDaVista(vista);
  const dias = useMemo(() => Array.from({ length: n }, (_, i) => somarDias(inicio, i)), [inicio, n]);
  const hoje = hojeIso();
  const nomeMes = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("pt-BR", { month: "long" });
  const ano = dias[n - 1].slice(0, 4);
  const titulo = nomeMes(dias[0]) === nomeMes(dias[n - 1]) ? `${nomeMes(dias[0])} ${ano}` : `${nomeMes(dias[0])} – ${nomeMes(dias[n - 1])} ${ano}`;
  const andar = (k) => setVista({ ...vista, ref: somarDias(vista.ref, (vista.tipo === "semana" ? 7 : 28) * k) });
  const sug = Object.fromEntries((agenda?.sugestoes || []).map((s) => [s.data, s]));
  const pecas = {};
  (agenda?.pecas || []).forEach((p) => p.data_agenda && (pecas[p.data_agenda] = [...(pecas[p.data_agenda] || []), p]));
  const casaPeca = (p) => casa(busca, p.atual?.criativo?.titulo, p.objetivo, nomeFormato(p.formato), STATUS[p.status]?.rotulo, nomeSegmento(p.segmento));
  const casaSug = (s) => casa(busca, s.tema, s.rotulo, s.pilar, s.data_comemorativa, nomeFormato(s.formato), nomeSegmento(s.segmento));
  // quantos itens da tela casam com a busca (só o que aparece: peças e sugestões de dias futuros sem peça)
  const achados = !busca.trim() ? null : dias.reduce((n, d) => {
    const ps = pecas[d] || [];
    return n + ps.filter(casaPeca).length + (d >= hoje && !ps.length && sug[d] && casaSug(sug[d]) ? 1 : 0);
  }, 0);

  return (
    <div className={`cal cal-${vista.tipo}`}>
      <div className="cal-barra">
        <h2><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16v14H4zM4 10.5h16M8.5 3.5v4M15.5 3.5v4M9 15l2 2 4-4" /></svg>Calendário de conteúdo</h2>
        <div className="cal-nav">
          <button className="btn-icone p" onClick={() => andar(-1)} aria-label="Anterior">‹</button>
          <button className="btn-icone p" onClick={() => andar(1)} aria-label="Próximo">›</button>
          <span className="cal-titulo">{titulo}</span>
          {!agenda && <span className="cal-lendo"><span className="giro" /> lendo a agenda…</span>}
          {agenda && achados !== null && (
            <span className={`cal-achados ${achados ? "" : "nada"}`} role="status">
              {achados ? `${achados} ${achados === 1 ? "resultado" : "resultados"} nestas semanas`
                : <>Nada com “{busca.trim()}” nestas semanas.</>}
            </span>
          )}
        </div>
        <div className="seg-pilula">
          <button className={vista.tipo === "mes" ? "on" : ""} onClick={() => setVista({ tipo: "mes", ref: vista.ref })}>Mês</button>
          <button className={vista.tipo === "semana" ? "on" : ""} onClick={() => setVista({ tipo: "semana", ref: vista.ref })}>Semana</button>
          <button onClick={() => setVista({ ...vista, ref: hoje })}>Hoje</button>
        </div>
      </div>
      <div className="cal-grade">
        {DIAS_SEMANA.map((d) => <div key={d} className="cal-cab">{d}</div>)}
        {dias.map((d) => {
          const passado = d < hoje;
          const s = !passado ? sug[d] : null;
          const ps = pecas[d] || [];
          const virada = d.slice(8) === "01";
          return (
            <div key={d} className={`cal-celula ${d === hoje ? "hoje" : ""} ${passado ? "passado" : ""}`}>
              <span className="cal-dia-n">{Number(d.slice(8))}{virada && <em> {nomeMes(d).slice(0, 3)}</em>}</span>
              {ps.map((p) => (
                <button key={p.id} className={`chip-cal peca ${STATUS[p.status]?.cls || ""} ${casaPeca(p) ? "" : "apagado"}`} onClick={() => onPeca(p)}
                  title={`${p.atual?.criativo?.titulo || p.objetivo} · ${STATUS[p.status]?.rotulo}`}>
                  <svg viewBox="0 0 24 24" aria-hidden="true">{ICONE_FORMATO[p.formato] || ICONE_FORMATO.reels}</svg>
                  <span>{nomeFormato(p.formato)}</span>
                  <small>{p.atual?.criativo?.titulo || p.objetivo}</small>
                </button>
              ))}
              {s && !ps.length && (
                <button className={`chip-cal sug ${s.data_comemorativa ? "comemorativa" : ""} ${s.tipo_data === "ferramenta" ? "ferramenta" : ""} ${s.tipo_data === "radar" ? "radar" : ""} ${casaSug(s) ? "" : "apagado"}`}
                  title={`${s.horario} · ${s.tema}`} onClick={() => onSugestao(s, segmentos)}>
                  <svg viewBox="0 0 24 24" aria-hidden="true">{ICONE_FORMATO[s.formato] || ICONE_FORMATO.reels}</svg>
                  <span>{nomeFormato(s.formato)}</span>
                  <small>{vista.tipo === "semana" ? `${s.horario} · ${s.tema}` : s.rotulo || s.data_comemorativa || s.pilar}</small>
                </button>
              )}
              {!passado && !ps.length && (
                <button className="cal-novo" onClick={() => onNovo(d, s)} aria-label={`Novo post em ${d}`}>+ post</button>
              )}
            </div>
          );
        })}
      </div>
      <div className="cal-legenda">
        <span><i className="l-sug" />sugestão, toque pra criar</span>
        <span><i className="l-data" />perto de data comemorativa</span>
        <span><i className="l-ferramenta" />ferramenta da semana</span>
        <span><i className="l-radar" />novidade do radar (fonte oficial)</span>
        <span><i className="l-peca" />peça aprovada</span>
        <span className="mudo">Horários de referência: Opinion Box, Buffer e Sprout Social (2026)</span>
      </div>
    </div>
  );
}

