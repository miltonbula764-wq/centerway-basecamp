# Monitorização e revisões programadas — v1

A migração **0020** prepara revisões humanas. Não executa C02/C03/C04, não abre casos nem executa/encerra intervenções. As permissões e os contratos existentes continuam a autorizar cada operação. O cenário FlowReports mantém o seu contrato específico.

## Fontes e significado

- O Core fornece estados, fundamentos, próximas orientações e janelas pela mesma projeção de `core_followup_queue`. A extração para `_core_followup_projection` preserva o contrato público e RLS. O worker pode ler a projeção como proprietário da função; não cria uma sessão humana.
- Cada indicador aprovado tem uma entrada de medição independente, incluindo denominadores documentados e compatibilidade de fingerprints C02. Observações C01 provenientes de CSV e API são tratadas igualmente. Medições posteriores ao corte ou ao `as_of` da análise exigem nova revisão. Isto não prova deterioração.
- A cadência documentada, ancorada na última medição compatível, permite sinalizar dados desatualizados. Sem cadência ou medição de referência, há uma pendência explícita; nenhum prazo é criado.
- O prazo C04 vem da configuração versionada. Contradição, configuração incompleta ou revisão de contrato histórico continuam pendentes. Indicadores independentes não se bloqueiam mutuamente.
- A data C08 vem da execução autorizada. Antes dela, aguarda-se; depois, é possível rever a suficiência das medições. C09/C10 aberto continua com necessidade de evidência. Só o estado persistido `closed_resolved` é apresentado como encerrado.
- `available` significa **preparar revisão humana**, nunca autorização para executar ou garantia de evidência suficiente. `current` apenas significa que esta verificação não identificou nova revisão. Não existe score, SLA ou frequência comercial presumida.

## Processamento, persistência e concorrência

`cw_review_scans` guarda o cursor por empresa; `cw_review_entries` guarda a projeção atual. Mudanças materiais criam uma revisão em `cw_review_events`, append-only. Uma nova verificação igual só atualiza `checked_at`. Referências substituídas são retiradas da fila atual com estado `retired`, sem apagar histórico.

`process_review_schedule(10)` processa até dez empresas elegíveis (limite absoluto 20), até 50 referências por empresa. Bloqueios `FOR UPDATE SKIP LOCKED` evitam disputar o mesmo cursor. Há uma fase limitada de retirada de referências após cada percurso. A ordenação é determinística, sem prioridade comercial. Próximas páginas podem ser processadas na chamada seguinte; um ciclo concluído ou falhado fica elegível após um minuto. Esta é uma frequência técnica de detecção, não uma regra do produto. Não existe garantia de latência fixa para filas grandes.

A função só é executável pelo papel **NOLOGIN `centerway_review_scheduler`**, sem acesso direto às tabelas nem às operações C01–C10. A função SECURITY DEFINER contém a capacidade limitada de preparação. `authenticated`, `anon` e `service_role` não recebem acesso ao worker. Nenhuma chave privilegiada vai para o frontend.

`prepare_scheduled_reviews(tenant, operation_uuid)` é a alternativa manual para admin/operator. Processa uma página; pedidos concorrentes com o mesmo UUID devolvem a mesma tentativa. Leitores só consultam. Mudanças de papéis são revalidadas no servidor. Um erro transacional da página reverte o seu progresso e regista apenas SQLSTATE em `cw_review_attempts`; o erro completo não é exposto. Uma nova tentativa usa outro UUID. O worker regista `actor_kind=scheduler`, sem `actor_id`; a preparação humana regista a identidade real.

Cancelamento/timeout ou indisponibilidade total do banco podem impedir o registo da tentativa na mesma transação. Devem ser consultados também os logs de infraestrutura do Cron. Não há retenção automática de históricos nesta versão; definir uma política de retenção exige uma decisão posterior.

## Central de Acompanhamento

Abrir `/app/acompanhamento`. A secção «Monitorização e revisões programadas» mostra filtros por estado/indicador, datas documentadas, última tentativa, último ciclo completo, falhas e ligações para os registos reais. As leituras são paginadas, usam RLS e não processam a fila. «Atualizar revisões» volta a ler; «Preparar próximo lote» processa explicitamente uma página.

