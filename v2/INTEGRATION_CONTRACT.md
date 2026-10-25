# Missão 06 — contrato interno de integração v1

Parte do PR #35 (`851aede`). Configurações declarativas por SaaS, sem alterações ao
Core, C01–C06, catálogo sandbox, interface ou contrato HTTP 1.1.0. Não há novos
endpoints, conectores, ingestão de eventos reais, avaliação de condições ou execução.

## Documento de configuração

Ver exemplos completos de [colaboração](examples/integrations/collaboration.json),
[faturação](examples/integrations/billing.json) e [suporte](examples/integrations/support.json).
São **declarações sintéticas do autor das fixtures**, não métricas descobertas,
objetivos recomendados, evidências reais ou integrações disponíveis. Os nomes dos
nichos não aparecem no código de validação/repositório.

| Campo obrigatório | Significado |
| --- | --- |
| `schema_version` | Inteiro 1; versões de contrato desconhecidas são recusadas |
| `tenant` | SaaS proprietária; igual ao escopo autorizado da importação |
| `data_classification` | `synthetic` ou `declared`; declaração não significa verificação |
| `provenance` | `source_ref`, `supplied_by`, `recorded_at` UTC, declarados pelo fornecedor |
| `product` | `name`, `description`, sem inferência de contexto |
| `customers` | `entity`, `id_field`, `description`: identidade contratual, não registos de clientes |
| `value_goals` | IDs, descrições e referências explícitas a métricas/evidências |
| `metrics` | IDs, descrições, unidade, tipo numérico, origem e eventos referenciados |
| `events` | IDs, descrições, origem, campo identificador do cliente e campos tipados |
| `evidence` | IDs, descrições, tipo, origem, disponibilidade declarada, referências e campos tipados |
| `capabilities` | IDs, descrições, condições, permissões exigidas e critérios de verificação |

Não há campos opcionais com defaults ocultos. Listas podem estar vazias quando a
SaaS ainda não forneceu definições. Um objetivo presente exige referência declarada;
se falta informação para o definir, omitir esse objetivo, sem inventar indicadores.
`source_ref` é uma referência textual de proveniência, nunca um URL a executar.
Não incluir segredos, dados pessoais ou conteúdo de evidências nestes metadados.

Cada lista admite até 100 entradas, IDs únicos locais à lista e referências apenas
à própria configuração. IDs: `[a-z0-9][a-z0-9_-]{0,63}`. Nomes de campos:
`[a-zA-Z][a-zA-Z0-9_]{0,63}`. Documento até 65536 bytes; texto até 2000 caracteres,
nome de produto até 128 e referências de origem até 256. Campos extra, JSON ambíguo
com chaves repetidas, NaN/Infinity, tipos incorretos e referências pendentes são
recusados. O validador stdlib é `centerway.integration_contract.validate/load`.

Eventos declaram um campo obrigatório string que identifica o cliente. Cada campo
tem `name`, `type` e `required`; tipos: string, number, integer, boolean e timestamp.
Métricas numéricas descrevem significado/unidade/origem; não há fórmulas inferidas,
agregações automáticas, limiares por nicho ou execução de expressões.

Evidência tem tipo event/metric/document/state e disponibilidade declared/unavailable.
Event/metric exigem referências correspondentes. `declared` só regista a alegação
do fornecedor: não prova que um conector, medição ou evidência existe em runtime.

## Catálogo de capacidades

Adicionar uma entrada com ID novo estende o catálogo sem código específico de SaaS.
Cada capacidade exige condições não vazias e permissões explícitas:
`required_role: operator` e `requires_human_approval: true|false`. Estes são requisitos
futuros, **não uma autorização de execução**. Não há adapters, credenciais, scripts,
URLs de execução ou flag de ativação neste contrato.

Condições e critérios de verificação referem `evidence_ref`, `field`, `operator` e
`value`. `exists` não admite value; eq/ne admitem o tipo declarado; lt/lte/gt/gte
exigem número ou timestamp. Números são finitos e limitados a ±(2^53−1); integer
recusa booleanos/frações. Timestamps são ISO UTC. Campos têm de existir na evidência,
cuja disponibilidade deve ser declared. Nenhum desses predicados é avaliado agora.

`verification.operational` é obrigatório e não vazio. `verification.value` pode
estar vazio: significa ausência de critérios de valor, sem completar ou presumir
recuperação. Cada critério de valor deve ligar-se a um objetivo em `value_goal_refs`,
por evidência ou métrica explicitamente referenciada. Cada objetivo selecionado
exige pelo menos um critério. Não se transforma êxito operacional em êxito de valor.

## Persistência e consulta interna

`centerway.integrations.IntegrationRepository` usa o SQLite existente e memberships
atuais do backend. A instalação das duas tabelas opcionais é **explícita**; abrir o
servidor/repositório não cria tabelas, não migra nem repara. Não há dependências novas.

