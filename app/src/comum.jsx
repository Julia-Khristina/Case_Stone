import { useState } from "react";
import { nomeFormato, vezes } from "./util.js";

const NOMES = {
  tema_principal: "tema", tipo_hook: "gancho", tipo_cta: "chamada", convite_participacao: "convite a participar",
  mensagem_generica: "frase motivacional", tipo: "formato",
  quem_aparece: "quem aparece", gancho_visual: "começo do vídeo", cenario: "cenário", rosto_nos_3s: "rosto nos 3 primeiros segundos",
  fala_nos_3s: "fala nos 3 primeiros segundos", texto_na_tela_inicio: "texto na tela logo no início",
  legendas_queimadas: "fala escrita na tela", cta_no_final: "chamada no final",
};
const VALORES = {
  financas: "finanças", dor: "dor do cliente", historia_de_empreendedor: "história de empreendedor",
  receita_ou_tecnica: "ensinar a fazer", seguir: "pedir para seguir", link: "mandar para um link", imagem: "imagem estática",
  casa: "em casa", negocio_real: "no negócio de verdade", estudio: "em estúdio", escrito: "só escrita", falado: "falada",
  ambos: "falada e escrita", cena_encenada: "cena encenada", rosto_falando: "rosto falando", dono_do_negocio: "dono do negócio",
  bastidor_do_negocio: "bastidor do negócio", texto_grande: "texto grande",
};
export const rotuloPadrao = (p) =>
  p.valor === "True"
    ? NOMES[p.caracteristica] || p.caracteristica
    : `${NOMES[p.caracteristica] || p.caracteristica} “${VALORES[p.valor] || p.valor.replaceAll("_", " ")}”`;

export function RefCard({ r }) {
  const trecho = r.titulo_ou_trecho || r.trecho || "";
  const [semCapa, setSemCapa] = useState(false);
  const capa = r.capa || (r.post_id ? `/api/capas/${r.post_id}.jpg` : null);
  return (
    <a className="ref" href={r.link} target="_blank" rel="noreferrer">
      {capa && !semCapa && (
        <div className="ref-capa">
          <img src={capa} alt="" loading="lazy" onError={() => setSemCapa(true)} />
          <span className="ref-formato">{r.plataforma === "youtube" ? "YouTube" : "Instagram"} · {nomeFormato(r.formato)}</span>
        </div>
      )}
      <div className="ref-topo">
        <b>@{r.perfil}</b>
        {(semCapa || !capa) && <span className="mudo">{r.plataforma === "youtube" ? "YouTube" : "Instagram"} · {nomeFormato(r.formato)}</span>}
      </div>
      <p>{trecho.length > 150 ? trecho.slice(0, 150) + "…" : trecho}</p>
      {r.lift_perfil != null && <span className="ref-lift">{vezes(r.lift_perfil)} a média do perfil</span>}
    </a>
  );
}
