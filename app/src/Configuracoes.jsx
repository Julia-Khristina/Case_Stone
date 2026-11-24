import { useEffect, useState } from "react";
import { api } from "./api.js";
import { fmtData, fmtNum } from "./util.js";

/* Preferências locais (sem login): o nome só serve para a saudação e fica no navegador de quem usa. */
const CHAVE = "boapauta.perfil";
const ler = () => {
  try { return JSON.parse(localStorage.getItem(CHAVE)) || {}; } catch { return {}; }
};

export function usePerfilLocal() {
  const [perfil, setPerfil] = useState(ler);
  useEffect(() => {
    const f = () => setPerfil(ler());
    window.addEventListener("boapauta-perfil", f);
    return () => window.removeEventListener("boapauta-perfil", f);
  }, []);
  const salvar = (novo) => {
    try { localStorage.setItem(CHAVE, JSON.stringify(novo)); } catch {}
    setPerfil(novo);
    window.dispatchEvent(new Event("boapauta-perfil"));
  };
  return [perfil, salvar];
}

export default function Configuracoes() {
  const [perfil, salvar] = usePerfilLocal();
  const [nome, setNome] = useState(perfil.nome || "");
  const [salvo, setSalvo] = useState(false);
  const [base, setBase] = useState(null);
  const [protegido, setProtegido] = useState(false);
  const [token, setToken] = useState(perfil.token || "");
  const [tokenSalvo, setTokenSalvo] = useState(false);
  const [agente, setAgente] = useState(null);
  useEffect(() => {
    api.panorama().then(setBase).catch(() => {});
    api.acesso().then((a) => setProtegido(a.protegido)).catch(() => {});
    api.metricasAgente().then(setAgente).catch(() => {});
  }, []);
  const num = (n, casas = 1) => (n == null ? "—" : Number(n).toFixed(casas).replace(".", ","));

  return (
    <div className="config">
      <div className="pagina-topo">
        <div>
          <h1>Configurações</h1>
          <p className="mudo">Preferências deste navegador. O BoaPauta não tem login e não guarda dados pessoais no servidor.</p>
        </div>
      </div>

      <section className="config-bloco">
        <h2>Como a gente te chama?</h2>
        <form onSubmit={(e) => { e.preventDefault(); salvar({ ...perfil, nome: nome.trim() }); setSalvo(true); }}>
          <label htmlFor="nome">Nome para a saudação</label>
          <div className="linha-form">
            <input id="nome" value={nome} onChange={(e) => { setNome(e.target.value); setSalvo(false); }} placeholder="Seu nome" maxLength={40} />
            <button className="btn primario">Salvar</button>
          </div>
          {salvo && <p className="mudo pequeno">Salvo neste navegador. Aparece no histórico das peças que você aprovar ou ajustar.</p>}
        </form>
      </section>

      {protegido && (
        <section className="config-bloco">
          <h2>Senha de acesso</h2>
          <form onSubmit={(e) => { e.preventDefault(); salvar({ ...perfil, token: token.trim() }); setTokenSalvo(true); }}>
            <label htmlFor="token">Este servidor pede senha para criar, ajustar e aprovar peças</label>
            <div className="linha-form">
              <input id="token" type="password" value={token} onChange={(e) => { setToken(e.target.value); setTokenSalvo(false); }} placeholder="Senha" autoComplete="current-password" />
              <button className="btn primario">Salvar</button>
            </div>
            {tokenSalvo && <p className="mudo pequeno">Salva neste navegador.</p>}
          </form>
        </section>
      )}

      <section className="config-bloco">
        <h2>Desempenho do agente</h2>
        {!agente ? <p className="mudo">Carregando…</p> : !agente.execucoes ? <p className="mudo">Ainda não há peças geradas.</p> : (
          <dl className="config-lista">
            <dt>Execuções</dt><dd>{agente.execucoes} ({agente.criativos} criativos, {agente.chamadas_llm} chamadas a modelos)</dd>
            <dt>Tempo por peça</dt><dd>{num(agente.latencia_mediana_s, 0)} s no meio; 9 em cada 10 em até {num(agente.latencia_p90_s, 0)} s</dd>
            <dt>Conferências</dt><dd>{Math.round((agente.primeira_tentativa_pct || 0) * 100)}% passam de primeira; média de {num(agente.tentativas_media, 2)} tentativas</dd>
            <dt>Nota do avaliador</dt><dd>{num(agente.nota_media_juiz)} em média</dd>
            <dt>Reescrita pelo avaliador</dt><dd>{agente.juiz.precisaram_de_reescrita
              ? `${agente.juiz.precisaram_de_reescrita} peças reescritas; nota ${num(agente.juiz.nota_media_antes)} → ${num(agente.juiz.nota_media_depois)}`
              : "nenhuma peça precisou até agora"}</dd>
          </dl>
        )}
      </section>

      <section className="config-bloco">
        <h2>Sobre a base</h2>
        {!base ? <p className="mudo">Carregando…</p> : (
          <dl className="config-lista">
            <dt>Posts analisados</dt><dd>{fmtNum(base.kpis.posts)} de {base.kpis.perfis} perfis (Instagram e YouTube)</dd>
            <dt>Última coleta</dt><dd>{fmtData(base.kpis.coletado_em, { day: "2-digit", month: "long", year: "numeric" })}</dd>
            <dt>Ranking</dt><dd>Posts de até 6 meses (com 14 dias ou mais), com pelo menos 150 curtidas e dentro do escopo: orientam o empreendedor, sem receita, política, raça, gênero, religião ou polêmica</dd>
            <dt>Fontes</dt><dd>Instagram Graph API (Business Discovery) e YouTube Data API v3, sem scraping</dd>
            <dt>IA</dt><dd>Uma IA escreve os posts e outra, de outra empresa, avalia; uma terceira assiste aos vídeos. Nenhum número é escrito por IA.</dd>
          </dl>
        )}
      </section>
    </div>
  );
}
