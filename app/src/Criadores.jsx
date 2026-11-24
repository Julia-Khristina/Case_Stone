import { useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import { Barra, Carregando, Chip, Erro, Modal, Voltar } from "./ui.jsx";
import { DIMENSOES, FAIXAS, fmtNum, linkPerfil, nomeFormato, nomeSegmento, vezes } from "./util.js";

const ALERTAS = {
  parceiro_atual: "já é parceiro", publi_concorrente: "publi de concorrente", curtidas_ocultas: "curtidas ocultas",
  poucos_posts_rotulados: "pouca amostra", conta_de_marca: "conta de marca",
};

export default function Criadores() {
  const [comp, setComp] = useState({ transversais: 2, setoriais: 3, setores: [] });
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState(null);
  const [editando, setEditando] = useState(false);
  const [filtro, setFiltro] = useState("todos");
  const [segmentos, setSegmentos] = useState([]);

  const carregar = () => {
    setErro(null);
    api.criadores({ transversais: comp.transversais, setoriais: comp.setoriais, setores: comp.setores.join(",") })
      .then(setDados).catch(setErro);
  };
  useEffect(carregar, [comp]);
  useEffect(() => {
    api.segmentos().then(setSegmentos).catch(() => {});
  }, []);

  async function convidar(c) {
    await api.convidar(c);
    carregar();
  }

  const lista = useMemo(() => {
    const l = dados?.criadores || [];
    return filtro === "todos" ? l : l.filter((c) => c.tipo === filtro || c.plataforma === filtro);
  }, [dados, filtro]);

  if (erro) return <Erro erro={erro} onRetry={carregar} />;
  if (!dados) return <Carregando texto="Calculando o scorecard…" />;
  const ind = dados.indicados;
  const reservaDe = Object.groupBy ? Object.groupBy(ind.reservas, (r) => r.reserva_de) : agrupar(ind.reservas);

  return (
    <>
      <div className="pagina-topo">
        <div>
          <h1>Criadores</h1>
          <p className="mudo">Quem a Stone pode chamar para uma parceria, com base em como o público reage aos posts nos últimos 90 dias.</p>
        </div>
        <button className="btn" onClick={() => setEditando(true)}>Ajustar composição</button>
      </div>

      <section className="bloco">
        <div className="bloco-topo">
          <h2>Indicados para contato</h2>
          <span className="mudo">{comp.transversais} transversais (falam com qualquer negócio) + {comp.setoriais} setoriais ({ind.motivo_setores})</span>
        </div>
        <h3 className="grupo-tit">Transversais</h3>
        <div className="indicados">
          {ind.transversais.map((c) => <Indicado key={c.perfil} c={c} reservas={reservaDe[c.perfil]} onConvidar={convidar} />)}
        </div>
        <h3 className="grupo-tit">Setoriais</h3>
        <div className="indicados">
          {ind.setoriais.map((c) => <Indicado key={c.perfil} c={c} reservas={reservaDe[c.perfil]} onConvidar={convidar} />)}
        </div>
        {(() => {
          // só quem ficou de fora por um motivo além da nota (parceiro, publi de concorrente, conta de marca)
          const fora = (ind.excluidos || []).filter((e) => !String(e.motivo_exclusao).startsWith("nota abaixo"));
          return fora.length > 0 && (
            <p className="mudo pequeno">Fora da indicação por outro motivo: {fora.map((e) => `${e.nome} (${e.motivo_exclusao})`).join("; ")}.</p>
          );
        })()}
      </section>

      <section className="bloco">
        <div className="bloco-topo">
          <h2>Todos no radar ({dados.criadores.length})</h2>
          <div className="seletor pequeno">
            {[["todos", "Todos"], ["transversal", "Transversais"], ["setorial", "Setoriais"], ["instagram", "Instagram"], ["youtube", "YouTube"]].map(([k, n]) => (
              <button key={k} className={filtro === k ? "on" : ""} onClick={() => setFiltro(k)}>{n}</button>
            ))}
          </div>
        </div>
        <div className="tabela-rolagem">
          <table className="tabela">
            <thead>
              <tr><th>Criador</th><th>Segmento</th><th>Público</th><th>Nota</th>{DIMENSOES.map(([k, n, mede, curto]) => <th key={k} title={`${n}: ${mede}`} className="dim">{curto}</th>)}<th /></tr>
            </thead>
            <tbody>
              {lista.map((c) => (
                <tr key={c.plataforma + c.perfil} onClick={() => (window.location.hash = `#/criadores/${c.plataforma}/${encodeURIComponent(c.perfil)}`)}>
                  <td><div className="criador-cel"><Foto c={c} tam="p" /><div><b>{c.nome}</b><div className="mudo pequeno">{c.plataforma === "youtube" ? "YouTube" : "Instagram"} · @{c.username}</div></div></div></td>
                  <td>{nomeSegmento(c.segmento)}<div className="mudo pequeno">{c.tipo}</div></td>
                  <td>{fmtNum(c.seguidores)}<div className="mudo pequeno">{FAIXAS[c.faixa] || c.faixa}</div></td>
                  <td><span className="nota">{c.nota}</span></td>
                  {DIMENSOES.map(([k]) => <td key={k} className="dim">{Math.round(c[k] ?? 0)}</td>)}
                  <td>{c.alertas.map((a) => <Chip key={a} tom="alerta">{ALERTAS[a] || a}</Chip>)}{c.convidado && <Chip tom="verde">na lista</Chip>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mudo pequeno">{dados.nota_metodologica} Cada dimensão é um percentil entre perfis da mesma plataforma e faixa de público.</p>
      </section>

      {editando && (
        <Composicao comp={comp} segmentos={segmentos} onClose={() => setEditando(false)} onSalvar={(c) => { setComp(c); setEditando(false); }} />
      )}
    </>
  );
}

const agrupar = (l) => l.reduce((m, r) => ({ ...m, [r.reserva_de]: [...(m[r.reserva_de] || []), r] }), {});

function Foto({ c, tam = "" }) {
  return c.foto
    ? <img className={`foto ${tam}`} src={c.foto} alt="" loading="lazy" />
    : <div className={`foto ${tam}`}>{c.nome.slice(0, 1)}</div>;
}

function Indicado({ c, reservas, onConvidar }) {
  const [enviando, setEnviando] = useState(false);
  return (
    <article className="indicado">
      <Foto c={c} />
      <div>
        <a href={`#/criadores/${c.plataforma}/${encodeURIComponent(c.perfil)}`}><b>{c.nome}</b></a>
        <div className="mudo pequeno">{c.plataforma === "youtube" ? "YouTube" : "Instagram"} · {fmtNum(c.seguidores)} seguidores · {nomeSegmento(c.segmento)}</div>
        {reservas?.length > 0 && <div className="mudo pequeno">Reserva: {reservas.map((r) => `${r.nome} (${r.nota})`).join(", ")}</div>}
      </div>
      <div className="mini-dims">
        {DIMENSOES.map(([k, n, mede, curto]) => (
          <div key={k} title={`${n}: ${mede}`}><span>{curto}<em>{Math.round(c[k] ?? 0)}</em></span><Barra valor={c[k]} /></div>
        ))}
      </div>
      <div className="indicado-acoes">
        <span className="nota grande">{c.nota}</span>
        {c.convidado ? (
          <span className="mudo pequeno">Na lista de contato ✓</span>
        ) : (
          <button className="btn pequeno" disabled={enviando} onClick={async () => { setEnviando(true); await onConvidar(c); }}>
            Pôr na lista de contato
          </button>
        )}
        <a className="btn-link pequeno" href={linkPerfil(c)} target="_blank" rel="noreferrer">Ver no {c.plataforma === "youtube" ? "YouTube" : "Instagram"}</a>
      </div>
    </article>
  );
}

function Composicao({ comp, segmentos, onClose, onSalvar }) {
  const [c, setC] = useState(comp);
  const alternar = (s) => setC({ ...c, setores: c.setores.includes(s) ? c.setores.filter((x) => x !== s) : [...c.setores, s] });
  return (
    <Modal
      titulo="Composição dos indicados"
      onClose={onClose}
      rodape={<><button className="btn" onClick={onClose}>Cancelar</button><button className="btn primario" onClick={() => onSalvar(c)}>Aplicar</button></>}
    >
      <p className="mudo">Transversais falam de gestão, finanças ou vendas para qualquer negócio. Setoriais falam com um setor (mercadinho, beleza, moda…). Cada vaga tem uma reserva.</p>
      <div className="contadores">
        {[["transversais", "Transversais"], ["setoriais", "Setoriais"]].map(([k, n]) => (
          <label key={k}>
            {n}
            <div className="contador">
              <button onClick={() => setC({ ...c, [k]: Math.max(0, c[k] - 1) })}>−</button>
              <b>{c[k]}</b>
              <button onClick={() => setC({ ...c, [k]: Math.min(6, c[k] + 1) })}>+</button>
            </div>
          </label>
        ))}
      </div>
      <h3>Setores prioritários (opcional)</h3>
      <div className="seletor quebra">
        {segmentos.map((s) => (
          <button key={s} className={c.setores.includes(s) ? "on" : ""} onClick={() => alternar(s)}>{nomeSegmento(s)}</button>
        ))}
      </div>
      <p className="mudo pequeno">Sem prioridade, o sistema escolhe primeiro setores onde a Stone ainda não tem parceiro.</p>
    </Modal>
  );
}

export function Perfil({ plataforma, perfil }) {
  const [c, setC] = useState(null);
  const [erro, setErro] = useState(null);
  useEffect(() => {
    api.criador(plataforma, perfil).then(setC).catch(setErro);
  }, [plataforma, perfil]);
  if (erro) return <><Voltar para="#/criadores">Criadores</Voltar><Erro erro={erro} /></>;
  if (!c) return <Carregando />;
  return (
    <>
      <Voltar para="#/criadores">Criadores</Voltar>
      <div className="pagina-topo">
        <div className="perfil-cab">
          <Foto c={c} tam="g" />
          <div>
            <h1>{c.nome}</h1>
            <p className="mudo">
              {c.plataforma === "youtube" ? "YouTube" : "Instagram"} · @{c.username} · {fmtNum(c.seguidores)} seguidores ({FAIXAS[c.faixa] || c.faixa}) ·{" "}
              {c.tipo} · {nomeSegmento(c.segmento)}
            </p>
            <div className="linha-chips">
              {c.alertas.map((a) => <Chip key={a} tom="alerta">{ALERTAS[a] || a}</Chip>)}
              {c.convidado && <Chip tom="verde">na lista de contato</Chip>}
            </div>
          </div>
        </div>
        <div className="nota-bloco"><span className="nota enorme">{c.nota}</span><small>nota de 0 a 100</small></div>
      </div>

      <div className="peca-grade">
        <section className="painel">
          <h3>Como a nota se forma</h3>
          {DIMENSOES.map(([k, n, d]) => (
            <div key={k} className="dim-linha">
              <div><b>{n}</b><span className="mudo pequeno"> {d}</span></div>
              <Barra valor={c[k]} />
              <span>{Math.round(c[k] ?? 0)}</span>
            </div>
          ))}
          <p className="mudo pequeno">
            {c.posts_elegiveis} posts na janela, {c.posts_rotulados} com rótulo de texto e {c.posts_vistos || 0} vistos pela análise de vídeo.
            {" "}Autenticidade {c.autenticidade_fonte === "video"
              ? "calculada pelo vídeo (quanto aparece o dono do negócio ou o negócio de verdade)."
              : "aproximada pelo tipo de perfil (poucos posts deste perfil passaram pela análise de vídeo)."}
          </p>
        </section>
        <section className="painel">
          <h3>Posts que mais engajaram</h3>
          {c.melhores_posts.map((p) => (
            <a key={p.post_id} className="ref" href={p.link} target="_blank" rel="noreferrer">
              <div className="ref-capa">
                <img src={`/api/capas/${p.post_id}.jpg`} alt="" loading="lazy" onError={(e) => { e.currentTarget.parentElement.style.display = "none"; }} />
              </div>
              <div className="ref-topo"><b>{nomeFormato(p.formato)}</b><span className="ref-lift">{vezes(p.lift_perfil)} a média do perfil</span></div>
              <p>{p.trecho}</p>
            </a>
          ))}
          <a className="btn" href={linkPerfil(c)} target="_blank" rel="noreferrer">Abrir perfil</a>
        </section>
      </div>
    </>
  );
}
