# CENTERWAY P01: plano integral e auditoria de coerência Lovable/Codex

Este documento é só planeamento: não altera código nem cria ligações. Ao ser aprovado, a única coisa a executar é a missão **L02.2** da secção 4. Tudo o que é backend fica como proposta, para revisão do ChatGPT e posterior entrega ao Codex.

Fontes verificadas nesta análise (leitura pública do branch `recovery-mvp/l01-authenticated-api`): `api/README.md`, `api/openapi.json` (só o cabeçalho e as rotas) e `ORCHESTRATION.md`. Não li `AGENTS.md` nem `PROJECT_STATE.md` e não executei a API.

## 1. Resumo executivo

- O backend L01 dá para demonstrar o percurso de **um cliente de cada vez**: login, ler a projeção F06 (`journey`) e enviar 10 comandos idempotentes.
- **Não** suporta uma aplicação navegável como a interface L02 atual. Faltam várias coisas:
  - não há lista de clientes com nomes nem visão agregada;
  - não há catálogo, políticas, provisionamento ou regras de descoberta por HTTP;
  - não há paginação;
  - não há HTTPS publicado.
- A UI L02 mostra hoje dados que **não existem na API**:
  - nomes de empresa, segmento, plano e responsável;
  - prioridade e "próxima etapa" em linguagem natural;
  - os KPIs da Visão Geral;
  - as fontes com "cobertura".
- Isto tem de ser marcado como mock ou removido antes da integração.
- **O maior bloqueio não é de UX, é de rede.** A API só corre em loopback e HTTP, e o preview da Lovable é HTTPS e público. Sem um gateway HTTPS publicado (proposta GAP-01), não há integração real possível a partir da Lovable.
- Caminho mais barato: alinhar já o mock ao formato real da `journey` F06 (L02.2). Depois disso, a ligação real fica limitada a trocar o adaptador.

## 2. A arquitetura real hoje

