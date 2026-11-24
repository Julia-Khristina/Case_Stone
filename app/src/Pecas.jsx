import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import Painel from "./Painel.jsx";
import { Guia } from "./Guia.jsx";
import { hojeIso, segundaDe, somarDias } from "./Calendario.jsx";
import { Carregando } from "./ui.jsx";
import BarraTopo, { casa } from "./Topo.jsx";
import { fmtData, nomeFormato, nomeSegmento } from "./util.js";

/* Peças: a fila de trabalho. O que revisar, o que está pronto pra publicar, e o guia detalhado da semana. */
const COLUNAS = [
  ["revisar", "Pra revisar", "A IA escreveu; falta o seu ok."],
  ["aprovada", "Aprovadas", "Prontas pra publicar no dia marcado."],
  ["outras", "Sem data ou com problema", "Aprovadas sem data, ou que não passaram nas conferências."],
];
const ICONE_COLUNA = {
  revisar: <path d="M12 7v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z" />,
  aprovada: <path d="m7 12.5 3.2 3.2L17 9" />,
  outras: <path d="M12 7v6M12 16.5v.5" />,
};

/* Miniatura honesta: no carrossel, o slide 1 de verdade (gerado pelo app); nos vídeos, um bloco com o ícone do formato. */
function Miniatura({ p }) {
  const [semSlide, setSemSlide] = useState(false);
  const carrossel = p.formato === "carrossel" && p.atual?.criativo;
  return (
    <span className={`cp-mini mini-${p.formato}`} aria-hidden="true">
      <svg viewBox="0 0 24 24">{p.formato === "carrossel"
        ? <path d="M4 5h16v14H4zM4 15l5-5 4 4 3-3 4 4" />
        : <path d="M8 5v14l11-7z" />}</svg>
      {carrossel && !semSlide && (
        <img src={`/api/pecas/${p.id}/slides/1.png?v=${encodeURIComponent(p.atualizado_em || "")}`} alt="" loading="lazy" onError={() => setSemSlide(true)} />
      )}
    </span>
  );
}

function Vazio({ busca }) {
  return (
    <div className="quadro-vazio">
      <svg viewBox="0 0 64 64" aria-hidden="true">
        <rect x="10" y="14" width="40" height="36" rx="6" /><path d="M10 24h40M20 9v9M40 9v9" />
        <path d="M20 34h4M30 34h4M20 41h4" /><circle cx="48" cy="46" r="9" className="vazio-alerta" /><path d="M48 41.5v5M48 50v.3" className="vazio-marca" />
      </svg>
      <b>Nada por aqui.</b>
      <span>{busca ? "Nenhuma peça desta coluna casa com a busca." : "Quando surgir algo, aparece aqui."}</span>
    </div>
  );
}

export default function Pecas() {
  const [pecas, setPecas] = useState(null);
  const [aberta, setAberta] = useState(null);
  const [guia, setGuia] = useState(false);
  const [busca, setBusca] = useState("");
  const carregar = useCallback(() => api.pecas().then(setPecas).catch(() => setPecas([])), []);
  useEffect(() => { carregar(); }, [carregar]);

  const ini = segundaDe(hojeIso()), fim = somarDias(ini, 6);
  const grupos = useMemo(() => {
    const g = { revisar: [], aprovada: [], outras: [] };
    (pecas || []).filter((p) => casa(busca, p.atual?.criativo?.titulo, p.objetivo, nomeFormato(p.formato), nomeSegmento(p.segmento), `@${p.atual?.conta || "impulsostone"}`,
      { revisar: "pra revisar", ajuste: "pra revisar", aprovada: "aprovada", falhou: "problema" }[p.status])).forEach((p) => {
      if (p.status === "revisar" || p.status === "ajuste") g.revisar.push(p);
      else if (p.status === "aprovada" && p.data_agenda) g.aprovada.push(p);
      else g.outras.push(p);
    });
    const porData = (a, b) => (a.data_agenda || "9999").localeCompare(b.data_agenda || "9999");
    Object.values(g).forEach((l) => l.sort(porData));
    return g;
  }, [pecas, busca]);
  const daSemana = (pecas || []).filter((p) => p.status === "aprovada" && (p.data_agenda ? p.data_agenda >= ini && p.data_agenda <= fim : String(p.atualizado_em).slice(0, 10) >= ini));

  if (!pecas) return <Carregando />;
  return (
    <div className="pecas">
      <header className="plan-topo">
        <div className="topo-linha">
          <h1>Peças <span>o que falta revisar e o que está pronto</span></h1>
          <BarraTopo busca={busca} setBusca={setBusca} placeholder="Buscar por peça, formato ou status…" />
        </div>
      </header>

      <section className="guia-faixa">
        <svg className="guia-brilho" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM18.5 15l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" /></svg>
        <div>
          <small>Toda sexta</small>
          <h2>Guia detalhado da semana</h2>
          <p>{daSemana.length
            ? `${daSemana.length} ${daSemana.length === 1 ? "peça aprovada" : "peças aprovadas"} de ${fmtData(ini)} a ${fmtData(fim)} viram um e-mail aprofundado para os empreendedores.`
            : `Aprove peças desta semana (${fmtData(ini)} a ${fmtData(fim)}) para montar o e-mail aprofundado de sexta.`}</p>
        </div>
        <button className="btn guia-abrir" onClick={() => setGuia(true)}>Abrir o guia <span aria-hidden="true">→</span></button>
      </section>

      <div className="quadro">
        {COLUNAS.map(([chave, nome, ajuda]) => (
          <section key={chave} className={`quadro-col col-${chave}`}>
            <header>
              <i className="col-icone"><svg viewBox="0 0 24 24" aria-hidden="true">{ICONE_COLUNA[chave]}</svg></i>
              <b>{nome}</b><span className="quadro-n">{grupos[chave].length}</span>
            </header>
            <p className="mudo pequeno">{ajuda}</p>
            {grupos[chave].length === 0 && <Vazio busca={busca} />}
            {grupos[chave].map((p) => (
              <button key={p.id} className="cartao-peca" onClick={() => setAberta(p.id)}>
                <Miniatura p={p} />
                <span className="cp-texto">
                <span className="cp-topo">
                  <i>{nomeFormato(p.formato)}</i>
                  {p.atual?.juiz?.media_ponderada != null && <em title="Nota do avaliador independente, de 0 a 10">Nota {p.atual.juiz.media_ponderada.toFixed(1).replace(".", ",")}</em>}
                </span>
                <b>{p.atual?.criativo?.titulo || p.objetivo}</b>
                <small className="cp-meta"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16v14H4zM4 10.5h16M8.5 3.5v4M15.5 3.5v4" /></svg>{p.data_agenda ? `${fmtData(p.data_agenda, { weekday: "short", day: "2-digit", month: "2-digit" }).replace(/^./, (c) => c.toUpperCase())}${p.horario ? ` · ${p.horario}` : ""}` : "Sem data"} · {nomeSegmento(p.segmento)} · @{p.atual?.conta || "impulsostone"}</small>
                {p.status === "falhou" && <small className="cp-alerta">Não passou nas conferências</small>}
                {p.atual?.falhas?.length > 0 && p.status !== "falhou" && <small className="cp-alerta">Com pendência</small>}
                </span>
                <svg className="cp-seta" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg>
              </button>
            ))}
          </section>
        ))}
      </div>

      {aberta && <Painel key={aberta} abertura={{ tipo: "peca", id: aberta }} onFechar={() => setAberta(null)} onMudou={carregar} />}
      {guia && <Guia inicio={ini} onClose={() => setGuia(false)} />}
    </div>
  );
}
