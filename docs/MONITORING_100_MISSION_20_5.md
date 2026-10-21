# Missão 20.5 — monitorização contínua de 100 clientes

Base: `main` `899f10590f9a72298071024eafe7d23810442421`, com 20.4 integrada. Ensaio exclusivamente descartável, sem Lovable, Supabase hospedado, publicação ou merge. Usa a mesma Central, motor de revisão, scheduler e outbox existentes; não acrescenta classificador, agendador ou políticas comerciais.

## Plano antecipado e cobertura

[Plano executável](../e2e/monitoring-100-plan.json) fixado antes dos dados. Empresa **Pulse SaaS** com **100 clientes**, dois indicadores numéricos independentes (`cycle_minutes`, menor é melhor, meta ≤60 min; `delivery_pct`, maior é melhor, meta ≥95%). Segunda empresa com três clientes e outro administrador, perfil e credencial C01. Autenticação GoTrue/password grant real para cinco contas; PostgreSQL17 em tmpfs, PostgREST, C01 HTTPS com verificação de certificado. Dados inteiramente sintéticos, com documentos/objetivos humanos por URN.

Perfil aprovado: média, cadência diária, duas janelas de um dia, cobertura mínima 100%, denominador mínimo 1. Baseline e três dias históricos são enviados por C01; análises/avaliações são chamadas explicitamente por RPC. Deterioração exige duas janelas >150 min, ou ambas <95% para entrega. Metas individuais exigem **cada** janela selecionada. Todos os 100 clientes têm as duas configurações documentadas antes do envio.

| Clientes | Mudança enviada e expectativa definida | Resultado exigido pelo cenário |
|---|---|---|
| 001–020 | Duração 160→170 min nas janelas correntes | Antes de análise: revisão por novas medições. Depois da RPC explícita: C02 `deterioration_candidate`, C04 `not_achieved`. |
| 021–040 | Recuperação aparente, 55→50 min | Revisão sem inferência automática. RPC explícita: `no_deterioration`/`achieved`; sem abrir caso ou concluir promessa global. |
| 041–060 | Falta a última medição, cobertura insuficiente | `insufficient_data`/`inconclusive`, mantendo o cliente e indicador na fila. |
| 061–080 | Última medição atrasada | Inicialmente insuficiente; C01 posterior sinaliza nova revisão. Nova RPC demonstra 85→80 min: `no_deterioration`/`not_achieved`. |
| 081–100 | Duração 90→80 min; entrega 90→92% | Duração `no_deterioration`/`not_achieved`; entrega `deterioration_candidate`/`not_achieved`. Eixos independentes, sem score global. |
| 001–010 · correção posterior | 170→50 na última medição | Antes de RPC: nova revisão. Depois: `no_deterioration` porque a persistência deixa de existir; C04 continua `not_achieved` pois a janela anterior tem 160 min. Evidência anterior preservada. |

Os 100 resultados são comparados individualmente, não apenas por contagem agregada. `needs_refresh` é conservador por cliente: outro indicador pode invalidar o token de cache, mas os motivos de medição e as avaliações permanecem específicos de cada indicador. Isso é exposto como limite do contrato existente, sem novo classificador.

Dez casos são abertos por decisão humana sobre C04 inicial fundamentado; cinco aguardam autorização, três têm execução humana declarada e janela real de três segundos, um prossegue para ciclo 2 após C09 insuficiente e C10 `remain_open`, e outro permanece em investigação. Responsáveis iniciais: operador A em 001–005 e operador B em 006–010. O ciclo seguinte não reutiliza aprovação/execução. Os dez estados e versões permanecem idênticos durante ingestão/monitorização. Não há encerramento nem recuperação prospectiva alegada após uma espera curta.

## Cron real, preparação manual e concorrência

