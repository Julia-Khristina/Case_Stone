import { useEffect, useState } from "react";
import { api } from "./api.js";
import { Erro, Modal } from "./ui.jsx";
import { fmtData, nomeFormato } from "./util.js";

export function Guia({ inicio, onClose }) {
  const [semana, setSemana] = useState(null);
  const [historico, setHistorico] = useState([]);
  const [atual, setAtual] = useState(null);
  const [gerando, setGerando] = useState(false);
  const [erro, setErro] = useState(null);
  useEffect(() => {
    api.semanaGuia(inicio).then(setSemana).catch(setErro);
    api.guias().then((l) => {
      setHistorico(l);
      const daSemana = l.find((pb) => pb.inicio === inicio);
      if (daSemana) setAtual(daSemana);
    }).catch(() => {});
  }, [inicio]);
  async function gerar() {
    setGerando(true);
    setErro(null);
    try {
      const pb = await api.gerarGuia(semana?.inicio);
      setAtual(pb);
      setHistorico((h) => [pb, ...h]);
    } catch (e) {
      setErro(e);
    }
    setGerando(false);
  }
  return (
    <Modal
      titulo="Guia detalhado da semana"
      largo
      onClose={gerando ? () => {} : onClose}
      rodape={
        <>
          <span className="rodape-nota">A Stone envia pela própria ferramenta de e-mail. O BoaPauta não guarda endereços.</span>
          {atual && <a className="btn" href={api.guiaUrl(atual.id)} download={`guia_detalhado_${atual.inicio}.html`}>Baixar HTML</a>}
          <button className="btn primario" onClick={gerar} disabled={gerando || !semana?.pecas.length}>
            {gerando ? "Escrevendo…" : atual && atual.inicio === semana?.inicio ? "Gerar de novo" : "Gerar guia"}
          </button>
        </>
      }
    >
      <p className="mudo">
        Toda sexta, o conteúdo das peças aprovadas na semana vira um e-mail aprofundado para os empreendedores:
        passo a passo, exemplo prático, erro comum e como o Impulso ajuda. Cada seção passa pelas mesmas conferências dos criativos.
      </p>
      {semana && (
        <div className="por-que">
          <b>Semana de {fmtData(semana.inicio)} a {fmtData(semana.fim)}: {semana.pecas.length} peça(s) aprovada(s)</b>
          {semana.pecas.length ? (
            <ul>{semana.pecas.map((p) => <li key={p.id}>{p.titulo} <span className="mudo">({nomeFormato(p.formato)})</span></li>)}</ul>
          ) : (
            <p className="mudo">Aprove ao menos uma peça desta semana no Planejamento para gerar o guia.</p>
          )}
        </div>
      )}
      <Erro erro={erro} />
      {gerando && <div className="aviso gerando"><span className="giro" /> Escrevendo e conferindo cada seção…</div>}
      {atual?.secoes?.some((s) => s.pendencias?.length) && (
        <div className="aviso">
          Revisar antes de enviar: {atual.secoes.filter((s) => s.pendencias?.length).map((s) => `“${s.titulo}” (${s.pendencias.join("; ").replace("clareza=", "clareza ")})`).join("; ")}.
          O texto ficou um pouco abaixo do alvo de clareza mesmo depois das reescritas.
        </div>
      )}
      {atual?.falhas?.length > 0 && (
        <div className="aviso">Ficaram de fora por não passar nas conferências: {atual.falhas.map((f) => f.post).join("; ")}.</div>
      )}
      {atual && (
        <>
          <p className="mudo pequeno">
            Prévia do guia de {fmtData(atual.inicio)} a {fmtData(atual.fim)}, gerado em {new Date(atual.gerado_em).toLocaleString("pt-BR")}
            {historico.length > 1 ? ` · ${historico.length} versões guardadas` : ""}
          </p>
          <iframe className="previa-email" title="Prévia do guia" src={api.guiaUrl(atual.id)} />
        </>
      )}
    </Modal>
  );
}
