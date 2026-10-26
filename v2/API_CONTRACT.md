# CENTERWAY V2 — contrato HTTP 1.5.0

Contrato do backend Python da Missão 03, baseado no PR #32. Especificação importável:
[`contracts/openapi.json`](contracts/openapi.json), OpenAPI 3.1 / JSON Schema 2020-12.
Não há URL publicado, interface nova, uso de Lovable ou integração real nesta missão.
Na demo, tudo continua fictício: `environment_type: "sandbox"` e `decision_mode: "simulator-v1"`.
Production devolve `production` / `disabled` na view operacional, sem dados ou intervenções simuladas. A API separada de evidências permanece inativa.

## Extensão 1.5.0: entrada SaaS server-to-server

POST `/api/webhooks/ingest` usa HMAC-SHA256 sobre os bytes originais e headers
assinados (origem, chave, timestamp e nonce), sem sessão humana. Só existe entrada
funcional com configuração privada explícita e HTTPS; não aceita browser/CORS.
A origem configurada fixa SaaS, clientes, versão/hash M06 e mapeamento declarativo.
Cada mensagem insere no máximo uma declaração M07 inativa; não consulta dados,
não autoriza e não executa. Replay/idempotência, rotação, limites e exemplos:
[contrato de integração](WEBHOOK_CONTRACT.md). API global anuncia 1.5.0.

## Extensão 1.4.0: continuidade e ciclos históricos

GET `/api/orchestration/cases` acrescenta `lifecycle=active|closed|all` (default
active), `cycle_number`, predecessor e resumo de fecho. GET
`/api/orchestration/cycle` exige tenant/customer/case_id e fornece contexto ou
snapshot histórico congelado. POST `/api/orchestration/open`, `/close` e `/review`
são decisões administrativas explícitas, autenticadas, para operador: confirmação
humana, request_id, contexto/versão quando aplicável e sessão do cookie. Nunca
aceitam actor/role/token em JSON. Incerto/pendente bloqueia encerramento e sucessor;
review apenas regista unresolved. Nenhum resultado C06 encerra automaticamente.
Ver [contrato de continuidade, campos, erros e upgrade explícito](CONTINUITY_CONTRACT.md).
Production recusa os novos POST; casos e operações de negócio continuam inativos.
Sem DDL no HTTP ou migração automática. A extensão foi introduzida em 1.4.0; contratos de
motores e endpoints anteriores preservados, com extensão da consulta M13.

## Extensão 1.3.0: consulta da orquestração inativa

GET `/api/orchestration/cases` consulta estados, impedimentos e referências dos
casos coordenados M06–M12. Exige sessão e membership atual; viewer pode ler.
`tenant` obrigatório; filtros `customer`, `case_id` (exige customer), `state`;
paginação `after` e `limit` (1–50). Query estrita, sem campos repetidos/vazios ou
claims de role. `next_after` é null ao terminar. A leitura **não processa casos**
e não autoriza ações; `updated_at` é a última transição processada.
Ver [estados, resposta, limites e instruções](ORCHESTRATION_CONTRACT.md) e schemas
`OrchestrationCase`/`OrchestrationPage` no OpenAPI. Não há endpoints de escrita,
IA, aprovação ou execução novos. Sem setup opcional devolve 503. Production
continua bloqueado para inscrição/processamento e só permite consulta inativa.
As respostas dos caminhos anteriores são preservadas; header de versão é 1.3.0.

## Extensão 1.2.0: evidências inativas

POST `/api/evidence` recebe lotes autorizados por SaaS/cliente/configuração; GET
`/api/evidence/view` consulta registos, proveniência e qualidade estrutural. Ver
[contrato, exemplos, limites e preparação](EVIDENCE_API.md) e os schemas Evidence*
no OpenAPI. Exigem sessão e membership; só operadores podem ingerir. A entrada é
permitida em production apenas no armazenamento separado e inativo: **não desbloqueia
C01–C06, ações ou observações sandbox**. Os endpoints anteriores são preservados.
Sem preparação explícita do armazenamento opcional, os novos caminhos devolvem 503.

## Extensão 1.1.0: modo permanente

