# CENTERWAY MVP — F03: investigação de deterioração

Extensão sobre a F02 do PR #50 (`45f7555`). A migração `004` acrescenta investigações,
fatores, evidências, verificações e conclusões versionadas. Não modifica nenhum
ficheiro, função, tabela ou resultado F01/F02. Não altera a aplicação antiga.

O motor procura **requisitos documentados não satisfeitos**, entre fatores submetidos
explicitamente por pessoas ou integrações autorizadas. Pode investigar processos,
recursos, competências, dependências, políticas, fatores comerciais e condições
externas, além da própria SaaS. Não deduz candidatos a partir de métricas de utilização,
não gera hipóteses e não procura documentos na Internet. Sem dados contextuais, devolve
as lacunas necessárias para prosseguir, mantendo a investigação inconclusiva.

## Instalação e testes

Numa base isolada com F01 e F02 instaladas, aplicar uma única vez, como o mesmo
administrador das migrações anteriores:

```sh
psql -X -v ON_ERROR_STOP=1 -f recovery-mvp/sql/004_deterioration_investigation.sql
```

Numa base nova, aplicar `001` a `004` por ordem. Nada desta missão é aplicado à base
antiga ou a produção. A F03 usa as empresas, clientes, fontes e logins da F01.

```sh
./recovery-mvp/tests/run-f03.sh
```

Requisitos: Docker, Bash e Python 3.12+. O runner cria PostgreSQL 17 descartável, sem
portas publicadas, aplica as migrações, executa a suite inteira e remove o contentor.
Espera pelo processo PostgreSQL definitivo, evitando confundir o servidor temporário
de bootstrap da imagem com a base pronta. O runner F01 permanece intacto.

**46 testes:** 27 regressões F01/F02 e 19 testes F03. As verificações usam ligações
reais de autor, revisor, outro revisor, outra empresa e utilizador sem permissões.
Os cenários F03 fazem commit apenas nessa base descartável para permitir que sessões
distintas vejam os dados umas das outras. Rejeições usam rollback. Há cobertura de
atomicidade, concorrência e commits tardios, além dos cenários de negócio pedidos.

## Limite do que é demonstrado

`impedimento_demonstrado` significa, exclusivamente, que as verificações registadas
sustentam duas proposições no instante explícito do fator:

1. Um requisito documentado aplica-se ao objetivo do contrato.
2. A condição necessária para satisfazer esse requisito não está satisfeita.

Isso demonstra um requisito não satisfeito **no âmbito dos registos e verificações
fornecidos**. Não demonstra que esse impedimento causou a deterioração, que explica
todo o período ou que continua presente agora. A hipótese causal nunca é promovida
a facto, mesmo quando as condições de um impedimento são sustentadas.

Um revisor diferente do autor é obrigatório para a verificação. Trata-se de separação
entre principais PostgreSQL, não de certificação de independência entre pessoas ou
organizações. O sistema valida estrutura, referências, identidade, versões, coerência
e cronologia; não executa o protocolo no mundo real, não lê documentos externos e
não confirma os seus bytes. Nem `verified` da F01/F02 nem uma revisão humana são
convertidos em prova independente pelo software.

Todos os relatórios incluem:

```json
{
  "independent_verification": "not_established",
  "causal_inference": "not_performed",
  "demonstration_scope": "documented_requirement_unmet_at_assessment_time",
  "execution_authorized": false
}
```

## Fluxo interno

### 1. Abrir a investigação sobre uma deteção específica

```sql
SELECT centerway.open_investigation(
  :tenant_uuid, :client_uuid, :investigation_uuid,
  :detection_run_uuid, :contract_revision, :question
);
```

O UUID da investigação é fornecido pelo chamador. A deteção deve existir no mesmo
âmbito e a revisão do contrato deve estar efetivamente em `result.periods` dessa
execução F02. O período selecionado pode ser anterior ao último período do run.
A associação é imutável: uma nova deteção exige outra investigação. A chamada não
reexecuta a F02 nem aceita um snapshot de deteção do chamador.

