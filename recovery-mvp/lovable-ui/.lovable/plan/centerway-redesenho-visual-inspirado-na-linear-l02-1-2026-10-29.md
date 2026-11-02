# CENTERWAY: redesenho visual inspirado na Linear (L02.1)

Este redesenho mexe só no aspeto da interface. Os dados de demonstração, o adaptador de dados, as rotas e os textos de segurança ("Demonstração", "Ação sintética", "Recuperação observada não comprova causalidade") ficam exatamente como estão. Não reconstrói o backend F01–F06 nem liga a API real.

## 1. O que observei na Linear

**Verificado** (página pública linear.app, capturada a 29/10/2026, incluindo a imagem do produto mostrada nessa página):
- Fundo quase preto e neutro, sem tom azulado. Hierarquia feita com 3–4 cinzentos de texto em vez de cores.
- Títulos grandes e muito apertados (espaçamento negativo entre letras). O texto da interface é pequeno, entre 13 e 14 px, com peso médio.
- Uma sans-serif de sistema/grotesca em toda a interface e uma monoespaçada para identificadores (por exemplo "DRV-8852").
- Sidebar estreita e sem moldura:
  - itens com 28–32 px de altura e ícones de 14–16 px em cinzento;
  - grupos com rótulo pequeno e discreto ("Workspace", "Favorites");
  - o item ativo é só um fundo ligeiramente mais claro, sem barra colorida.
- Cabeçalho de página fino, de cerca de 44 px:
  - à esquerda, o identificador e o título;
  - à direita, navegação "1 / 84" e setas, e ícones em botões circulares com contorno.
- Detalhe em duas colunas: o conteúdo principal à esquerda e um painel de "Properties" à direita, em lista de pares ícone + valor, sem moldura.
- Estados como ícones circulares pequenos ou pontos coloridos. As etiquetas são cápsulas com contorno de 1 px e ponto de cor; não há fundos coloridos fortes.
- A atividade aparece como linha temporal muito compacta: avatar pequeno, texto em cinzento com os nomes em destaque, e a hora relativa.
- Bordas finas e de baixo contraste. As sombras quase não existem: a profundidade vem da diferença de luminosidade das superfícies e de uma moldura exterior arredondada (cerca de 12 px).
- Quase não há cor de destaque: o amarelo/azul aparece só em ícones de estado.

**Inferido, sem verificação** (a aplicação autenticada não estava acessível):
- Listas densas de linhas com cerca de 36 px, em vez de tabelas com cartões.
- Seleção com a tecnologia de teclado, paleta de comandos (Ctrl/Cmd+K) e menus de contexto.
- Transições curtas (120–200 ms) com suavização e passagem do rato que só muda o fundo.
- Tema claro equivalente: fundo branco-acinzentado e os mesmos níveis de cinzento invertidos.
- Foco visível em anel subtil e boa navegação por teclado.

## 2. Diferenças face ao CENTERWAY atual

| Área | CENTERWAY hoje | Direção proposta |
|---|---|---|
| Paleta | Azul-petróleo saturado, superfícies azuladas | Petróleo muito dessaturado, quase neutro; o ciano só em foco, seleção e um ponto de marca |
| Tipografia | Fraunces (serifada) em títulos, Plex Sans | Uma só grotesca (Inter Tight ou Geist, gratuitas) + Geist Mono ou Plex Mono. Retirar a serifada |
| Tamanhos | 14–16 px, títulos de 30 px | Interface a 13 px; títulos de página a 20–22 px, apertados |
| Densidade | Painéis com 16–20 px de margem interior, muitos cartões | Listas em linhas de 36 px e secções separadas por linhas finas, não por caixas |
| Sidebar | 256 px, itens de 44 px, destaque ciano | 232 px, itens de 30 px no computador (44 px no telemóvel), destaque neutro, grupos com rótulo |
| Cabeçalho | Só o banner de demonstração | Barra de página de 44 px: trilho de navegação, contagem, filtros e ações à direita |
| Estados | Cápsulas com fundo colorido | Ícone/ponto de estado + texto em cinzento; cor só no ponto |
| Painéis | Bordas e cantos visíveis em toda a parte | Uma moldura exterior arredondada para a área de conteúdo; dentro, divisórias de 1 px |
| Movimento | Quase nenhum | Passagem do rato e foco em 120 ms; abertura de painéis em 180 ms; respeitar "reduzir movimento" |