```python
from centerway.store import Store
from centerway.integrations import IntegrationRepository

repository = IntegrationRepository(Store.open_existing(private_database_path))
snapshot = repository.get(authenticated_user, tenant, version=1)
config = snapshot['config']
# Futuros componentes podem consultar product/customers/metrics/evidence/capabilities.
# Esta missão não liga esta leitura a nenhum componente ou execução.
versions = repository.history(authenticated_user, tenant)
```

O utilizador tem de vir de autenticação confiável do backend. Leitores consultam;
só operadores da SaaS acrescentam versões. Cada operação revalida runtime, prazo
da demo, estrutura/proteções e membership atual; não confia numa role fornecida
pelo chamador. Configurações de uma SaaS não são procuradas através de outra.

`append(user, tenant, config, expected_version)` cria versão sequencial; 0 significa
primeira versão. Exige a versão atual para evitar substituições concorrentes: uma
vence, a outra recebe conflito 409. Não altera linhas antigas. `get(..., version=N)`
fixa a versão histórica; sem versão lê a mais recente. Ausência é 404, sem fallback
para outra SaaS, fixture ou regra sandbox. Os resultados são cópias independentes.

Cada versão guarda documento completo/proveniência, autor autorizado, hora de
importação do servidor, hash do conteúdo e hash do registo anterior. History inclui
proveniência e classificação por versão. Triggers impedem UPDATE/DELETE; verificações
de integridade detetam lacunas, conteúdo/autor alterados e proteções removidas, sem
reparação. Hashes não são assinatura externa: o administrador do ficheiro/SO continua
confiável e pode reescrever uma cadeia completa. Não há aprovação criptográfica.

## CLI local e testes

A partir de `v2`, validar os três exemplos sem base, contas ou rede:

```sh
python3 -m centerway.integrations validate --file examples/integrations/collaboration.json
python3 -m centerway.integrations validate --file examples/integrations/billing.json
python3 -m centerway.integrations validate --file examples/integrations/support.json
python3 -m unittest discover -s tests -p test_integrations.py -v
```

Os testes criam bases temporárias e memberships das três SaaS. Para uma base já
provisionada e uma conta operator autorizada, os comandos são:

```sh
python3 -m centerway.integrations init --db /private/runtime.sqlite3
python3 -m centerway.integrations append --db /private/runtime.sqlite3 \
  --user authorized-operator --tenant configured-saas \
  --file /private/supplier-configuration.json --expected-version 0
python3 -m centerway.integrations get --db /private/runtime.sqlite3 \
  --user authorized-operator --tenant configured-saas --version 1
python3 -m centerway.integrations history --db /private/runtime.sqlite3 \
  --user authorized-operator --tenant configured-saas
```

`init` é uma alteração explícita e aditiva de estrutura, pelo responsável local;
recusa armazenamento existente/parcial. Os comandos não foram executados contra
bases existentes do utilizador. Fazer backup antes de instalação futura. O argumento
user é uma identidade selecionada pelo operador local confiável, não um login ou
prova remota de identidade. Não expor a CLI como serviço. `get` imprime metadados;
apenas usar em terminal privado. Falhas da CLI têm saída genérica sem conteúdo do
ficheiro. Nenhum servidor recebe ou disponibiliza estas configurações por HTTP.

## Verificação executada

73 testes Python passaram, sem skips, incluindo os 12 novos testes de integração,
os ciclos sandbox e o proxy Caddy real em loopback. Três ensaios Chromium passaram:
registo de 150 clientes e interface responsiva, demo HTTPS privada com Pixel 7
emulado, e CORS same-site. `compileall` e `git diff --check` passaram. Os testes
usaram apenas bases temporárias; não validam uma integração real ou Android físico.

## Production e limites

Production recusa os exemplos/classificação synthetic. Pode guardar declarações
explícitas de fornecedor (`declared`), que continuam **não verificadas e inativas**;
alterar apenas a classificação de uma fixture não a torna real. O responsável local
é responsável pela veracidade da declaração. Todos os bloqueios da Missão 05
permanecem: sem clientes operacionais, ações ou recuperações reais. As seis tabelas
de negócio continuam vazias e protegidas, independentemente do catálogo configurado.
O armazenamento também distingue laboratório, demo privada e production; remover
um marcador de demo não converte o repositório nem remove a sua expiração.

Não há registos de clientes, ingestão real, descoberta de métricas, execução/avaliação
de condições, aprovação humana implementada, conectores, IA, scheduler ou alterações
à UI. C01–C06 continuam a usar exclusivamente a lógica sandbox anterior. A leitura
valida toda a cadeia da SaaS; sem paginação/cache, não é ensaio de escala de histórico.
Não há ativação de versão: a última versão é a mais recente declaração, não uma
configuração aprovada para negócio. Futuras execuções terão de fixar a versão,
validar evidências/consentimento e continuar a respeitar os bloqueios de production.
