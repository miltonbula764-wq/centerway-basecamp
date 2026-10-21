# Missão 20.6 — preparação da validação hospedada

Base: `main` **d0ca58b1a0ab7fc45f3ee56751601b0407f17175**, integração da Missão 20.5/PR #25. Esta missão prepara a auditoria; **a aprovação do ambiente hospedado permanece PENDENTE**. Não houve acesso à Lovable, Supabase hospedado, execução de deploy, migrações ou alteração de Cron hospedados. Os testes Actions usam exclusivamente infraestruturas descartáveis existentes. Não se repetiu a campanha manual da Missão 20.5 nem se criaram funcionalidades comerciais.

## Parecer de prontidão

O repositório fornece contratos e regressões para autenticação, isolamento, C01–C10 e monitorização. Isso permite preparar uma campanha controlada, mas não comprova a configuração instalada. Documentos históricos (incluindo `supabase/tests/DEVELOPMENT_READINESS.md`) não são inventário atual do projeto remoto. Não presumir que 0020–0027, a função Edge ou o Cron já estejam instalados.

Bloqueadores antes de qualquer ensaio hospedado: identidade inequívoca do projeto/base/versão publicada, inventário de migrações efetivamente aplicadas, ACL/RLS e função Edge conformes, duas empresas sintéticas segregadas e contas reais com papéis distintos, propriedade/capacidade/calendário do Cron conhecidos, backup restaurável e responsável pela janela. Nenhum destes pontos foi certificado remotamente nesta missão.

| Área | Prova preparada / aprovação exigida | Estado hospedado |
|---|---|---|
| Autenticação | Sessão real confirmada; `/auth/v1/user` corresponde ao utilizador esperado; sem sessão/expirada/revogada recusadas; admin/operator/viewer reais; logout limpa cache e troca de empresa não publica resposta antiga | Pendente |
| RLS | Catálogo sem RLS desligada; duas empresas com sentinelas não vazias; leituras próprias completas, filtros/IDs estrangeiros vazios ou recusa prevista, inclusive RPCs; anon sem dados privados; nenhuma service key no browser | Pendente |
| Migrações | 28 ficheiros 0000–0027 inventariados por SHA-256 e journal; reconciliar com ledger real e definições instaladas, constraints compostas, triggers e ACLs; nenhuma divergência inexplicada | Pendente |
| C01 | Função `ingest-v1`, caminho `/observations`, contrato e configuração `verify_jwt=false` confirmados; GET produz 405 `method_not_allowed`, sem RPC de ingestão; chave própria de integração nunca confundida com JWT | Pendente |
| Core / C02–C10 | Leituras autorizadas e paginação sem escritas; histórico/versionamento e elegibilidade preservados; nenhuma análise, caso, autorização, execução ou C10 derivada de uma simples leitura | Pendente |
| Cron | Um único job esperado, comando corrigido, papel restrito, dono/base certos, calendário minuto e estado deliberado; execução natural + tentativa por empresa, falhas de ambas as camadas observadas | Pendente |
| Monitorização | Central, responsabilidades e inbox por destinatário; paginação cobre conjunto conhecido; entradas antigas identificáveis, falhas recuperáveis; revisão é pendência humana, não conclusão de valor | Pendente |
| Operação | Logs sem segredos; limites de carga/janela aprovados; responsável, backup e reversão ensaiados em cópia; sem impactos em clientes reais | Pendente |

Uma consulta vazia não prova RLS. Um 200 não prova destinatário correto. `rls=true` não prova que as policies sejam corretas. O analisador sinaliza um subconjunto de bloqueadores: saída 0 significa somente que não encontrou esses desvios no snapshot fornecido, **nunca aprovação hospedada**. Também são obrigatórias as provas manuais/contextuais desta matriz.

## Reprodução sem contacto remoto

```sh
python3 -m unittest discover -s scripts/hosted-readiness -p 'test_*.py' -v
python3 scripts/hosted-readiness/audit.py > /tmp/centerway-source-readiness.json
```

Só lê ficheiros locais; não lê `.env`, não recebe URL nem executa SQL/HTTP. `migration-manifest.json` fixa os bytes dos 28 SQL e a ordem do journal. Alteração inesperada falha o teste. O manifesto não é uma lista de migrações executadas.

O job `browser` de `browser-e2e.yml` executa os 14 testes offline, ambas as consultas SQL na sua base descartável e analisa o catálogo completo. Nesse job não existe `pg_cron`: a consulta deve devolver `available=false`; o bloqueio é reconhecido, não transformado em aprovação. As regressões existentes mantêm autenticação real descartável, SQL/RLS, concorrência, browser, recuperação, unitários, tipos, build e auditorias. A prova real do scheduler da Missão 20.5 continua no job existente separado; não a confundir com o teste offline do analisador.