## 3. Identidade própria (sem copiar)

- Sem logótipo, ícones ou imagens da Linear, e sem reproduzir os layouts exatos dela.
- Marca CENTERWAY:
  - logótipo em texto monoespaçado com espaçamento largo e um pequeno marcador geométrico próprio (dois traços convergentes, "center way");
  - acento ciano-petróleo próprio, em vez do roxo/índigo da Linear.
- Tom "evidencial", próprio do CENTERWAY:
  - os blocos Factos, Hipóteses, Contradições e Em falta usam marcadores de forma diferentes (círculo cheio, círculo vazio, losango, tracejado), não só cor;
  - assim a informação também é acessível a quem não distingue cores.
- O banner "Ambiente de demonstração" mantém-se, mais discreto: uma faixa fina em âmbar dessaturado.

## 4. Tokens sugeridos

```text
Escuro (por omissão)                 Claro (preparado, sem botão de alternância)
--background     oklch(0.145 0.006 220)   oklch(0.985 0.002 220)
--surface        oklch(0.175 0.007 220)   oklch(1 0 0)
--surface-raised oklch(0.205 0.008 220)   oklch(0.97 0.003 220)
--surface-hover  oklch(0.225 0.008 220)   oklch(0.95 0.004 220)
--border         oklch(0.26 0.006 220)    oklch(0.91 0.004 220)
--border-subtle  oklch(0.21 0.006 220)    oklch(0.94 0.003 220)
--fg             oklch(0.95 0.003 220)    oklch(0.2 0.01 220)
--fg-muted       oklch(0.70 0.006 220)    oklch(0.45 0.01 220)
--fg-subtle      oklch(0.55 0.006 220)    oklch(0.6 0.008 220)
--accent (marca) oklch(0.78 0.10 205)     oklch(0.55 0.12 210)
Estados (só pontos/ícones): ok 165, warn 80, risk 28, info 225, neutral; croma ≤ 0.10
Tipo: 12 / 13 (base) / 14 / 16 / 20 / 28; peso 400 / 510 / 600; títulos com espaçamento -0.02em
Espaço: base de 4 px; linha de lista 36 px; item de sidebar 30 px; barra de página 44 px
Raio: 4 (controlos) / 6 (cápsulas) / 10 (moldura exterior)
Sombra: só nos elementos flutuantes (menus, painéis laterais, tooltips)
Movimento: --ease-out cubic-bezier(.2,.8,.2,1); 120 ms / 180 ms
```

## 5. Componentes partilhados (em src/components/cw/)

- `AppShell` v2: sidebar com grupos (Operação: Visão Geral, Clientes; Valor: Contratos, Recuperação; Análise: Investigações, Intervenções), rodapé "Sobre" e a moldura exterior da área de conteúdo.
- `PageBar`: trilho de navegação, título, contagem, espaço para filtros e ações (incluindo `LockedAction`).
- `ListView` + `ListRow`: linhas densas com colunas configuráveis. No telemóvel passam a linha em 2 níveis (título, depois metadados), sem deslocamento horizontal.
- `StatusDot` / `StatusLabel`: substituem `Pill` nos estados. Uma `Tag` com contorno fica para as etiquetas.
- `PropertyPanel`: coluna direita de propriedades, usada no detalhe do cliente e das investigações.
- `ActivityFeed`: atividade compacta.
- `FilterChips` e `SegmentedTabs`: com a mesma lógica local de hoje.
- `EvidenceBlock`: Factos, Hipóteses, Contradições e Em falta, com marcadores de forma.
- `MetricStrip`: números inline separados por divisórias, sem caixas grandes.
- `KbdHint`: decorativo. A paleta de comandos fica fora desta fase.

## 6. As 6 páginas

1. **Visão Geral:**
   - os números ficam numa faixa compacta no topo, em vez de 5 caixas;
   - "Clientes que precisam de atenção" passa a lista densa agrupada por prioridade (Alta / Média), com ponto de estado;
   - "Evidência insuficiente" e "Atividade" passam a uma coluna direita com feed compacto.
2. **Clientes:**
   - barra com pesquisa e filtros, e lista densa com colunas Empresa, Objetivo, Evidência, Prioridade e Próxima etapa, cada linha clicável inteira;
   - o detalhe fica em duas colunas: à esquerda o cabeçalho, a linha temporal e as secções (Contrato, Lacunas, Ações); à direita o `PropertyPanel` (segmento, plano, responsável, evidência, fontes);
   - acrescentar navegação "anterior / seguinte" entre clientes.
