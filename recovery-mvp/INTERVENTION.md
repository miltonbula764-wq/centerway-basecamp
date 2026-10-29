# F04 — decisão e intervenção sintética

Migração adicional `006_synthetic_interventions.sql`, sobre PR #52. F01–F03.1
permanecem intactas. Aplicar apenas na base isolada MVP, nunca na aplicação antiga.
Testes: `./recovery-mvp/tests/run-f03.sh` (descobre todas as migrações e testes).

## Configuração administrativa e autorização prévia

O administrador provisiona explicitamente as tabelas, usando SQL parametrizado:

- `sandbox_flags(tenant_id,client_id,id,environment,value,last_execution)`:
  recurso booleano exclusivamente `isolated_synthetic`, inicialmente sem execução.
- `intervention_catalog(tenant_id,id,name,category,scope,control,action,
  expected_value,desired_value,risk,priority)`: apenas `set_synthetic_flag` é suportado;
  estado esperado e desejado devem diferir. Risco inteiro 0–3, declarado pelo configurador.
  Categoria, âmbito e controlo devem coincidir com o candidato F03. Não há catálogo
  predefinido, recomendação gerada ou execução de código SQL fornecido pelo utilizador.
- `intervention_policies(tenant_id,client_id,id,catalog_id,resource_id,principal,
  valid_from,valid_until,max_attempts,max_risk,max_report_age,max_observation_age)`:
  autorização prévia vinculada a principal PostgreSQL, cliente, edição de catálogo e
  recurso. Datas finitas, limite positivo de tentativas e idades máximas explícitas.
  Tentativas falhadas também consomem o limite. Permissão não é inferida da membership.
- `intervention_revocations(tenant_id,client_id,policy_id,reason)`: revogação append-only.
  A inserção serializa com execuções concorrentes; ao terminar a revogação, nenhuma
  execução nova pode usar essa política.

O grupo `centerway_api` tem apenas leitura sob RLS sobre configuração e registos.
Não pode conceder políticas, criar recursos ou alterar o catálogo. Provisionamento
administrativo é a fronteira confiável; um administrador capaz de mudar o esquema
continua fora desta garantia. Use logins não privilegiados para as chamadas internas.

Catálogo e políticas são edições imutáveis e auditadas. Para alterar uma autorização,
revogar a anterior e criar uma nova. Várias políticas ativas constituem permissões
alternativas válidas; revogar uma não revoga outras autorizações da mesma ação.

## Decidir e executar

`centerway.run_intervention(tenant,client,investigation_id,report_id)` recebe um relatório
F03 persistido, não uma conclusão enviada pelo chamador. A operação:

1. Valida identidade e âmbito, serializa execução/reversão na empresa e captura a
   investigação atual pela F03. Bloqueia novos registos de fatores/evidências/revisões
   durante a decisão para evitar executar enquanto aparece incerteza relevante.
2. Compara o hash de entrada com o relatório fornecido. Um relatório desatualizado,
   globalmente inconclusivo ou sem candidato sustentado é bloqueado.
3. Encontra ações explicitamente configuradas com categoria/âmbito/controlo compatíveis,
   autorização vigente para o principal e recurso, risco dentro do limite, quota
   disponível, relatório recente e instante de observação dentro da idade permitida.
4. Seleciona a menor prioridade numérica; empate é resolvido pelo UUID da política.
   É uma preferência determinística configurada, não uma previsão de eficácia.
5. Bloqueia o recurso, revalida o fim de validade da política e exige o valor esperado.
   Uma precondição não satisfeita regista falha sem alteração do recurso.
6. Grava decisão, execução, antes/depois e alteração da flag atomicamente. Os triggers
   gravam auditoria na mesma transação. Uma falha SQL inesperada reverte a transação
   completa; o serviço chamador deve registá-la no seu log operacional.

Estados: `blocked`, `executed`, `failed`. Razões incluem `stale_report`,
`uncertain_investigation`, `no_authorized_eligible_action`, `authorization_changed`,
`authorization_expired`, `resource_precondition_failed` e `synthetic_execution_only`.
Ausência de autorização não produz um efeito. Tentativas bloqueadas são auditadas,
mas não consomem quota. O retorno contém a identidade da execução quando criada e
`value_recovery = not_evaluated`: executar uma alteração sintética não demonstra
recuperação de valor nem altera resultados F01/F02/F03.

Existe no máximo uma execução bem-sucedida por investigação/fator, mesmo com novo
relatório, catálogo ou política. Repetições são decisões bloqueadas auditáveis;
não são outra execução. O índice único e o lock protegem pedidos concorrentes.
Uma nova chamada pode selecionar outro fator elegível da investigação.

## Reversão

`centerway.undo_intervention(tenant,client,execution_id)` exige membership atual e o
mesmo principal da execução original. A autorização de execução inclui a permissão
permanente de desfazer **essa execução sintética**, inclusive após expiração/revogação,
para permitir limpeza do ambiente. Não autoriza nova intervenção.

A reversão exige que a execução original continue a ser a última alteração do recurso;
caso contrário, rejeita `resource_changed`. Grava outro evento antes/depois e repõe a
flag. Repetir a mesma reversão reutiliza esse evento. Não permite reverter uma reversão
nem reexecutar o fator já executado. Não altera ou apaga o histórico original.

## Auditoria e leitura

Decisões incluem relatório F03 exato, fator selecionado, política, principal, data e
razão. Execuções incluem decisão, recurso, estados e eventual `undo_of`. Todas as
referências têm âmbito composto por empresa/cliente. Leitura direta das tabelas é
permitida sob RLS; só as funções escrevem o recurso e o histórico operacional.
A configuração e o provisionamento também geram eventos de auditoria.

A flag de F03 `execution_authorized=false` continua intacta: F03 não concede execução.
F04 obtém autorização exclusivamente da política administrativa e das suas condições.
Verificações registadas não se tornam prova independente nem causa comprovada.

## Limitações

Um adaptador sintético booleano; nenhuma rede, conector externo, tarefa paga, email,
frontend ou ação real. Risco/prioridade/adequação semântica da ação ao fator são
configurados por pessoas; o motor verifica correspondência e limites, não prevê
impacto. A área isolada é lógica, exclusivamente nas novas tabelas; o administrador
é responsável por instalar as migrações numa base isolada. Não constitui sandbox de
execução arbitrária: não executa scripts, URLs ou código fornecido pelo catálogo.

Lock por empresa e locks partilhados das tabelas F03 favorecem correção em vez de
paralelismo. Não há scheduler, retry automático, SLA, deteção semântica de dois fatores
que representem o mesmo impedimento, ou prova de recuperação. Políticas permitem um
conjunto explícito de condições, sem linguagem de expressão genérica. Idempotência
refere-se ao efeito, não à reutilização da decisão bloqueada. Nenhuma parte de F05
foi implementada.

Validação desta entrega: 53 testes de integração aprovados (49 regressões e quatro
casos F04 com subcasos de autorização, incerteza, risco, expiração, revogação, falha,
quota, duplicação, reversão, concorrência, relatório desatualizado e isolamento).