São **fotografias da última verificação**, com `checked_at`, versões e referências. Datas entretanto atingidas e novas observações, análises, configurações, avaliações ou eventos são sinalizadas como necessidade de atualização. A orientação nunca substitui a validação atual da operação. A fila Core existente continua a consultar o estado atual. Os pedidos são cancelados e a cache isolada na troca de empresa/logout; respostas tardias de preparação não publicam sucesso noutra empresa.

## Instalação posterior no ambiente escolhido

Esta secção regista a instalação original da migração 0020. Para auditar a `main` atual e um job já instalado, seguir primeiro a [preparação da Missão 20.6](HOSTED_READINESS_MISSION_20_6.md): inventariar todas as migrações e atualizar somente o comando por ID, com verificação de drift. Não reaplicar esta sequência histórica sem rever o estado do destino.

Nada foi instalado no backend hospedado nesta missão.

1. Rever e integrar o PR; aplicar **somente a nova migração 0020** pelo processo gerido existente. Preservar 0000–0019, journal e snapshots. Não usar `drizzle push` para substituir o esquema existente.
2. Confirmar a leitura da Central e uma preparação manual autorizada. As análises e decisões continuam manuais.
3. Ativar separadamente a extensão **Supabase Cron (`pg_cron`)** se ainda não estiver disponível. O mecanismo oficial suporta SQL e funções PostgreSQL: [Supabase Cron quickstart](https://supabase.com/docs/guides/cron/quickstart).
4. Executar `scripts/monitoring/install-cron.sql` como `postgres`. Regista o job `centerway-prepare-reviews-v1`, uma vez por minuto. O comando usa a transação implícita do job, limita-a a 45 segundos e assume o papel restrito antes de chamar o worker. `BEGIN/COMMIT` explícitos não são usados: em `cron.use_background_workers=on` impedem as subtransações PL/pgSQL necessárias ao tratamento de falhas. A Missão 20.5 verifica execuções reais em PostgreSQL descartável. Executar novamente atualiza o mesmo job.
5. Verificar `cron.job`, `cron.job_run_details` e `cw_review_attempts`; sucessos do Cron não substituem a verificação de falhas individuais por empresa. Desativar com `SELECT cron.unschedule('centerway-prepare-reviews-v1');`.

A migração não ativa o Cron nem instala automaticamente jobs. Não há endpoint público de agendamento ou segredo adicional. A instalação gerida e o job no Supabase hospedado **não foram executados nem verificados** aqui.

## Execução e validação isoladas

Requisitos existentes: Docker, Python3, psql, Node, Bun; Chromium/Playwright para browser. A partir do commit do PR, executar:

```sh
python3 scripts/mvp/start-local.py --monitoring
```

O script exporta o commit sem `.env`, instala dependências congeladas e cria PostgreSQL17 descartável, GoTrue e PostgREST em loopback, com utilizadores sintéticos. Mostra o ficheiro PRIVADO das contas temporárias. Prepara os cenários e testes de monitorização; **não instala Cron**. Abrir `/app/acompanhamento`. Para novos dados, usar a preparação manual; este comando local não é um daemon. Encerrar apenas esta stack com `python3 scripts/mvp/stop-local.py`.

O workflow `browser-e2e.yml` verifica a migração sobre dados pré-existentes, o motor e papéis via autenticação real, e os cenários de browser. `e2e/scheduled-reviews.py` testa mais de 600 entradas, isolamento, novas observações API/CSV, cursor, concorrência, replay, falha/recuperação, ausência de escritas nos dados anteriores e leituras sem efeitos. Provas temporais SQL adicionais são revertidas e identificadas como testes de papéis/claims, distintos de login GoTrue real. A regressão operacional verifica uma janela curta realmente decorrida, evidência insuficiente e encerramento válido com fixtures retrospectivas sintéticas explicitamente identificadas.

O browser inclui viewport móvel, filtros, navegação, persistência, troca de empresa com resposta pendente e logout. Um viewport Chromium não comprova um dispositivo Android real. Não foram feitos testes na URL hospedada, nem instalação/execução do serviço Cron hospedado.