3. **Contratos de Valor:**
   - lista densa com uma linha por contrato;
   - um painel lateral abre ao clicar, com baseline, mínimo e meta numa régua horizontal, método, período, fonte e revisões em linha temporal;
   - os contratos por confirmar ficam com o estado bem visível.
4. **Investigações:**
   - à esquerda a lista de investigações, à direita o detalhe;
   - no detalhe: deteções em monoespaçada, os 4 `EvidenceBlock` empilhados e tabs Candidatos / Referências / Versões;
   - o aviso de causalidade fica fixo junto aos candidatos;
   - no telemóvel, a lista abre o detalhe num ecrã próprio, com botão de voltar.
5. **Intervenções:**
   - lista agrupada por estado (Bloqueada / Autorizada / Executada), com contagens no cabeçalho de cada grupo;
   - cada linha mostra as etiquetas "Ação sintética" e "Não é uma intervenção real";
   - o painel lateral, só de leitura, mostra a justificação e a decisão, e tem `LockedAction`.
6. **Recuperação:**
   - faixa com os 4 estados;
   - uma linha por caso com uma régua compacta antes → depois e a marca do mínimo;
   - 3 indicadores lado a lado: Execução, Melhoria e Mínimo atingido;
   - o aviso de causalidade aparece no topo e no painel de detalhe.

## 7. Fases e prioridades

- **P1 (base):**
  - novos tokens e tipos de letra em `styles.css` e no cabeçalho principal;
  - retirar a Fraunces;
  - `StatusDot`, `Tag`, `PageBar`, `AppShell` v2.
  - Só isto já muda o aspeto das 6 páginas.
- **P2 (listas):** `ListView`/`ListRow` aplicados a Clientes, Intervenções, Contratos e Visão Geral, com a versão para telemóvel.
- **P3 (detalhe):** `PropertyPanel`, painel lateral com URL de pesquisa (`?id=`), detalhe do cliente e investigações em duas colunas.
- **P4 (acabamento):**
  - movimento e "reduzir movimento";
  - estados de foco;
  - verificação de contraste AA;
  - tokens do tema claro definidos (sem botão de alternância);
  - capturas de ecrã em 1280 px e 390 px.

## 8. Preservação e limites

- Ficam intactos: `src/domain/types.ts`, `src/data/*` (dados, interface do cliente API e adaptador de demonstração) e os carregamentos de dados de cada rota.
- As páginas continuam a ler só através de `api`.
- Sem chamadas de rede, autenticação, tokens, backend, base de dados ou integrações; sem ligação à API L01 e sem publicação.
- Mantêm-se todos os rótulos "Demonstração", os avisos de causalidade e os `LockedAction`.
- Nenhum dado novo é inventado como real. Se surgir algum campo novo (por exemplo, a ordem para "anterior / seguinte"), é calculado a partir dos dados de demonstração que já existem.

## 9. Riscos

- Ficar demasiado parecido com a Linear (trade dress). Mitigação: acento, logótipo, marcadores evidenciais e grupos de navegação próprios, e nenhum ativo da Linear.
- Densidade a mais no telemóvel. Mitigação: alvos de toque de 44 px e listas em 2 níveis abaixo de 768 px.
- Contraste baixo com cinzentos subtis. Mitigação: `--fg-subtle` só para metadados, e verificação AA do texto principal.
- Painel lateral com URL: risco de regressão na navegação. Mitigação: o painel é opcional e o detalhe do cliente mantém a rota atual.

## 10. Critérios de aceitação

- As 6 páginas e o detalhe do cliente usam os novos tokens e não ficam cores fixas nos componentes.
- Texto de interface de 13 px, um só tipo de letra sans, títulos sem serifa.
- Listas densas no computador; sem deslocamento horizontal a 390 px; alvos de toque de 44 px ou mais no telemóvel.
- Os estados distinguem-se por forma/ícone e não só por cor; foco visível em todos os elementos interativos.
- Os rótulos de demonstração, os avisos de causalidade e as ações bloqueadas continuam presentes e visíveis.
- `src/data` e `src/domain` sem alterações de comportamento; o teste existente passa e o projeto compila sem erros.
- Nenhum pedido de rede novo é visto no navegador.