Os caminhos e schemas de pedidos anteriores são preservados. A união de respostas
View adiciona `ProductionRegistryView`; a autenticação adiciona o cookie
`__Host-cw_production_session` (Secure, HttpOnly, SameSite=Strict, Path=/, uma hora).
Production não tem lease global, mas sessões continuam a expirar e ser revogadas.
Contas são configuradas por CLI privada, nunca pelo frontend.

GET `/api/view` sem detalhe devolve identidade/memberships reais e registo vazio:

```json
{"user":"operations-owner","memberships":[{"tenant":"tenant-one","role":"operator"}],"environment_type":"production","decision_mode":"disabled","registry":[],"counts":{"observation":0,"deterioration":0,"investigation":0,"intervention":0,"recovery":0,"exceptions":0,"stable":0}}
```

Filtrar por tenant exige membership; consultar cliente/caso devolve 503. As seis
mutações de negócio em production devolvem 503 para operador autorizado, sem efeito;
leitores/tenants alheios recebem 403. Os sucessos dos endpoints de negócio preexistentes
e os seus exemplos abaixo descrevem o **sandbox**. A view operacional production nunca deve ser interpretada pelo frontend
como autorização para executar ações ou prova de recuperação real.

Exemplo de bloqueio:

```http
POST /api/execute
Content-Type: application/json

{"tenant":"tenant-one","customer":"client-one","case_id":"case-one"}
```

Resposta 503, após autenticação e autorização, sem execução:

```json
{"error":"Operação indisponível em production: não preparada/autorizada; nenhum efeito foi executado.","code":"unavailable"}
```

Ver [configuração e limites](PERMANENT_FOUNDATION.md). Não há endpoints novos de
administração, integração real ou frontend production nesta missão.

## Transporte e autenticação

- Pedidos POST: JSON UTF-8, `Content-Type: application/json`, objeto, até **65536 bytes**.
  Não enviar campos extra, chaves repetidas, NaN/Infinity ou parâmetros na query.
  Schemas cobrem a estrutura; limites temporais e validações após trim são semânticos.
- Respostas de API: JSON, `Cache-Control: no-store`, header
  `X-Centerway-API-Version: 1.4.0`. As respostas de sucesso anteriores são preservadas.
- Autenticação por cookie HttpOnly; sem JWT, bearer token, API key ou role no browser.
  Login devolve apenas `user`; o browser guarda o cookie recebido por `Set-Cookie`.
- Modo privado: `__Host-cw_session`, Secure, HttpOnly, SameSite=Strict, Path=/,
  sem Domain, duração de uma hora. A pré-visualização inteira expira em até 24 h.
  Só usar credenciais entregues por um canal privado; nunca colocá-las no código,
  variáveis `VITE_*`, localStorage, exemplos, logs ou pedidos na query.
- Modo laboratório: `cw_session`, oito horas, **exclusivamente em loopback**. Não
  suporta CORS externo nem pode servir a base privada. Não usar as suas contas
  numa integração externa. A preparação privada do PR #32 mantém-se obrigatória.
- APIs protegidas exigem sessão e membership atual. Leitores consultam; só operadores
  da SaaS executam mutações. SaaS, cliente e caso são verificados no servidor.

## Superfície existente

Não existem `/api/cases` ou `/api/interventions`. Casos, evidências e intervenções
do sandbox continuam a ser lidos em `/api/view`. O novo `/api/evidence` é a entrada
separada de evidências inativas, descrita na extensão 1.2.0.

