# Missão 20.8 — Connected onboarding

## Âmbito e prova

Implementação integrada no produto, a partir de `d764f893ea47448836f8a64f1b8660fdd3b0a143` (main após PR #27). Não instala serviços, não agenda trabalhos e não modifica algoritmos C01–C10. O laboratório usa PostgreSQL 17, GoTrue 2.177.0, PostgREST 12.2.3 e o handler C01 existente, servido em HTTPS local. **PostHog é um servidor OAuth/HTTP controlado: nenhuma autorização hospedada, consulta de dados reais ou compatibilidade empírica com um projeto PostHog é alegada.**

A implementação executável inclui OAuth, armazenamento cifrado, descoberta limitada de grupos/eventos, revisão humana, bootstrap separado da ingestão, pedidos duráveis C01, correções com recibo real, watermarks e worker opt-in. O mock exercita esses caminhos; não substitui a validação externa que ainda falta.

## Experiência e fronteiras humanas

Em Visão geral → Ligar PostHog, um administrador responde a cinco perguntas: serviço, unidade B2B/B2C já definida, resultado prometido, fontes existentes e consentimento. A região é uma seleção da fonte. O tipo da empresa nunca muda. A finalidade, categorias, scopes, retenção e dependência da sessão são apresentados antes da saída para autorização.

Após OAuth, escolhe explicitamente um tipo de grupo. A descoberta mostra até 200 clientes, nomes editáveis, referências estáveis e até 20 eventos observados nos últimos sete dias UTC. O utilizador seleciona até cinco métricas e escolhe uma janela histórica inicial. Contagens são classificadas como atividade até confirmação humana; não são propostas metas ou regras de deterioração a partir de frequências de eventos. A direção também exige escolha humana.

Há duas saídas: mapear explicitamente contagens para indicadores compatíveis de um perfil já aprovado; ou criar um rascunho e completar as regras no editor de Perfil existente. A aprovação continua a chamar `approve_value_profile`, incluindo todas as condições do contrato. **A primeira versão não elimina a revisão técnica/comercial do perfil.** Uma contagem sem justificação de resultado, baseline ou regras não ativa recolha. Uso B2C sem grupos, inferência de causas, comprovação de documentos, avaliação C04, cumprimento global da promessa, criação de casos e intervenções não são automatizados.

A confirmação é do administrador sobre as metas do indicador; não equivale à confirmação do cliente nem cria uma configuração individual C04. Metas ausentes continuam ausentes, conforme o contrato existente. A confirmação cria clientes apenas durante a ativação, depois da aprovação. O bootstrap usa `create_value_profile_draft`, a aprovação autorizada e um wrapper privado para os `subjects` confirmados. A API C01 continua a receber exclusivamente medições para clientes existentes e perfil aprovado.

## Segurança

- Rotas `/api/connected/*` autenticam o Bearer humano em GoTrue (`/auth/v1/user`) e verificam sub, role, exp e session_id. Cada operação revalida membership administrativa, sua identidade e sessão real na base. O backend não usa `service_role`.
- OAuth é server-side: state e nonce aleatórios de 256 bits, hashes em DB, cookie nonce HttpOnly/SameSite=Lax/Secure em produção; PKCE S256; validade dez minutos; estado consumido antes da troca de código, inclusive quando a troca falha. Callback usa a mesma sessão autenticada e limpa o query string. O tenant pendente no browser não concede autorização.
- Hosts PostHog fixos por região; discovery validado; endpoints exatos e redirects HTTP recusados. Nenhum host/projeto/token é recebido como autoridade do browser. Tokens e introspection têm de declarar exatamente um projeto, zero organizações e apenas `project:read group:read query:read`. Refresh preserva projeto e scopes; uma falha exige reautorização.
- Schema `connected_private` não exposto no PostgREST. Todas as tabelas têm FORCE RLS. `anon`, `authenticated`, `service_role` e `authenticator` não recebem acesso. A capacidade NOLOGIN/NOINHERIT `centerway_connector_backend` é concedida apenas a um login de runtime dedicado, sem superuser/BYPASSRLS/service_role. O código rejeita runtime privilegiado e exige TLS verificado fora do laboratório.
- AES-256-GCM com IV aleatório, envelope versionado e AAD empresa/ligação/finalidade. A chave de 32 bytes é exclusivamente do gestor de segredos do runtime. Access/refresh, segredo C01 e verifier PKCE nunca são enviados ao frontend nem guardados em claro na DB. Perder a chave requer novas autorizações; backups devem reter o acesso controlado à versão de chave correspondente.
- A perda de membership administrativa revoga imediatamente a credencial C01 do conector, retira os segredos da ligação e coloca a revogação PostHog numa fila cifrada. Reinserir o membro não herda consentimento. Uma sessão inválida impede leituras, mesmo que um access token PostHog ainda esteja válido. Um pedido externo já autorizado pode terminar; não há promessa de cancelar efeitos já confirmados.
- Desligar bloqueia novos lotes e conserva observações/histórico. A revogação remota pode ficar pendente por falha de transporte; o worker tenta novamente e mantém código de erro. A capacidade de revogação é privada do backend e não aceita endpoints arbitrários.
- Logs/respostas de erro contêm apenas códigos controlados, status e contagens. Não ativar logging de Authorization, query strings OAuth, parâmetros SQL ou corpos de fornecedor no proxy/APM. O callback requer `Referrer-Policy: no-referrer` no proxy e exclusão de query strings dos access logs, antes de produção.

## Tradução e sincronização

A identidade usa SHA-256 de região/projeto/índice do grupo/group_key; não usa nomes mutáveis nem transforma pessoas em clientes. Propriedades extras dos grupos e tokens de projeto são descartados; apenas o nome do grupo é proposto como nome empresarial editável. Eventuais nomes pessoais devem ser removidos/revistos antes de confirmar.

Consultas HogQL geradas pelo servidor contam eventos por grupo explicitamente escolhido, usando `JSONExtractString(properties, '$groups', '<tipo>')`, sem IDs pessoais. As fronteiras usam `toDateTime('YYYY-MM-DD 00:00:00', 'UTC')` explicitamente: literais sem timezone seriam interpretados no fuso do projeto PostHog. Datas são validadas no calendário; eventos e grupo são literais escapados; não há SQL livre. Esta expressão ainda precisa de validação no projeto PostHog autorizado (tipos/representação reais de `$groups`). Respostas truncadas ou acima dos limites bloqueiam a sincronização; não se declara cobertura completa por amostragem.

Cada execução processa um dia UTC concluído, com dois dias de sobreposição e avanço a cada terceiro passe. Watermarks por indicador mantêm projeto/revisão; o lote é atómico entre os indicadores selecionados. A janela inicial é explícita (até 366 dias). Uma ausência de evento não vira zero e não prova falha ou cumprimento. A cobertura C01 declara a janela consultada, **não completude comercial**. Clientes novos não são automaticamente acrescentados ao mapeamento confirmado: rever a seleção exige desligar e autorizar novamente. Atrasos anteriores à sobreposição exigem revisão/reimportação explícita; esta versão não deteta automaticamente todo o passado.

O pedido completo e UUID são confirmados na fila antes de HTTP. Reenvios mantêm corpo, UUID e chaves das observações. Uma resposta ambígua não avança watermarks. A alteração de uma contagem já aceite cria nova observação, com nova chave e `corrects_observation_id` obtido por consulta privada, autenticada, restrita à origem da ligação. Sem esse ID real, a correção fica bloqueada. Nenhuma observação é inserida diretamente pelo conector.

Até 1.000 linhas/1 MB por fatia; até 120 leituras privadas PostHog/hora por ligação e dez tentativas C01/minuto (abaixo da quota C01 de 30). `Retry-After` é respeitado, com limite de uma hora e pendência durável. Rate limits/503/erros de transporte são recuperáveis; 4xx determinísticos bloqueiam o lote, preservando-o para inspeção. Perfil aprovado diferente interrompe o processamento; não se remapeia silenciosamente. Vários workers/pedidos da mesma empresa são serializados com advisory lock; empresas diferentes usam locks distintos.

Exemplo de envelope produzido (IDs ilustrativos, sem credenciais):

```json
{"profile_id":"00000000-0000-4000-8000-000000000001","source":"posthog:us:41","coverage":{"start":"2026-10-20T00:00:00Z","end":"2026-10-21T00:00:00Z","declared":true},"rows":[{"subject_external_ref":"posthog:<hash-estavel>","indicator_key":"ph_<hash-evento>","observed_at":"2026-10-20T00:00:00Z","value_numeric":"10","unit":"events","idempotency_key":"ph:<hash-medicao>"}]}
```

## Instalação futura — não executada

1. Rever este PR, testes, risco de privacidade, retenção e documentação comercial. Não há autorização implícita para produção.
2. Aplicar apenas a migração aditiva 0028 pelo processo Drizzle gerido, após backup e confirmação da identidade do projeto. Journal e snapshot 0000–0027 são preservados. A migração cria schema, tabelas privadas, role e trigger de invalidação; não copia observações nem modifica Cron.
3. Provisionar login DB dedicado NOINHERIT, sem privilégios adicionais, e conceder `centerway_connector_backend`. Nunca configurar o URL do postgres administrador. Usar ligação direta ou pooler em modo sessão; transaction/statement pooling não é suportado, pois claims, role e advisory locks pertencem à sessão PostgreSQL. A aplicação deve ter runtime com TCP/TLS PostgreSQL e Node crypto compatíveis. **O target Cloudflare por omissão do repositório não foi validado para este conector**. Pode servir o backend Bun separadamente (`bun scripts/connectors/server.ts`) com proxy no mesmo domínio, ou validar um target Node adequado. Não expor porta de DB à Internet.
4. Configurar no servidor: `CW_CONNECTOR_ORIGIN`, `CW_POSTHOG_CLIENT_ID` (exatamente `<origin>/api/connected/metadata`), `CW_CONNECTOR_DATABASE_URL`, `CW_CONNECTOR_KEY` (base64 de 32 bytes), `SUPABASE_URL`, chave pública `SUPABASE_PUBLISHABLE_KEY`, `CW_C01_URL` HTTPS exato do endpoint existente. Nunca usar prefixo `VITE_` para segredos. `CW_LOCAL_MVP` e `CW_POSTHOG_MOCK` ficam ausentes em produção.
5. Servir o CIMD público HTTPS num domínio controlado; contém client_id, client_name, redirect_uris exatas e `com.posthog: {scopes: [...], optional_scopes: []}`. Verificar o conteúdo externamente, metadata OAuth/protected-resource, issuer, scopes, PKCE, endpoint de revogação e região. Não trocar as restrições por uma chave pessoal para contornar dificuldades.
6. Configurar proxy: HTTPS, cookie seguro, no-referrer, sem cache das APIs, sem logs de código/token, limites de corpo e timeout coerentes. Validar WAF/rate limit não autenticado da infraestrutura. O limitador da aplicação não é um WAF.
7. Administrador autoriza um projeto sintético controlado, confirma grupos, objetivo e perfil. Verificar minimização, query real, paginação, correção, refresh e desconexão. Só depois autorizar dados externos e a instalação de scheduler independente.
8. O worker é opt-in: `bun scripts/connectors/worker.ts --once`. O scheduler externo deve executar a cada cinco minutos com timeout e alertas; a DB serializa ligações e persiste os resultados. **Não há job hospedado instalado ou execução real de scheduler comprovada nesta missão.** A validade de sessão e chave C01 limita a continuidade: reautorização/renovação manual pode ser necessária. Não há autorização indefinida herdada.

## Reproduzir

Base descartável vazia com GoTrue/PostgREST, `psql`, Docker, Bun 1.3, Node 22, OpenSSL e Playwright. Copiar fonte para pasta isolada excluindo `.env*`, instalar `bun install --frozen-lockfile`, instalar dependências bloqueadas de `e2e/` e Chromium. Não carregar `.env` do repositório.

No GitHub-hosted CI, `PG_CONTAINER` identifica o serviço PostgreSQL; executar `python3 e2e/start_backend.py`, depois `bash e2e/connected/test.sh --serve`. O modo local usa o mesmo arranque com `--local-mvp` e exige `cw-mvp-db`, imagem postgres:17, label centerway.disposable=mvp e dados tmpfs, apenas 127.0.0.1:5432. Passar `CW_LOCAL_MVP=1` ao teste local. O teste só aceita o backend loopback gerado. Esperar `e2e/private/connected-runtime.json`, executar `cd e2e && npx playwright test --config connected/playwright.config.mjs`. É possível usar `CW_BROWSER_BIN=/usr/bin/chromium`. Terminar o processo após o browser.

O teste espera o backoff real de 60 segundos; não falsifica relógios. Contas, chaves, certificados e estados ficam em `e2e/private` fora dos artefactos. `e2e/logs/connected-results.json` é o resultado sanitizado e reproduzível. A suite SQL `e2e/connected/rls.sql` verifica ACL/FORCE RLS. Os workflows anteriores continuam a executar regressões C01–C10, monitorização, permissões, tipos, build e auditoria; o novo workflow acrescenta o percurso conectado.

## Rollback e decisão de aprovação

Desativar o worker e retirar configuração/rota do conector antes de regressar à aplicação anterior. Desligar ligações por operações autorizadas enquanto o backend/chave estiverem disponíveis; escoar a fila de revogação e confirmar a revogação junto do fornecedor. Preservar a chave cifrante enquanto existirem segredos pendentes/backups sujeitos a retenção. Revogar o login/capacidade do runtime. Manter a migração aditiva e histórico para investigação; **não executar DROP CASCADE**, apagar perfis, clientes ou observações já aceites. Uma eventual remoção do schema/trigger precisa de migração posterior revista, com fila vazia e zero ligações ativas. O journal não é recuado.

Aprovar engenharia local apenas com CI verde, dois tenants isolados, callback vinculado à sessão, aprovação humana bloqueante, pedidos duráveis, correções preservadas e zero execução automática C02–C10. Aprovar ligação hospedada apenas depois de concluir os gates 1–8 acima e recolher evidência real. Aprovação deste PR não é aprovação de deploy ou recolha externa.

## Referências verificadas antes da implementação

- [PostHog OAuth/CIMD/discovery/scopes](https://posthog.com/docs/api/oauth), [API e quotas](https://posthog.com/docs/api), [groups](https://posthog.com/docs/api/groups), [queries](https://posthog.com/docs/api/query), [SQL](https://posthog.com/docs/sql).
- [Guia oficial OAuth de engenharia](https://github.com/PostHog/posthog/blob/master/docs/published/handbook/engineering/oauth-development-guide.md): seleção única com required_access_level, introspection do próprio access token, scoped_teams/organizations. Fontes consultadas em 22/10/2026; não congelam o comportamento futuro do fornecedor.
- Contratos internos: ingestion-api, C02 semantics, Core/C04 configurable, operational journey/cycles, team access, operational onboarding e responsibilities/notifications. Esses motores não foram substituídos.

A referência oficial [SQL expressions](https://posthog.com/docs/sql/expressions) fundamenta o timezone UTC explícito; [metadata OAuth oficial](https://github.com/PostHog/posthog/blob/master/posthog/api/oauth/metadata.py) fundamenta os endpoints e protected-resource verificados.

O patch versionado `patches/postgres@3.4.9.patch` impede reutilizar uma lease reservada após fecho do socket, rejeita pedidos pendentes e torna release idempotente. A regressão termina apenas o backend PostgreSQL da própria ligação descartável e comprova uma nova operação autorizada. O encerramento do worker é limitado a dois segundos. A versão e auditoria do pacote permanecem preservadas.