É permitido abrir uma investigação para esclarecer uma deteção inconclusiva. Mas a
conclusão F03 só pode ser conclusiva quando o período selecionado da F02 indica
`deterioracao_demonstrada` ou comparação `worsening`. Um período sem esse sinal gera
`no_supported_deterioration_in_selected_period`, sem candidatos para intervenção.
O sinal continua condicionado à evidência declarada da F02, preservada integralmente.

### 2. Acrescentar fatores, evidências e verificações

```sql
SELECT centerway.append_investigation_record(
  :tenant_uuid, :client_uuid, :investigation_uuid,
  :kind, :entity_uuid, :expected_revision, :reason, :business_fields_jsonb
);
```

`kind` é `factor`, `evidence` ou `verification`. Revisão esperada 0 cria a revisão 1;
qualquer correção exige a última revisão e cria a seguinte. O retorno é o registo
persistido completo. Usar parâmetros do driver. O JSON contém apenas campos de
negócio: âmbito, ID, revisão própria, autor e datas de registo são gerados/protegidos
pela função. Não há flags de facto comprovado, causalidade, ação autorizada ou estado
final que o chamador possa enviar.

Os textos seguem o domínio F01: 1–2000 caracteres, com conteúdo não branco. Tipos JSON,
campos desconhecidos, obrigatórios, enums e timestamps com fuso são validados.

**Fator — `factor`**

| Campo | Significado |
|---|---|
| `scope` | `internal`, `external` ou `mixed` |
| `category` | Categoria livre, sem taxonomia limitada a problemas técnicos |
| `hypothesis` | Hipótese explicitamente proposta; nunca usada como texto de um facto |
| `requirement` | Requisito cuja aplicabilidade ao objetivo será investigada |
| `condition` | Proposição testável sobre a satisfação desse requisito |
| `test_protocol` | Como verificar a proposição, fornecido pelo responsável |
| `assessment_at` | Instante finito dentro do período F02 selecionado, não futuro |
| `control` | `saas`, `client`, `third_party`, `unknown` ou `none` |
| `responsible_party` | Obrigatório para os três primeiros controlos; nulo nos restantes |

As evidências do fator dizem respeito ao mesmo instante e às mesmas proposições.
Para investigar outro instante ou significado, usar outro fator ou uma nova revisão.
A nova revisão não herda automaticamente evidências das anteriores.

**Evidência — `evidence`**

| Campo | Significado |
|---|---|
| `factor_id`, `factor_revision` | Proposição exata investigada |
| `purpose` | `requirement_applies` ou `condition_met` |
| `assertion` | Booleano explicitamente observado/documentado para essa proposição |
| `kind` | `direct_observation`, `document`, `reproduction` ou `usage_context` |
| `source_id`, `source_revision` | Fonte F01 exata da mesma empresa/cliente; pode ser externa à SaaS |
| `reference`, `content_sha256` | Localizador e digest declarado de 64 hexadecimais minúsculos |
| `collected_at` | Data de recolha finita, não futura, com fuso |

`requirement_applies = true` afirma que o requisito se aplica ao objetivo do contrato;
`condition_met = false` afirma que a condição não está satisfeita. São duas questões
separadas e ambas exigem evidência e verificação. O instante a que se aplicam é
`factor.assessment_at`; a recolha documental pode ser posterior ou anterior. É o
produtor e o revisor que sustentam essa aplicabilidade temporal.

`usage_context` pode ser preservado como contexto, mas não sustenta nenhuma das duas
proposições, mesmo que um revisor o confirme. Uma baixa utilização não é convertida
em impedimento de negócio. Correções podem alterar a afirmação ou suporte, mas não
podem mudar fator/versão, finalidade ou tipo de evidência dentro do mesmo ID.

**Verificação — `verification`**

