# F06 — integração operacional e contrato para futura interface

Migração adicional `008_operational_orchestration.sql`, após 001–007 na base isolada.
Não substitui nem modifica os motores F01–F05. Validar com
`./recovery-mvp/tests/run-f03.sh`, incluindo o percurso sintético completo F01 → F02 →
descoberta F03.1 → verificações reais F03 → autorização/execução sintética F04 → F05.

## Porta de comandos

```sql
SELECT centerway.operate(
  :tenant_uuid, :client_uuid, :request_uuid, :operation, :arguments_jsonb
);
```

Envelope `operation_receipts`: tenant_id, client_id, request_id, operation, arguments,
status (`completed` ou `error`), result, actor e recorded_at. `completed` significa
que a porta delegada retornou; o resultado de negócio pode ser blocked, failed ou
inconclusivo. A interface tem de ler ambos os níveis. Nenhum novo critério de
suficiência, autorização ou recuperação foi acrescentado pela orquestração.

Todas as chaves indicadas abaixo são obrigatórias e não nulas, sem chaves adicionais:

| Operação | Argumentos | Motor delegado |
|---|---|---|
| append_value | kind,id,expected_revision,reason,data | F01 append_version |
| detect | contract_id,revisions,as_of,required_periods | F02 run_detection |
| discover_company | as_of | F03.1 discover_impediments |
| open_investigation | id,detection_id,contract_revision,question | F03 open_investigation |
| append_investigation | investigation_id,kind,id,expected_revision,reason,data | F03 append_investigation_record |
| investigate | investigation_id,as_of | F03 run_investigation |
| intervene | investigation_id,report_id | F04 run_intervention |
| undo | execution_id | F04 undo_intervention |
| plan_recovery | id,decision_id,pre_revision,post_revision,reason | F05 create_recovery_plan |
| evaluate_recovery | plan_id,as_of | F05 evaluate_recovery |

IDs são UUIDs; revisões e limites são inteiros; revisions é uma lista de inteiros;
as_of é um instante explícito com fuso; data segue o contrato de negócio original.
Usar parâmetros do driver. Tenant/client vêm do envelope autenticado, nunca do JSON.
Não há defaults de metas, períodos, resultados ou verificações.

`discover_company` é deliberadamente uma operação **da empresa inteira**: inclui os
seus vários clientes, como a porta F03.1 existente. O client do envelope identifica
onde fica o recibo e não restringe a descoberta. O utilizador tem de ter membership
na empresa. Nenhuma operação percorre empresas não autorizadas.

Configurar regras/entradas estruturadas pelas portas register_discovery_rule e
register_discovery_input F03.1. Catálogo, recursos e políticas F04 continuam de
provisionamento administrativo; a interface de utilizador não pode autoautorizar
intervenções. A orquestração não cria revisores nem disfarça verificações automáticas
como verificações humanas. Chamadas de verificação usam o login real do revisor.

## Retoma e tratamento de erros

Guardar um request_uuid antes de enviar o comando. Repetir **o mesmo UUID, operação,
argumentos e principal** após timeout ou perda de resposta. O recibo é imutável e a
mesma resposta é devolvida, incluindo IDs gerados pelos motores. Um lock serializa
pedidos concorrentes da mesma chave. Se o processo cair antes do commit, efeito e
recibo são revertidos; se o commit ocorrer e a resposta se perder, a repetição lê o
recibo e não repete a ação. F04 também impede efeito duplicado com pedidos distintos.

Reutilizar um UUID para outro conteúdo ou principal rejeita request_identity_conflict.
Para tentar novamente após corrigir dados/permissões, usar outro UUID. Um recibo de
erro não é reexecutado automaticamente: conserva sqlstate e message. O subcomando
é executado numa subtransação; qualquer exceção reverte integralmente os seus efeitos,
mas o recibo de erro e a auditoria permanecem na transação exterior se esta fizer commit.
Falhas de autenticação, envelope inválido e cliente inexistente são rejeitadas antes
do recibo. Se o chamador fizer rollback, também reverte o recibo.

Não há background worker, saga distribuída ou retry em loop. Cada comando tem a sua
transação PostgreSQL. Sob isolamento forte, repetir a transação inteira com a mesma
chave em erros de serialização. Bloqueios externos devem ter timeout no serviço.

