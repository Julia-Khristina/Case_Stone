import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "./api.js";
import { RefCard, rotuloPadrao } from "./comum.jsx";
import { Barra, Carregando, Erro } from "./ui.jsx";
import { CONFERENCIAS, CRITERIOS, PARTE, STATUS, falhaLegivel, fmtData, nomeFormato, nomeSegmento, vezes } from "./util.js";
import { hojeIso } from "./Calendario.jsx";

/* Painel lateral: o único lugar onde um post nasce e é revisado.
   Abre a partir de uma sugestão do calendário, de um dia livre, do botão "Novo post" ou de uma peça existente.
   À esquerda, a conversa (guiada por regras, sem IA); à direita, o palco: sugestão → proposta → IA ao vivo → peça.
   O modelo de linguagem só roda ao criar ou ajustar. */

const diaLongo = (iso) => fmtData(iso, { weekday: "long", day: "2-digit", month: "2-digit" });
const maiuscula = (t) => t.charAt(0).toUpperCase() + t.slice(1);

// O painel vai direto para o <body>: a página cria uma camada própria (isolation) e, dentro dela, o painel ficava
// atrás do menu fixo. No body, o véu desfocado cobre também o menu.
export default function Painel(props) {
  return createPortal(<PainelConteudo {...props} />, document.body);
}