| Método e caminho | Entrada | Resposta de sucesso | Permissão |
| --- | --- | --- | --- |
| GET `/api/orchestration/cycle` | Escopo exato | 200 contexto/abertura/fecho/revisões históricos | Membership / leitor |
| POST `/api/orchestration/open` | Motivo, predecessor, request_id e confirmação | 200 abertura idempotente | Operador + sessão |
| POST `/api/orchestration/close` | Contexto/hash, versão, motivo, disposição, request_id e confirmação | 200 fecho imutável; não implica recuperação | Operador + sessão |
| POST `/api/orchestration/review` | Nota, referências de evidências, contexto, request_id e confirmação | 200 revisão unresolved, sem desbloqueio | Operador + sessão |
| GET `/api/orchestration/cases` | SaaS, lifecycle, filtros e paginação | 200 estados/impedimentos inativos; não processa | Membership / leitor |
| POST `/api/evidence` | `tenant`, `customer`, `config_version`, `records` | 200 recibo atómico/idempotente; sempre inativo | Operador |
| GET `/api/evidence/view` | Escopo/versão e paginação | 200 registos/proveniência/qualidade estrutural | Membership / leitor |
| POST `/api/login` | `user`, `password` | 200 `{ "user": "…" }` + cookie | Credencial válida |
| POST `/api/logout` | `{}` | 200 `{}`; sessão revogada e cookie removido | Sessão |
| GET `/api/view` | Query opcional abaixo | 200 registo ou detalhe de cliente | Membership / leitor |
| POST `/api/customers` | `tenant`, `customer`, `name`, `scenario?` | 201 `{ "customer": "…" }` | Operador |
| POST `/api/observations` | `tenant`, `customer`, `observations` | 200 `batch_id`, `inserted`, `reused` | Operador |
| POST `/api/advance` | `tenant`, `customer`, `case_id?` | 200 `case_id`, `reused?` | Operador |
| POST `/api/execute` | `tenant`, `customer`, `case_id` | 200 `case_id`, `reused` | Operador |
| POST `/api/verify` | `tenant`, `customer`, `case_id` | 200 medição C06 | Operador |
| POST `/api/simulate-usage` | `tenant`, `customer`, `case_id` | 200 `{ "reused": false }` | Operador / Nimbus |
| OPTIONS nos caminhos acima | Origin, Access-Control-Request-Method, headers opcionais | 204, sem corpo | Sem sessão; não autentica |

GET `/api/view` admite apenas `tenant`, `customer`, `case_id`, uma vez cada,
com valor não vazio até 128 caracteres. `customer` exige `tenant`; `case_id` exige
ambos. Parâmetros desconhecidos, repetidos ou vazios são 400. Sem `tenant`, devolve
apenas os clientes das memberships da sessão; com `tenant` sem cliente, filtra essa
SaaS. Não existe paginação/pesquisa no servidor: o frontend filtra o resumo recebido.
Os identificadores nas mutações também têm de ser strings não vazias até 128 caracteres.
Na criação de cliente aplicam-se as regras mais restritas abaixo.

## Exemplos de pedidos e respostas

Exemplos fictícios. `<conta-privada>`, `<segredo-privado>` e `<id-do-caso>` são
marcadores, não credenciais ou IDs utilizáveis. Cookie e Origin são tratados pelo
browser; clientes HTTP de teste privados têm de fornecer a Origin HTTPS configurada.

### Login, registo e cliente

```http
POST /api/login
Content-Type: application/json

{"user":"<conta-privada>","password":"<segredo-privado>"}
```

200: `{"user":"<conta-privada>"}`. Não existe token no JSON nem endpoint de refresh.
Para saber sessão/permissões, fazer GET `/api/view`; 401 exige novo login.

```http
POST /api/customers
Content-Type: application/json

{"tenant":"atlas","customer":"cliente-exemplo","name":"Cliente fictício Exemplo","scenario":"blocked"}
```

201: `{"customer":"cliente-exemplo"}`. O cliente nasce sem observações.
ID: 1–64 caracteres `[a-z0-9][a-z0-9_-]*`, único por SaaS; nome com 1–120 caracteres
após trim. `scenario` é `blocked` (omissão) ou `operational`, exclusivamente uma
configuração fictícia inicial. As SaaS disponíveis continuam `atlas` e `nimbus`.
Cliente duplicado: 409, sem substituir o anterior.

GET `/api/view` pode devolver este corpo completo, antes de C01:

```json
{
  "user": "<conta-privada>",
  "memberships": [{"tenant":"atlas","role":"operator"}],
  "decision_mode": "simulator-v1",
  "environment_type": "sandbox",
  "registry": [{"tenant":"atlas","customer":"cliente-exemplo","name":"Cliente fictício Exemplo","case_id":null,"stage":null,"bucket":"observation"}],
  "counts": {"observation":1,"deterioration":0,"investigation":0,"intervention":0,"recovery":0,"exceptions":0,"stable":0}
}
```

GET `/api/view?tenant=atlas&customer=cliente-exemplo` acrescenta:

| Campo | Conteúdo |
| --- | --- |
| `role` | Permissão da sessão na SaaS selecionada |
| `environment` | `tenant`, `customer`, `name`, `state`, `revision`: estado **atual** |
| `case` | Caso selecionado/mais recente, ou null; inclui todos os snapshots C01–C06 |
| `cases` | Resumos `id`, `stage`, `created_at`, do mais recente para o mais antigo |
| `latest_case_id` | ID mais recente, ou null |
| `catalogue` | Mapa de ações autorizadas para a SaaS: label, tenant, cause, permission, effect |
| `history` | Todos os ciclos do cliente, ordenados por ID crescente: id, tenant, case_id, actor, stage, detail, created_at |

Acrescentar `&case_id=<id-do-caso>` consulta esse caso histórico. O `environment`
continua a ser o **atual**, não uma reconstrução histórica. Para mostrar a intervenção
antiga, usar `history` filtrado pelo mesmo `case_id`; `case_id: null` identifica os
registos de criação/ingestão do cliente. Nenhuma password, hash ou sessão é devolvida.

### Observações, evidências e decisão

```http
POST /api/observations
Content-Type: application/json

{"tenant":"atlas","customer":"cliente-exemplo","observations":[{"day":"2026-10-24","value":2,"source":"manual-sandbox"}]}
```

200: `{"batch_id":"<id-do-lote>","inserted":1,"reused":false}`.
São aceites 1–366 linhas por lote. `day`: ISO `AAAA-MM-DD`, até à data atual do
processo Python e no máximo 365 dias atrás; ajustar a data ilustrativa ao ensaio.
`value`: inteiro 0–1000000 (booleano não é inteiro válido). `source`: 1–64 caracteres
simples com o mesmo padrão do ID. Cada dia aparece uma vez por cliente.

O lote é atómico. Mesmo dia/valor/fonte é reaproveitado; outro valor/fonte no dia
existente é 409 e reverte o lote. Reenvio idêntico, mesmo reordenado, devolve
`inserted: 0, reused: true`; lote parcialmente sobreposto só conta novas linhas.
Novos dados invalidam ciclos ainda em C01–C04, preservando os snapshots antigos.

```http
POST /api/advance
Content-Type: application/json

{"tenant":"atlas","customer":"cliente-exemplo"}
```

200: `{"case_id":"<id-do-caso>"}`. Sem `case_id` (ou com null), inicia C01; se já
existe ciclo ativo, devolve o mesmo ID e `reused: true`. Depois de um ciclo terminal,
inicia outro ciclo, preservando o histórico e o estado atual do ambiente.

Para avançar **uma** etapa C02, C03 ou C04:

```json
{"tenant":"atlas","customer":"cliente-exemplo","case_id":"<id-do-caso>"}
```

Enviar para POST `/api/advance`. Resposta 200: `{"case_id":"<id-do-caso>"}`.
Reler `/api/view` após a resposta. Evidências e decisões vêm do servidor, nunca do
body do browser. Os campos de `case` ficam disponíveis gradualmente:

| Campo | Snapshot persistido |
| --- | --- |
| `observation` | sufficient, rows (id/day/value/source), metric, window, rule |
| `detection` | status, baseline/recent/drop/evidence_ids; ou insufficient_data + reason |
| `investigation` | state, revision, observation_ids, metric, cause, sha256 |
| `decision` | mode, is_real_ai=false, action ou null, classification, reason, evidence_hash |
| `verification` | null até C06; última medição do caso depois de C06 |

C02 exige 14 dias completos e comparáveis da mesma fonte, sete anteriores contra
sete recentes, baseline positivo e queda ≥ 30%. O hash identifica o snapshot de
investigação; não certifica uma fonte externa. Não existe GET autónomo de observações
brutas: as evidências consultáveis são os snapshots criados por C01–C03 e o histórico.

### Intervenção e verificação

O mesmo body com `tenant`, `customer`, `case_id` é usado nas três operações seguintes:

- POST `/api/execute`: 200 `{"case_id":"<id-do-caso>","reused":false}`.
  C05 escolhe a ação da decisão persistida, valida catálogo/revisão e grava os efeitos
  com a execução e o histórico numa transação. Repetição: `reused: true`, sem novos
  efeitos. `history` com `stage: "C05"` contém `action`, `before`, `after`, `execution_key`.