| Campo | Significado |
|---|---|
| `evidence_id`, `evidence_revision` | Evidência exata verificada |
| `verdict` | `confirmed`, `rejected` ou `unverifiable` |
| `checked_assertion` | Igual à afirmação para confirmação; oposta para rejeição; nula quando não verificável |
| `method`, `explanation` | Procedimento realmente registado e explicação do resultado |
| `source_id`, `source_revision` | Fonte exata do suporte de verificação |
| `reference`, `content_sha256` | Referência e digest declarado do registo de verificação |
| `checked_at` | Não anterior à recolha nem ao instante avaliado, e não futuro |

O principal da ligação deve diferir do autor da revisão de evidência verificada.
Um revisor tem uma linha de versões por evidência/versão; não pode abrir várias
linhas para votar. Outro revisor pode registar a sua própria verificação. Correções
mantêm o mesmo revisor e a mesma evidência/versão. Corrigir uma evidência exige uma
nova verificação da revisão corrigida; a antiga não é reutilizada.

Os logins e memberships são provisionados administrativamente como na F01. As funções
não criam revisores automaticamente, não enviam mensagens e não solicitam verificações
fora da base. Um revisor não pode corrigir o registo de outro revisor.

### 3. Produzir a conclusão determinística

```sql
SELECT centerway.run_investigation(
  :tenant_uuid, :client_uuid, :investigation_uuid, :as_of_timestamptz
);
```

O corte é obrigatório, finito e não futuro. Uma única instrução captura o snapshot:
raiz da investigação, execução F02 congelada, última revisão de cada fator visível,
última revisão de cada evidência da versão exata do fator, últimas verificações da
versão exata da evidência e fontes referenciadas. O autor não pode escolher apenas
as evidências favoráveis na chamada de avaliação.

Para cada finalidade de cada fator:

- Sem evidência elegível: informação em falta.
- Sem verificação, ou com `unverifiable`: informação em falta.
- Com qualquer `rejected`: contradição não resolvida.
- Com afirmações elegíveis divergentes: contradição, mesmo que uma tenha mais
  verificadores ou que outra ainda não tenha sido revista. Não há votação ou média.
- Só há facto com verificação registada quando existe evidência, todas as verificações
  relevantes confirmam, cada evidência tem verificação e todas as afirmações concordam.

Os factos são proposições booleanas com instante, suporte e referências. O motor não
copia o texto da hipótese para a lista de factos. Quando há contradição, as declarações
originais ficam no snapshot e na categoria de contradições, sem afirmar ambas como
factos estabelecidos.

| Estado do fator | Regra |
|---|---|
| `impedimento_demonstrado` | Requisito aplicável e condição não satisfeita, ambos suportados, sem lacunas/contradições, com sinal F02 pertinente |
| `impedimento_nao_demonstrado` | Dados completos indicam requisito não aplicável ou condição satisfeita |
| `inconclusivo` | Falta suporte, há contradições ou não há sinal F02 pertinente |

A conclusão global é `inconclusivo` se não houver fatores ou se qualquer fator estiver
inconclusivo. Se todos estiverem resolvidos e algum demonstrar um impedimento, será
`impedimento_demonstrado`; caso contrário, `nenhum_impedimento_demonstrado`. Este último
não prova ausência de outros impedimentos fora do âmbito investigado.

## Estrutura do relatório e interface para intervenção futura

```sql
SELECT centerway.read_investigation_context(
  :tenant_uuid, :client_uuid, :investigation_uuid, :investigation_run_uuid
);
```

É uma leitura `SECURITY INVOKER` sob RLS, sem recomputação. Retorna SQL `NULL` para
registo inexistente ou invisível. O resultado inclui o snapshot, algoritmo `f03-v1`,
identidade, corte, hash, autor e cadeia de revisão, além das categorias:

- `observed_facts`: proposições com verificação registada, referências exatas de
  evidência e verificação, e `basis = recorded_verification`.
- `hypotheses`: texto proposto, âmbito e categoria; sempre `causal_status = not_established`.
- `contradictions`: afirmações incompatíveis/rejeitadas e referências das suas versões.
- `missing_information`: finalidade, fator e evidência/verificação relevante quando
  existente, com códigos de lacuna. Não inventa os dados que faltam.
