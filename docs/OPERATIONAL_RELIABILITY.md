# Fiabilidade e recuperação — Missão 19

Trabalho sobre a main `f4805ece488a6a6be0dc4e6cc31ed32199043727`. Sem acesso à Lovable/Supabase hospedado, deploy, merge, serviços pagos ou dados reais.

## Problemas corrigidos e fronteiras

- **Upload HTTP sem prazo próprio:** um corpo JSON que nunca terminava mantinha o handler à espera antes do timeout do pedido à base. A leitura tem agora prazo total de 10 segundos, limite existente de 2 MB e cancelamento por desconexão. Um cancelamento do stream que também não termina não prende a resposta. Retorna 408 sem iniciar importação. O limite de 30 segundos no transporte à RPC permanece.
- **Confirmação perdida após commit:** a interface CSV afirmava «Nada foi gravado» em qualquer erro de rede. Agora declara que o resultado é desconhecido e orienta a consultar o histórico/repetir o mesmo ficheiro e chaves. O endpoint devolve 503 com `Retry-After: 1`, `request_id` e `retry_same_idempotency_key: true` quando não consegue confirmar o resultado. Não faz retries automáticos nem altera os limites C01.
- **Diagnóstico HTTP:** logs estruturados `c01_http` incluem apenas status, código técnico limitado, duração, request_id e UUID de operação válido. Nenhum token, password, chave de integração, payload, email ou mensagem SQL é registado pelo handler. UUIDs permitem cruzar uma tentativa com o histórico C01 por operação; não são credenciais.
- **Plano genérico do Core:** a carga revelou consultas de vários segundos com plano genérico, contra dezenas de milissegundos com plano específico para os parâmetros, para as mesmas entradas sob RLS. A migração provisória 0026 define `plan_cache_mode=force_custom_plan` somente em `_core_followup_engine`. Preserva corpo, classificador, assinatura, autorização e RLS. A prova compara hashes das entradas e mede antes/depois; não fixa um SLA artificial. Não foram adicionados índices especulativos.
- **Dependências:** atualizadas as resoluções vulneráveis de brace-expansion nas linhas 1/5, js-yaml 4, nanoid 3, shell-quote 1 e source-map-js 1; a linha antiga esbuild 0.18 usada pelo tooling passa a 0.25.12 por override, validado com instalação frozen, testes/build e smoke check Drizzle. Não se atualizou a arquitetura TanStack/Lovable nem se acrescentaram bibliotecas de runtime. A auditoria online é uma fotografia dos avisos conhecidos, não prova de ausência de vulnerabilidades futuras.

Autenticação/equipas, C01–C04, Core/ciclos, monitorização/notificações e onboarding mantêm os contratos existentes. A campanha anterior completa permanece ativa. Atribuição de responsáveis não autoriza intervenções; um recibo ou término de janela não prova valor. A chegada de dados e os workers não abrem, executam ou encerram casos.

## Campanha reproduzível

O workflow `.github/workflows/browser-e2e.yml` monta PostgreSQL17/GoTrue/PostgREST próprios, com emails exclusivamente sintéticos auto-confirmados no ambiente de teste. Migrações são aplicadas em ordem sobre fixtures não vazias, com comparação de dados/grants anteriores.