function PainelConteudo({ abertura, onFechar, onMudou }) {
  const [msgs, setMsgs] = useState([]);
  const [entrada, setEntrada] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [palco, setPalco] = useState({ modo: "carregando" });
  const [pedido, setPedido] = useState(null);
  const [peca, setPeca] = useState(null);
  const [esperandoAjuste, setEsperandoAjuste] = useState(false);
  const [segmentos, setSegmentos] = useState(abertura.segmentos || []);
  const fimRef = useRef(null);
  const emCurso = palco.modo === "vivo" && palco.etapa !== "pronto" && !palco.erro;

  const dizer = (texto, botoes) => setMsgs((m) => [...m, { de: "bot", texto, botoes }]);
  const ouvir = (texto) => setMsgs((m) => [...m.map((x) => ({ ...x, botoes: undefined })), { de: "voce", texto }]);

  useEffect(() => { if (!segmentos.length) api.segmentos().then(setSegmentos).catch(() => {}); }, []);
  useEffect(() => { fimRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs]);
  useEffect(() => {
    const esc = (e) => e.key === "Escape" && !emCurso && onFechar();
    window.addEventListener("keydown", esc);
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", esc); document.body.style.overflow = ""; };
  }, [emCurso, onFechar]);

  // ---------- abertura ----------
  useEffect(() => {
    if (abertura.tipo === "sugestao") {
      const s = abertura.s;
      setPalco({ modo: "sugestao", s });
      dizer(`Bora criar o post de ${diaLongo(s.data)}? A agenda sugere ${s.tema.charAt(0).toLowerCase() + s.tema.slice(1)} (${nomeFormato(s.formato)}, ${s.horario}). Sigo com essa ideia ou você prefere outro objetivo?`,
        [{ rotulo: "Seguir com essa ideia", acao: { tipo: "usar_sugestao" }, principal: true },
         { rotulo: "Escrever outro objetivo", acao: { tipo: "outro" } }]);
    } else if (abertura.tipo === "novo") {
      setPalco({ modo: "novo", data: abertura.data || null });
      setPedido({ data_agenda: abertura.data || null, horario: abertura.s?.horario || null });
      dizer(abertura.data
        ? `Post pra ${diaLongo(abertura.data)}. Qual é o objetivo? Pode escrever do seu jeito.`
        : "Qual post a gente faz? Me conta o objetivo em uma frase. Se quiser marcar na agenda, coloca a data junto (ex.: 05/12).");
    } else {
      api.peca(abertura.id).then((p) => { setPeca(p); setPalco({ modo: "peca" }); falarDaPeca(p); })
        .catch((e) => { setPalco({ modo: "erro" }); dizer(`Não achei essa peça (${e.message}).`); });
    }
  }, []);

  function falarDaPeca(p, prefixo) {
    const a = p.atual;
    if (!a.criativo) {
      dizer("Essa peça não passou nas conferências e ficou sem texto. Quer tentar de novo com o mesmo objetivo?",
        [{ rotulo: "Tentar de novo", acao: { tipo: "refazer" }, principal: true }]);
      return;
    }
    const nota = a.juiz?.media_ponderada != null ? ` Nota do avaliador: ${a.juiz.media_ponderada.toFixed(1).replace(".", ",")}.` : "";
    const pend = a.falhas?.length ? ` Ficou pendente: ${a.falhas.map(falhaLegivel).join("; ")}.` : "";
    if (p.status === "aprovada") {
      dizer(`“${a.criativo.titulo}” já está aprovada${p.data_agenda ? ` pra ${diaLongo(p.data_agenda)}` : ""}.${nota} Quer ajustar alguma coisa?`,
        [{ rotulo: "Pedir ajuste", acao: { tipo: "pedir_ajuste" } }]);
    } else {
      dizer(`${prefixo || "Essa é"} “${a.criativo.titulo}”.${nota}${pend} Quer aprovar ou pedir um ajuste?`,
        [{ rotulo: "Aprovar", acao: { tipo: "aprovar" }, principal: true }, { rotulo: "Pedir ajuste", acao: { tipo: "pedir_ajuste" } }]);
    }
  }

  // ---------- etapas ----------
  async function propor(novo) {
    setPedido(novo);
    const prop = await api.proposta({ objetivo: novo.objetivo, segmento: novo.segmento, formato: novo.formato });
    const n = { conta: "impulsostone", ...novo, formato: prop.formato };
    const outraConta = n.conta === "stone" ? "impulsostone" : "stone";
    setPedido(n);
    setPalco({ modo: "proposta", prop, pedido: n });
    const fortes = prop.padroes.filter((p) => p.leitura !== "inconclusivo");
    const outro = prop.formato === "carrossel" ? "reels" : "carrossel";
    dizer(
      `Proposta para o @${n.conta}: ${nomeFormato(prop.formato)}${n.segmento ? ` pra ${nomeSegmento(n.segmento).toLowerCase()}` : ""}, apoiada em ${plural(fortes.length, "padrão que engaja", "padrões que engajam")} e ${plural(prop.referencias.length, "post real", "posts reais")} (estão no painel). ` +
        (prop.reserva_geral && n.segmento ? `Sobre ${nomeSegmento(n.segmento).toLowerCase()} a base ainda tem pouco, então completei com o que engaja em geral. ` : "") +
        "Nada foi escrito ainda.",
      [{ rotulo: "Criar este post", acao: { tipo: "criar" }, principal: true }, { rotulo: `Trocar pra ${nomeFormato(outro)}`, acao: { tipo: "formato", formato: outro } },
       { rotulo: `Fazer para o @${outraConta}`, acao: { tipo: "conta", conta: outraConta } }],
    );
  }

  async function aoVivo(chamar, prefixo) {
    setPalco({ modo: "vivo", etapa: "dados", eventos: {}, tentativas: [] });
    let final = null;
    await chamar((tipo, dados) => {
      setPalco((x) => aplicarEvento(x, tipo, dados));
      if (tipo === "conferencias" && dados.falhas?.length) dizer(String(dados.tentativa).startsWith("juiz")
        ? "A versão reescrita quebrou uma conferência, então fica a anterior."
        : `A tentativa ${dados.tentativa} não passou em ${plural(dados.falhas.length, "conferência", "conferências")}. Reescrevendo com a correção exata.`);
      if (tipo === "feedback_juiz") dizer(`O avaliador deu ${String(dados.nota?.toFixed?.(1) ?? dados.nota).replace(".", ",")} e apontou o que melhorar: ${dados.criterios.map((k) => (CRITERIOS[k] || k).toLowerCase()).join(", ")}. Reescrevendo com o retorno dele; fica a versão com a nota maior.`);
      if (tipo === "pronto") final = dados.peca;
      if (tipo === "erro") dizer(dados.mensagem);
    });
    if (final) {
      setPeca(final);
      onMudou?.();
      setTimeout(() => setPalco({ modo: "peca" }), 1400);    // deixa ver a trilha completa antes de mostrar a peça
      falarDaPeca(final, prefixo);
    }
  }

  async function executar(acao) {
    setOcupado(true);
    try {
      if (acao.tipo === "texto") await responder(acao.texto);
      else if (acao.tipo === "usar_sugestao") {
        const s = abertura.s;
        ouvir("Seguir com essa ideia");
        await propor({ objetivo: s.tema, segmento: segmentos.includes(s.segmento) ? s.segmento : null, formato: s.formato, data_agenda: s.data, horario: s.horario });
      } else if (acao.tipo === "outro") {
        ouvir("Escrever outro objetivo");
        setPedido({ data_agenda: abertura.s?.data || null, horario: abertura.s?.horario || null });
        dizer("Beleza. Qual é o objetivo do post? Pode escrever do seu jeito.");
      } else if (acao.tipo === "criar") {
        ouvir("Criar este post");
        dizer("Escrevendo. Acompanha no painel: cada etapa aparece enquanto acontece.");
        const p = pedido;
        await aoVivo((cb) => api.criarAoVivo({ objetivo: p.objetivo, formato: p.formato, segmento: p.segmento, data_agenda: p.data_agenda, horario: p.horario, conta: p.conta || "impulsostone" }, cb), "Pronta:");
      } else if (acao.tipo === "conta") {
        ouvir(`Fazer para o @${acao.conta}`);
        await propor({ ...pedido, conta: acao.conta });
      } else if (acao.tipo === "formato") {
        ouvir(`Trocar pra ${nomeFormato(acao.formato)}`);
        await propor({ ...pedido, formato: acao.formato });
      } else if (acao.tipo === "aprovar") {
        ouvir("Aprovar");
        const p = await api.aprovar(peca.id);
        setPeca(p);
        onMudou?.();
        dizer(p.data_agenda ? `Aprovada ✓ e marcada pra ${diaLongo(p.data_agenda)}${p.horario ? `, ${p.horario}` : ""}. Ela entra no guia detalhado da semana.` : "Aprovada ✓. Ela entra no guia detalhado da semana.");
      } else if (acao.tipo === "pedir_ajuste") {
        ouvir("Pedir ajuste");
        setEsperandoAjuste(true);
        dizer("O que precisa mudar? Pode escrever do seu jeito, tipo “o gancho tá fraco, cita o caixa de dezembro”.");
      } else if (acao.tipo === "refazer") {
        ouvir("Tentar de novo");
        await propor({ objetivo: peca.objetivo, segmento: peca.segmento, formato: peca.formato, data_agenda: peca.data_agenda, horario: peca.horario, conta: peca.atual?.conta || "impulsostone" });
      }
    } catch (e) {
      dizer(`Não deu certo: ${e.message}`);
    }
    setOcupado(false);
  }

  async function responder(texto) {
    ouvir(texto);
    // Pergunta não é pedido de ajuste nem objetivo de post: responde (sem gastar IA) e não reescreve nada.
    if (ehPergunta(texto)) {
      dizer(respostaPergunta(texto, peca) + (esperandoAjuste && peca
        ? " Se quiser mudar algo na peça, é só escrever o quê (ex.: “o gancho tá fraco, cita o caixa de dezembro”)." : ""));
      return;
    }
    if (esperandoAjuste && peca) {
      setEsperandoAjuste(false);
      dizer("Reescrevendo. A versão atual fica guardada no histórico.");
      await aoVivo((cb) => api.ajusteAoVivo(peca.id, texto, cb), "Nova versão:");
      return;
    }
    if (/engaj|insight|achado|criador|parceri|embaixador/i.test(texto)) {
      dizer("Isso fica nas páginas Insights e Criadores, no menu à esquerda. Aqui eu cuido de criar e revisar posts.");
      return;
    }
    const formato = formatoDe(texto);
    if (pedido?.objetivo && formato && texto.trim().split(/\s+/).length <= 4) { await propor({ ...pedido, formato }); return; }
    if (texto.trim().length < 8) { dizer("Me conta um pouco mais: qual é o objetivo do post?"); return; }
    const data = dataDe(texto) || pedido?.data_agenda || null;
    let horario = pedido?.horario || null;
    if (dataDe(texto)) {
      const ag = await api.agenda(data, undefined, 7);
      horario = ag.sugestoes.find((s) => s.data === data)?.horario || null;
      dizer(`Anotado pra ${diaLongo(data)}${horario ? `, horário de referência ${horario}` : ""}.`);
    }
    const objetivo = texto.replace(/\s*(no dia|para o dia|pro dia|dia|em|para|pra)?\s*\b\d{1,2}\/\d{1,2}(\/\d{2,4})?\b/i, "").trim();
    await propor({ objetivo, segmento: segmentoDe(texto), formato, data_agenda: data, horario });
  }

  const enviar = (e) => {
    e.preventDefault();
    const t = entrada.trim();
    if (!t || ocupado) return;
    setEntrada("");
    executar({ tipo: "texto", texto: t });
  };

  const titulo = peca?.atual?.criativo?.titulo || (palco.modo === "sugestao" ? palco.s.tema : pedido?.objetivo) || "Novo post";
  const quando = peca?.data_agenda || pedido?.data_agenda || abertura.s?.data || abertura.data;
  return (
    <div className="painel-fundo" onMouseDown={(e) => e.target === e.currentTarget && !emCurso && onFechar()}>
      <aside className="painel" role="dialog" aria-label="Criação e revisão do post">
        <header className="painel-topo">
          <div>
            <span className="painel-quando">{quando ? maiuscula(diaLongo(quando)) : "Sem data"}{(peca?.horario || pedido?.horario) ? ` · ${peca?.horario || pedido?.horario}` : ""}
              {peca && <i className={`painel-status ${STATUS[peca.status]?.cls || ""}`}>{STATUS[peca.status]?.rotulo}</i>}</span>
            <h2>{titulo}</h2>
          </div>
          <button className="painel-fechar" onClick={onFechar} disabled={emCurso} aria-label="Fechar">×</button>
        </header>
        <div className="painel-corpo">
          <section className="painel-conversa">
            <div className="mensagens">
              {msgs.map((m, i) => (
                <div key={i} className={`msg ${m.de}`}>
                  <p>{m.texto}</p>
                  {m.botoes && (
                    <div className="respostas">
                      {m.botoes.map((b) => (
                        <button key={b.rotulo} className={`btn pequeno ${b.principal ? "primario" : ""}`} disabled={ocupado} onClick={() => executar(b.acao)}>{b.rotulo}</button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {ocupado && <div className="msg bot digitando"><span /><span /><span /></div>}
              <div ref={fimRef} />
            </div>
            <form className="caixa-msg" onSubmit={enviar}>
              <input value={entrada} onChange={(e) => setEntrada(e.target.value)} disabled={ocupado}
                placeholder={esperandoAjuste ? "O que precisa mudar?" : "Escreva aqui…"} />
              <button className="enviar" disabled={ocupado || !entrada.trim()} aria-label="Enviar">
                <svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
              </button>
            </form>
          </section>
          <section className="painel-palco" key={palco.modo}>
            {palco.modo === "carregando" && <Carregando />}
            {palco.modo === "sugestao" && <PalcoSugestao s={palco.s} onPedir={(t) => !ocupado && executar({ tipo: "texto", texto: t })} />}
            {palco.modo === "novo" && <PalcoNovo data={palco.data} onExemplo={(t) => !ocupado && executar({ tipo: "texto", texto: t })} />}
            {palco.modo === "proposta" && <PainelProposta prop={palco.prop} pedido={palco.pedido} />}
            {palco.modo === "vivo" && <PainelVivo estado={palco} />}
            {palco.modo === "peca" && peca && <PalcoPeca peca={peca} />}
          </section>
        </div>
      </aside>
    </div>
  );
}

/* ---------- palcos ---------- */
// Novidades da semana em fontes oficiais (radar): cada uma pode virar um post pelo chat, mesmo fora da agenda.
function Novidades({ onPedir, sem }) {
  const [itens, setItens] = useState(null);
  useEffect(() => { api.radar().then((r) => setItens(r.itens || [])).catch(() => setItens([])); }, []);
  const lista = (itens || []).filter((x) => x.link !== sem).slice(0, 4);
  if (!lista.length) return null;
  const TIPO = { prazo: "Prazo", regra_nova: "Regra nova", oportunidade_de_venda: "Oportunidade", ferramenta: "Ferramenta", alerta: "Alerta", data: "Data" };
  return (
    <div className="novidades">
      <h4>Novidades da semana <small>fontes oficiais</small></h4>
      {lista.map((x) => (
        <div className="novidade" key={x.link}>
          <span className={`nv-tipo nv-${x.tipo}`}>{TIPO[x.tipo] || x.tipo}</span>
          <b>{x.titulo_curto}</b>
          <p>{x.o_que_muda}</p>
          <div className="nv-rodape">
            <a href={x.link} target="_blank" rel="noreferrer">{x.fonte} · {fmtData(x.publicado_em.slice(0, 10), { day: "2-digit", month: "2-digit" })}</a>
            {onPedir && <button className="btn pequeno" onClick={() => onPedir(x.tema_post)}>Criar post sobre isso</button>}
          </div>
        </div>
      ))}
    </div>
  );
}

function PalcoSugestao({ s, onPedir }) {
  const j = s.justificativa;
  return (
    <div className="palco-sugestao">
      <span className="vivo-etiqueta">{s.radar ? "Sugestão do radar" : "Sugestão da agenda"}</span>
      <h3 className="palco-tema">{s.tema}</h3>
      <div className="palco-fatos">
        <div><small>Formato</small><b>{nomeFormato(s.formato)}</b></div>
        <div><small>Horário de referência</small><b>{s.horario}</b></div>
        <div><small>Segmento</small><b>{nomeSegmento(s.segmento)}</b></div>
        <div><small>Pilar</small><b>{s.pilar}</b></div>
      </div>
      {s.radar && (
        <a className="radar-fonte" href={s.radar.link} target="_blank" rel="noreferrer">
          <small>Fonte oficial · {s.radar.fonte}</small><b>{s.radar.titulo_fonte}</b>
        </a>
      )}
      {j ? (
        <div className="porque">
          <h4>Por que este post neste dia</h4>
          <div className="porque-bloco"><small>Quando</small><p>{j.quando}</p></div>
          <div className="porque-bloco"><small>O quê</small>{j.o_que.map((t) => <p key={t}>{t}</p>)}</div>
          {j.exemplo && (
            <a className="porque-bloco porque-exemplo" href={j.exemplo.link} target="_blank" rel="noreferrer">
              <small>Exemplo real do top</small>
              <p>@{j.exemplo.perfil}: {j.exemplo.titulo_ou_trecho}{j.exemplo.lift_perfil ? ` (${String(j.exemplo.lift_perfil.toFixed(1)).replace(".", ",")}× a média do perfil)` : ""}</p>
            </a>
          )}
          <details className="porque-mais"><summary>Todos os motivos</summary>
            <ul className="palco-motivos">{s.motivos.map((m) => <li key={m}>{m}</li>)}</ul></details>
        </div>
      ) : (
        <>
          <h4>Por que esse dia</h4>
          <ul className="palco-motivos">{s.motivos.map((m) => <li key={m}>{m}</li>)}</ul>
        </>
      )}
      <p className="mudo pequeno">Horários: {s.fontes_horario.join("; ")}.</p>
      <Novidades onPedir={onPedir} sem={s.radar?.link} />
    </div>
  );
}

function PalcoNovo({ data, onExemplo }) {
  const exemplos = ["Ensinar a separar o dinheiro da loja do dinheiro de casa", "Mostrar como controlar o fiado do mercadinho",
    "Convidar donos de salão para a comunidade do Impulso"];
  return (
    <div className="palco-novo">
      <span className="vivo-etiqueta">Novo post{data ? ` · ${diaLongo(data)}` : ""}</span>
      <h3 className="palco-tema">Do objetivo ao post pronto, em menos de um minuto.</h3>
      <ol className="palco-passos">
        <li><b>Você conta o objetivo</b><span>Do seu jeito, na conversa ao lado.</span></li>
        <li><b>A proposta aparece aqui</b><span>Formato, o que engaja e posts reais de referência. Sem IA ainda.</span></li>
        <li><b>A IA escreve ao vivo</b><span>Com conferências e um avaliador independente.</span></li>
        <li><b>Você aprova ou pede ajuste</b><span>Nada sai sem o seu ok.</span></li>
      </ol>
      <h4>Pra começar rápido</h4>
      <div className="palco-exemplos">{exemplos.map((e) => <button key={e} onClick={() => onExemplo(e)}>{e}</button>)}</div>
      <Novidades onPedir={onExemplo} />
    </div>
  );
}

function PalcoPeca({ peca }) {
  const a = peca.atual;
  const c = a.criativo;
  const [copiado, setCopiado] = useState(false);
  if (!c) return <div className="aviso erro">Essa peça não tem texto: {(a.erros || []).join(" ")}</div>;
  const decisoes = peca.historico.filter((h) => h.acao);
  return (
    <div className="palco-peca">
      <div className="peca-colunas">
      <div className="peca-doc">
        {c.caso && <p className="vivo-caso"><small>O caso por trás da peça</small>{c.caso}</p>}
        <small className="rotulo">Gancho</small>
        <p className="vivo-gancho">{c.gancho}</p>
        <ol className="vivo-partes">{c.corpo.map((t, i) => <li key={i}><small>{PARTE[peca.formato] || "Parte"} {i + 1}</small> {semPrefixo(t)}</li>)}</ol>
        <p className="vivo-cta"><span>{c.cta}</span></p>
        <div className="peca-legenda">
          <small className="rotulo">Legenda</small>
          <p>{c.legenda}</p>
          <button className="btn pequeno" onClick={() => { navigator.clipboard?.writeText(c.legenda); setCopiado(true); }}>{copiado ? "Copiada ✓" : "Copiar legenda"}</button>
        </div>
      </div>
      <div className="peca-lado2">
        {a.melhoria_juiz && (
          <div className="melhoria-juiz">
            <small>Retorno do avaliador</small>
            <p>
              {a.melhoria_juiz.mantida === "original"
                ? <>A reescrita guiada pelo avaliador não superou a versão original ({fmtNota(a.melhoria_juiz.antes)}), que foi mantida.</>
                : <>Nota antes do retorno do avaliador: <b>{fmtNota(a.melhoria_juiz.antes)}</b> → depois: <b>{fmtNota(a.melhoria_juiz.depois)}</b></>}
            </p>
          </div>
        )}
        {a.juiz && !a.juiz.erro && (
          <div className="vivo-juiz">
            <b>{a.juiz.media_ponderada?.toFixed(1).replace(".", ",")}</b>
            <ul>{Object.entries(a.juiz.scores || {}).map(([k, v]) => <li key={k}><span>{CRITERIOS[k] || k}</span><Barra valor={v * 10} /><em>{v}</em></li>)}</ul>
          </div>
        )}
        <ul className="vivo-checks">
          {Object.entries(a.conferencias || {}).map(([k, ok]) => <li key={k} className={ok ? "ok" : "falha"}>{ok ? "✓" : "✗"} {CONFERENCIAS[k] || k}</li>)}
        </ul>
        {peca.formato === "carrossel" && <a className="btn" href={api.slidesUrl(peca.id)}>Baixar slides (PNG)</a>}
      </div>
      </div>
      {peca.formato === "carrossel" && <PreviaCarrossel peca={peca} />}
      {a.referencias?.length > 0 && (
        <>
          <h4>Posts reais que serviram de base</h4>
          <div className="refs">{a.referencias.map((r) => <RefCard key={r.post_id} r={r} />)}</div>
        </>
      )}
      {decisoes.length > 0 && (
        <p className="mudo pequeno palco-historico">
          {decisoes.map((h) => `${h.acao === "aprovar" ? "Aprovada" : "Ajuste pedido"}${h.quem && h.quem !== "equipe Stone" ? ` por ${h.quem}` : ""} em ${new Date(h.em).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}${h.motivo ? ` (${h.motivo})` : ""}`).join(" · ")}
        </p>
      )}
    </div>
  );
}

const SEGMENTO_POR_PALAVRA = [
  [/sal[aã]o|beleza|est[eé]tica|manicure|cabel|barbearia|unha/i, "beleza_estetica"],
  [/mercadinho|mercado|bairro|quitanda|armaz[eé]m|conveni[eê]ncia/i, "comercio_bairro"],
  [/padaria|restaurante|lanche|comida|doce|bolo|confeitaria|marmita|aliment/i, "alimentacao"],
  [/moda|roupa|loja de roupa|acess[oó]rio|brech[oó]/i, "moda_acessorios"],
  [/\bpet|cachorro|gato|banho e tosa/i, "pets"],
  [/artesanato|artes[aã]|ateli[eê]|produ[cç][aã]o pr[oó]pria/i, "artesanato_producao"],
  [/motorista|entrega|uber|motoboy|transporte/i, "transporte_entregas"],
];
const FORMATO_POR_PALAVRA = [[/carrossel/i, "carrossel"], [/reels?\b/i, "reels"], [/stories/i, "stories"], [/shorts?\b/i, "short"]];
const ETAPAS = [
  ["dados", "Lendo a base"],
  ["escrevendo", "Escrevendo"],
  ["conferencias", "Conferindo"],
  ["avaliando", "Avaliando"],
  ["pronto", "Pronta"],
];
const fmtNota = (n) => (n == null ? "—" : Number(n).toFixed(1).replace(".", ","));
const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;
// O rótulo "Slide 2" já aparece; tira "Slide 2:", "2." ou "2️⃣" que o modelo às vezes repete no texto
const semPrefixo = (t) => String(t).replace(/^\s*((slide|tela|cena)\s*\d+\s*[:\-–]\s*|\d+[.)]\s*|[0-9]️?⃣\s*)+/i, "").trim();

// "05/12" ou "5/12/2026" → data ISO; sem ano, usa a próxima ocorrência a partir de hoje
function dataDe(texto) {
  const m = texto.match(/\b(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?\b/);
  if (!m) return null;
  const hoje = hojeIso();
  let ano = m[3] ? Number(m[3].length === 2 ? "20" + m[3] : m[3]) : Number(hoje.slice(0, 4));
  const iso = (a) => `${a}-${String(m[2]).padStart(2, "0")}-${String(m[1]).padStart(2, "0")}`;
  if (!m[3] && iso(ano) < hoje) ano += 1;
  const d = iso(ano);
  return Number.isNaN(new Date(d + "T12:00:00").getTime()) ? null : d;
}

const segmentoDe = (t) => (SEGMENTO_POR_PALAVRA.find(([re]) => re.test(t)) || [])[1] || null;

// Perguntas no chat: termina com "?" ou começa com palavra de pergunta. Não viram objetivo de post nem ajuste.
const ehPergunta = (t) => /\?\s*$/.test(t.trim()) ||
  /^\s*(por ?que|pq|porque|como|o que|qual|quais|quem|onde|quando|cad[eê]|pra que|para que)\b/i.test(t);

function respostaPergunta(t, peca) {
  const s = t.toLowerCase();
  if (/\bcor(es)?\b|visual|paleta|design|fonte|layout|identidade/.test(s))
    return "As cores não são escolha da IA. O carrossel usa a identidade visual do Impulso Stone (verde Sherwood e lima, fonte Hanken Grotesk), "
      + "definida no arquivo de identidade (config/tokens_visuais.yaml) e conferida no contraste para leitura. A IA escreve só o texto; "
      + (peca?.atual?.conta === "stone" ? "nas peças da @stone, a assinatura muda para stone. " : "")
      + "Para mudar as cores, a equipe altera esse arquivo, não a peça.";
  if (/nota|avalia|juiz|crit[eé]rio|6,|7,|8,|9,/.test(s))
    return "A nota vem de um avaliador independente, um modelo de outra empresa, numa rubrica de 7 critérios (segue o que engaja, próximo passo claro, "
      + "tom, clareza, fidelidade à oferta, concretude e profundidade). A nota de cada critério está no painel. Se algum fica abaixo de 7, "
      + "o agente já tenta uma reescrita guiada pelo retorno do avaliador.";
  if (/refer[eê]ncia|base|post real|exemplo|de onde/.test(s))
    return "A peça se apoia em posts reais do top da base: os que mais superaram a média do próprio perfil, dentro do escopo (orientam o empreendedor). "
      + "Eles aparecem no painel com link; o texto nunca é copiado deles.";
  if (/formato|carrossel|reels|stories|short/.test(s))
    return "O formato vem do que mais engaja na base para esse tema e da agenda da semana, que varia os formatos. Dá para trocar na proposta, antes de a IA escrever.";
  if (/dia|data|hor[aá]rio|quando/.test(s))
    return "O dia vem da agenda: datas comemorativas com fases de preparação, obrigações como o DAS, novidades do radar e orientações nos dias livres. "
      + "O horário é de referência, de pesquisas públicas. O motivo de cada dia está em “Por que este post neste dia”.";
  return "Aqui eu cuido de criar e revisar posts. Para entender o que engaja, veja Insights; para parceiros, Criadores.";
}
const formatoDe = (t) => (FORMATO_POR_PALAVRA.find(([re]) => re.test(t)) || [])[1] || null;
const resumoPadrao = (p) => `${p.leitura === "mais no top" ? "usar" : "evitar"} ${rotuloPadrao(p)}`;

/* Estado do painel ao vivo a partir de cada evento transmitido pela API */
function aplicarEvento(x, tipo, dados) {
  const v = x.modo === "vivo" ? { ...x } : { modo: "vivo", eventos: {}, tentativas: [] };
  v.eventos = { ...v.eventos, [tipo]: dados };
  if (tipo === "dados") v.etapa = "escrevendo";
  if (tipo === "escrevendo") { v.etapa = "escrevendo"; v.tentativas = [...v.tentativas, { n: dados.tentativa }]; }
  if (tipo === "rascunho") { v.rascunho = dados.criativo; v.etapa = "conferencias"; }
  if (tipo === "conferencias") {
    v.tentativas = v.tentativas.map((t) => (t.n === dados.tentativa ? { ...t, conferencias: dados.conferencias, falhas: dados.falhas } : t));
    v.etapa = dados.falhas?.length ? "escrevendo" : "avaliando";
  }
  if (tipo === "avaliando") v.etapa = "avaliando";
  if (tipo === "juiz") v.juiz = dados.juiz;
  if (tipo === "pronto") { v.etapa = "pronto"; v.peca = dados.peca; }
  if (tipo === "erro") v.erro = dados.mensagem;
  return v;
}

function PainelProposta({ prop, pedido }) {
  const fortes = prop.padroes.filter((p) => p.leitura !== "inconclusivo");
  return (
    <div>
      <div className="vivo-etiqueta">Proposta · ainda sem IA</div>
      <h2>{pedido.objetivo}</h2>
      <p className="mudo">@{pedido.conta || "impulsostone"} · {nomeFormato(prop.formato)} · {nomeSegmento(pedido.segmento)}{pedido.data_agenda ? ` · ${fmtData(pedido.data_agenda, { weekday: "short", day: "2-digit", month: "2-digit" })} ${pedido.horario || ""}` : ""}</p>
      <h3>O que a peça vai seguir</h3>
      <ul className="padroes">{fortes.map((p, i) => <li key={i} className={p.leitura === "mais no top" ? "mais" : "menos"}><b>{p.leitura === "mais no top" ? "Usar" : "Evitar"}</b> {rotuloPadrao(p)} <span className="mudo">· {vezes(p.lift)}, {p.n_perfis} perfis</span></li>)}</ul>
      <h3>Posts reais em que ela se apoia</h3>
      <div className="refs">{prop.referencias.map((r) => <RefCard key={r.post_id} r={r} />)}</div>
    </div>
  );
}

function PainelVivo({ estado }) {
  const e = estado;
  const ordem = ETAPAS.map(([k]) => k);
  const atual = ordem.indexOf(e.etapa);
  const dados = e.eventos?.dados;
  const ultima = e.tentativas?.[e.tentativas.length - 1];
  const c = e.peca?.atual?.criativo || e.rascunho;
  return (
    <div className="vivo">
      <ol className="trilha">
        {ETAPAS.map(([k, nome], i) => (
          <li key={k} className={i < atual || e.etapa === "pronto" ? "feito" : i === atual ? "agora" : ""}>
            <span className="ponto" />
            <span>{nome}{k === "escrevendo" && e.tentativas?.length > 1 && <small>tentativa {e.tentativas.length}</small>}</span>
          </li>
        ))}
      </ol>
      {e.erro && <div className="aviso erro">{e.erro}</div>}

      {dados && (
        <div className="vivo-bloco">
          <h3>Da base</h3>
          <p className="pequeno">{plural(dados.padroes.length, "padrão confiável", "padrões confiáveis")} e {plural(dados.referencias.length, "post real", "posts reais")} de referência ({nomeFormato(dados.formato)}).</p>
          <div className="vivo-chips">{dados.padroes.slice(0, 5).map((p, i) => <span key={i}>{resumoPadrao(p)} <b>{vezes(p.lift)}</b></span>)}</div>
        </div>
      )}

      {c && (
        <div className={`vivo-bloco rascunho ${e.etapa === "pronto" ? "" : "provisorio"}`}>
          <h3>{e.etapa === "pronto" ? "A peça" : "Rascunho"} <small className="mudo">{nomeFormato(c.formato)}</small></h3>
          {c.caso && <p className="vivo-caso"><small>O caso</small>{c.caso}</p>}
          <p className="vivo-gancho">{c.gancho}</p>
          <ol className="vivo-partes">{c.corpo.map((t, i) => <li key={i}><small>{PARTE[c.formato] || "Parte"} {i + 1}</small> {semPrefixo(t)}</li>)}</ol>
          <p className="vivo-cta"><span>{c.cta}</span></p>
        </div>
      )}

      {ultima?.conferencias && (
        <div className="vivo-bloco">
          <h3>Conferências <small className="mudo">tentativa {ultima.n}</small></h3>
          <ul className="vivo-checks">
            {Object.entries(ultima.conferencias).map(([k, ok]) => <li key={k} className={ok ? "ok" : "falha"}>{ok ? "✓" : "✗"} {CONFERENCIAS[k] || k}</li>)}
          </ul>
          {ultima.falhas?.length > 0 && e.etapa !== "pronto" && <p className="pequeno mudo">Reescrevendo com a correção: {falhaLegivel(ultima.falhas[0])}</p>}
        </div>
      )}

      {(e.etapa === "avaliando" || e.juiz) && (
        <div className="vivo-bloco">
          <h3>Avaliador independente</h3>
          {!e.juiz ? <p className="mudo pequeno"><span className="giro" /> lendo a peça com a rubrica…</p> : e.juiz.erro ? <p className="mudo pequeno">Não conseguiu dar nota a esta versão.</p> : (
            <div className="vivo-juiz">
              <b>{e.juiz.media_ponderada?.toFixed(1).replace(".", ",")}</b>
              <ul>{Object.entries(e.juiz.scores || {}).map(([k, v]) => <li key={k}><span>{CRITERIOS[k] || k}</span><Barra valor={v * 10} /><em>{v}</em></li>)}</ul>
            </div>
          )}
        </div>
      )}

      {e.etapa === "pronto" && e.peca?.formato === "carrossel" && e.peca.atual?.criativo && <PreviaCarrossel peca={e.peca} />}
    </div>
  );
}

function PreviaCarrossel({ peca }) {
  const [slides, setSlides] = useState(null);
  const [erro, setErro] = useState(null);
  useEffect(() => {
    setSlides(null);
    setErro(null);
    api.slides(peca.id).then(setSlides).catch(setErro);
  }, [peca.id, peca.atualizado_em]);
  return (
    <section className="bloco">
      <div className="bloco-topo">
        <h2>Prévia do carrossel</h2>
        <span className="mudo">PNG 1080 × 1350 no visual Impulso · cada nova versão gera slides novos</span>
      </div>
      <Erro erro={erro} />
      {!slides && !erro && <Carregando texto="Montando os slides…" />}
      {slides && (
        <div className="previa-slides">
          {slides.map((u, i) => <a key={u} href={u} target="_blank" rel="noreferrer"><img src={u} alt={`Slide ${i + 1}`} loading="lazy" /></a>)}
        </div>
      )}
    </section>
  );
}
