# BoaPauta

O que engaja o empreendedor vira post do Impulso Stone.

O BoaPauta analisa posts públicos de Instagram e YouTube que falam com micro e pequenos empreendedores (MPEs), descobre o que diferencia os posts que mais engajam e usa isso para:

- propor e escrever posts curtos para o **@impulsostone** ou para a **@stone** (Reels, carrossel, Stories, Shorts), cada conta com a sua oferta, sempre citando os posts reais em que se apoiam;
- montar uma agenda com datas comemorativas (calculadas para qualquer ano), orientações práticas, ferramentas da semana, rodízio de segmentos e horários de referência;
- indicar criadores para parceria (2 transversais + 3 setoriais, com reservas), com nota explicada;
- gerar o **Playbook de conteúdo para a Stone**: o que engaja, o que evitar, formatos recomendados, perfis em destaque, exemplos reais e os criativos aprovados prontos para produção;
- gerar o **guia detalhado da semana**, um e-mail para o empreendedor que aprofunda o assunto das peças aprovadas.

Projeto individual Stone × Inteli Academy. Entrega: 24/11/2026.

Arquitetura e decisões em detalhe: [docs/arquitetura.html](docs/arquitetura.html).

## Estado

Tudo abaixo roda com dados e modelos reais (nenhum dado simulado no app). Os testes automáticos usam um LLM falso só para não gastar cota.

| Parte | Estado |
|---|---|
| Descoberta de perfis (busca no YouTube → @ do Instagram na descrição, API oficial) | Pronta. 56 perfis aprovados em revisão humana; recusas registradas em `config/perfis_recusados.csv` |
| Coleta: Instagram (Graph API, Business Discovery) e YouTube (Data API v3) | Rodada em 22/11/2026: 4.043 posts de 55 perfis, com limitador de chamadas e retomada |
| Camada 0: métricas, top 10% por plataforma e faixa (e por formato no YouTube), grupo controle | Pronta: 3.352 posts elegíveis, 740 dentro do escopo, 68 top e 67 controle (janela de 6 meses) |
| Filtro de escopo (orienta o empreendedor, 150+ curtidas, sem tema sensível) | Pronto em 24/11/2026: termos sensíveis + classificador de IA + tema da camada 1 + piso de curtidas |
| Camada 1: rótulos de texto (Groq) | Pronta: 135 de 135 posts do top e do controle |
| Camada 2: vídeo, imagem e áudio (Gemini) | Versão 3 (24/11/2026), com música, volume, tom e ritmo da fala, qualidade do áudio e efeitos: 126 de 135 posts. Ficaram fora 9 Reels com música licenciada (a API não entrega o arquivo). Links do Instagram renovados antes da análise (`scripts/renovar_midia.py`) |
| Padrões top × controle (lift, intervalo de 90%, mínimo de 3 perfis) | Pronta |
| Agente (LangGraph): proposta sem LLM, geração a partir de um caso concreto, 8 conferências, reescrita, juiz e reescrita guiada pelo juiz, para as duas contas | Pronto e testado ao vivo |
| Servidor MCP (`run_agent`, `padroes`, `posts_de_referencia`, `pecas_aprovadas`) | Pronto e testado pelo protocolo MCP |
| Scorecard de criadores e indicação | Pronta |
| Agenda | Pronta |
| App React (Planejamento, Peças, Insights, Criadores) + API FastAPI | Pronto e testado ponta a ponta no navegador |
| Playbook de conteúdo para a Stone (HTML, sem LLM) | Pronto (`scripts/gerar_playbook.py` ou botão em Insights); precisa de 5 peças aprovadas para fechar a seção de criativos |
| Guia detalhado da semana (e-mail ao empreendedor) | Pronto e testado ao vivo (Groq), com reescrita quando a seção não passa nas conferências |
| Camada 3: validação humana dos rótulos (kappa) | Planilha de 52 posts às cegas e página de preenchimento prontas; falta preencher |
| Calibração do avaliador com notas humanas | Planilha das peças avaliadas e comparação prontas; falta preencher |
| Testes | Unidade, integração (API e MCP pelo protocolo) e ponta a ponta no navegador (Playwright); CI no GitHub Actions |