## Consulta de percurso

```sql
SELECT centerway.client_journey(:tenant_uuid, :client_uuid);
```

Projeção `f06-v1`, num snapshot SQL e com RLS. SQL NULL significa cliente ausente ou
invisível. Não há escrita nem recomputação nesta leitura. Devolve versões de contratos,
fontes, evidências, deteções, investigações e respetiva última avaliação persistida,
decisões, execuções/reversões, planos de recuperação e sua última avaliação, recibos
e `work_items` com stage, next, IDs, blockers, needed, result e as_of quando aplicável.
Snapshots de evidência nas avaliações permitem inspecionar o suporte e as referências
exatas. Consultar as portas históricas dos motores para um run anterior específico.

Os work_items são uma orientação de integração sobre **estados persistidos**, não um
novo motor de decisão. Um cliente pode ter vários contratos/investigações em paralelo;
não é reduzido a um único estado global. Um relatório antigo pode ter sido invalidado
por novos dados: F04 revalida sempre antes da execução. Não usar esta projeção como
prova de permissão, de elegibilidade atual ou de recuperação causal.

| Próxima etapa | Interpretação |
|---|---|
| append_value | Falta contrato explícito/fonte |
| detect | Fornecer revisões, corte e política de períodos |
| supply_context_or_open_investigation | Falta investigação ligada à deteção; fornecer contexto, descobrir ou abrir explicitamente |
| investigate | Avaliar fatores/evidências já registados |
| supply_evidence_or_verification | Exibir lacunas e contradições da F03, recolher dados reais |
| review_investigation_conclusion | Rever conclusão sem candidato acionável; nenhuma execução é sugerida |
| review_intervention_authorization | Rever suporte e configuração; F04 fará a decisão autorizada |
| review_execution_blocker | Exibir razão F04; corrigir condições antes de outro pedido |
| plan_recovery | Definir explicitamente janelas comparáveis F05 |
| evaluate_recovery | Avaliar evidência real anterior/posterior |
| supply_outcome_evidence_and_reevaluate | Falta suporte suficiente para F05; recolher evidência e usar outro pedido |
| review_observed_recovery | Exibir conclusão F05 e seus limites, sem iniciar nova ação |

## Integração futura com Lovable

Esta entrega é SQL interno, sem API HTTP/browser ou frontend. Um futuro adaptador
Lovable deve: autenticar o utilizador, associar a ligação PostgreSQL ao principal
correto, validar membership e cliente, usar parâmetros tipados e transações curtas,
conservar a chave antes de comandos e apresentar recibos/estados dos motores sem
reinterpretar evidência ou causalidade. Não ligar o browser como administrador ou
partilhar um login privilegiado entre utilizadores. O mecanismo de sessão continua
session_user conforme F01; um tenant arbitrário num cabeçalho não autentica o pedido.

Apresentar execution_succeeded, improvement_observed e recuperação de valor como
campos distintos. Renderizar hypotheses como hipóteses e dados ausentes como lacunas;
não preencher campos em falta para permitir avançar. As autorizações F04 limitam-se
à área sintética; nenhuma ação real é exposta por esta integração.

## Limitações

A consulta devolve histórico sem paginação e pode crescer; não há SLA nem benchmark.
Pode mostrar tarefas históricas ainda sem investigação e decisões antigas bloqueadas,
mesmo após outras tentativas; mantém referências e não declara que todo item ainda
exige ação atual. Para várias possibilidades, o utilizador/integração seleciona IDs
explícitos. Recibos e argumentos contêm dados de negócio autorizados: não copiar para
logs públicos. Eventos de transporte antes da transação não são auditados nesta base.

A camada preserva as limitações semânticas dos motores: evidências declaradas,
verificações registadas, ausência de atribuição causal e execução exclusivamente
sintética. Nenhuma evidência, verificação ou resultado é gerado pela orquestração.
Sem frontend, IA paga, conectores externos, intervenções reais ou deploy.

Validação: 60 testes de integração (57 regressões e três casos F06 com subcenários
de recuperação, ausência de recuperação, insuficiência, verificação por outro
principal, autorização recusada, falha sintética, repetição após perda de resposta,
concorrência, erros persistidos e isolamento). Fixtures numéricas e janelas curtas
são sintéticas e explícitas; não são resultados fabricados pelos motores.