| Peça | Estado |
|---|---|
| Motores F01–F06 e transporte L01 (67 testes) | Implementado, mas não integrado em main (PRs #49–#56) |
| `POST/GET/DELETE /v1/session` | Implementado. Token opaco de 900 s, só em memória |
| `GET /v1/tenants/{t}/clients/{c}/journey` | Implementado. Projeção `f06-v1` com RLS e sem paginação |
| `POST /v1/tenants/{t}/clients/{c}/operations` | Implementado. 10 operações, `request_id` idempotente, 409 em caso de conflito |
| Utilizadores da demo | alice e reviewer (empresa A), reader (só leitura), bob (empresa B). 1 contrato e 1 fonte SYNTHETIC |
| Papéis | **Parcial.** Só existem como scopes por utilizador num ficheiro de configuração do servidor. Não há papel formal operador/revisor/admin na API |
| `discover_company` | Implementado, mas a demo não concede o scope `company_tenants` |
| Catálogo F04, políticas, regras e entradas F03.1, provisionamento de utilizadores | Só fora do HTTP (SQL/admin). **Não acessível pela UI** |
| HTTPS, CORS de produção, deploy, SSO/MFA, paginação, métricas | Fora do âmbito atual |
| Frontend L02 (Lovable) | Implementado só como mock. O adaptador `CenterwayApiClient` tem uma forma inventada, que não corresponde à F06 |

**Facto útil:** `GET /v1/session` devolve `clients: {tenant: [client_uuid]}`. Daí sai uma lista navegável de clientes autorizados, mas **só com UUIDs**, sem nomes.

## 3. Matriz de gaps: real vs mock

Legenda de estado: **Real** = pode ser feito com o L01 atual; **Proposto** = exige backend novo; **Fora MVP** = fica para depois do MVP.

| Página | Dados mostrados hoje | Fonte real | Ações | Endpoint real | Em falta (GAP) |
|---|---|---|---|---|---|
| Login | (não existe) | sessão | entrar e sair | `POST/DELETE /v1/session` | GAP-01 HTTPS |
| Empresa e scopes | (não existe) | `GET /v1/session` | escolher tenant/cliente | sim | GAP-02 nomes |
| Visão Geral | KPIs, prioridade, atividade | Só agregável lendo N `journey` | nenhuma | N × `GET journey` | GAP-03 resumo agregado (P1); a prioridade é inventada |
| Clientes (lista) | nome, segmento, plano, prioridade | só UUIDs dos scopes | pesquisar | `GET /v1/session` | GAP-02 metadados (P0 para a demo) |
| Cliente (detalhe) | linha temporal, fontes, ações | `journey`: versões, `work_items`, recibos | ver o percurso | `GET journey` | Real. É preciso trocar a linha temporal mock por `work_items` e recibos |
| Contratos | objetivo, baseline, mínimo, meta, revisões | `journey`: versões de contrato | `append_value` | `POST operations` | Real. A forma do campo `data` depende do contrato F01, a confirmar |
| Fontes e evidências | cobertura (inventada) | `journey`: fontes, evidências e snapshots | `append_value` | sim | Retirar a "cobertura"; mostrar só o que vem nos snapshots |
| Deteção | (implícita) | `journey`: deteções | `detect` | sim | Real |
| Investigações | factos, hipóteses, contradições, em falta | `journey`: investigações e última avaliação | `open_investigation`, `append_investigation`, `investigate` | sim | Real. A verificação humana exige o login real do revisor |
| Descoberta | (não existe) | recibo | `discover_company` | sim, mas sem scope | GAP-05: regras e entradas por HTTP (P2) |
| Intervenções | catálogo e estados | `journey`: decisões, execuções e reversões | `intervene`, `undo` | sim | GAP-04: leitura do catálogo e das políticas (P1). Escrita fica fora do MVP |
| Recuperação | antes/depois, 4 estados | `journey`: planos e última avaliação | `plan_recovery`, `evaluate_recovery` | sim | Real |
| Configuração | (não existe) | nenhuma | nenhuma | nenhum | GAP-06 provisionamento: fora do MVP, fica em admin/SQL |

**Só no frontend, com a `journey`:**
- detalhe do cliente, contratos, investigações, intervenções e recuperação, todos por cliente;
- linha temporal de `work_items`;
- recibos;
- formulários dos 10 comandos.

**Exige novas portas HTTP:**
- lista de clientes com nomes;
- Visão Geral agregada;
- leitura do catálogo e das políticas;
- descoberta configurável;
- paginação.

## 4. Plano de missões

| # | Responsável | Missão | Critério de aceitação |
|---|---|---|---|
| **L02.2** | Lovable (próxima, só mock) | Alinhar o mock e os tipos à F06 sem mudar o design (detalhe abaixo) | Compila e o teste passa; nenhum campo inventado aparece sem a etiqueta "Mock"; não há rede nova |
| C01 | Codex | Decidir o modo de publicação: gateway HTTPS e CORS para a origem exata da Lovable (GAP-01) | `curl` HTTPS de fora devolve 401 sem Bearer; CORS só para a origem do preview |
| C02 | Codex | GAP-02: metadados mínimos do cliente (opcional) | Testes com RLS e scopes; nada fora do scope |
| L03.1 | Lovable | Adaptador real, só de leitura: login, sessão e `journey`, com token em memória | E2E com alice, reader e bob (abaixo) |
| L03.2 | Lovable | Comandos com `request_id` persistido e os ecrãs de estado | Replay devolve o mesmo recibo; 409 é mostrado; não há retry automático de `intervene` |
| C03 | Codex | GAP-03 e GAP-04, se aprovados | Testes de scope e de tamanho |
| L04 | Lovable | Demo publicável (só depois de C01 e da decisão D3) | Verificação de segurança; sem segredos no cliente |

**L02.2, o que muda:**
- `src/domain/types.ts` passa a ter tipos espelho da `journey` F06 (`work_items` com stage, next, blockers, needed, result, as_of; recibos com status e result; os campos `execution_succeeded`, `improvement_observed` e recuperação em separado).
- Tipos de UI à parte: o detalhe do cliente agrega os vários contratos e casos em paralelo.
- Os dados mock passam a ter a forma da projeção F06 e um mapeador `journey → viewmodel`.
- Os campos sem fonte real ficam marcados "Mock: sem fonte na API" (nome, segmento, plano, prioridade) ou saem. A "cobertura" das fontes é removida.
- `CenterwayApiClient` passa a refletir o contrato real: `getSession`, `getJourney(tenant, client)`, `operate(tenant, client, req)`.
- O mock simula as respostas 401, 403, 404, 409, 422 e 503 para os ecrãs de estado.
- Ecrãs de estado partilhados: a carregar, vazio, sessão expirada, sem permissão, conflito, indisponível e sem rede.
- Formulários dos comandos ficam bloqueados (`LockedAction`). Não há login real.

**E2E sintético (L03), com base nas contas da demo do Codex:**
1. alice entra, vê o seu cliente e corre `detect`, que devolve um recibo.
2. Repetir o mesmo `request_id` devolve o mesmo recibo; um conflito devolve 409.
3. reader recebe 403 nos comandos.
4. bob recebe 404 ou 403 no cliente da empresa A.
5. O segundo cliente da A dá 403.
6. Ao fim de 900 s aparece o ecrã de sessão expirada e o rascunho é preservado.
7. Com a base parada aparece o ecrã de serviço indisponível (503).

**Menor custo em créditos Lovable:** L02.2 é uma só missão, reutiliza todos os componentes atuais e não toca no design. L03 só arranca depois de C01, para não integrar contra algo que não está publicado.

## 5. Contrato de UI (resumo técnico)

- **Sessão:** o token fica só em memória (estado React). Não usar localStorage nem cookies. Ao recarregar a página, a sessão perde-se. O countdown de `expires_in` vem do servidor.
- **401:** limpar o token, ir para o login e preservar o rascunho do formulário em memória.
- **403:** mostrar "Sem permissão para esta operação ou cliente". **Não esconder** ações com base nos scopes como se isso fosse segurança: os scopes servem só para a UX, e quem decide é o servidor.
- **404:** "Cliente inexistente ou não visível", sem distinguir os dois casos.
- **409:**
  - se for um `request_id` reutilizado, mostrar o recibo original e pedir um novo pedido explícito;
  - se for uma revisão desatualizada, mostrar "Os dados mudaram" e recarregar a `journey`.
- **422 ou recibo `error`:** mostrar `code=engine_rejected` e o sqlstate sem reinterpretar. Só se tenta outra vez com um novo `request_id`.
- **503 ou perda de rede:** mostrar o ecrã de serviço indisponível. Para comandos, a UI guarda o `request_id` e o corpo **antes** de enviar e oferece "Repetir o mesmo pedido". Nunca há retry automático de `intervene` ou `undo`.
- **HTTP 200:** o resultado é mostrado em dois níveis: o recibo (`completed`/`error`) e o resultado de negócio (blocked, failed, inconclusivo, ...). Execução, melhoria observada e mínimo atingido aparecem sempre como três campos separados.
- **`work_items`:** apresentados como "orientação com base no estado guardado", com o `as_of` visível. Nunca como "elegível" ou "autorizado".
- **Sem dados ou projeção grande:** há estado vazio explícito. Sem paginação, a projeção grande tem um aviso.

## 6. Human-in-the-loop

- A UI nunca autoriza: `intervene` só pede, e quem decide é a F04 com a política provisionada. O botão diz "Pedir avaliação F04", não "Autorizar".
- A verificação humana F03 é feita só pelo login real do revisor. A UI mostra quem está autenticado e avisa quando é o mesmo principal que registou o fator, porque o servidor rejeita esse caso.
- Proveniência:
  - cada valor mostra a revisão, o autor (actor do recibo) e o `recorded_at`;
  - hipóteses e factos nunca partilham o mesmo bloco visual (isto já está implementado);
  - as lacunas ficam sempre visíveis.
- Ações de alto risco (`intervene`, `undo`, `discover_company`) exigem confirmação explícita com o resumo dos argumentos e a etiqueta "Sintético, sem efeito externo".

## 7. Propostas ao Codex (não executar sem decisão)

| GAP | Prioridade | Motivo | Contrato sugerido | Necessário? |
|---|---|---|---|---|
| GAP-01 Gateway HTTPS publicado e CORS para a origem exata | **P0** | Sem isto, nenhum browser da Lovable chega à API | Proxy TLS com `X-Forwarded-*` de confiança explícita, documentada | Sim, para qualquer integração real |
| GAP-02 Metadados do cliente | **P0 para a demo** | A lista mostra só UUIDs | `GET /v1/tenants/{t}/clients` → `[{client_id, display_name}]`, filtrado pelos scopes e RLS | Útil, mas a alternativa é aceitar UUIDs com alias local não persistido |
| GAP-03 Resumo agregado | P1 | A Visão Geral exige N chamadas | `GET /v1/tenants/{t}/summary` → contagens por stage | Não é preciso para a demo com 1–2 clientes |
| GAP-04 Leitura do catálogo e das políticas F04 | P1 | Explicar porque é que uma intervenção está bloqueada | `GET .../intervention-catalog`, só leitura | Desejável no MVP. Escrita fora do MVP |
| GAP-05 Regras e entradas de descoberta por HTTP | P2 | A descoberta F03.1 não é configurável pela UI | `register_discovery_rule` e `input` como operações | Não na demo |
| GAP-06 Provisionamento de utilizadores, SSO e MFA | Fora MVP | Segurança operacional | Fora do HTTP | Não |
| GAP-07 Paginação e limite da `journey` | P1 | Risco de memória e tempo | `?limit&cursor` por secção | MVP com volume real |

Requisitos comuns a todos os gaps:
- testes com principal sem privilégios;
- RLS mantida;
- sem DSN no cliente;
- sem aumentar o scope por omissão.

## 8. Auditoria do design atual (inspirado na Linear)

- **Manter:** a densidade, a sidebar agrupada, os estados com forma, o painel de propriedades e os painéis laterais com URL. Estão adequados à dimensão da demo.
- **Corrigir na L02.2** (funcional, não cosmético):
  - a linha temporal do cliente deve vir dos `work_items` e mostrar vários contratos e casos em paralelo; hoje mostra um único estado linear, o que é enganador;
  - a "Prioridade" deve ser removida ou marcada como mock;
  - a Visão Geral deve deixar claro que é agregada sobre os clientes autorizados.
- **No telemóvel:** as listas estão boas. Os formulários dos comandos (L03) devem ser ecrãs completos, não painéis laterais.
- Não proponho mudanças visuais adicionais.

## 9. Decisões para aprovação (máx. 5)

1. **D1, publicação da API (GAP-01).** Recomendo um gateway HTTPS gerido pelo Codex numa infraestrutura própria. A alternativa (usar funções de servidor da Lovable como proxy) continua a precisar de um endpoint público, por isso não resolve o problema.
2. **D2, lista de clientes.** Recomendo pedir o GAP-02 (só `display_name`). Para a demo, aceitar UUIDs com alias.
3. **D3, demo pública.** Recomendo não publicar com dados ligados antes de existir uma revisão de segurança. A demo mock pode ser publicada se o fundador quiser.
4. **D4, papéis.** Recomendo manter os scopes por utilizador (alice operadora, reviewer revisor, reader leitor) sem criar um sistema de papéis no MVP.
5. **D5, Visão Geral.** Recomendo agregar no cliente com N chamadas enquanto houver 10 clientes ou menos e pedir o GAP-03 só a seguir.

## 10. Limites e riscos

- O `openapi.json` foi lido só de forma parcial. Os schemas `data` de cada operação dependem dos contratos F01–F05, que não foram lidos. O L02.2 vai modelá-los como `unknown` validado, sem inventar campos.
- Os PRs não estão em main, por isso o contrato ainda pode mudar e deve ser fixado no commit do #56.
- Risco de a UI sugerir causalidade ou autorização: mitigado com os textos fixos e os três campos separados.
- Risco de custo: integrar antes de existir o GAP-01 desperdiça créditos.
- Não guardar nem pedir credenciais da demo. As passwords ficam no ficheiro privado do servidor.

