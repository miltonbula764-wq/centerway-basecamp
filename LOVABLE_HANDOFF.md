# CENTERWAY L03-PREP / B01 — contrato demonstrativo para Lovable

Issue [#60](https://github.com/miltonbula764-wq/centerway-basecamp/issues/60).
Base obrigatória PR #59, `eeae52ef4d1fbf3bdc524299203098fe75f6badd`.
Esta entrega prepara integração **sem alterar a Lovable ou publicar a API**.
O L01Transport, journey-mapper, mocks e ecrãs L02.2 são contexto fornecido pela issue;
a sua implementação externa não foi inspecionada, executada ou alterada aqui.
Não se declara que Lovable-hosted consegue comunicar com o backend.

## Artefactos e formato exato

- Fonte HTTP: [OpenAPI L01/C02](recovery-mvp/api/openapi.json), versão `c02-v1`,
  e [README API](recovery-mvp/api/README.md). Não há uma segunda API nem alterações
  ao OpenAPI original.
- Fonte semântica: [F06](recovery-mvp/ORCHESTRATION.md), [F04](recovery-mvp/INTERVENTION.md),
  [F05](recovery-mvp/RECOVERY.md), [F03](recovery-mvp/INVESTIGATION.md) e demais contratos
  F01/F02/F03.1 existentes. A UI não deve recalcular esses motores.
- Exemplos canónicos: [capture.json](recovery-mvp/integration/fixtures/v1/capture.json),
  `fixture_version=l03-prep-v1`, `synthetic_only=true`, `source=real-local-c03-https-api`.
  Os hashes `contracts` identificam OpenAPI, documentos semânticos e cenário C03 usados.
- [bundle.schema.json](recovery-mvp/integration/fixtures/v1/bundle.schema.json) valida
  o pacote de handoff, **não substitui** os schemas HTTP do OpenAPI. contracts.py
  valida as respostas/exemplos contra o OpenAPI real e acrescenta gates de integração
  onde o OpenAPI é genérico. Comparação com nova captura exige campos/valores exatos,
  exceto os placeholders tipados e coleções explicitamente normalizadas abaixo.
- [Matriz dos 71 casos](recovery-mvp/integration/fixtures/v1/CASE_MATRIX.md): identifica
  o resultado esperado/PASS de cada caso, incluindo recusas e falhas. O resultado
  verificável é o teste/CI aprovado no SHA entregue; não basta ler a coluna PASS.

Cada elemento de `cases` tem **somente** esta estrutura; localizar pelo `id`, não por
um índice numérico fixo. `request.json` é um pedido realmente enviado (sanitizado),
`response.json` é a resposta efetivamente recebida (sanitizada):

```json
{
  "id": "authentication-required-401",
  "actor": "alice",
  "request": {
    "method": "GET",
    "path": "/v1/tenants/a1000000-0000-0000-0000-000000000001/clients",
    "json": null
  },
  "response": {
    "status": 401,
    "json": {"error": {"code": "authentication_required"}}
  },
  "transport_error": null
}
```

Este exemplo é uma transcrição do caso real exportado, não uma resposta construída à
mão. Para consumir offline, usar `case.response.status` e **apenas**
`case.response.json` como corpo de transporte. Não enviar o envelope de handoff inteiro
à API. Não substituir dados existentes nos motores por estes exemplos. Não existe
stub HTTP novo: os JSON são suficientes para testes de mapeamento offline sem rede.
Os snapshots completos de journey estão no pacote; não foram reduzidos a resumos.

## Sanitização, rastreabilidade e ausência de segredos

Todas as respostas vêm de uma execução local nova da C03, com Caddy real → Gunicorn TLS
→ PostgreSQL 17 verify-full e identidades reais **de demonstração**. CaptureScenario
reutiliza o Scenario C03 intacto; acrescenta checkpoints e testes. Não simula a resposta,
a base, o motor ou a autorização. Os números de input são exclusivamente fixtures
sintéticas, não resultados empresariais reais.

Antes de exportar, substituem-se valores efémeros por placeholders com tipos válidos:

| Dado | Representação sanitizada | Regra |
|---|---|---|
| Password de login | `<PASSWORD:alice>` (ou outra conta de demonstração) | String writeOnly; nunca password real |
| access_token 201 | `<SESSION:alice:1>` (conta e ordinal de login) | String tipada; **não é Bearer utilizável** |
| UUID gerado | `00000000-0000-4000-8000-000000000001`, etc. | UUID válido; bindings bijetivos preservam referências |
| UUID fixo da C03 | Mantido | Identifica apenas empresas/clientes/fontes sintéticos conhecidos |
| Timestamps dinâmicos | Datas exemplificativas de 2025 | Janelas/cronologia sanitizadas; não são datas de execução real |
| Datas de negócio fixas da provisão C03 | Datas sintéticas de 2024 mantidas | Input conhecido e não efémero |
| input_hash / request_key F02 | 64 hexadecimais tipados numerados | Identidade/repetição preservada; não são digests recalculáveis |
| content_sha256 de evidência | Mantido | Digest declarado da fixture sintética; não certifica documento externo |

Não há headers exportados. Não há DSNs, passwords de base, hashes de password, tokens
reais, cookies, chaves privadas ou PII. O exportador recusa campos/padrões de segredo,
credenciais conhecidas fora das posições substituídas, token inesperado e email. O teste
verifica também que UUIDs/timestamps/fingerprints efémeros não ficaram no pacote.
Alice/reviewer/reader/bob são identidades sintéticas fixas, não pessoas reais.

A normalização de tempo usa as janelas declaradas dos pedidos e a execução F04 recebida
para preservar intervalos, durações iguais, contiguidade e posição anterior/posterior.
Os metadados de relógio são distribuídos por ordem entre essas âncoras, removendo jitter.
A comparação vincula cada timestamp/UUID/fingerprint variável ao mesmo símbolo em todos
os casos e rejeita referências partidas ou símbolos colapsados. **Janelas de negócio,
versões, números, bools, nulls, estados, scopes e campos são exatos**; não há fallback
para um estado inventado. O instante exato e o fingerprint original não são exportados.
Não usar o pacote para recalcular hashes, reproduzir temporalmente o motor ou reenviar
pedidos: os exemplos são válidos como formatos/estados de transporte, não credenciais
ou comandos executáveis contra um ambiente real.

São ordenadas canonicamente apenas coleções de registos identificados, originalmente
ordenadas por UUID efémero: contracts, sources, evidence_history, investigations,
work_items, factors, evidence, verifications e recovery_plans. Cada elemento completo
e cada referência/revisão é preservado. Não se reordena paginação, periods, operations,
decisions, executions ou listas de referências. Uma mudança de tipo, campo ou estado
faz falhar o contrato/golden; nunca se descarta um campo desconhecido para fazer passar.

`demo=false` nas respostas C03 ativa os guardas HTTPS/PG, conforme C01/C03. **Não
significa dados reais.** O consumidor offline deve mostrar a etiqueta SYNTHETIC com
base neste pacote explicitamente sintético; não declarar produção pelo booleano demo.

## Endpoints → dados → apresentação futura

As paths abaixo são da API existente. Frontend nunca recebe principal/DSN para abrir
uma ligação PostgreSQL; principal na sessão é informação confirmada pelo servidor.
`tenant`/`client` vêm das permissões e seleção atuais; UUID conhecido não concede acesso.

| Método/rota | Corpo de sucesso | Uso futuro na UI |
|---|---|---|
| POST /v1/sessions | 201: access_token, token_type, expires_in, demo | Iniciar sessão após HTTPS real; Bearer só em memória; placeholders aqui apenas offline |
| GET /v1/session | username, principal, clients, operations, company_tenants | Confirmar sessão e scopes; não mostra nomes de clientes |
| DELETE /v1/session | 204 sem JSON | Limpar sessão e dados visíveis; não tentar interpretar JSON vazio |
| GET /v1/tenants/{tenant}/clients | data=[{client_id,display_name}], next_cursor, demo | Lista de clientes autorizados e nomes persistidos; renderizar texto, nunca HTML |
| GET /v1/tenants/{tenant}/clients/{client}/journey | data=projeção F06 f06-v1, demo | Mostrar percurso, evidências, versões, lacunas e histórico sem inferir estado global |
| POST /v1/tenants/{tenant}/clients/{client}/operations | data=recibo F06, demo | Acompanhar resultado persistido; examinar os três níveis abaixo |

Listagem: default limit=50, mínimo 1, máximo 100, UUID crescente, cursor exclusivo;
passar `next_cursor` como `after` sem o alterar e parar em null. `data=[]` não é erro.
Não há total nem snapshot entre pedidos. Não usar comprimento da primeira página como
total. Uma empresa não autorizada dá 403 sem provar existência. Falta de autorização
por cliente não é sinónimo de cliente eliminado.

A C03 original dá apenas um cliente da A a reader. Para capturar duas páginas reais,
**o teste concede explicitamente A2 a reader na configuração privada descartável**,
reinicia a API e prova que a sessão anterior fica inválida. Essa concessão não está
na C03 entregue, não é feita via HTTP e não muda permissões do produto. Os casos
`reader-denied-client-403` e `directory-reader` são anteriores à concessão;
`session-reader-2` e as páginas são posteriores. Não combinar esses scopes como se
fossem um único estado simultâneo de permissões. Bob continua isolado na empresa B.

## HTTP, recibo e resultado de negócio são três níveis distintos

1. `case.response.status`: transporte HTTP. 200 não prova valor, autorização atual ou
   execução. `response=null` com transport_error não é um HTTP 503 inventado.
2. `body.data.status`, quando data é um recibo F06: apenas `completed` ou `error`.
   Não criar recibo `blocked`. Um recibo error contém result sanitizado com sqlstate e
   code=engine_rejected. Repetir a sua chave devolve esse erro, sem reexecutar.
3. `body.data.result`: resultado da operação. Na F04, `status=blocked|executed|failed`;
   em run F03/F05 há outro nível `.result`, onde está o estado semântico do relatório.

Exemplos reais para consultar no pacote, sem construir objetos alternativos:

| Caso | Pointers dentro de response.json | Leitura correta |
|---|---|---|
| intervene-01 | /data/status=completed; /data/result/status=blocked | Pedido avaliado; ação recusada por incerteza, sem execução |
| intervene-02 | /data/status=completed; /data/result/status=executed | Flag sintético executado; ainda não demonstra recuperação |
| engine-error-receipt-422 | /data/status=error; /data/result/code=engine_rejected | Erro persistido do motor; não usar mensagens SQL como texto de UI |
| invalid-envelope-422 | /error/code=invalid_parameters | Rejeição HTTP antes do motor, sem recibo |
| evaluate_recovery-01 | /data/result/result/status=resultado_inconclusivo | Dados posteriores em falta; melhoria null, não zero/false |
| evaluate_recovery-02 | /data/result/result/status=recuperacao_completa | Mínimo numérico restaurado nos dados sintéticos; causalidade não estabelecida |

Uma recuperação completa não exige atingir o target se o mínimo for inferior.
Separar `execution_succeeded`, `improvement_observed`, `minimum_met`, `baseline_met`
e `status`. Null permanece desconhecido. Conservar
`causal_attribution=not_established`, `independent_verification=not_established` e
`causal_inference=not_performed` onde existirem; não ocultar esses limites na UI.
Quality=verified e registo por login separado não são verificação independente/humana.

## Journey f06-v1 e lacunas

Validar o envelope e a versão antes de mapear. Campos de data: tenant_id, client_id,
contract_version, authorization_basis, causal_attribution, contracts, sources,
evidence_history, detections, investigations, decisions, executions, recovery_plans,
operations e work_items. Não substituir recovery_plans por um campo inventado recovery.
Preservar objetos completos e nulls; qualquer inconsistência deve bloquear o mapeamento
em testes e gerar estado de erro de contrato na futura interface, sem inferir sucesso.

- Contratos: objetivo, resultado esperado, indicador, baseline, mínimo e período são
  declarações persistidas, nunca inferidas de utilização.
- Deteções: result.state é o último período selecionado; periods e comparação são
  separados de sustained_deterioration (true/false/null). Piora não é causa.
- Investigações: result diferencia observed_facts, hypotheses, contradictions,
  missing_information, excluded_evidence e referências com versões. Hipótese não é facto.
- Recovery plans: os campos result, evidence_snapshot, report_id e as_of da projeção
  refletem a última avaliação persistida. Histórico dos recibos/versões continua presente.
- work_items são orientação **histórica**. `review_execution_blocker` pode coexistir
  com recuperação posterior; não apagar nem interpretar como autorização atual.
  `authorization_basis=engine_checks_required_at_execution` exige revalidação do motor.
  operations na sessão é uma permissão de transporte, não uma política F04.

Checkpoints capturados: inicial; contrato; deteção; investigação sem fatores; relatório
com lacunas; recusa F04; relatório sustentado; execução; recuperação inconclusiva;
recuperação completa; journey com recibo de erro. Os snapshots e revisões não foram
reescritos para demonstrar um sucesso. O replay F06 produz a mesma decisão e a base
confirma uma execução/um evento de recibo, sem duplicação.

## HTTP e falhas → estado de interface

| Resultado | Tratamento futuro |
|---|---|
| 201 | Sessão criada; usar token real só quando houver HTTPS externo autorizado |
| 200 | Interpretar corpo/versão; nunca promover automaticamente a sucesso de negócio |
| 204 | Sem corpo; sessão revogada |
| 401 | Pedir autenticação e limpar sessão/dados de empresa; não renovar silenciosamente |
| 403 | Mostrar acesso/origem/operação recusados; não tentar outra empresa para enumerar |
| 404 | Rota ou cliente visível ausente segundo code; fixture cobre rota desconhecida, não prova eliminação de cliente |
| 409 | Conflito de identidade/conteúdo da chave; não gerar intervenção substituta automaticamente |
| 422 | Pedido/motor rejeitado; distinguir corpo error de recibo data.status=error |
| 503 | Indisponibilidade da base/API/gateway; preservar chave de comandos com resultado incerto |
| Sem resposta HTTP | Falha de rede/TLS/CORS no futuro; fixture prova connection_refused com gateway parado, não todas essas causas |

L01 também documenta 400/413/415/429/500: não há novos exemplos desses estados nesta
captura. Não transformar status ausente/desconhecido em recuperação ou lista vazia.
CORS não autentica, e um erro CORS pode chegar ao browser apenas como falha de rede.
OPTIONS e origens exatas mantêm a validação C01/L01 já coberta pela regressão anterior;
a captura v1 não exporta preflights, headers ou provas de CORS Lovable-hosted.

## Repetição, validação e gates de aceitação

Requisitos: Docker local, Python 3.12/venv, OpenSSL e Bash, como na C03. Nenhuma conta
cloud, cartão, domínio ou credencial externa. Da raiz:

```sh
./recovery-mvp/integration/test.sh
```

Executa 83 regressões inalteradas (60 motores + 11 HTTP + oito HTTPS + quatro C03),
mais sete testes L03-PREP: **90 testes**, com **71 casos de transporte dentro da nova
suite**, não 71 testes adicionais. --handoff-only executa apenas os sete novos testes.
A verificação date-time é explícita, incluindo datas impossíveis/sem fuso, sem
depender de extras opcionais do JSON Schema. A validação de schemas/fixtures estáticos não faz rede; a comparação live usa somente
o C03 loopback. Pode haver downloads de dependências/imagens no setup, não tráfego à
Lovable ou a um backend externo.

Gates: nova execução corresponde às fixtures; OpenAPI/versões/shape válidos; identidade
alice/reviewer/reader/bob; paginação e status esperados; recibos/gaps/recuperação não
causal; idempotência/auditoria/RLS empresarial; sanitização e rejeição de drift,
referências partidas, credenciais, campos desconhecidos e null→zero/false. A matriz
lista cada caso. Um único erro faz falhar a suite; não se atualizam goldens no CI.

Para regenerar explicitamente, após revisão e nova execução real:

```sh
./recovery-mvp/integration/test.sh --generate
```

Gera capture.json e CASE_MATRIX.md sanitizados; não editar respostas manualmente.
Rever o diff e executar os testes antes de versionar. Mudança semântica exige nova
versão do pacote/normalização e decisão explícita; não remover gates para aceitar drift.
Segredos só existem no estado privado temporário C03, removido após os testes; o
exportador não grava raw HTTP. Nenhum workflow carrega esse estado como artefacto/cache.

O workflow novo recovery-mvp-handoff.yml verifica preservação integral de motores,
API e C01/C02/C03 e repete a captura/schema/comparação; os três workflows anteriores
ficam intactos. Resultados locais e remotos devem ser confirmados no mesmo commit.
Não confundir CI aprovado com prontidão para produção.

## O que continua bloqueado até uma futura missão L03

**Nenhuma chamada de rede deve ser ativada na Lovable nesta missão**, incluindo health,
login, sessão, diretório, journey e operações. api.getcenterway.com continua apenas
hostname futuro: não foi consultado, configurado, publicado ou comprovado. Não apontar
uma UI hosted para localhost, fixtures, IP provisório ou HTTP; localhost pertence ao
dispositivo do utilizador e o CA local não é uma autoridade pública.

L03 exige uma missão posterior autorizada para host/HTTPS real, DNS/origens exatas,
certificado público e verificação de rede externa; depois teste de browser hosted com
contas sintéticas e validação do transporte/mapper real. Até lá, somente consumo offline
destas fixtures para preparar mapeamento; sem ativar login, ações reais ou políticas.
Nunca pôr DSNs, passwords PG, credenciais administrativas ou tokens em frontend.

Limitações mantidas: exemplos não são exaustivos de todas as combinações F01–F06;
sem frontend/stub novo, teste Lovable-hosted, cloud/ARM, DNS, publicação, emissão de TLS
público, prova causal/independente, dados reais ou intervenções reais. Sem certificação
externa de segurança. Dados inconsistentes bloqueiam os testes; um eventual defeito
no backend deve ser reportado para correção separada, sem mudar permissões nesta missão.