1. Regressões SQL/RLS, HTTP, API HTTPS local, equipas, C02–C04, Core, múltiplos ciclos, agendamento, responsáveis/notificações e onboarding.
2. `e2e/reliability/scale.py --seed`: 100 novas empresas, 1.000 clientes, 100.000 observações, todas pela importação C01 autenticada; uma empresa tem 505 clientes e as restantes 99 têm cinco. A fonte e todos os nomes são explicitamente sintéticos.
3. `plan.py --baseline`, instalação exclusivamente descartável de 0026 e `plan.py`: mesmas entradas sob role/JWT claims PostgreSQL, medição de planos genérico/específico e confirmação de saída equivalente após correção. Estes probes SQL não são apresentados como logins HTTP.
4. Browser real, incluindo conta nova até C04, permissões, sessões, respostas tardias e o commit CSV cuja confirmação é deliberadamente perdida antes da interface repetir as mesmas chaves.
5. `scale.py`: 10 casos, dois ciclos completos por caso, autorizações próprias, janelas reais explicitamente configuradas de um segundo e resultados inconclusivos por ausência de medições posteriores. Lotes/filas e consultas são medidos; 24 pedidos concorrem em oito ligações com três identidades autenticadas reais. Paginação integral do tenant maior. A preparação usa o Core existente; não há outro classificador.
6. `recovery.py`: desconexão de transação C01 após escrita/before commit, perda de resposta depois de um commit HTTP real, término do backend de um comando Core HTTP bloqueado num gatilho só de testes, replay sem novo ciclo duplicado, processamento de outbox interrompido e reinício real de PostgREST. Barreiras/gatilhos de falha são removidos e nunca pertencem à migração do produto.
7. `restore.py`: backup lógico privado e restauração num segundo PostgreSQL17 independente, sem porta pública; comparação de todas as linhas public/auth, sequências, roles, membros de roles, owners, grants, RLS/policies, funções, triggers, constraints e índices. GoTrue/PostgREST separados comprovam login real e isolamento na base restaurada. Uma paragem PostgreSQL `immediate` exige recuperação WAL e preserva dados comprometidos. O supervisor de testes conserva o tmpfs enquanto o processo PostgreSQL reinicia; não é alegado que tmpfs sobrevive à perda do container/host.
8. Auditorias Bun/npm, smoke check de Drizzle, unitários com rede bloqueada, tipos e build.

Executar estes scripts apenas após preparar a stack e fixtures conforme o workflow. Guardas recusam bases remotas e containers existentes não autorizados. Ficheiros de backup, hashes de autenticação e env de teste ficam em `e2e/private`, fora dos artifacts; são removidos após o teste de restauração. Apenas relatórios agregados e logs de validação são publicados como artifacts temporários do workflow.

## Medições e interpretação

`e2e/logs/reliability-*.json` regista versão PostgreSQL, shared_buffers, max_connections, CPU/cgroup, memória, duração de importações, mediana/máximo de cinco amostras por consulta, paginação e leituras concorrentes. O snapshot Docker e contadores PostgreSQL delimitam o consumo observado. `memory.peak` é o máximo de vida do cgroup inteiro, não um pico exclusivo do teste/servidor. Snapshots não são um perfil de consumo contínuo.

O ambiente local usa quota de dois CPUs, limite de memória 8 GiB e tmpfs; o runner GitHub tem hardware próprio identificado em cada relatório. As amostras incluem HTTP, autenticação e PostgreSQL quando indicado; a comparação de planos é uma medição SQL separada. Dados sintéticos, caches quentes, pequeno número de amostras e hardware partilhado impedem extrapolar capacidade de produção ou prometer RTO/RPO/SLA. Os relatórios locais e Actions são resultados de execuções distintas.

## Diagnóstico e retoma operacional

- CSV/API: consultar lote, erros por linha, operação idempotente e proveniência. Em resposta perdida, reutilizar as chaves originais; não gerar outra identidade para «tentar de novo». Uma falha temporária de transporte não comprova rollback. Uma resposta de lote recusado efetivamente persistida continua a indicar atomicidade/zero inserções.
- API: correlacionar request_id nos logs e operation_id nos registos existentes; 429 exige aguardar Retry-After. 401 exige verificar expiração/revogação e rotação autorizada, nunca usar service_role como substituição. Uma chave desconhecida não permite atribuir com segurança uma falha a uma empresa; não se inventa esse vínculo.
- C02/C03/C04/Core: consultar versões, cut-offs, referências e eventos; repetir com identidade original quando o contrato a oferece. Conflito de versão exige atualizar o dossier, sem sobrescrever decisões concorrentes. Autorizações permanecem ligadas ao seu plano/ciclo.
- Monitorização/outbox: consultar tentativas e SQLSTATE, fase/cursor e next_try_at. Retomar os workers existentes, de forma limitada e autorizada; trabalhos bloqueados por transação interrompida são libertados pelo PostgreSQL. Respeitar backoff técnico; não encurtar janelas de negócio ou alterar o relógio. O Cron hospedado continua a exigir configuração separada.

## Backup hospedado e instalação posterior

