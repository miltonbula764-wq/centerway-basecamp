# Contrato de Valor e portas internas — F01

## Identidade e versões

Uma empresa SaaS é `tenant_id`; o seu cliente é `client_id`. O cliente só existe
no âmbito da empresa. Cada entidade é identificada por
`(tenant_id, client_id, id, revision)`, com IDs UUID e revisão inteira a partir de 1.
Há quatro tipos: `source`, `contract`, `evidence` e `assessment`.
Todas as referências incluem empresa, cliente e versão exata. Não existe resolução
implícita para a versão mais recente de uma fonte ou contrato.

Cada escrita cria uma linha imutável, com `actor = session_user`, `recorded_at`
gerado pela base e `reason` obrigatório. O mesmo commit cria um evento em
`audit_log`, com snapshot completo. Uma correção é a revisão seguinte do mesmo ID;
a revisão anterior permanece consultável. Nunca se atualiza ou elimina uma versão.
Uma nova revisão de contrato não muda os contratos associados às evidências antigas.

## Campos de negócio

Todos os campos abaixo são obrigatórios, salvo a referência de evidência de uma
avaliação. Textos devem conter 1–2000 caracteres e não podem ser apenas espaços.
Campos desconhecidos, metadados reservados e conversões de string para número são
rejeitados. Números são decimais PostgreSQL finitos; datas devem indicar fuso horário.

### Fonte (`source`)

| Campo | Significado |
|---|---|
| `name` | Nome explícito da fonte |
| `locator` | Localizador do sistema/documento de origem |
| `method` | Descrição de como os dados são obtidos |

A revisão da fonte fixa estes metadados. Alterá-los exige uma nova revisão.

### Contrato (`contract`)

| Campo | Significado |
|---|---|
| `objective` | Objetivo declarado pelo responsável |
| `expected_outcome` | Resultado de negócio esperado, em texto |
| `indicator` | Indicador de resultado escolhido explicitamente |
| `unit`, `measurement_method` | Unidade e método de medição/composição do valor |
| `direction` | `higher` (mais é melhor) ou `lower` (menos é melhor) |
| `baseline` | Valor inicial conhecido |
| `minimum_acceptable` | Limite que satisfaz o mínimo contratado |
| `target` | Alvo quantitativo desejado; pode ser mais exigente que o mínimo |
| `baseline_start`, `baseline_end` | Intervalo de referência da baseline |
| `period_start`, `period_end` | Intervalo de avaliação |
| `source_id`, `source_revision` | Fonte exata usada para comparar baseline e resultado |
| `baseline_reference` | Referência concreta que sustenta a baseline |

Os intervalos são `[início, fim)`, em instantes com fuso. O período da baseline
termina antes ou no início da avaliação e não pode terminar no futuro.
Ambos os intervalos devem ser finitos e não vazios.

Para `higher`: `baseline <= minimum_acceptable <= target`.
Para `lower`: `baseline >= minimum_acceptable >= target`.
Igualdade entre baseline e mínimo permite contratos explícitos de manutenção.
Metas que aceitam deterioração face à baseline não são suportadas nesta F01.

Não é possível comprovar a natureza de negócio de um indicador a partir do seu nome.
O responsável deve escolher um resultado; logins, cliques ou tempo na SaaS não são,
por si só, obtenção de valor. A camada não transforma métricas de utilização em
resultado nem cria objetivos a partir delas.

### Evidência e resultado observado (`evidence`)

| Campo | Significado |
|---|---|
| `contract_id`, `contract_revision` | Contrato exato que dá significado à observação |
| `source_id`, `source_revision` | Fonte exata, obrigatoriamente igual à do contrato |
| `evidence_type` | `outcome` ou `usage` |
| `quality` | `verified`, `partial` ou `disputed`, declarado pelo produtor |
| `observed_value` | Resultado numérico observado; nunca substituído por zero ausente |
| `unit`, `measurement_method` | Devem coincidir exatamente com o contrato |
| `period_start`, `period_end` | Janela observada, contida na avaliação e já terminada |
| `reference` | Localizador do suporte concreto desta observação |
| `content_sha256` | Digest declarado do suporte, 64 caracteres hexadecimais minúsculos |

Uma janela parcial pode ser registada, mas não sustenta conclusão de valor.
Ausência de observação é representada pela ausência de evidência, não por uma
observação inventada. Correções podem mudar valor, qualidade e suporte, mas não
contrato/versão, tipo ou janela de medição. Uma observação diferente usa outro ID.

### Avaliação (`assessment`)