- POST `/api/verify`: relê o ambiente e devolve a medição abaixo. É repetível, mas
  cada chamada acrescenta um registo C06. Um ciclo histórico com outro mais recente
  pode ser consultado, mas não receber novas verificações.
- POST `/api/simulate-usage`: só Nimbus depois da intervenção; cria quatro relatórios
  explicitamente simulados, sem chamar SaaS externos. 200 `{"reused":false}`; repetição
  `{"reused":true}`. Não é um endpoint de ingestão real de utilização.

Exemplo completo de uma resposta C06 **operacional apenas**, no sandbox:

```json
{
  "operational_recovered": true,
  "value_recovered": false,
  "outcomes_before": 0,
  "outcomes_after": 0,
  "gained": 0,
  "value_target": 4,
  "probe": "Percurso de primeiro valor disponível.",
  "measured_at": "2026-10-24T12:00:00+00:00",
  "scope": "sandbox",
  "reason": "Recuperação de valor exige pelo menos 4 novos resultados persistidos; disponibilidade técnica por si só não prova valor."
}
```

Não apresentar `operational_recovered` como recuperação de valor ou retenção real.
`history` C06 preserva medições anteriores e acrescenta a revisão do ambiente à
medição. C05/C06 não aceitam action, outcome, evidence, role ou user fornecidos pelo cliente.

## Estados, ações e reenvios

| `case.stage` | Próxima operação possível |
| --- | --- |
| sem caso | advance sem case_id → observed |
| observed | advance com case_id → detected, healthy ou insufficient_data |
| detected | advance com case_id → investigated |
| investigated | advance com case_id → decided ou needs_review |
| decided | execute → executed |
| executed | verify → verified; Nimbus pode simular uso posterior |
| verified | verificar novamente, simular uso Nimbus se aplicável, ou iniciar novo ciclo |
| healthy / insufficient_data / needs_review / stale_evidence | consultar; corrigir contexto/dados quando possível e iniciar novo ciclo |

O servidor autoriza cada pedido. Estados na UI não conferem permissão. Os grupos
`bucket` referem-se ao ciclo **mais recente**: observation, deterioration,
investigation, intervention, recovery, exceptions, stable. Operação recuperada sem
valor continua em intervention; healthy é stable, não recovery.

Não fazer retry cego de `/api/advance`: com case_id cada chamada avança uma etapa,
sem case_id um novo ciclo pode ser criado depois de um terminal. Serializar os
pedidos por cliente, bloquear cliques simultâneos e reler o estado após timeout.
`verify` também não é idempotente no histórico. `execute`, reenvios de observações
e o lote de `simulate-usage` não repetem os seus efeitos; verificar `reused`.

## Erros e tratamento no frontend

```json
{"error":"Sem permissão para esta SaaS ou operação.","code":"forbidden"}
```

`code` é estável; `error` é texto humano e não deve orientar lógica por comparação
literal. A adição de `code` preserva o campo `error` do frontend atual. Logs HTTP omitem
queries, headers e bodies; falhas internas não devolvem nem registam o texto da exceção.

| HTTP | code | Tratamento |
| --- | --- | --- |
| 400 | invalid_request | Rever formato, campos, IDs, datas ou escopo; não repetir igual |
| 401 | unauthenticated | Credencial inválida ou sessão ausente/expirada; voltar ao login |
| 403 | forbidden | Verificar origem e membership/role; não contornar no cliente |
| 404 | not_found | Recurso/caso não existe no escopo; não procurar noutro tenant |
| 405 | method_not_allowed | Usar o método indicado em Allow |
| 409 | conflict | Reler caso/ambiente; pode ser estado, dados em conflito, evidência desatualizada ou caso histórico |
| 413 | payload_too_large | Dividir/reduzir o lote para ≤ 65536 bytes |
| 415 | unsupported_media_type | Enviar application/json |
| 421 | misdirected_request | Host HTTPS diferente do configurado |
| 429 | rate_limited | Aguardar Retry-After (60 segundos) antes de novo login |
| 500 | internal_error | Sem detalhes internos; não repetir mutações cegamente |
| 503 | unavailable | Pré-visualização expirada ou configuração privada indisponível |

