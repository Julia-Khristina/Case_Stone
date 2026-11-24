import { useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import { RefCard } from "./comum.jsx";
import { Carregando, Erro, Modal } from "./ui.jsx";
import { fmtData, fmtNum, nomeFormato, nomeSegmento, vezes } from "./util.js";

/* Insights: o que engaja no nicho, separado em "Faça", "Evite" e "Engaja, mas não recomendamos".
   Mesma linguagem visual do Playbook (número grande, capas reais, avisos em destaque). */
const pct = (x) => `${Math.round((x || 0) * 100)}%`;
const rede = (p) => (p === "youtube" ? "YouTube" : "Instagram");

export default function Inicio() {
  const [segmentos, setSegmentos] = useState([]);
  const [segmento, setSegmento] = useState("");
  const [filtroRede, setFiltroRede] = useState("todas");
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState(null);
  const [exemplosDe, setExemplosDe] = useState(null);

  useEffect(() => {
    api.segmentos().then(setSegmentos).catch(() => {});
  }, []);
  const carregar = () => {
    setDados(null);
    setErro(null);
    api.panorama(segmento || undefined).then(setDados).catch(setErro);
  };
  useEffect(carregar, [segmento]);

  const grupos = useMemo(() => {
    const todos = dados?.achados || [];
    // mesmo achado com sinal trocado na outra rede: avisar para tratar cada rede separadamente
    const comOposto = todos.map((a) => ({ ...a, oposto: todos.find((b) => b !== a && b.caracteristica === a.caracteristica && b.valor === a.valor && b.leitura !== a.leitura) }));
    const l = comOposto.filter((a) => filtroRede === "todas" || a.plataforma === filtroRede);
    return {
      faca: l.filter((a) => a.leitura === "mais no top" && a.recomendado),
      evite: l.filter((a) => a.leitura === "menos no top"),
      naoRecomendado: l.filter((a) => a.leitura === "mais no top" && !a.recomendado),
    };
  }, [dados, filtroRede]);

  return (
    <>
      <div className="pagina-topo">
        <div>
          <h1>Insights</h1>
          <p className="mudo">O que aparece mais (ou menos) nos posts que mais engajam em 55 perfis que falam com pequenos empreendedores. Cada cartão abre os posts reais por trás dele.</p>
        </div>
        <select value={segmento} onChange={(e) => setSegmento(e.target.value)} aria-label="Segmento" style={{ maxWidth: 260 }}>
          <option value="">Todos os segmentos</option>
          {segmentos.map((s) => <option key={s} value={s}>{nomeSegmento(s)}</option>)}
        </select>
      </div>

      <section className="guia-faixa">
        <svg className="guia-brilho" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM18.5 15l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" /></svg>
        <div>
          <small>Para as equipes da @stone e do @impulsostone</small>
          <h2>Playbook de conteúdo</h2>
          <p>Sugestões de melhoria para o Instagram de cada conta, comparando o que elas publicam com o que engaja no nicho, com vídeos de referência e criativos prontos.</p>
        </div>
        <div className="faixa-botoes">
          <a className="btn" href="/api/playbook.html" target="_blank" rel="noreferrer">Abrir</a>
          <a className="btn primario guia-abrir" href="/api/playbook.html?baixar=true">Baixar HTML <span aria-hidden="true">→</span></a>
        </div>
      </section>

      <Erro erro={erro} onRetry={carregar} />
      {!dados && !erro && <Carregando texto="Lendo a base…" />}
      {dados && (
        <>
          <section className="kpis">
            <div><b>{fmtNum(dados.kpis.posts)}</b><span>posts analisados</span></div>
            <div><b>{dados.kpis.perfis}</b><span>perfis no radar</span></div>
            <div><b>{fmtNum(dados.kpis.top)}</b><span>posts que mais engajam</span></div>
            <div><b>{fmtData(dados.kpis.coletado_em, { day: "2-digit", month: "short" })}</b><span>última coleta</span></div>
          </section>

          <div className="ins-filtro">
            <span className="mudo pequeno">Rede</span>
            <div className="seg-pilula">
              {[["todas", "Todas"], ["instagram", "Instagram"], ["youtube", "YouTube"]].map(([k, n]) => (
                <button key={k} className={filtroRede === k ? "on" : ""} onClick={() => setFiltroRede(k)}>{n}</button>
              ))}
            </div>
            <span className="mudo pequeno ins-explica">“3,0×” = aparece três vezes mais nos posts que mais engajam do que nos demais. Só entra o que aparece em 3 perfis ou mais.</span>
          </div>

          <section className="ins-bloco">
            <h2 className="ins-titulo"><span className="ins-tag faca">Faça</span>O que aparece mais nos posts que mais engajam</h2>
            {grupos.faca.length === 0 && <p className="mudo">Nenhum padrão confiável neste recorte. Tente “Todos os segmentos”.</p>}
            <div className="ins-cartoes">
              {grupos.faca.map((a, i) => <CartaoAchado key={i} a={a} onVer={() => setExemplosDe(a)} />)}
            </div>
          </section>

          {grupos.evite.length > 0 && (
            <section className="ins-bloco">
              <h2 className="ins-titulo"><span className="ins-tag evite">Evite</span>O que aparece menos nos posts que mais engajam</h2>
              <div className="ins-evite">
                {grupos.evite.map((a, i) => (
                  <button key={i} className="ins-evite-item" onClick={() => setExemplosDe(a)}>
                    <b>{a.nome}</b>
                    <span>{rede(a.plataforma)} · {pct(a.pct_top)} dos posts que mais engajam × {pct(a.pct_controle)} dos demais</span>
                    {a.n_perfis < 4 && <small>concentrado em poucos perfis</small>}
                    {a.oposto && <small>no {rede(a.oposto.plataforma)} é o contrário</small>}
                  </button>
                ))}
              </div>
            </section>
          )}

          {grupos.naoRecomendado.length > 0 && (
            <section className="ins-bloco">
              <h2 className="ins-titulo"><span className="ins-tag nao">Engaja, mas não recomendamos</span></h2>
              {grupos.naoRecomendado.map((a, i) => (
                <div key={i} className="ins-nao">
                  <div className="ins-lift">{vezes(a.lift)}</div>
                  <div>
                    <b>{a.nome}</b>
                    <p>Aparece {vezes(a.lift)} mais nos posts que mais engajam no orgânico, mas nos anúncios do Impulso a frase motivacional teve o menor CTR do histórico. O BoaPauta não usa isso para criar posts.</p>
                  </div>
                  <button className="btn-link" onClick={() => setExemplosDe(a)}>Ver exemplos</button>
                </div>
              ))}
            </section>
          )}

          <section className="ins-bloco">
            <h2 className="ins-titulo">Formatos no Instagram</h2>
            <div className="ins-formatos">
              {dados.formatos.map((f) => (
                <div key={f.valor} className="ins-formato">
                  <b>{nomeFormato(f.valor)}</b>
                  <div className="ins-barras">
                    <div><span>Posts que mais engajam</span><i><em className="top" style={{ width: pct(f.pct_top) }} /></i><strong>{pct(f.pct_top)}</strong></div>
                    <div><span>Demais</span><i><em className="ctl" style={{ width: pct(f.pct_controle) }} /></i><strong>{pct(f.pct_controle)}</strong></div>
                  </div>
                  <small className={f.leitura === "menos no top" ? "leitura menos" : "leitura"}>{f.leitura === "inconclusivo" ? "sem diferença clara" : f.leitura === "menos no top" ? "aparece menos no top" : "aparece mais no top"}</small>
                </div>
              ))}
            </div>
          </section>
        </>
      )}

      {exemplosDe && <Exemplos achado={exemplosDe} segmento={segmento} onClose={() => setExemplosDe(null)} />}
    </>
  );
}

function CartaoAchado({ a, onVer }) {
  return (
    <article className="ins-cartao" onClick={onVer} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onVer()}>
      <div className="ins-lift">{vezes(a.lift)}</div>
      <div className="ins-texto">
        <span className="ins-meta">{rede(a.plataforma)} · {a.n_perfis} perfis{a.n_perfis < 4 && <em> · concentrado em poucos perfis</em>}</span>
        <h3>{a.nome}</h3>
        <p>Em {pct(a.pct_top)} dos posts que mais engajam e em {pct(a.pct_controle)} dos demais.</p>
        {a.oposto && <small className="ins-oposto">No {rede(a.oposto.plataforma)} é o contrário: trate cada rede separadamente.</small>}
      </div>
      <div className="ins-capas">
        {(a.exemplos || []).slice(0, 2).map((r) => (
          <span key={r.post_id} className="ins-capa">
            {r.capa ? <img src={r.capa} alt="" loading="lazy" /> : <i>▶</i>}
            {r.lift_perfil != null && <em>{vezes(r.lift_perfil)}</em>}
          </span>
        ))}
      </div>
    </article>
  );
}

function Exemplos({ achado, segmento, onClose }) {
  const [lista, setLista] = useState(null);
  const [erro, setErro] = useState(null);
  useEffect(() => {
    api.exemplos(achado, segmento || undefined).then(setLista).catch(setErro);
  }, [achado, segmento]);
  return (
    <Modal titulo="Exemplos reais" onClose={onClose} largo>
      <p className="objetivo">{achado.frase}</p>
      <Erro erro={erro} />
      {!lista && !erro && <Carregando />}
      {lista && lista.length === 0 && <p className="mudo">Sem exemplos com rótulo neste recorte.</p>}
      <div className="refs">{lista?.map((r) => <RefCard key={r.post_id} r={r} />)}</div>
    </Modal>
  );
}
