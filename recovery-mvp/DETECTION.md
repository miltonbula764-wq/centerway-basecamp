# CENTERWAY MVP — F02: deteção de deterioração

Extensão independente sobre a F01 do PR #49 (`2a06c47`). A migração
`sql/003_deterioration_detection.sql` acrescenta um motor determinístico e um registo
imutável de execuções. Não altera as tabelas, funções, avaliações, documentação ou
testes da F01. Os ficheiros `README.md` e `CONTRACT.md` continuam a documentar a F01;
este documento descreve a extensão F02.

O motor calcula os quatro estados a partir dos dados persistidos. Não aceita uma
conclusão, um valor observado ou uma lista de evidências fornecidos na chamada.
Não executa IA, investigação de causas, intervenções, frontend ou integração Lovable.

## Instalação e verificação

Numa base **isolada** que já tenha recebido as migrações F01, aplicar apenas:

```sh
psql -X -v ON_ERROR_STOP=1 -f recovery-mvp/sql/003_deterioration_detection.sql
```

Usar o administrador da base F01, nunca a base da aplicação antiga. Numa instalação
nova, aplicar `001`, `002` e `003` por ordem. A migração é transacional e executada
uma única vez; a role `centerway_api` e as identidades continuam as da F01.

Para os testes, sem credenciais ou bases externas:

```sh
./recovery-mvp/tests/run.sh
```

O runner F01, preservado, já descobre todas as migrações e testes. Cria PostgreSQL 17
num contentor descartável, sem portas publicadas, e remove-o ao terminar. A suite
inclui 27 testes: 9 de regressão F01 e 18 novos testes de deteção, com subcasos para
ambos os sentidos, limiares, qualidade, contradições, histórico e segurança. As
sessões da aplicação não são proprietárias nem superusers. Os testes de concorrência
fazem commit apenas nessa base descartável; os restantes casos usam rollback.

## Contrato de execução

```sql
SELECT centerway.run_detection(
  p_tenant           => :empresa_uuid,
  p_client           => :cliente_uuid,
  p_contract         => :contrato_uuid,
  p_revisions        => :revisoes_integer_array,
  p_as_of            => :instante_com_fuso,
  p_required_periods => :numero_de_periodos
);
```

Usar parâmetros do driver. Não há configuração de negócio por omissão:

- `p_revisions`: entre 1 e 120 revisões distintas e positivas do mesmo contrato,
  todas pertencentes à empresa/cliente autenticados e registadas até ao corte.
  Cada revisão define **um período completo** e os seus próprios critérios F01.
  A ordem enviada não importa; o motor ordena pelos instantes do período.
- Não selecionar duas revisões que definam exatamente o mesmo intervalo. Uma correção
  de contrato para esse período deve ser selecionada explicitamente em substituição
  da anterior. Isso não apaga a revisão antiga nem as suas avaliações.
- `p_as_of`: instante finito, não futuro. Limita o que já estava registado, tanto
  contratos/fontes como evidências, e determina se cada período terminou. Não é
  apenas a data observada: dados introduzidos hoje não existiam no corte de ontem.
- `p_required_periods`: inteiro entre 2 e 120, fornecido pelo chamador, que define a
  duração mínima do critério de deterioração sustentada. A F02 não escolhe este número.

Os limites de 120 são limites operacionais do pedido, não limiares de negócio.
Um único período pode ser avaliado; a sustentação será desconhecida por falta de
períodos. Referências inválidas, não autorizadas ou indisponíveis no corte causam
erro antes de qualquer registo de execução. Falta de evidência para um contrato
válido gera um resultado inconclusivo auditável.

A F01 permite uma janela por revisão de contrato. Usar revisões consecutivas para
períodos distintos é uma configuração explícita do produtor. A F02 não reparte uma
meta mensal em metas diárias, não soma janelas parciais, não cria metas e não deduz
cadência. A lista selecionada delimita a análise; o motor não afirma ter analisado
períodos ou revisões fora dessa lista.

## Seleção e suficiência das evidências

Uma única instrução SQL captura contratos, fontes e evidências num snapshot coerente.
Para cada ID de evidência, é selecionada a maior revisão visível com `recorded_at <=
p_as_of`. Uma correção substitui a versão antiga **na execução nova**, não no histórico.
Todas as evidências selecionadas ficam no `input_snapshot`, inclusive as excluídas
ou que bloqueiam uma conclusão. Não se escolhe uma evidência favorável entre várias.

Regras `f02-v1`, para cada período:

1. `usage` é excluído da obtenção de valor, independentemente do número ou qualidade.
2. Valores só são candidatos quando `evidence_type = outcome` e a janela coincide
   exatamente com a janela do contrato. Janelas parciais não são agregadas nem
   normalizadas; o valor fica excluído com motivo `incomplete_window`.
3. Qualquer evidência de resultado `partial` ou `disputed` torna o período inconclusivo,
   mesmo quando também existe um resultado completo declarado `verified`. Trata-se
   de uma regra conservadora: a incerteza declarada não é descartada pelo motor.