## Recolha futura de metadados — somente após autorização

**Não executada nesta missão.** O operador selecionará explicitamente a ligação TLS do projeto autorizado num serviço/libpq privado, sem password em argumentos, scripts ou logs. Não usar o pooler em modo transação para uma revisão que dependa de identidade de sessão. Confirmar previamente destino, papel e base; não reutilizar variáveis de ambientes antigos. Executar como operador de auditoria autorizado a consultar catálogos e os metadados Cron. Isso é diferente de testar RLS como utilizador final.

```sh
# FUTURO: o nome de serviço privado determina o destino, não o repositório.
# Guardar fora de Git/artifacts públicos, com permissões 0600 e diretório 0700.
psql -X -qAt 'service=centerway_audit_approved sslmode=verify-full' \
  -v ON_ERROR_STOP=1 -f scripts/hosted-readiness/catalog.sql > catalog-private.json
psql -X -qAt 'service=centerway_audit_approved sslmode=verify-full' \
  -v ON_ERROR_STOP=1 -f scripts/hosted-readiness/cron.sql > cron-private.json
python3 scripts/hosted-readiness/audit.py --catalog catalog-private.json --cron cron-private.json
```

As consultas usam transação **READ ONLY**, timeout 15s, lock timeout 2s e ROLLBACK. Não leem linhas de clientes, credenciais, sessões, payloads, comandos de outros jobs ou mensagens de erro potencialmente sensíveis. O catálogo inclui nomes/ACLs, hashes de definições, constraints e triggers; mesmo esses metadados merecem acesso restrito. Falta de permissões/objeto gera erro ou resultado bloqueante; não elevar privilégios automaticamente. Não chamar RPCs de negócio nestas consultas.

O inventário inclui a localização de possíveis ledgers `__drizzle_migrations`/`schema_migrations`, sem presumir equivalência entre Drizzle e o migrador gerido. O operador deve inspecionar o esquema real do ledger, exportar apenas identificador, hash e data e reconciliar cada entrada com o processo que a produziu. Os marcadores de reconciliação 0017/0019/0023/0024/0027 não substituem os SQL anteriores: confirmar bytes e objetos, não apenas o último número. Nunca preencher o ledger para esconder uma divergência nem executar `drizzle push`. Comparar as definições/ACLs/FKs/triggers com uma base descartável da mesma revisão; hashes de `pg_get_functiondef` dependem da versão PostgreSQL e exigem revisão de diferenças de formatação/owner, não reparação automática.

## Verificações HTTP e UI não destrutivas preparadas

Executar futuramente com browser/cliente aprovado, sessão já existente e chave pública, sem registar headers, cookies, tokens, email ou corpos privados em artifacts. TLS deve manter verificação. Não criar contas, resetar passwords, desativar confirmação de email ou obter service keys como parte desta leitura. Login/refresh/logout podem alterar sessões de autenticação: são um ensaio funcional separado e precisam de janela autorizada, embora não alterem dados comerciais.

1. `GET /auth/v1/user` com a sessão própria: 200 e ID igual ao da conta autorizada. Repetir sem sessão: 401/403, sem perfil privado. Uma sessão revogada deve ser recusada; não provocar a sua revogação na fase de leitura. Registar apenas status e ID sintético anonimizado. A confirmação de identidade não prova RLS.
2. `GET /rest/v1/subjects?select=id,tenant_id&tenant_id=eq.<EMPRESA_A>&limit=25` como membro A: comparar com a lista privada de sentinelas A; repetir filtro B: zero linhas ou recusa contratual. Inverter como B e como viewer; anon não vê sentinelas. Repetir por ID direto em `observations`, `c03_bundles`, `c04_evaluations`, `cw_operational_cases`, `cw_review_entries` e `cw_notifications`, evitando campos sensíveis. Listas devem ser paginadas até ao fim; comparar conjunto, não só contagem. Nenhuma consulta com `service_role` conta como prova de RLS.
3. `GET /functions/v1/ingest-v1/observations`, sem credencial de integração: 405 e código `method_not_allowed` no contrato atual; gateway pode exigir `apikey` pública. 404/401 inesperados exigem investigar instalação/gateway; não os aceitar como sucesso da API. O handler verifica método antes de autenticar ou chamar PostgreSQL. Isto prova presença/roteamento, **não ingestão funcional**. Mesmo GET gera logs técnicos; não é ausência total de efeitos operacionais.
4. Leitura das RPCs existentes por GET PostgREST, com parâmetros nomeados dos contratos/tipos da revisão: `core_followup_queue`, `scheduled_reviews`, `case_responsibility`, `notification_inbox`, `operational_cycle_history`. Usar IDs sintéticos conhecidos, `_limit` documentado e cursores retornados; repetir cada página e comparar IDs. Não usar POST a RPCs arbitrárias para descobrir se escrevem. Não chamar `prepare_scheduled_reviews`, `prepare_operational_notifications`, `mark_notification_read` ou comandos Core: escrevem. Comparar versões/históricos antes/depois; um Cron concorrente pode legitimamente atualizar monitorização, por isso correlacionar atores/instantes sem exigir congelar o serviço.
5. UI `/app/acompanhamento`: abrir/filtros/paginação e inbox; não carregar nos botões de preparação, atribuição, leitura de notificação ou transição. Troca de empresa e respostas pendentes não podem mostrar dados da outra. Não atualizar prazos nem contornar janelas com o relógio do browser.

