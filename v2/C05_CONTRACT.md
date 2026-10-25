# C05 — autorização e execução controlada (Missão 11)

Parte do PR #40 (`38acb5e`), branch `centerway-v2/missao-11-controlled-execution`.
Motor interno separado do Core/sandbox e dos motores M06–M10. Não acrescenta
endpoints HTTP, adaptadores reais, credenciais, executores de negócio ou C06.
**Production e intervenções externas permanecem bloqueadas.**

## Fluxo e autorização

`ExecutionRepository` em `centerway.controlled_execution`:

```python
# Backend local de confiança; não aceitar user/adapter de uma resposta de IA.
engine = ExecutionRepository(store)
intent = engine.prepare(user, tenant, customer, c04_request_id, execution_id,
                        adapter=test_adapter)
# Exibir e rever a intenção exata antes de confirmar. O chamador representa
# uma decisão humana explícita; nunca ligar este método à resposta do modelo.
approval = engine.approve(user, tenant, customer, execution_id,
                          intent['record_hash'], human_confirmed=True,
                          session_token=authenticated_session_token,
                          ttl_seconds=300, adapter=test_adapter)
result = engine.execute(operator, tenant, customer, execution_id,
                        adapter=test_adapter)
# Leitura interna para futuro C06; não verifica efeitos/recuperação.
audit = engine.get(reader, tenant, customer, execution_id)
```

`test_adapter` não existe como opção de configuração nem vem instalado. Só os
testes o injetam explicitamente. Sem adaptador, `prepare` recusa com 503.
O exemplo descreve a interface interna, não uma integração real disponível.

1. **Preparar:** Core exige membership operator no tenant; C04 tem de estar
   `proposal_validated`, reproduzível e sem novas versões/evidências nesse cliente.
   Valida outra vez catálogo, evidências, condições históricas e permissões C04.
   Captura uma observação nova do adaptador de teste e valida as condições atuais.
   Persiste intenção com proposta, configuração, capacidade, versões, proveniência,
   descriptor do adaptador, revisão atual e hash das condições observadas.
2. **Aprovar:** exige `human_confirmed is True`, hash exato da intenção e uma
   sessão existente, não expirada, pertencente ao aprovador operator. Guarda
   identidade, hash da sessão (nunca o token), vínculo à intenção e expiração
   de 1–300 segundos, limitada também à sessão. Volta a observar e validar
   estado/revisão e fontes. Mesmo capacidades que dispensam aprovação na
   configuração exigem aprovação humana nesta missão: política mais restritiva.
3. **Executar:** revalida operator executor, operator aprovador, sessão original,
   expiração, proposta/versões/catálogo e uma nova observação. A revisão e os
   valores têm de coincidir com a intenção/aprovação; nem uma condição ainda
   verdadeira permite ignorar uma mudança de revisão. Reserva tentativa única
   numa transação antes de chamar o adaptador, sem manter lock SQLite durante I/O.
4. **Registar:** guarda recibo limitado e sanitizado ou resultado incerto, com
   ator executor, chave idempotente, aprovação, revisões e timestamps. O resultado
   fica persistido mesmo se a sessão/permissão/demo expirar durante I/O; o acesso
   posterior continua recusado. Aprovação/condições não são uma autorização
   perpétua e leitura histórica nunca renova autorização.

A sessão e o hash verificam a identidade autenticada e o vínculo à intenção;
não são prova biométrica de presença humana. A interface é local/de confiança,
como os motores anteriores. Um futuro endpoint de aprovação terá de implementar
uma interação humana explícita com autenticação/CSRF, sem aceitar claims do modelo.
Nesta missão não há esse endpoint nem acesso remoto ao executor.

## Contrato de adaptador

`ExecutionAdapter` / `ExecutionReceipt` em `centerway.execution_adapter`.
Sem URLs, comandos, código dinâmico, parâmetros arbitrários ou segredos fornecidos
pela IA. O binding é construído exclusivamente pelo backend a partir do C04.

