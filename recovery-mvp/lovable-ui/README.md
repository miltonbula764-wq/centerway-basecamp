# CENTERWAY — MVP Interface (L02)

Interface visual (só frontend) para acompanhar valor entregue a clientes SaaS. Dados 100% sintéticos, rotulados "Demonstração".

## Rotas
`/app` · `/app/clientes` · `/app/clientes/:id` · `/app/contratos` · `/app/investigacoes` · `/app/intervencoes` · `/app/recuperacao` · `/app/sobre`

## Estrutura
- `src/domain/l01.ts` — transporte HTTP L01 (sessão, journey, operations, recibos)
- `src/domain/f06.ts` — projeção `client_journey` f06-v1 e work_items
- `src/domain/types.ts` — view models da UI
- `src/data/mock/journeys.ts` — projeções sintéticas + metadados só-demo (GAP-02)
- `src/data/journey-mapper.ts` — journey → view models
- `src/data/transport.ts` — `L01Transport`, `L01Error`, desenho de reenvio idempotente (inativo)
- `src/data/mock-adapter.ts` — transporte mock e o ponto único `api`
- `src/components/cw/` — shell, primitivas e ecrãs de estado

## Limites
Sem backend, autenticação, base de dados, tokens ou chamadas de rede. Ações de escrita desativadas ("Disponível após integração segura"). Intervenções são sintéticas. Recuperação observada não comprova causalidade.

## L03-OFFLINE (feito, sem rede)
Os 71 casos da captura Codex (PR #61, `l03-prep-v1`, HTTPS local, sintéticos) estão em `src/test/fixtures/l03-prep-v1/` e são reproduzidos por `FixtureTransport` em `src/test/l03-fixtures.test.ts` (`bunx vitest run`). Não é integração live; a UI continua em demonstração.

## Ligação futura (L03)
1. Obter o contrato OpenAPI da API L01.
2. Implementar um adaptador real de `CenterwayApiClient` chamado via funções de servidor (nunca PostgreSQL direto do browser).
3. Trocar `api` em `mock-adapter.ts`.
4. Ativar escrita só após autenticação/autorização seguras.

## L03.2-PREP (headless, inactive)
- `src/data/session-controller.ts`: session states logged_out/authenticating/authenticated/expired/forbidden/unavailable, TTL, 401 wipe, 403 keeps session, directory pagination, journey-derived flow, in-memory drafts.
- `HttpTransport` base URL must be a bare HTTPS origin (no path, query, fragment or credentials).
- Activation gates (not met): public HTTPS API, exact CORS origin configured server-side, explicit approval of an L03 live mission. Neither module is imported by the app.