- `excluded_evidence`: utilização preservada mas excluída da demonstração.
- `factor_conclusions`: estado e razões de cada fator, suporte explícito em
  `supporting_facts`, controlo e responsável declarados.
- `intervention_candidates`: apenas fatores demonstrados, com controlo `saas`, `client`
  ou `third_party` e responsável explícito, **quando a conclusão global é conclusiva**.

`potentially_actionable` no fator indica apenas a condição local de elegibilidade.
Uma investigação globalmente inconclusiva tem sempre `intervention_candidates = []`,
mesmo quando um fator isolado já tem suporte. `unknown`/`none` nunca geram candidatos.
Não se escolhe intervenção, prioridade, prazo ou responsável adicional. Controlo e
responsável são declarações de configuração, não capacidades comprovadas de execução.

O consumidor futuro deve usar a conclusão e os limites do relatório completo, não
apenas uma flag isolada. `execution_authorized` é sempre falso. Nenhuma intervenção,
scheduler, aprovação operacional, frontend ou parte da F04 foi implementada.

## Histórico, segurança e repetição

Todas as tabelas novas têm RLS, permissões de leitura por empresa e bloqueio de
UPDATE/DELETE/TRUNCATE. Escritas só passam pelas funções autorizadas. Referências
compostas incluem empresa, cliente e investigação quando aplicável; evidências de
outra investigação não podem ser ligadas por UUID simples. O âmbito e a associação
à deteção não podem ser alterados.

Autoria é `session_user`, não JSON ou variável de sessão. Cada inserção gera o evento
imutável F01 em `audit_log`, na mesma transação. Falhas não deixam gravações parciais;
rejeições não são guardadas fora da transação. Administradores continuam fora desta
fronteira: podem alterar o esquema, como documentado na F01.

Advisory locks serializam correções do mesmo ID. Revisões esperadas desatualizadas
produzem `40001/revision_conflict`. Repetições de criação com o mesmo ID produzem
conflito de unicidade; não alteram o registo existente.

A mesma investigação, corte e snapshot SHA-256 reutiliza o run, sem novo evento de
criação. Novos dados visíveis para o mesmo corte geram revisão com `revision_of`.
Outro corte inicia outra cadeia. Como na F02, a data de registo não é a data de commit:
um commit tardio pode revelar dados anteriores ao corte. Cada snapshot fica congelado,
e não é reinterpretado em leituras posteriores. Em isolamento mais forte que
`READ COMMITTED`, o cliente deve repetir a transação inteira em conflito de concorrência.

Alterações de protocolo, requisito, condição ou instante exigem nova versão do fator,
com novo suporte explícito. Alterações de semântica do motor exigirão outro algoritmo,
preservando os relatórios existentes.

## Limitações

- O motor verifica coerência e suficiência **dos registos fornecidos**; não comprova
  a verdade dos documentos, a independência dos principais ou a execução real do teste.
- Proposições booleanas por fator e instante. Não há análise textual, causal,
  estatística, descoberta automática de fatores ou reconciliação semântica entre fatores.
  Afirmações inconsistentes registadas em fatores distintos não são unificadas automaticamente.
- Fontes e hashes são declarados; não há download, armazenamento de anexos ou cálculo
  de digest sobre documentos externos. Os exemplos dos testes são inteiramente sintéticos.
- O snapshot é histórico: não estabelece persistência do impedimento nem a sua atualidade.
  Rever o contexto antes de qualquer futura decisão operacional será responsabilidade
  de outra missão, não uma autorização produzida por esta F03.
- O controlo e responsável são declarados. Não há gestão nova de identidades, roles
  funcionais, revogação, notificações, anexos ou integrações externas.
- Sem paginação, limites de volume demonstrados, SLA ou proteção WORM contra o administrador.
  Uma nova revisão de fator exige nova evidência, mesmo quando a alteração parece editorial;
  a F03 prefere a referência explícita à reutilização silenciosa.

A entrega termina na investigação e na sua porta de leitura. Não avança para F04.