A migração **0026 é provisória**: a **0025 ainda aguarda instalação hospedada**, conforme contexto recebido. Instalar 0025 e depois a alteração nova, apenas após revisão e confirmação/reconciliação da numeração. Não reescrever 0000–0025, snapshots ou marcadores existentes. Esta missão não aplica nada no serviço hospedado.

O teste lógico não configura nem verifica backups Supabase hospedados. A integração responsável precisa de definir frequência, retenção, cifragem/acesso, capacidade de restauração, RPO/RTO e eventual PITR conforme o plano efetivamente disponível, sem ativar serviços pagos sem autorização. JWT/provider secrets, configuração de GoTrue/Edge Functions, credenciais de conexão e objetos de Storage requerem recuperação própria; pg_dump não os fornece. Globals são exportados sem passwords de roles. Roles especiais e procedimentos de restauração do Supabase gerido não podem ser presumidos idênticos ao laboratório PostgreSQL. Repetir um ensaio autorizado na infraestrutura de destino antes de afirmar prontidão de recuperação em produção.

## Review freshness regression found during validation

The unchanged 0020 implementation on main can miss new immutable inputs:
`ingested_at`/`created_at` use transaction start, but `checked_at` uses wall time.
A long/concurrent transaction (or the same SQL transaction) can therefore add an
observation after preparation whose timestamp is earlier than `checked_at`.
The temporal regression now refreshes entries immediately before import, so an
unrelated already-stale entry cannot mask this defect. It asserts current → stale
→ current without modifying clocks, deleting checks or editing old observations.

Provisional 0026 adds an invoker/RLS-protected immutable-input identity token to
the mutable review cache and compares it during reads. Existing snapshots without a
token require preparation once; old events are preserved. The token is outside
business facts/fingerprints: adding or updating it alone creates no review event
or notification. This is invalidation,
not a second classifier: `_review_facts`, C02/C04/Core decisions are unchanged.
It covers observations, analyses, configurations, evaluations and case events,
including transactions with timestamps predating preparation. No cases are
modified by reads. The original temporal regression runs after 0026 in CI.

Restore verification compares effective table ACLs (`aclexplode` with PostgreSQL
defaults), since pg_dump can restore an explicit owner-only ACL as the equivalent
NULL default. Owners, grantors, grantees, grant options and every permission remain
checked. Auth/REST are quiesced before the abrupt-crash fingerprint, avoiding
legitimate session writes during the comparison interval; real login/RLS are
verified both before and after recovery.

Logical restore requires exact table rows and sequence values. After an abrupt
PostgreSQL crash, sequences can legitimately advance over unused WAL-preallocated
values (observed: GoTrue `refresh_tokens_id_seq` +31), unlike transactional rows.
The crash test requires identical committed rows/catalog, non-cyclic sequences,
no backward movement/reuse, and reports those gaps. Contiguous identifiers are
not a PostgreSQL guarantee; gaps are not evidence of lost application records.

## Logout e respostas não autorizadas

O ensaio de browser verifica login GoTrue, logout HTTP bem-sucedido, remoção da
cache e bloqueio de nova navegação protegida. Uma chamada deliberada a `/user`
com a sessão acabada de revogar devolve 403 `session_not_found` nesta versão do
GoTrue; uma chamada anónima à RPC protegida devolve 401 sem dados da empresa.
Essas recusas são proteção esperada, não sucesso de uma operação protegida.
O 401 intermitente do ensaio local anterior não incluía a URL: não foi possível
atribuir retrospectivamente a sua origem. O teste original mantém a verificação
estrita de erros de consola e agora regista somente método/caminho de qualquer
401 inesperado, sem headers, query strings, tokens ou corpos. Repetições locais
do percurso de logout passaram; o resultado da campanha limpa Actions é separado.

O ensaio de recuperação da outbox respeita o limite de 25 trabalhos por chamada:
drena o backlog com um máximo explícito de chamadas, exige entrega/attempt única
do plano interrompido, ausência de trabalhos pendentes/falhados no tenant de
ensaio, e compara o hash integral das notificações em três chamadas sem trabalho.
Crescimento por processamento de eventos diferentes não é confundido com duplicação.