## Como rodar

```bash
python -m venv .venv && .venv\Scripts\activate      # Linux/macOS: . .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium                # slides do carrossel em PNG
cp .env.example .env                                 # preencha as chaves (o .env nunca vai para o git)
python -m pytest                                     # testes sem rede e sem chave
```

Com Docker (API + app num container; os dados ficam na pasta `data/` da máquina, montada como volume):

```bash
docker compose up --build                            # http://localhost:8000
```

Dados internos da Stone (persona e CTR dos anúncios do Impulso) ficam em `config/stone_interno.yaml`, **fora do git**; o modelo vazio é `config/stone_interno.exemplo.yaml`. Sem o arquivo, tudo funciona, só sem esses dados. O banco do app (`data/app/`) e o playbook gerado (`docs/playbook_stone.html`, que traz o CTR interno) também ficam fora do git.

### App

```bash
cd app && npm install && npm run build && cd ..     # uma vez (ou depois de mudar o front)
python -m src.api                                    # http://localhost:8000
```

Eventos ao vivo: `POST /api/pecas/ao-vivo` e `POST /api/pecas/{id}/ajuste/ao-vivo` transmitem cada etapa do agente (`text/event-stream`: dados, escrevendo, rascunho, conferencias, avaliando, juiz, pronto ou erro).

Fotos dos criadores: `python scripts/baixar_fotos.py` (APIs oficiais; ficam em `data/fotos/`, fora do git).

**Acesso.** Em uso local, o app não pede senha. Para colocar num servidor, defina `BOAPAUTA_TOKEN` no `.env`: criar, ajustar e aprovar peças passam a exigir a senha (a equipe informa em Configurações); a leitura continua aberta. `BOAPAUTA_GERACOES_POR_MINUTO` (padrão 6) limita as gerações com modelo de linguagem para um clique repetido não esgotar a cota. O nome informado em Configurações vai para o histórico de cada peça ("Aprovada por …").