- **Execução real:** PostgreSQL17 com a extensão Debian `pg_cron`, `cron.use_background_workers=on`, job original `centerway-prepare-reviews-v1`, calendário `* * * * *`. Instalação repetida confirma um só job. Dois disparos naturais são comprovados por `cron.job_run_details` e tentativas `actor_kind=scheduler`, `actor_id=null`, correlacionadas com esses disparos (tolerância de observabilidade de 1 s: o launcher pode persistir `start_time` alguns milissegundos depois de o worker começar; nenhum timestamp de negócio é alterado). Depois desses dois disparos de minuto, o **mesmo job/comando** usa `5 seconds` exclusivamente como cadência técnica do ensaio descartável, até concluir uma volta completa sobre os 100 clientes (401 referências iniciais). São disparos reais adicionais de pg_cron, identificados separadamente; não representam a frequência de produção ou uma alteração de regras comerciais. Nenhum relógio de negócio muda. O job é depois removido apenas da base descartável.
- **Preparação manual:** `prepare_scheduled_reviews` via HTTP/JWT de admin/operator completa os percursos e as ondas. As tentativas registam `actor_kind=human` e o utilizador real. Essas chamadas não são apresentadas como execução agendada.
- **Provas diretas do worker:** quatro chamadas concorrentes sob o papel NOLOGIN `centerway_review_scheduler`, identificadas separadamente no resultado. Não contam como disparos Cron. O papel não tem acesso direto às tabelas nem capacidade C01–C10; authenticated/anon/service_role não podem invocar o scheduler.
- Lotes de revisão limitados a 50 referências e notificações a 25 trabalhos. Uma onda pode chegar depois de parte do cursor ter sido verificada: o teste conclui a volta em curso e uma volta completa seguinte, preservando os lotes existentes. Paginação da Central/revisões em páginas de 17 e inbox de 13 prova cursores completos, sem saltos ou duplicados. Existem 200 eixos de medição e, no fim, 410 referências ativas incluindo avaliações e casos. Os clientes continuam visíveis após cada onda.
- Quatro pedidos manuais iguais avançam uma única página/tentativa; atribuição concorrente com o mesmo UUID cria uma revisão; decisões concorrentes diferentes para a mesma revisão produzem HTTP 200/409, sem sobrescrever a decisão vencedora. A reatribuição final é outra decisão explícita. O número de avisos de atribuição pode variar conforme a decisão que vence; cada aviso é comparado com o histórico efetivamente persistido.

## Notificações e segurança

O teste verifica cada destinatário segundo o acontecimento original e a revisão de atribuição aplicável: autorização/falha → admin; revisão do caso/fim de observação → responsável válido ou admin de fallback; atribuição/alteração → membros explicitamente envolvidos. Plano e fotografia de revisão partilham a ocorrência e não duplicam o aviso de autorização. Novas evidências não repetem a mesma ocorrência de fim de C08. Ciclos repetidos sem mudanças não criam revisões materiais nem novas notificações.

Zero duplicados pela chave contratual empresa/adesão/acontecimento/tipo; caixas privadas por utilizador e empresa, leitor sem avisos alheios, marcação de leitura idempotente e negada a outro destinatário. Escrita direta nas tabelas de revisão, outbox, atribuições e Core bloqueada. Administração da outra empresa não lê dados nem executa RPCs da Pulse. SQL/RLS com papéis reais é separado dos logins HTTP e termina com rollback.

Cada ingestão verifica que C02–C04 e estados/eventos Core não mudaram. Cada fase de monitorização verifica hashes de medições, perfis, análises, evidências, avaliações e decisões humanas. Históricos iniciais de C01–C04, eventos Core e revisões/tentativas de monitorização permanecem intactos. Hashes C03 são reconstruídos por SQL independente. Leituras da Central/revisões/inbox não escrevem dados. Só as RPCs explicitamente chamadas criam novas análises; nenhum worker abre casos, autoriza, executa ou decide C10. Recibos sintéticos não certificam ações externas e `causality=not_established`/`promise_fulfillment=not_determined` permanecem explícitos.

## Falhas e recuperação

1. Erro de teste após a primeira atualização real da página, na segunda linha: subtransação reverte toda a página, `processed=0`, cursor sem avanço e tentativa persistida com **P0951**. Repetição do UUID devolve a falha original; operação nova recupera. Detalhes internos não chegam à resposta/inbox.
2. Erro de entrega de notificação: trabalho preservado com **P0952** e tentativa falhada imutável. O teste espera o **minuto real** de `next_try_at`; não altera esse timestamp. Processadores concorrentes recuperam com uma única notificação e duas tentativas (falha/sucesso).
3. Interrupção real de backend depois de preparar uma página dentro de uma transação ainda não confirmada: terminação dirigida com `pg_terminate_backend`, hashes completos iguais após rollback e repetição HTTP do mesmo UUID segura. É uma prova SQL com papel/claims autenticados, distinta de GoTrue HTTP. A tentativa interrompida não persiste porque a transação não confirmou; o relatório identifica a evidência de infraestrutura em vez de inventar uma tentativa de falha durável.

Triggers de injeção pertencem apenas ao ensaio descartável, são removidos em `finally` e não desativam guardas existentes. Não há relógio de negócio alterado, alteração de cadência ou critério comercial para facilitar resultados.

## Defeito comprovado e regressão

A primeira execução real do comando original, sob `cron.use_background_workers=on`, falhou com:

```text
FATAL: BeginInternalSubTransaction: unexpected state BEGIN
CONTEXT: PL/pgSQL function _review_process(uuid,uuid,uuid)
```

O comando de [install-cron.sql](../scripts/monitoring/install-cron.sql) continha `BEGIN ... COMMIT`. O background worker já inicia a transação; o `BEGIN` explícito deixa o estado interno incompatível com o bloco PL/pgSQL que trata falhas por subtransação. A correção retira somente esse par redundante, mantendo **`SET LOCAL statement_timeout='45s'`**, **`SET LOCAL ROLE centerway_review_scheduler`**, a mesma função e o mesmo calendário. Os disparos reais do cenário são a regressão, juntamente com a verificação dos limites de capacidade/timeout e da instalação idempotente. Nenhuma migração ou lógica comercial C01–C10 foi alterada. O job hospedado não foi consultado, instalado ou atualizado.