Sem sentinelas pré-existentes, permissões de leitura suficientes ou baseline, marcar **NÃO EXECUTADO / BLOQUEADO**. Criar dados sintéticos, credenciais de integração, enviar POST C01 (mesmo inválido pode persistir tentativas), fazer correções/replays e percorrer C02–C10 são uma fase funcional hospedada posterior, explicitamente autorizada e segregada. Os ensaios locais existentes fundamentam o desenho dessa fase, mas não a substituem.

## Cron: descoberta e correção segura do comando instalado

O defeito comprovado no PR #25 era o comando com `BEGIN; ... COMMIT;`. Em `cron.use_background_workers=on`, pg_cron já fornece a transação: o wrapper explícito provocou `BeginInternalSubTransaction: unexpected state BEGIN` ao entrar nas subtransações PL/pgSQL do worker. A correção retirou **apenas** esse wrapper. Não concluir que todo modo/versionamento Cron tem o mesmo sintoma; verificar a extensão, configuração e logs do destino. A ausência dessa mensagem não prova que o comando esteja atualizado.

Comando canónico, conservando timeout 45s, capacidade e lote:

```sql
SET LOCAL statement_timeout='45s'; SET LOCAL ROLE centerway_review_scheduler; SELECT public.process_review_schedule(10);
```

A consulta `cron.sql` inspeciona apenas `centerway-prepare-reviews-v1`, não expõe o comando bruto, assinala wrapper antigo, comparação canónica e calendário `* * * * *`. Ausência, duplicação, comando/calendário diferente, estado inativo, falha ou execução sem fim são bloqueadores para certificar operação normal. Um job intencionalmente inativo não deve ser reativado por um teste. Os últimos 20 registos não cobrem todo o histórico; o operador deve filtrar o intervalo de manutenção e investigar execuções antigas ainda em curso. O estado `succeeded` significa que a chamada SQL terminou: falhas por empresa são capturadas pelo produto e podem coexistir com esse sucesso.

Procedimento futuro, **não autorizado para execução nesta missão**:

1. Identificar projeto, base, extensão e versão, `cron.use_background_workers`, timezone, dono do job e capacidade `centerway_review_scheduler` (NOLOGIN/NOINHERIT/sem superuser/BYPASSRLS). Verificar que anon/authenticated/service_role/authenticator não herdam essa capacidade. Confirmar o worker SECURITY DEFINER, search_path e grants exatos; nenhum papel público o executa.
2. Numa sessão privada de administrador, recolher **o registo completo desse único job** e o comando original exato, `md5(command)`, dono, base, host/porta, calendário e estado. Guardar encriptado/restrito, fora dos artifacts. Fazer snapshot/backup pelo processo gerido e confirmar restauro numa cópia. Se já é canónico, não escrever. Se está ausente/duplicado ou difere além do wrapper, parar e investigar; não criar outro job.
3. Rever janela de mudança, instâncias em curso e possíveis revisões/notificações. Atualizar um comando só afeta próximas execuções; não cancela workers ativos. Se for necessária pausa, desativar **só o job identificado**, apenas com autorização específica, aguardar fim dos workers e depois atualizar; preservar o estado original e combinar explicitamente o momento de reativação. Não cancelar sessões genéricas. O advisory lock do template só coordena operadores que o utilizem, não fornece pausa do scheduler.
4. Preparar e rever cópia privada de [`update-cron.sql.example`](../scripts/hosted-readiness/update-cron.sql.example), substituindo todos os placeholders. O ficheiro não é executável sem edição, não integra workflows nem migrações. Usa ID + nome único + fingerprint do comando e comparação de dono/base/calendário/estado; aborta se houver drift. `cron.alter_job(..., command := ...)` altera **somente o comando**. Se a versão instalada não suporta a assinatura/permissões, parar e rever a compatibilidade; não atualizar diretamente `cron.job`, nem conceder superuser. Os BEGIN/COMMIT exteriores pertencem à manutenção, não à string do job.
5. Confirmar antes do commit/recolha seguinte que ID, nome, dono, base, host/porta, calendário, estado e número de jobs ficaram iguais; só o comando deve diferir. O instalador `scripts/monitoring/install-cron.sql` é para a instalação gerida: usar `cron.schedule(nome,...)` sem investigar pode criar um job sob outro dono ou alterar calendário. **Não o reaplicar cegamente** como reparação de um job existente.
6. Observar pelo menos dois ticks **naturais** no calendário minuto original e, se existir backlog, um ciclo completo por empresa sintética. Correlacionar `cron.job_run_details` (status/tempos) com `cw_review_attempts` (`actor_kind=scheduler`, `actor_id IS NULL`), cursor/`last_completed_at` conforme esquema instalado e revisões/notificações esperadas. Não invocar o worker manualmente e chamar a isso prova de scheduler; não acelerar calendário ou falsificar relógio no hospedado. Sem backlog não se exige uma tentativa nova por tick; o ciclo completo anterior pode ainda não estar elegível. Identificar falhas por empresa e outbox separadamente.
7. Confirmar conjunto de destinatários, ausência de duplicados por acontecimento/destinatário e nenhuma nova análise C02–C04, caso, autorização ou decisão C10 atribuível ao worker. Distinguir atividades humanas concorrentes pelos atores/eventos. Interrupção sem tentativa persistida exige logs de infraestrutura. Sem acesso a esses registos, a prova fica incompleta.

## Reversão e riscos

- **Antes do commit da manutenção:** qualquer falha aborta a transação; executar ROLLBACK e confirmar comando original. Timeouts de lock devem interromper a mudança, não ampliar indiscriminadamente o timeout.
- **Depois do commit:** capturar diagnóstico privado. Se o comando anterior já era defeituoso, restaurá-lo e reativá-lo não é uma recuperação segura: com autorização de incidente, desativar somente esse job e manter preparação humana autorizada por lotes, registada como manual. Não apaga backlog/histórico. Se a mudança era sobre um comando comprovadamente funcional, restaurar por `cron.alter_job` o comando exato previamente guardado, verificando ID/fingerprint atual para impedir sobrescrever outra intervenção. Restaurar estado/calendário/dono/base originais; mudanças adicionais exigem plano próprio. Não dar UPDATE a tabelas comerciais para desfazer notificações/revisões já entregues.
- Não há down migration nesta missão. Se o inventário de migrações divergir, bloquear campanha e abrir revisão independente de migração; nunca tentar reverter migrações históricas para passar a auditoria. Reverter o commit de preparação não reverte um comando que alguém venha a instalar no futuro.
- Secrets/PII, projeto errado, drift de função Edge, grants excessivos, cursor atrasado, outbox em retry, duplicação sob donos diferentes, workers simultâneos e histórico sem retenção são riscos a verificar. As duas consultas metadados usam snapshots separados; não são fotografia atómica do sistema. Recolher timestamps e repetir se houver manutenção concorrente.
- Não há SLA comercial ou garantia de latência de produção. A cadência minuto, lote de empresas e páginas de referências limitam o progresso; definir budget técnico e timeout de observação antes da campanha. Ausência de alertas não garante sucesso; incluir tentativas técnicas/outbox e logs Cron, sem inventar outro scheduler/classificador.

## Evidência e decisão

Registar revisão Git, projeto/base (no inventário privado), versão PostgreSQL/pg_cron/Edge/frontend, janela UTC, operador e papéis, resultado esperado/obtido de cada linha da matriz, cursores/IDs sintéticos, falhas e passos de reversão. Redigir artifacts antes de partilhar: nunca credenciais, tokens, comandos de outros jobs ou dados de clientes. Cada item fica APROVADO, REPROVADO ou NÃO EXECUTADO, com motivo e ligação à evidência. Aprovação exige todos os bloqueadores resolvidos e revisão humana. O PR entrega instrumentos e critérios; a execução/alteração hospedada continua para uma autorização posterior.