| Campo | Significado |
|---|---|
| `contract_id`, `contract_revision` | Contrato exato avaliado |
| `evidence_id`, `evidence_revision` | Evidência exata; ambos nulos ou ambos preenchidos |
| `state` | Um dos quatro estados abaixo |
| `rationale` | Justificação explícita do produtor |

A base grava também `validation_policy = f01-v1`, metadado não editável que
identifica estas regras. Uma evolução semântica deve preservar este histórico e
introduzir uma nova política, sem reinterpretar avaliações antigas.

O produtor submete a conclusão. A base valida a sua consistência; não descobre
objetivos, não escolhe evidências e não executa um motor de deteção.
Correções de avaliação mantêm o contrato/versão e podem referenciar uma nova revisão
da evidência. Avaliações antigas nunca são recalculadas. Uma referência antiga é
permitida e permanece explícita; esta API não afirma que seja o estado atual do cliente.

## Estados e precedência

Primeiro, a evidência deve ser de resultado (`outcome`), `verified`, cobrir exatamente
a janela completa do contrato e corresponder à sua versão. O período deve estar
terminado. Caso falte qualquer requisito de suficiência, só se admite
`resultado_inconclusivo`. Referências inexistentes/incompatíveis são erros, não
conclusões inconclusivas silenciosas.

Com evidência suficiente, a classificação admissível é:

| Estado | `higher` | `lower` |
|---|---|---|
| `deterioracao_demonstrada` | observado < baseline | observado > baseline |
| `valor_demonstrado` | observado >= mínimo | observado <= mínimo |
| `valor_insuficiente` | baseline <= observado < mínimo | mínimo < observado <= baseline |

A igualdade no mínimo demonstra o mínimo contratado. Atingir o `target` não é
necessário para este estado; o alvo continua disponível para análise futura.
Deterioração significa piora numérica face à baseline, sem teste estatístico ou
atribuição causal. Inconclusivo significa que não é possível concluir com o suporte
registado; insuficiente exige suporte suficiente e resultado aquém do mínimo.

## Escrita interna

```sql
SELECT centerway.append_version(
  p_tenant           => :empresa_uuid,
  p_client           => :cliente_uuid,
  p_kind             => :tipo,          -- source | contract | evidence | assessment
  p_id               => :entidade_uuid,
  p_expected_revision => :ultima_revisao, -- 0 para criar
  p_reason           => :motivo,
  p_data             => :campos_jsonb
);
```

Usar parâmetros do driver, nunca concatenar dados em SQL. `p_data` contém apenas os
campos de negócio descritos acima; não enviar IDs de âmbito, revisão da própria
entidade, autor, data de registo ou motivo dentro do JSON. O retorno JSON é a versão
persistida completa. Não há valores de negócio por omissão.

A operação valida autorização, estrutura, referências, datas, limiares e conclusão,
serializa escritas do mesmo ID com advisory lock transacional e compara a última
revisão. O incremento e o evento de auditoria pertencem à mesma transação. Uma falha
não deixa gravação parcial. Colisões do hash de lock apenas serializam IDs adicionais.

Ordem inicial: provisionar empresa/cliente/principal administrativamente; registar
fonte; registar contrato; registar evidência quando existir; submeter avaliação.
Uma avaliação inconclusiva pode existir sem evidência.

Erros principais (SQLSTATE): `42501` acesso negado, `22023` pedido/campo/tipo inválido,
`23502` obrigatório ausente, `23503` referência inválida, `23514` violação de regra,
`22P02` representação inválida, `P0002` referência de contrato/evidência não encontrada,
`40001` conflito de revisão e `55000` tentativa de mutar histórico. O chamador deve
tratar a classe de erro; mensagens de constraints não são uma API de apresentação.

## Leitura para deteção e investigação futuras

```sql
SELECT centerway.read_contract_context(
  :empresa_uuid, :cliente_uuid, :contrato_uuid, :revisao
);
```

Retorna `contract`, `source`, `evidence_history` e `assessment_history`, sempre com
referências completas. As listas são ordenadas por ID/revisão. Retorna SQL `NULL`
quando a versão não existe ou não está visível. A leitura é `SECURITY INVOKER`, com
RLS, num snapshot da instrução SQL. O histórico pode crescer posteriormente, mas as
versões nele existentes permanecem imutáveis. Para reproduzir uma conclusão, guardar
as referências exatas, nunca a ideia de “último resultado”.

As tabelas versionadas e `audit_log` têm leitura direta sob RLS para consultas
internas filtradas. Não existem permissões diretas de INSERT/UPDATE/DELETE/TRUNCATE
para `centerway_api`. Chaves estrangeiras compostas impedem referências entre
empresas/clientes; o âmbito não pode ser mudado por UPDATE. Provisionamento e
credenciais ficam sob controlo administrativo, fora desta porta.
