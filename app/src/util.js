export const SEGMENTOS = {
  alimentacao: "Alimentação",
  artesanato_producao: "Artesanato e produção",
  beleza_estetica: "Beleza e estética",
  comercio_bairro: "Comércio de bairro",
  moda_acessorios: "Moda e acessórios",
  pets: "Pets",
  transporte_entregas: "Transporte e entregas",
  servicos: "Serviços",
  financas: "Finanças",
  vendas: "Vendas",
  marketing: "Marketing",
  gestao: "Gestão",
  empreendedorismo: "Empreendedorismo",
  geral: "Geral",
  todos: "Todos os segmentos",
};
export const nomeSegmento = (s) => (s ? SEGMENTOS[s] || s.replaceAll("_", " ") : "Todos os segmentos");

export const FORMATOS = { reels: "Reels", carrossel: "Carrossel", stories: "Stories", shorts: "Shorts", short: "Short", video: "Vídeo", imagem: "Imagem" };
export const nomeFormato = (f) => FORMATOS[f] || f;

// Como cada formato chama as partes do corpo
export const PARTE = { reels: "Cena", shorts: "Cena", carrossel: "Slide", stories: "Tela" };

export const STATUS = {
  revisar: { rotulo: "Para revisar", cls: "st-revisar" },
  aprovada: { rotulo: "Aprovada", cls: "st-aprovada" },
  ajuste: { rotulo: "Ajuste pendente", cls: "st-ajuste" },
  falhou: { rotulo: "Não gerou", cls: "st-falhou" },
};

export const CONFERENCIAS = {
  referencias_existem: "Baseado em posts reais da base",
  caso_concreto: "Parte de um caso concreto",
  sem_contas: "Sem contas nem fórmulas",
  cta_presente: "Termina com um próximo passo claro",
  sem_promessa_exagerada: "Sem promessas exageradas",
  fiel_a_oferta: "Fiel ao que o Impulso oferece",
  linguagem_simples: "Linguagem simples",
  tamanho_do_formato: "Tamanho certo para o formato",
};

export const CRITERIOS = {
  aderencia_aos_padroes: "Segue o que engaja",
  proximo_passo_claro: "Próximo passo claro",
  tom_impulso: "Tom do Impulso",
  clareza_para_o_publico: "Clareza",
  fidelidade_a_oferta: "Fiel à oferta",
  concretude: "Concreto",
  profundidade: "Profundidade",
};

export const DIMENSOES = [
  // [chave, nome, o que mede, rótulo curto para colunas e barras] · mesmos nomes do Playbook
  ["consistencia", "Consistência", "engaja acima da própria média com frequência", "Consistência"],
  ["conversa", "Conversa", "comentários em relação às curtidas", "Conversa"],
  ["autenticidade", "Autenticidade", "aparece o dono do negócio ou o negócio de verdade", "Autenticidade"],
  ["marca", "Combina com a marca", "temas próximos dos pilares do Impulso", "Marca"],
  ["frequencia", "Frequência", "posta com regularidade", "Frequência"],
];

export const fmtData = (iso, o = { day: "2-digit", month: "2-digit" }) =>
  iso ? new Date(iso.length === 10 ? iso + "T12:00:00" : iso).toLocaleDateString("pt-BR", o) : "";

export const fmtNum = (n) => (n == null ? "—" : Number(n).toLocaleString("pt-BR"));
export const vezes = (x) => (x == null ? "só no top" : `${x.toFixed(1).replace(".", ",")}×`);   // sem lift: 0% nos demais

export const linkPerfil = (c) =>
  c.plataforma === "instagram" ? `https://www.instagram.com/${c.username || c.perfil}/` : `https://www.youtube.com/channel/${c.perfil}`;

export const FAIXAS = { nano: "nano", micro: "micro", medio: "médio", grande: "grande", mega: "mega" };

// As falhas do verificador são escritas para orientar o modelo; aqui viram frase para a equipe
export const falhaLegivel = (f) =>
  String(f).replace(/clareza=([\d.,]+) abaixo de ([\d.,]+)/i, (_, v, m) => `texto um pouco difícil de ler (clareza ${Math.round(Number(v))}, o mínimo é ${Math.round(Number(m))})`);