4. Valores diferentes em evidências de resultado para a mesma janela completa são
   contraditórios, mesmo que todos impliquem a mesma classificação. Não há média,
   votação, prioridade pela ordem ou escolha do mais recente entre IDs diferentes.
5. Sem resultado completo, com contradição/incerteza ou com período ainda aberto,
   `observed_value` calculado é `null` e o estado é `resultado_inconclusivo`. Os
   valores originais continuam no snapshot; ausência nunca é convertida em zero.
6. Com resultado completo, concordante e declarado `verified`, aplicar os critérios
   numéricos F01. Múltiplos registos concordantes não aumentam a independência da prova.

A condição `verified` é uma declaração do produtor. **Nenhuma execução estabelece
verificação independente**, mesmo quando o estado conserva o nome `valor_demonstrado`
ou `deterioracao_demonstrada` da F01. Estes estados são conclusões condicionais aos
registos declarados, e não prova causal ou independente. Todas as execuções incluem:

```json
{
  "support_basis": "producer_declared_evidence",
  "independent_verification": "not_established",
  "causal_inference": "not_performed"
}
```

Localizadores, hashes declarados, autores, datas, versões de fonte, contrato e
evidência são preservados. O motor não descarrega documentos nem valida os seus bytes.

## Quatro estados por período

Com evidência suficiente, mantém-se a semântica F01:

| Estado | `higher` | `lower` |
|---|---|---|
| `deterioracao_demonstrada` | valor < baseline | valor > baseline |
| `valor_demonstrado` | valor >= mínimo | valor <= mínimo |
| `valor_insuficiente` | baseline <= valor < mínimo | mínimo < valor <= baseline |
| `resultado_inconclusivo` | suporte insuficiente/contraditório ou período aberto | igual |

A igualdade no mínimo é suficiente. `target` não substitui o mínimo. A igualdade
na baseline não é deterioração. A classificação usa decimal PostgreSQL, sem
arredondamento introduzido pelo motor.

O `state` no topo da execução corresponde ao último período selecionado, ordenado
cronologicamente; os estados de todos os períodos ficam em `result.periods`.
Não há promoção do pior estado histórico para estado atual.

## Comparação entre períodos

Cada período inclui `comparison` com o período imediatamente anterior selecionado.
A comparação exige:

- intervalos contíguos, sem lacunas ou sobreposição;
- duração igual em segundos;
- todos os campos de negócio do contrato iguais, exceto início/fim da avaliação;
- ambos os resultados conclusivos.

Isto inclui objetivo, resultado esperado, indicador, unidade, método, direção,
baseline e respetiva referência/janela, mínimo, alvo e **a mesma versão da fonte**.
Metadados de autoria, motivo e criação da revisão não afetam a compatibilidade.
Uma mudança de semântica impede a comparação, embora cada período possa continuar
a ser avaliado separadamente pelo seu próprio contrato.

Quando comparável, `delta = valor_atual - valor_anterior`, com estado `worsening`,
`improving` ou `unchanged`, interpretado segundo `higher`/`lower`. Não se calcula
percentagem, tolerância estatística, significância ou causalidade. Sem comparação
válida, `status = inconclusive`, `delta = null` e há um motivo explícito.

Uma redução de 20 para 18 num contrato `higher`, baseline 10 e mínimo 15, continua
como `valor_demonstrado`, mas a comparação indica `worsening`. Os números deste
exemplo são sintéticos; não são configuração inserida pelo motor.

## Deterioração sustentada

A regra explícita `f02-v1` exige que os **últimos N períodos selecionados**:

1. estejam terminados e tenham resultado conclusivo;
2. sejam comparáveis em todos os N−1 pares internos;
3. estejam todos em `deterioracao_demonstrada` face à baseline contratada.

`result.sustained_deterioration` tem três valores:

| Valor | Significado |
|---|---|
| `true` | Os N períodos satisfazem o critério |
| `false` | Há N períodos conclusivos e comparáveis, mas pelo menos um não está deteriorado |
| `null` | Não é possível avaliar a sustentação: faltam períodos/dados ou a sequência é incompatível |

Não se atravessam lacunas, contradições ou períodos inconclusivos para construir uma
sequência. Um problema fora dos últimos N períodos permanece no histórico, mas não
invalida uma sequência final de N períodos completa e comparável.

Esta definição mede **persistência de um resultado pior que a baseline**, não queda estrita em todos
os períodos. Um patamar deteriorado pode ser sustentado; pode também haver melhoria
parcial, ainda sem recuperar a baseline. A comparação numérica fica separada para
que estas situações não sejam confundidas. O número N nunca é assumido pelo motor.

## Justificações auditáveis

Cada período guarda referências exatas, `reason_codes` e motivos de exclusão/comparação:

| Código | Significado |
|---|---|
| `missing_evidence` | Nenhuma evidência visível no corte |
| `no_outcome_evidence` | Nenhuma evidência de resultado |
| `no_complete_window` | Nenhum resultado cobre a janela completa |
| `partial_quality`, `disputed_quality` | Incerteza declarada pelo produtor |
| `contradictory_results` | Valores diferentes para a mesma janela completa |
| `period_not_closed` | Avaliação ainda não terminou no corte |
| `worse_than_baseline` | Piora numérica face à baseline |
| `minimum_met`, `minimum_not_met` | Mínimo atingido ou não atingido |
| `usage_is_not_outcome`, `incomplete_window` | Motivos de exclusão de um valor |
| `no_previous_period` | Primeiro período selecionado |
| `non_contiguous_periods`, `unequal_duration`, `incompatible_contracts` | Comparação sem compatibilidade |
| `inconclusive_period` | Um resultado necessário não permite concluir |
| `comparable_declared_results` | Comparação efetuada sobre resultados declarados |
| `insufficient_periods`, `incompatible_sequence` | Sustentação não avaliável |
| `sustained_baseline_deterioration`, `criterion_not_met` | Sustentação confirmada ou critério não satisfeito |

São razões determinísticas sobre a medição e o contrato. Não são causas do resultado.
`considered_evidence_refs` identifica os candidatos de janela completa, incluindo
os contraditórios, e não uma seleção de provas aceites. `excluded_evidence_refs`
explica valores não usados; uma declaração de qualidade incerta numa janela parcial
continua a bloquear a conclusão, conforme a regra conservadora acima.

## Persistência, repetição e concorrência

`detection_runs` é append-only, com RLS e a mesma fronteira de identidade da F01:
`session_user` associado administrativamente à empresa. Só `run_detection` escreve;
o chamador não pode falsificar resultados, snapshots, autor, hash ou algoritmo.
A função privada de avaliação não é executável por `centerway_api` nem por `PUBLIC`.

A chave do pedido é SHA-256 de algoritmo, âmbito, ID/revisões de contrato normalizadas,
corte e N. O hash de entrada é SHA-256 do snapshot JSONB canónico, serializado em UTC.
A mesma chave e os mesmos dados reutilizam a execução, sem duplicar o evento de
criação no audit log. Um advisory lock transacional serializa pedidos idênticos.

Novos dados visíveis para a mesma chave criam uma nova `revision`, com `revision_of`
a apontar para a execução anterior. Um novo corte ou configuração constitui outro
pedido, não uma revisão do pedido anterior. Todas as versões permanecem consultáveis;
nunca se recomputa ou altera uma execução guardada. Uma alteração semântica futura
exige outro identificador de algoritmo e deve preservar a leitura de `f02-v1`.

`p_as_of` usa a data de registo, não a data de commit: uma transação que tenha registado
uma evidência antes do corte mas só faça commit depois pode tornar-se visível numa
repetição posterior. Nesse caso, o novo hash produz uma revisão auditável. O snapshot
persistido é a autoridade para reproduzir cada execução. Contratos/fontes/evidências
são capturados juntos, evitando misturar leituras de momentos diferentes.

O resultado e o evento de `audit_log` são gravados na mesma transação. Rejeições não
persistem um log separado; um rollback reverte a execução e o evento. Em isolamento
`REPEATABLE READ`/`SERIALIZABLE`, o chamador deve repetir a transação inteira em caso
de conflito de serialização/unicidade, como noutras escritas concorrentes PostgreSQL.

## Porta interna para a investigação futura

```sql
SELECT centerway.read_detection_context(
  :empresa_uuid, :cliente_uuid, :run_uuid
);
```

A leitura é `SECURITY INVOKER`, sob RLS, e retorna SQL `NULL` para uma execução ausente
ou invisível. Devolve a execução persistida completa:

- identidade, autor, data, algoritmo, corte, N, hashes e encadeamento de revisão;
- `input_snapshot`: contratos, fontes e últimas revisões de evidência consideradas;
- `result`: estados, valores condicionais, comparações, sustentação, razões e limites
  de verificação/causalidade.

Esta porta fornece contexto auditável à futura investigação. Não cria um caso, não
identifica uma causa e não recomenda uma intervenção. Não implementa a missão F03.
As avaliações manuais da F01 continuam separadas em `assessment_versions`; a F02
não as sobrescreve nem as usa como substituto de evidência.

## Limitações desta entrega

Além dos limites F01: um indicador numérico por contrato; comparação conservadora
entre versões do mesmo contrato; períodos de duração fixa, sem normalização de meses
com durações diferentes; apenas evidência consolidada para janelas completas; sem
verificação independente, inferência causal ou teste estatístico. Não há scheduler:
a avaliação automática ocorre quando a porta interna é chamada.

A lista de períodos é explícita, não uma descoberta de todas as janelas possíveis.
O snapshot contém toda a evidência selecionada sem paginação; não há SLA ou benchmark
para volumes grandes. Não há WORM contra administradores, e a segurança depende do
provisionamento de logins não privilegiados, tal como na F01. Nenhuma migração foi
aplicada à aplicação antiga ou a produção nesta missão.