## Resultados, tempos e reprodução

Execução local de 2026-10-21: **2.863 asserções integradas** e **283 verificações SQL/RLS** aprovadas (67 permissões +35 C01 +70 C02 +40 C03 +71 monitorização). [Resultado por cliente, 100 linhas](MONITORING_100_MISSION_20_5_CLIENTS.csv) e [resumo técnico](MONITORING_100_MISSION_20_5_RESULTS.json).

- 100/100 clientes, 200 eixos e 410 referências ativas; segunda empresa com três clientes isolados.
- 15 pedidos C01, 1.168 apresentações aceites: **968 medições únicas** (950 principais +18 de controlo) e **200 reapresentações idempotentes**, zero rejeições de medições.
- Empresa principal: 231 análises/pacotes C03, 462 avaliações C04, dez casos e 39 eventos Core preservados, 1.252 revisões materiais e 191 tentativas de preparação.
- **1.229 notificações internas**, zero duplicados: autorização 5, atribuição 12, revisão de evidência 295, fim de observação 3, falha operacional 1, alteração de responsável 2, revisão disponível 911. Totais exclusivos deste ensaio; decisões concorrentes podem produzir contagens diferentes noutra execução, sempre verificadas contra os destinatários e acontecimentos persistidos.
- Cron real: dez disparos bem-sucedidos (dois no calendário original e oito na cadência técnica de cinco segundos), com volta completa dos clientes antes de qualquer preparação manual. Três provas de falha/interrupção recuperadas; um defeito real corrigido no comando Cron.

| Operação local | Chamadas | Mediana | p95 | Máximo |
|---|---:|---:|---:|---:|
| Lote manual de revisão | 181 | 40,4 ms | 64,7 ms | 113,1 ms |
| Página de revisões | 296 | 17,3 ms | 22,0 ms | 32,4 ms |
| Página da Central | 25 | 29,1 ms | 806,5 ms | 846,9 ms |
| Lote de notificações | 13 | 2,0 ms | 2,6 ms | 2,6 ms |
| C02–C04 explícitos, onda principal | 100 | 43,4 ms | 50,6 ms | 78,4 ms |

O resumo versionado e o artefacto distinguem contagens da empresa principal e de controlo, notificações por tipo, tentativas humanas/worker/Cron e tempos medidos por operação (mediana, p95, máximo). São tempos desta carga sintética e deste ambiente, sem SLA ou benchmark de produção.

Workflow [browser-e2e.yml](../.github/workflows/browser-e2e.yml), job independente **Monitoring / 100 customers and real pg_cron**. Recria a base vazia e executa [monitoring-100.py](../e2e/monitoring-100.py); mantém todas as missões anteriores, browser, auditorias, regressões unitárias, tipos e build. CI final e commit estão ligados no PR.

Reprodução local: Linux, Docker, Python3.12+, psql, OpenSSL e Bun1.3.0; checkout isolado sem `.env`, portas 5432/54321/54443 livres. `monitoring-cron-setup.py` cria exclusivamente um novo container rotulado com tmpfs e instala a extensão a partir de pacotes Debian assinados antes de iniciar PostgreSQL. Não apontar a uma base existente/remota.

```sh
export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=postgres PGDATABASE=cw_e2e
export PGPASSFILE=/dev/null PG_CONTAINER=cw-mvp-db CW_LOCAL_MVP=1
python3 e2e/monitoring-cron-setup.py
python3 e2e/start_backend.py --local-mvp
python3 -u e2e/monitoring-100.py
python3 scripts/mvp/stop-local.py
```

Aguardar os disparos e a repetição natural de um minuto faz parte do teste. Limpeza também após falha (`if: always()` no CI). Artefacto `monitoring-100-<run>-<attempt>` inclui esperado/obtido por cliente, casos, medições, evidências, revisões, outbox, notificações, tentativas e logs SQL. Credenciais/`.env` não são publicados no artefacto. Retenção de três dias; plano, cenário e resumo local ficam no repositório.

## Limites

A prova de Cron real vale para a instância descartável com background workers, não para o serviço hospedado. A fila é uma fotografia e a deteção tem lotes/cursor/frequência técnica, sem latência garantida. Um token conservador pode pedir refresh de outro eixo do cliente, sem alterar a avaliação desse indicador. Avisos preparam revisão humana; não comprovam deterioração, causalidade, recuperação, documentos externos ou promessa global. Um cancelamento antes de commit pode exigir logs de infraestrutura para ser identificado. Não há política nova de retenção, prioridade, elegibilidade ou intervenção. A NEXORA LAB independente não foi criada.