`descriptor()` deve devolver **exatamente**:

```json
{
  "kind": "test_adapter",
  "adapter_id": "explicit-sqlite-test",
  "version": "v1",
  "tenant": "collaboration",
  "capability_id": "reopen-delivery-queue",
  "idempotent": true,
  "atomic_conditions": true
}
```

Só é aceite com configuração `synthetic`, fora de production. O descriptor é
fixado na intenção e revalidado antes da aprovação/reserva. Identificadores de
adaptador/versão seguem o contrato de IDs M06; não selecionam executores.
Declarações destas garantias não certificam conectores reais: todos continuam
recusados nesta missão. Um futuro conector precisa de implementação e validação
independentes de credenciais, escopo, permissões e garantias no serviço remoto.

`observe(binding)` devolve exatamente:

```json
{
  "tenant": "collaboration",
  "customer": "fictional-account",
  "capability_id": "reopen-delivery-queue",
  "revision": "1",
  "observed_at": "2026-10-25T12:00:00+00:00",
  "facts": [{"evidence_ref":"operation-state","field":"paused","value":true}]
}
```

O timestamp do exemplo é ilustrativo. A observação tem de ocorrer durante a
chamada atual; não se aceita um timestamp histórico ou futuro. Máximo 16 KiB,
100 factos, apenas os campos exigidos pelas condições declaradas, com tipos e
operadores M06. Campos em falta, adicionais, repetidos/contraditórios ou valores
incompatíveis recusam. Não se escolhe arbitrariamente entre leituras conflitantes.
As observações ficam identificadas como originárias do adaptador de teste, com
as definições/fontes do contrato fixado; não são inseridas como evidência real.
Uma observação só pode ser usada até 5 segundos depois da leitura: limite de
segurança do despacho, não meta/métrica/regra de negócio. Nunca se deduz
persistência de uma observação C04 no passado.

`apply(execution_key, binding, snapshot)` recebe cópias desligadas dos registos.
O adaptador **tem de comparar atomicamente a revisão e condições atuais** e
persistir a chave juntamente com o efeito. Deve devolver `ExecutionReceipt`:

- `status`: `test_applied`, `failed_no_effect` ou `uncertain`;
- `receipt_id`: ID simples (1–128 caracteres), não texto livre/segredos;
- `before_revision`: revisão fixada no snapshot;
- `after_revision`: ID de revisão ou `None`; obrigatório e diferente da revisão anterior em `test_applied`; `None` em `failed_no_effect`.

`failed_no_effect` só é declaração explícita do adaptador que não aplicou efeito.
Exceção, timeout ou recibo inválido tornam o resultado `uncertain`, mesmo que o
adaptador tenha aplicado algo. Nunca se assume ausência de efeito após timeout.
Mensagens de exceção/recibos arbitrários não são persistidos. Só o adaptador
SQLite **definido nos testes** implementa efeito local; não toca no sandbox.

## Idempotência, concorrência e estados

Unicidade persistida por `(tenant,customer,execution_id)` e por proposta C04.
Outra proposta/ID também não pode contornar uma intenção para a mesma linhagem,
capacidade, adaptador e revisão/valores atuais (fingerprint único). A chave de
despacho inclui hashes da intenção e aprovação e é entregue ao adaptador.
Uma única tentativa por intenção; reservas concorrentes são serializadas pelo
SQLite. Reenvios consultam a tentativa/resultado; nunca repetem `apply`.

| Estado consultável | Significado |
| --- | --- |
| `awaiting_human_approval` | Intenção registada, sem autorização |
| `approved_test_only` | Aprovação humana registada; requer todas as revalidações |
| `uncertain_pending` | Reserva sem recibo: processo em curso/interrompido, efeito desconhecido |
| `test_applied` | Adaptador reportou efeito de teste, sem verificação C06 |
| `failed_no_effect` | Adaptador reportou falha sem efeito de teste |
| `uncertain` | Resultado não determinável; requer revisão |