Para desenvolver o front com recarga automática: `python -m src.api` num terminal e `cd app && npm run dev` em outro (http://localhost:5173, com proxy para a API). Documentação da API: http://localhost:8000/docs.

O app é organizado pelo trabalho da equipe (menu à esquerda):

- **Planejamento** (página inicial): o calendário de conteúdo ocupa a tela (mês = semana atual + 4 seguintes, ou semana), com as sugestões da agenda (datas comemorativas, rodízio de segmentos e horários de referência) e as peças já criadas. Tocar numa sugestão, num dia livre ("+ post") ou em "Novo post" abre o **painel lateral**, que desliza sobre o calendário desfocado. À esquerda do painel fica a conversa (guiada por regras, sem IA); à direita, o palco: sugestão → proposta (formato, padrões que engajam e posts reais de base, ainda sem IA) → IA ao vivo (o que veio da base, o caso, o rascunho, as conferências passando ou falhando, a reescrita, o avaliador e a prévia do carrossel) → peça pronta. Ali mesmo se aprova ou se pede ajuste em linguagem livre (gera nova versão e guarda a anterior). Datas como "05/12" na conversa marcam o post na agenda. O modelo só roda ao criar ou ajustar.
- **Busca** (Planejamento e Peças): sem diferenciar acento e maiúscula, com sinônimos ("décimo terceiro" acha "13º", "imposto" acha o DAS, "promoção" acha liquidação e Black Friday). No Planejamento, um contador mostra quantos itens casam nas semanas da tela, e os resultados dos próximos 6 meses aparecem logo acima do calendário, com um clique para ir até eles.
- **Peças** (`#/pecas`): a fila de trabalho em colunas (pra revisar, aprovadas, sem data ou com problema), com nota do avaliador em cada cartão. Cada cartão abre o mesmo painel lateral. No topo, o **Guia detalhado da semana** gera o e-mail de sexta para os empreendedores a partir das peças aprovadas.
- **Insights** (`#/insights`): todos os achados em frase simples, com "Ver exemplos", e os formatos que estão engajando. No topo, o botão do **Playbook de conteúdo** abre ou baixa o documento para a Stone.
- **Configurações**: nome (para a saudação e o histórico das peças), senha de acesso quando o servidor pede, dados da base e **desempenho do agente** (tempo por peça, conferências de primeira, nota média do avaliador e efeito da reescrita guiada por ele).
- **Criadores**: indicados com reserva, composição ajustável, lista de contato, tabela com todos os perfis e página de cada um explicando a nota.

Os endereços antigos (`#/agenda`, `#/achados`, `#/inicio`) redirecionam para as páginas novas.

### Pipeline de dados

```bash
python scripts/descobrir_perfis.py --fonte youtube   # sugere perfis; nunca sobrescreve config/perfis.csv
python scripts/aprovar_perfis.py                     # leva os aprovados para config/perfis.csv
python scripts/coletar.py --esperar                  # coleta (retoma de onde parou se bater o limite da Meta)
python scripts/calcular_metricas.py                  # camada 0 (coleta mais recente; --jsonl data/raw/<data> para outra)
python scripts/camada1.py --coleta data/raw/<data>   # rótulos de texto
python scripts/camada2.py --coleta data/raw/<data>   # rótulos de vídeo e imagem (--amostra para testar)
python scripts/preparar_validacao.py && python scripts/validar_rotulos.py   # camada 3 (kappa)
```

**Atualização semanal.** `python scripts/atualizar_base.py` roda tudo na ordem (coleta, métricas, capas, camadas 1 e 2 só nos posts novos, contas da Stone, playbook) e registra cada etapa em `data/processed/atualizacao.log`; uma etapa que falha (cota do Gemini, por exemplo) não impede as seguintes. `python scripts/atualizar_base.py --agendar` registra a tarefa no Agendador do Windows (segunda às 6h, ou assim que o computador ligar). O app recarrega a base sozinho quando a coleta ou as análises mudam, sem reiniciar o servidor.

Os dados ficam em JSONL e CSV (`data/`) e o estado do app em SQLite. A camada PostgreSQL herdada do Case Suno não era usada e foi arquivada fora do repositório.

**Validação humana** (camada 3 e calibração do avaliador):

```bash
python scripts/calibrar_juiz.py preparar             # planilha com as peças que o avaliador já pontuou
python scripts/pagina_validacao.py                   # data/validacao/validacao.html: formulário no navegador
python scripts/validar_rotulos.py                    # kappa por campo, rótulos da IA × pessoa
python scripts/calibrar_juiz.py comparar             # erro médio, Spearman e viés do avaliador por critério
```

A página salva o progresso no navegador e baixa as planilhas preenchidas (salve por cima das de `data/validacao/`). Na calibração, a pessoa dá a nota sem ver a do avaliador; um viés positivo grande indica avaliador generoso demais (até agora ele deu 10 em quase tudo), e aí se ajustam as âncoras da rubrica ou `juiz_media_minima`.

**Medir o retorno do avaliador:** `python scripts/medir_juiz.py --rodar 8` gera 8 peças reais e resume quantas precisaram de reescrita guiada pelo avaliador e quanto a nota mudou.

### Contas da Stone e Playbook de conteúdo

```bash
python scripts/contas_stone.py coletar               # @stone e @impulsostone pela Graph API (config/contas_stone.csv)
python scripts/contas_stone.py texto                 # camada 1 nos posts das contas
python scripts/contas_stone.py visual                # camada 2 (para sozinha quando a cota do Gemini acaba)
python scripts/contas_stone.py insights              # alcance, salvamentos e compartilhamentos (precisa de acesso)
```

**Insights das contas da Stone.** Alcance, salvamentos e compartilhamentos só vêm com o token de quem administra cada conta (permissão `instagram_manage_insights`). Com `STONE_IG_TOKEN_STONE` e `STONE_IG_TOKEN_IMPULSOSTONE` no `.env`, a etapa `insights` coleta esses números e as métricas ganham o engajamento sobre o alcance (`er_alcance`). Sem os tokens, a análise segue com curtidas e comentários.

As contas da Stone ficam **fora** da base de referência (`data/contas_stone/` e `data/processed/contas_stone/`): se entrassem em `config/perfis.csv`, mudariam o top e o grupo de comparação dos 55 perfis. Elas passam pelas mesmas métricas e prompts e são comparadas com o nicho ([src/analysis/contas_stone.py](src/analysis/contas_stone.py)): engajamento contra perfis da mesma faixa, mistura de formatos, lacunas em relação aos achados do nicho e o que rende acima ou abaixo da mediana da própria conta (grupos com 4 posts ou mais). Coleta de 23/11/2026: @stone (711 mil seguidores, 55 posts elegíveis) e @impulsostone (4,4 mil, 37 posts); vídeo analisado em 46 dos 92 posts (o Instagram não entregou o arquivo de parte dos Reels).

#### Gerar o Playbook

```bash
python scripts/gerar_playbook.py                     # → docs/playbook_stone.html (abre offline, imprime em PDF)
```

Painel em abas (**@impulsostone**, **@stone** e **Nicho**; os criativos aparecem na aba da conta para a qual foram escritos), um HTML único que abre offline, com capas e slides embutidos. Cada aba mostra os números da conta contra o nicho, os 3 movimentos principais (com barras "na conta × no top do nicho", régua de quanto rende na própria conta e capas dos posts de referência), formatos, os posts da conta que mais renderam e, no Impulso, os criativos aprovados em formato de celular; o resto fica recolhido. Conteúdo: resumo por conta, diagnóstico e recomendações de cada uma (com a base de cada recomendação e posts de referência do nicho), como ler os números, o que engaja (com lift, intervalo de 90% e posts de exemplo), o que evitar (incluindo o histórico de anúncios do Impulso, fonte interna), formatos recomendados, perfis em destaque, exemplos reais, criativos aprovados prontos para produção (com os posts em que se apoiam e a nota do avaliador), horários de referência e limites da análise. Nenhum texto é escrito por modelo de linguagem: tudo sai da base, e os criativos são as peças aprovadas no app. Com o app no ar, `GET /api/playbook.html` gera a versão do momento.

### Servidor MCP

```json
{"mcpServers": {"boapauta": {"command": "python", "args": ["-m", "src.servidor_mcp"], "cwd": "<pasta do projeto>"}}}
```

Ferramentas: `run_agent` (o contrato do agente, com `conta` = impulsostone ou stone), `padroes`, `posts_de_referencia` e `pecas_aprovadas`.

#### Levar as peças para o Canva

`pecas_aprovadas` entrega cada peça aprovada pronta para produção: título, caso, uma parte por slide ou cena (com o texto de tela), legenda, chamada, nota do avaliador, quem aprovou e, nos carrosséis, os PNGs já no visual da marca.

1. Num assistente de IA que aceite vários servidores MCP (por exemplo, o Claude no computador), conecte o servidor do BoaPauta (configuração acima) e o conector oficial do Canva.
2. Peça: "Pegue as peças aprovadas do @impulsostone no BoaPauta e monte cada carrossel no Canva, um slide por parte".
3. O assistente lê as peças pelo BoaPauta e cria os designs pelo conector do Canva; a equipe revisa no Canva antes de publicar.

O BoaPauta não guarda credencial do Canva: a conexão é do assistente, com a conta de quem usa.

### Configurar a Graph API

1. Converta uma conta do Instagram para profissional e vincule a uma página do Facebook.
2. Em developers.facebook.com, crie um app do tipo Business com o produto Instagram (login do Facebook).
3. Gere um token com `instagram_basic`, `pages_show_list`, `pages_read_engagement`, `business_management` e `instagram_manage_insights` (sem as duas últimas, o Business Discovery devolve o erro `#10`).
4. Estenda o token no Depurador de token (cerca de 60 dias; o do Explorer dura 1 hora).
5. Pegue o ID em `GET /me/accounts` → página → `instagram_business_account` e preencha `META_ACCESS_TOKEN` e `META_IG_USER_ID`.
6. Em modo de desenvolvimento, o limite é de cerca de 200 chamadas por hora; o coletor para sozinho e retoma depois.

## Como funciona

1. **Coleta**: 90 dias de posts de cada perfil aprovado, pelas APIs oficiais.
2. **Camada 0**: taxa de engajamento = (curtidas + comentários) ÷ seguidores; lift = quanto o post superou a média do próprio perfil. O top é o 10% de cada plataforma e faixa de seguidores (no máximo 5 posts por perfil); o grupo controle tem o mesmo tamanho e é sorteado com semente fixa.
3. **Camada 1** (Groq): tema, gancho, chamada para ação, tom, convite a participar, frase genérica, publi.
4. **Camada 2** (Gemini): quem aparece, rosto e fala nos 3 primeiros segundos, texto na tela, cenário, produção, chamada final, tom de voz. Protocolo único para qualquer vídeo (Short, Reels, vídeo longo): capa + início (0–5 s) + 5 s do meio + últimos 5 s; vídeo com menos de 15 s vai inteiro. Vários posts vão no mesmo pedido, cada um identificado, porque o plano gratuito limita pedidos por dia (20), não tokens.
5. **Padrões**: cada característica é comparada entre top e controle. Só vira achado com lift acima de 1,1 (ou abaixo de 0,9), intervalo de confiança coerente e presença em pelo menos 3 perfis; o resto aparece como "inconclusivo" ou "concentrado em poucos perfis".
6. **Agente**: a proposta usa só a base. A geração (Groq, `gpt-oss-120b`) parte de um **caso concreto** (um pequeno negócio, a dor específica, o que acontece se nada mudar) e lê o conteúdo completo dos posts de referência (legenda, o que se vê e as primeiras falas da camada 2). Para o @impulsostone, escreve com a oferta do programa (educação, mentoria, comunidade); para a @stone, com a oferta da marca (maquininha, conta, link de pagamento e crédito mediante análise, sem citar taxa nem condição). Passa por 8 conferências determinísticas (referências reais, caso concreto, chamada clara, sem promessa, fiel à oferta da conta, sem contas nem fórmulas, clareza, tamanho), até 2 reescritas e um juiz de outra família de modelo (`qwen3.8-27b`) com rubrica de 7 critérios, incluindo **profundidade**: conselho óbvio sem o como fazer tira no máximo 4. Tudo fica registrado em `data/processed/agent_runs.jsonl`.
7. **Retorno do juiz** ([src/agent/melhoria.py](src/agent/melhoria.py)): se o juiz reprova ou dá menos de 7 em algum critério, o agente reescreve uma vez com o retorno dele (critério, nota, justificativa e trecho), o juiz avalia de novo e fica a versão melhor. A reescrita só é aceita se subir a média sem criar um critério fraco novo; se a cota do modelo acabar no meio, fica a original. Antes e depois ficam em `agent_runs.jsonl`; `python scripts/medir_juiz.py` resume quanto o retorno do juiz melhorou os criativos.
8. **Revisão humana**: nada é publicado sem "Aprovar"; cada ajuste guarda a versão anterior e o motivo.

## Limpeza de escopo (24/11/2026)

A validação humana encontrou no top posts fora da proposta do TAPI: receitas, política, entretenimento e posts com poucas dezenas de curtidas (27% do top fora do tema; 43% com menos de 100 curtidas). O ranking passou a considerar só posts **dentro do escopo** ([src/analysis/escopo.py](src/analysis/escopo.py), [scripts/escopo.py](scripts/escopo.py)):

1. **Termos sensíveis** (código): política, raça, gênero, religião e polêmica não entram.
2. **Classificador de IA**: "o post orienta o micro empreendedor?" (sim, parcial, não) e "trata de tema sensível?".
3. **Tema** da camada 1: receita ou técnica do ofício e "outro" ficam fora.
4. **Piso de 150 curtidas**, perto da média por post da @stone; abaixo disso o post não concorre (nem ao top nem ao controle, para a comparação continuar justa).

Os posts fora do escopo continuam nas médias do nicho (a comparação das contas da Stone não muda); só não concorrem ao ranking. Para manter amostra com o piso, a janela do ranking passou de 90 dias para os 6 meses coletados; as referências do agente dão peso à recência (meia-vida de 45 dias). O controle passou a ser um sorteio estável por post (semente + id), para que tirar um post não embaralhe os demais.

| | Antes | Depois |
|---|---|---|
| Posts no top | 165 | 68 (19 perfis) |
| Mediana de curtidas no top | 214 | 3.300 |
| Top com menos de 100 curtidas | 71 | 0 |
| Top fora do tema (receita, "outro") | 45 | 0 |

Ficaram fora do escopo 2.612 posts elegíveis: 2.260 por poucas curtidas, 98 de receita ou técnica, 97 de tema "outro", 97 com tema sensível e 60 que não orientam o empreendedor. `python scripts/relatorio_escopo.py` refaz o antes × depois.

## Achados principais (base limpa, 24/11/2026)

| Plataforma | Achado | Lift | Perfis |
|---|---|---|---|
| Instagram | Música de fundo, baixa, por baixo da fala | 7,0× (volume baixo: 6,0×) | 4 |
| Instagram | Fala em tom calmo e acolhedor | 7,0× | 4 |
| Instagram | Gravado no negócio de verdade | 6,0× | 4 |
| Instagram | Gancho de promessa | aparece menos no top | 6 |
| YouTube | Tema finanças | 2,1× | 5 |
| YouTube | Música baixa, por baixo da fala | 1,4× | 10 |
| YouTube | Chamada pedindo para comentar | só no top (0% no controle) | 4 |
| YouTube | Chamada para link | aparece menos no top | 7 |

**Leitura com cautela**: os achados do Instagram vêm de 22 posts do top com vídeo, em 4 perfis: sinais fortes, mas com intervalo largo, a confirmar com mais coletas. Os do YouTube (até 10 perfis) são mais sólidos. Os campos de áudio são novos e ainda não passaram pela verificação de concordância feita com os campos visuais.

**Tensão para discutir com a Stone**: a frase motivacional genérica engaja no orgânico, mas o histórico de anúncios da Stone mostra que ela não gera clique. O BoaPauta não a usa para gerar peças.

## Decisões

| Decisão | Motivo |
|---|---|
| Instagram pela Graph API, sem scraping | O TAPI (4.3) exclui scraping e rotas que violam os Termos de Uso |
| Descoberta pelo YouTube | A Graph API remove as menções (@) das legendas de terceiros; as descrições do YouTube trazem o @ do Instagram |
| Proposta antes de gerar | O modelo de linguagem só roda com o "ok" da equipe: nenhum token gasto em ideia descartada |
| Mesmo recorte de vídeo para todos os formatos | Comparação top × controle justa entre Short, Reels e vídeo longo; 3 a 5 vezes menos tokens por post |
| Groq para texto, Gemini para vídeo | O cliente Groq do Case Suno já controla cota, cache e repetição; o Gemini lê vídeo e link do YouTube direto |
| App em React + FastAPI | Poucas páginas com modais e subpáginas; a API é a mesma que o servidor MCP usa |
| Estado do app em SQLite | Peças, versões, decisões e guias detalhados; vem com o Python e não exige servidor |
| Janela de 6 meses no ranking, posts com 14+ dias | Com o filtro de escopo e o piso de curtidas, 90 dias deixavam o top pequeno demais; a recência pesa na escolha das referências. Meta: voltar a 4–8 semanas quando as coletas semanais acumularem |
| Filtro de escopo antes do ranking | O top precisa ser referência para o micro empreendedor: sem receita, entretenimento, política, raça, gênero, religião ou polêmica, e com engajamento real (150+ curtidas) |
| Top por plataforma e faixa | A taxa de engajamento cai quando os seguidores sobem; misturar faixas favoreceria só os pequenos |
| Duas listas de criadores | A amostra de análise (variada, para aprender) é diferente dos indicados (saem da amostra depois da análise) |
| Taxonomia em dois eixos | Tipo (transversal ensina qualquer MPE; setorial é dono de um tipo de negócio) e macrossetor de lista fechada |
| Datas da agenda por tipo e fase | Cada data tem um tipo (venda no dia, temporada, obrigação, comunidade, feriado) e fases no tempo: o Natal vai de preço e estoque a última hora, agradecimento no dia e trocas depois; feriado ganha aviso de horário na véspera e não tem post de venda; DAS do MEI entra todo dia 20. As datas ativas revezam (antes, o 13º sumia atrás da Black Friday) e a mesma data não repete o texto (`config/datas_comemorativas.yaml`) |
| Dias sem data: orientação e radar de ferramentas | Nos dias sem data, a agenda sugere uma orientação prática (fluxo de caixa, fiado, golpes do Pix…) e, uma vez por semana, uma ferramenta gratuita ou oficial que o empreendedor costuma não usar (WhatsApp Business, Perfil da Empresa no Google, emissor de NFS-e do MEI, Registrato…), com custo e site oficial para a equipe conferir; nada de concorrente da Stone (`config/orientacoes.yaml`) |
| Datas por regra, não por ano | Cada data tem uma regra (dia fixo, dias depois da Páscoa, n-ésimo domingo, quinta de novembro + 1 para a Black Friday); a agenda não vence no fim do ano |
| Uma oferta por conta | O agente escreve para o Impulso (programa) ou para a Stone (produtos); a rubrica e as conferências cobram a oferta certa de cada uma |
| Senha opcional | Uso local sem atrito; publicado, as ações que gastam cota ou mudam dados pedem senha |
| Horários como orientação | Vêm de pesquisas públicas (Opinion Box, Buffer, Sprout Social 2026), não de dados da Stone |
| Guia detalhado sem e-mails guardados | A Stone envia pela própria ferramenta; o HTML traz `{{link_descadastro}}` e `{{link_impulso}}` para ela preencher |

## Base de código: o que veio do Case Suno

| Módulo | Mudança |
|---|---|
| `src/shared/` (cliente de LLM, cache, limites) | Nenhuma além do nome |
| `src/evaluation/judge.py` | Rubrica nova (`rubric_criativo.yaml`); avaliação tolerante a saída fora do formato |
| `src/evaluation/flesch_ptbr.py` | Um alvo único de clareza (`clareza_ok`) |
| `src/rendering/` | Visual Impulso, papéis capa / corpo / cta |
| `src/persistence/` (PostgreSQL) | Arquivada: o projeto usa JSONL, CSV e SQLite |
| `Dockerfile`, `docker-compose.yml` | Refeitos para a API FastAPI + app React (o Streamlit do Case Suno saiu) |

Novo: `src/collection/` (coletores e descoberta), `src/analysis/` (métricas, camadas 1 e 2, padrões, scorecard, indicação, agenda), `src/agent/` (contrato, ferramentas, gerador, verificador, grafo, serviço), `src/playbook.py` (Playbook da Stone), `src/guia.py` (guia detalhado), `src/api.py`, `src/servidor_mcp.py`, `app/`.

## Limitações conhecidas

- **Camada 2 por trechos**: ver só capa, início, meio e fim deixa escapar uma chamada para ação no meio do vídeo e não permite medir o ritmo de cortes (campo retirado). A autenticidade do scorecard usa o vídeo nos perfis com 3 ou mais posts analisados e, nos outros, a aproximação pelo tipo de perfil.
- **Reels com música licenciada**: a Graph API não entrega o vídeo deles (sem `media_url`). Ficaram fora da camada 2 23 Reels (17 do controle, 6 do top); a comparação visual do Instagram vale para Reels sem música licenciada, carrosséis e imagens.
- **Clareza do guia detalhado**: o e-mail usa mínimo de 50 (início da faixa "fácil" da escala de Martins et al.), e os posts, 55. Texto explicativo tem palavras mais longas que uma legenda; a conferência aponta as palavras longas para a reescrita.
- **Vários posts por pedido**: 20 posts foram analisados no protocolo em lote e também um a um (vídeo inteiro). Campos objetivos concordaram de 85% a 100% (kappa 0,56 a 1,00: rosto e fala nos 3 s, texto na tela, cenário, gancho, legenda na tela, chamada no final, quem aparece), sinal de que o lote não mistura posts. **Produção** (kappa 0,35), **tom de voz** (0,23) e **mostra ferramenta** (0,00, classe rara) mudam conforme o modelo vê o vídeo inteiro ou trechos e ficam fora dos achados (`config/limiares.yaml` → `camada2_campos_instaveis`).
- **Vídeos que o Gemini não lê**: um vídeo público do YouTube devolveu 403 e derrubava o lote inteiro; achado por busca binária e listado em `config/camada2_inacessiveis.json`.
- **Conteúdo raso nas primeiras versões**: as peças saíam corretas, mas óbvias ("separe as contas", "defina metas"). Causas: o gerador via só padrões e trechos curtos das referências, e o juiz não punia o óbvio. Correção: caso concreto obrigatório, conteúdo completo das referências, critério de profundidade e gerador no modelo maior.
- **O avaliador automático não confere contas**: num teste, uma peça ensinou "multiplique por 1,2 para 20% de margem" (isso é markup; a margem fica em cerca de 17%) e recebeu nota 10. O gerador não ensina fórmulas nem contas, e uma conferência no código barra instruções como "custo + 30%" ou "multiplique por" (a regra só no prompt não bastou). A aprovação humana continua obrigatória.
- **Cotas diárias**: o Groq gratuito tem 200 mil tokens por dia, e cada peça faz de 2 a 4 chamadas (geração, reescritas e juiz). Quando a cota acaba, o app avisa e diz quando tentar de novo.
- **Curtidas ocultas** chegam vazias e o post sai do ranking (afeta poucos perfis, como @shirleycontadora).
- **Comentários de terceiros**: a Graph API não traz o texto; o sinal de conversa usa comentários ÷ curtidas.
- **Links de mídia do Instagram** expiram em poucos dias; a camada 2 precisa rodar logo depois da coleta (ou recoletar).
- **Shorts** são aproximados por duração (até 180 s): o YouTube não informa se o vídeo é vertical.
- **Validação humana** dos rótulos e **calibração do avaliador** ainda não foram feitas (planilhas e página prontas em `data/validacao/`). Sinal de alerta: o avaliador deu 10 em quase todos os critérios das peças, então a nota dele ainda não discrimina bem.
- **Criativos para a @stone**: o agente não conhece taxas, prazos nem condições dos planos e foi proibido de citá-los; a equipe completa esses detalhes antes de publicar. O carrossel da @stone assina "stone", mas usa a paleta do Impulso.
- **Atualização automática** depende do computador ligado (a tarefa roda assim que ele liga, se perdeu o horário) e gasta cota das APIs proporcional aos posts novos.
- `documentos/` (material interno da Stone), `Case_Suno/`, `.env` e os dados brutos ficam fora do git.

## Próximos passos

1. **Interpretação dos achados por IA**: para cada achado (número calculado pelo código), a IA lê os posts do top com aquela característica e explica *por que* funcionam, com exemplos. Fica marcada como interpretação; o número continua vindo do código ("a IA lê e interpreta, o código calcula").
2. **Leitura qualitativa do top**: síntese por tema do que os posts mais fortes têm em comum.
3. **Recuração dos perfis**: tirar ou rebaixar os perfis com metade ou mais dos posts fora do escopo (receita, artesanato, entretenimento) e buscar perfis de educação para o MEI.
4. **Janela mais curta**: o que atrai o público muda rápido; com a atualização semanal acumulando coletas, reduzir a janela do ranking de 180 dias para 4 a 8 semanas.
5. **Concordância dos campos de áudio** (música, volume, tom e ritmo da fala), como foi feito com os campos visuais.
