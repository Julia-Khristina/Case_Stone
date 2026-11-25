import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import Calendario, { hojeIso, janelaDaVista, segundaDe, somarDias } from "./Calendario.jsx";
import Painel from "./Painel.jsx";
import { usePerfilLocal } from "./Configuracoes.jsx";
import BarraTopo, { casa } from "./Topo.jsx";
import { nomeFormato } from "./util.js";

/* Planejamento: a tela de todo dia. Um calendário só; tocar num dia abre o painel de criação e revisão. */
export default function Planejamento({ pecaId }) {
  const [perfil] = usePerfilLocal();
  const [vista, setVista] = useState({ tipo: "mes", ref: hojeIso() });
  const [agenda, setAgenda] = useState(null);
  const [semana, setSemana] = useState(null);
  const [abertura, setAbertura] = useState(null);
  const [busca, setBusca] = useState("");
  const [longe, setLonge] = useState(null);          // agenda dos próximos 6 meses, só carregada quando alguém busca

  // a busca também procura fora das semanas da tela: carrega 26 semanas uma vez e lista o que casa depois delas
  useEffect(() => {
    if (!busca.trim() || longe) return;
    api.agenda(segundaDe(hojeIso()), undefined, 182).then(setLonge).catch(() => {});
  }, [busca, longe]);
  const alem = useMemo(() => {
    if (!busca.trim() || !longe) return [];
    const { inicio, dias } = janelaDaVista(vista);
    const fim = somarDias(inicio, dias - 1);
    const fora = (d) => d && (d < inicio || d > fim) && d >= hojeIso();
    const sug = longe.sugestoes.filter((s) => fora(s.data) && casa(busca, s.tema, s.rotulo, s.pilar, s.data_comemorativa, nomeFormato(s.formato)))
      .map((s) => ({ data: s.data, texto: s.rotulo || s.data_comemorativa || s.tema }));
    const pcs = longe.pecas.filter((p) => fora(p.data_agenda) && casa(busca, p.atual?.criativo?.titulo, p.objetivo, nomeFormato(p.formato)))
      .map((p) => ({ data: p.data_agenda, texto: p.atual?.criativo?.titulo || p.objetivo }));
    return [...sug, ...pcs].sort((a, b) => a.data.localeCompare(b.data));
  }, [busca, longe, vista]);

  const carregar = useCallback(() => {
    const { inicio, dias } = janelaDaVista(vista);
    api.agenda(inicio, undefined, dias).then(setAgenda).catch((e) => setAgenda({ sugestoes: [], pecas: [], erro: e.message }));
    api.agenda(segundaDe(hojeIso()), undefined, 7).then(setSemana).catch(() => {});
  }, [vista]);
  useEffect(carregar, [carregar]);

  // link direto para uma peça (#/planejamento/peca/<id>) abre o painel dela
  useEffect(() => { if (pecaId) setAbertura({ tipo: "peca", id: pecaId }); }, [pecaId]);

  const fechar = useCallback(() => {
    setAbertura(null);
    if (pecaId) window.location.hash = "#/planejamento";
  }, [pecaId]);

  const resumo = useMemo(() => {
    if (!semana) return null;
    const ini = semana.inicio, fim = somarDias(ini, 6), hoje = hojeIso();
    const daSemana = semana.pecas.filter((p) => p.data_agenda >= ini && p.data_agenda <= fim);
    const comPeca = new Set(daSemana.map((p) => p.data_agenda));
    return {
      livres: semana.sugestoes.filter((s) => s.data >= hoje && !comPeca.has(s.data)).length,
      revisar: semana.pecas.filter((p) => p.status === "revisar").length,
      aprovadas: daSemana.filter((p) => p.status === "aprovada").length,
    };
  }, [semana]);

  const verSemana = () => {
    setVista({ tipo: "semana", ref: hojeIso() });
    document.querySelector(".cal")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const primeiroNome = (perfil.nome || "").split(" ")[0];
  return (
    <div className="plan">
      <header className="plan-topo">
        <div className="topo-linha">
          <h1><span className="ola">{primeiroNome ? `Olá, ${primeiroNome}` : "Olá"}!<svg className="ola-brilho" viewBox="0 0 40 40" aria-hidden="true"><path d="M8 18 15 4M14 22 30 10M18 30h16" /></svg></span>
            <span>Vamos planejar a semana?</span></h1>
          <BarraTopo busca={busca} setBusca={setBusca} placeholder="Buscar no calendário…" />
        </div>
        <div className="topo-linha">
          {resumo && (
            <div className="plan-resumo">
              <button className="resumo-card" onClick={verSemana} title="Ver a semana no calendário">
                <i className="rc-icone rc-sug"><svg viewBox="0 0 24 24"><path d="M4 6h16v14H4zM4 10.5h16M8.5 3.5v4M15.5 3.5v4M9 15l2 2 4-4" /></svg></i>
                <b>{resumo.livres}</b><span>{resumo.livres === 1 ? "sugestão esperando" : "sugestões esperando"} post nesta semana</span>
                <svg className="rc-seta" viewBox="0 0 24 24"><path d="m9 6 6 6-6 6" /></svg>
              </button>
              <a className="resumo-card" href="#/pecas">
                <i className="rc-icone rc-rev"><svg viewBox="0 0 24 24"><path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4" /></svg></i>
                <b>{resumo.revisar}</b><span>{resumo.revisar === 1 ? "peça" : "peças"} pra revisar</span>
                <svg className="rc-seta" viewBox="0 0 24 24"><path d="m9 6 6 6-6 6" /></svg>
              </a>
              <a className="resumo-card" href="#/pecas">
                <i className="rc-icone rc-ok"><svg viewBox="0 0 24 24"><path d="m7 12.5 3.2 3.2L17 9" /></svg></i>
                <b>{resumo.aprovadas}</b><span>{resumo.aprovadas === 1 ? "aprovada" : "aprovadas"} nesta semana</span>
                <svg className="rc-seta" viewBox="0 0 24 24"><path d="m9 6 6 6-6 6" /></svg>
              </a>
            </div>
          )}
        <button className="btn primario grande" onClick={() => setAbertura({ tipo: "novo" })}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg> Novo post
        </button>
        </div>
      </header>

      {alem.length > 0 && (
        <div className="busca-alem">
          <b>Também {alem.length === 1 ? "aparece" : "aparecem"} fora destas semanas:</b>
          {alem.slice(0, 8).map((x) => (
            <button key={x.data + x.texto} onClick={() => setVista({ tipo: "semana", ref: x.data })}>
              <span>{new Date(x.data + "T12:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}</span>{x.texto}
            </button>
          ))}
          {alem.length > 8 && <small>e mais {alem.length - 8}</small>}
        </div>
      )}

      <Calendario agenda={agenda} vista={vista} setVista={setVista} busca={busca}
        onSugestao={(s, segmentos) => setAbertura({ tipo: "sugestao", s, segmentos })}
        onPeca={(p) => setAbertura({ tipo: "peca", id: p.id })}
        onNovo={(data, s) => setAbertura({ tipo: "novo", data, s })} />


      {abertura && <Painel key={JSON.stringify(abertura).slice(0, 200)} abertura={abertura} onFechar={fechar} onMudou={carregar} />}
    </div>
  );
}