Não há retries automáticos, renovação de aprovação, reabertura de tentativas ou
resolução automática de pendências. Crash antes ou depois do efeito consome a
reserva; disponibilidade é sacrificada para evitar duplicações. Até uma falha
sem efeito exige fluxo futuro de revisão, não uma segunda chamada nesta missão.
Revogar a sessão/membership do aprovador bloqueia um despacho ainda não reservado.
Depois da reserva há uma fronteira inevitável de despacho: revogação posterior
não desfaz um efeito iniciado. O adaptador tem de aplicar o seu próprio fence
atómico; não se afirma atomicidade distribuída entre Core e serviço remoto.

## Auditoria e futuro C06

Setup opcional cria apenas `c05_metadata`, `c05_intents`, `c05_approvals`,
`c05_attempts`, `c05_results`, `c05_audit`. Sem instalação/migração no arranque HTTP.
Triggers recusam UPDATE/DELETE; FKs compostas preservam os vínculos de escopo.
Hashes verificam integridade/vínculos e o diário encadeado por intervenção.
O diário regista preparação, aprovação, despacho, resultado e recusas sanitizadas.
Uma recusa regista `claimed_principal`; não apresenta uma identidade tentada como
identidade autenticada. Aprovações válidas registam `session_verified`.
Esquema/triggers alterados ou histórico inconsistente recusam sem reparação.
Hashes locais não são assinaturas nem proteção contra administrador do ficheiro;
backups/restrição do host continuam necessários, como nos motores anteriores.

`get` exige membership atual (viewer pode ler). Devolve snapshots C04/C05,
aprovação, tentativa, recibo e diário para um futuro C06. Inclui sempre:
`external_execution: blocked`, `verification_status: not_performed`;
resultados têm `operational_recovered: null`, `value_recovered: null` e
`external_execution_authorized: false`. C04 continua `execution_authorized: false`.
**Efeito do adaptador de teste não é recuperação operacional ou de valor real.**

Erros `Problem`: 400 confirmação/TTL inválidos, 403 permissão/sessão,
404 identidade ausente no escopo, 409 condições/versões/duplicação incompatíveis,
503 storage/runtime/adaptador indisponível ou production bloqueado. Sem eco de
conteúdo externo ou segredos; códigos de recusa ficam no diário quando possível.
Não se escreve em tabelas antigas de Core, evidências, C02, C03 ou C04.

## Preparação e verificações

Numa cópia local já preparada até M10 (nunca migração dos dados existentes):

```sh
cd v2
python -m centerway.controlled_execution init --db /caminho/copia.sqlite3
python -m centerway.controlled_execution get --db /caminho/copia.sqlite3 \
  --user OPERADOR --tenant SAAS --customer CLIENTE --execution-id ID
python -m unittest discover -s tests -p test_controlled_execution.py -v
CADDY_BIN=/caminho/caddy python -m unittest discover -s tests -v
```

CLI só instala storage explicitamente e lê; não contém executores/configuração
para ativar ações. Testes criam bases temporárias e sessões privadas de teste,
injetam fixtures C04 identificadas e o adaptador SQLite de teste separado.
Cobrem três SaaS, clientes independentes (incluindo ID externo), efeito persistido,
aprovação/sessão/hash/TTL/roles, condições atuais/revisão/fence, novas evidências e
catálogo, isolamento, concorrência, reenvios, crash antes/depois do efeito,
timeout/recibo inválido, ausência de adaptador, imutabilidade/integridade,
backup, demo expirada durante I/O, production e preservação dos motores anteriores.

Limitações: não há conectores reais, autorização/executor de produção, interface
humana ou endpoint C05, parâmetros de intervenção, resolução de incerteza, retries,
rollback remoto ou C06. Só se executam efeitos explicitamente fictícios nos testes.
O contrato atual de condições é o da M06; não se inventam metas nem causas.

Missão 12: [C06 inativo, com evidências posteriores e planos temporais explícitos](C06_CONTRACT.md). Recibos C05 continuam sem comprovar recuperação real.