Pedidos HTTP malformados rejeitados antes de chegar ao handler podem produzir
erros do servidor HTTP padrão. HEAD não devolve corpo, conforme o protocolo.
Um bloqueio CORS/TLS aparece no browser como falha de rede, sem JSON legível;
não o interpretar como uma decisão do produto nem substituir por sucesso simulado.

## Frontend separado e CORS opt-in

Opção preferida: mesma origem HTTPS, com `/api/*` encaminhado ao Python pelo servidor
responsável pelo alojamento. Não exige CORS e mantém cookies Strict. Não existe
esse alojamento nem proxy implementado nesta missão.

Para um frontend HTTPS **same-site**, mas noutra origem (por exemplo subdomínios
sob o mesmo domínio controlado), o responsável pode acrescentar à operação privada:

```text
python3 -m centerway.preview serve [os mesmos argumentos privados de TLS/base] \
  --frontend-origin https://app.example.invalid
```

`.invalid` é marcador; não é uma configuração ativa. O argumento pode repetir-se.
CORS está desativado por omissão e é recusado no laboratório HTTP. Não aceita `*`,
HTTP, caminhos, credenciais no URL ou correspondência por sufixo. O Host do backend
continua fixo, o TLS obrigatório e a expiração da pré-visualização mantém-se.

Preflight: Origin exata permitida, método exato do endpoint, apenas header Content-Type.
Resposta 204 sem corpo, Access-Control-Allow-Origin exata, Allow-Credentials: true,
Vary: Origin e cache de preflight de 300 s. Não exige sessão e não altera dados.
Respostas autorizadas, incluindo 401/403/429, expõem apenas Retry-After e a versão
além dos headers comuns. Set-Cookie continua inacessível ao JavaScript.

No futuro cliente, usar `fetch` com `credentials: "include"`, URL base sem segredos
e os IDs capturados no momento da operação. Cookies são geridos pelo browser:

```js
const response = await fetch(`${API_BASE}/api/view?${new URLSearchParams({tenant, customer})}`, {
  credentials: "include"
});
const body = await response.json();
if (!response.ok) throw new Error(`${body.code}: ${body.error}`);
```

CORS **não** torna cookies Strict cross-site. O domínio padrão de um frontend
externo pode ser outro site; esses pedidos continuam bloqueados e cookies de
terceiros podem ser recusados pelo browser. Nessa situação, usar a mesma origem
por um proxy controlado ou planear uma revisão de autenticação separada. Não mudar
para SameSite=None, guardar tokens em JS ou abrir uma origem genérica como atalho.
Nenhuma ligação ao Lovable foi criada ou verificada aqui.

Ao trocar SaaS/cliente/logout, limpar os dados desse contexto e ignorar respostas
atrasadas de outro escopo. Consultar memberships no servidor; nunca confiar numa
role local. CORS não substitui sessões nem permissões.

## Verificações e limites

```sh
python3 -m pip install -r tests/requirements.txt  # jsonschema, apenas desenvolvimento
python3 -m unittest discover -s tests -v
npm ci --ignore-scripts
npx playwright install chromium
npm run test:browser
npm run test:private-browser
npm run test:cors-browser
```

Schemas, exemplos, referências e inventário dos endpoints são verificados; os
corpos HTTP reais dos dois percursos, exceções e histórico são validados contra o
OpenAPI. Os testes mantêm permissões, isolamento, rollback, execução única e 150
clientes. CORS é testado com HTTPS verificado em Python e com duas origens locais
same-site no Chromium, incluindo preflight, cookies, logout, erros legíveis e
origem não autorizada. Não é uma integração com um serviço/interface externo.

O teste Chromium usa exceção de certificado apenas no contexto descartável local;
a validação TLS do cliente Python confia explicitamente na CA de teste. Não prova
certificado público. O runtime continua sem dependências externas; jsonschema é
uma dependência de testes. Não há OAuth/refresh, paginação de API, notificações,
conectores, IA real, alojamento ou deploy. Os limites funcionais da Missão 02 e o
impedimento de publicação do PR #32 continuam válidos.
