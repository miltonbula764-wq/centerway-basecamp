# F05 — verificação da recuperação

Migração adicional `007_value_recovery.sql`, sobre o PR #53. Nenhuma migração,
função ou resultado F01–F04 é alterado. Instalar só na base MVP isolada, após 001–006.
Executar `./recovery-mvp/tests/run-f03.sh` para a suite completa.

## Janelas e contrato

`create_recovery_plan(tenant,client,plan_uuid,decision_uuid,pre_revision,post_revision,reason)`
fixa uma decisão F04 e duas revisões exatas do mesmo Contrato de Valor da investigação
que originou a decisão. O cliente deve fornecer revisões explícitas para definir as
janelas. Não se inferem cadência, duração, metas ou valores observados.

As janelas devem ter igual duração, com o fim da janela anterior antes ou no instante
da execução e o início da posterior no instante da execução ou depois. Intervalos
são `[início,fim)`. Todos os campos de negócio do contrato, incluindo fonte/versão,
baseline, mínimo, alvo, método, indicador, unidade, direção e proveniência da baseline,
devem coincidir entre o contrato original e as duas revisões. Só datas da avaliação
e metadados da revisão podem diferir. Não há conversão de totais em taxas.

Para decisões falhadas/bloqueadas sem execução, usa-se a data da decisão como âncora
para poder registar uma verificação inconclusiva auditável; nunca é tratada como uma
execução. A referência à execução efetiva e a eventuais reversões fica no snapshot.

É possível declarar janelas posteriormente à intervenção, mas isso é explícito na
data de registo do plano. A F05 não afirma que o desenho foi pré-registado nem que
não houve seleção retrospetiva de períodos. O plano é imutável; outro desenho exige
outro UUID, preservando os anteriores.

## Recolha e avaliação

Não há conector externo: produtores autorizados registam os resultados pela porta
F01 `append_version(...,'evidence',...)`, com o contrato/versão, janela, resultado,
unidade, método, fonte/versão, referência, digest declarado e qualidade explícitos.
A F05 consulta essas evidências; não lê o valor da flag sintética para fabricar
resultados. Os números de testes são fixtures sintéticas, não dados operacionais.

`evaluate_recovery(tenant,client,plan_uuid,as_of)` captura as últimas revisões visíveis
no corte usando o motor F02 existente. Cada janela exige resultado completo, terminado,
de negócio (`outcome`), concordante e declarado `verified`. Ausência, utilização,
qualidade parcial/disputada e contradições conservam a semântica inconclusiva F02;
não se escolhe uma observação favorável entre várias. As razões e referências de
cada período são preservadas nos campos `before` e `after` e no snapshot integral F02.

O relatório separa:

- `execution_succeeded`: existência de uma execução original F04 associada à decisão
  executada, sem converter esse sucesso em valor;
- `improvement_observed`: comparação numérica anterior/posterior, interpretada segundo
  `higher`/`lower`, ou nula se não for possível comparar;
- `minimum_met` e `baseline_met`: comparação posterior com os limites do contrato;
- `status`: conclusão da recuperação, segundo as regras abaixo.

| Estado | Regra com suporte suficiente |
|---|---|
| `recuperacao_completa` | Havia insuficiência anterior e o posterior atinge o mínimo aceitável |
| `recuperacao_parcial` | O posterior melhora face ao anterior, mas continua aquém do mínimo |
| `ausencia_de_recuperacao` | O posterior não melhora face ao anterior e não restaura o mínimo |
| `resultado_inconclusivo` | Falta suporte, há conflito, período aberto, execução não realizada ou reversão antes do fim da janela posterior |

Se o anterior já satisfazia o mínimo, a recuperação é inconclusiva com motivo
`no_prior_contractual_shortfall`; a melhoria e a satisfação posterior podem ser
observadas separadamente. Completa significa recuperação do mínimo contratado, não
necessariamente do alvo desejado. Parcial não significa cumprimento do contrato;
pode continuar abaixo da baseline. Igualdade no mínimo é suficiente; igualdade
entre anterior e posterior não é melhoria. Não há arredondamento, tolerância,
percentagem ou significância estatística inferidos pelo motor.

Uma reversão posterior ao fim da janela não apaga resultados históricos desse
intervalo. Reversão antes ou durante a janela posterior impede a conclusão sobre
recuperação após a intervenção. O relatório não afirma que o valor persiste hoje.

## Histórico e limites das conclusões

`read_recovery_context(tenant,client,plan_uuid,run_uuid)` lê o relatório armazenado,
sob RLS, sem recomputar com dados novos. Retorna SQL NULL para um registo invisível.
Snapshot inclui plano, decisão, execuções/reversões e execução F02 com contratos,
fontes, evidências e versões exatas. A auditoria transacional usa os triggers F01.

Cada execução é imutável e identificada por `f05-v1`, corte e hash SHA-256 dos dados.
Mesma entrada e corte reutilizam o registo. Se dados se tornarem visíveis para o
mesmo corte, cria-se uma revisão com `revision_of`, sem reescrever a anterior. Outro
corte inicia outra cadeia. Como F02, o corte usa data de registo, não data de commit;
commits tardios podem revelar informação que cria uma revisão de avaliação. Locks
serializam avaliações do mesmo plano. Nenhum campo de resultado é enviado pelo cliente.

Todos os estados são condicionados aos resultados declarados do produtor. O sistema
não verifica documentos externos nem estabelece independência. Todo relatório traz
`causal_attribution=not_established` e `independent_verification=not_established`.
Intervenções simultâneas, alterações de contexto, sazonalidade e seleção de janelas
podem explicar a melhoria: a F05 não os atribui a uma causa. Não é uma avaliação
experimental de eficácia nem uma estimativa contrafactual.

Limitações: um indicador numérico; duas janelas explicitamente configuradas de duração
igual; sem agregação de janelas parciais, taxas, normalização, descoberta automática de
períodos, análise causal, conectores, scheduler, simulador ou frontend. Planos e
relatórios são isolados por empresa/cliente, com escrita apenas por funções e leitura
sob RLS; administradores continuam fora da fronteira de imutabilidade da aplicação.
O resultado não autoriza nova intervenção e não implementa F06.

Validação: 57 testes de integração (53 regressões e quatro casos F05 com subcasos de
recuperação completa/parcial, ausência de melhoria, valor já suficiente, falta de
dados, utilização, contradições, falha F04, evidência tardia, histórico, janelas,
reversão e isolamento). Executados em PostgreSQL descartável com principais reais.
