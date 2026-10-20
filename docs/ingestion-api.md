# API de recolha C01 · v1

A API aceita observações de indicadores **já aprovados**, para clientes previamente registados na empresa. Não cria clientes, indicadores, objetivos, avaliações ou casos. C02–C10 continuam a exigir as operações humanas previstas nos seus contratos.

## Preparar a integração

Um administrador abre **Configurações → Integrações · API C01**. Define nome, **fonte exata** e expiração futura (até 365 dias). Copia o segredo apresentado uma única vez e guarda-o no gestor de segredos do sistema remetente. Não coloque a chave em aplicações públicas, URLs, repositórios ou logs.

Só se guarda SHA-256 de um segredo aleatório de 256 bits. Não é uma palavra-passe humana: hashing rápido de alta entropia permite comparação sem recuperar a chave. O identificador público da credencial não autentica pedidos. A chave não é um JWT Supabase e não permite consultas gerais nem administração do banco. A empresa vem exclusivamente da credencial validada.

O segredo desaparece ao sair, trocar de empresa, terminar sessão ou recarregar. A lista mostra apenas metadados, última utilização e estado HTTP. Se perder a resposta de criação, repita o pedido com o mesmo identificador: recebe o ID, **nunca o segredo novamente**. Revogue e crie outra chave se necessário. A interface mantém a identidade do pedido enquanto os campos não mudam.

Esta versão não envia emails nem chama sistemas externos. O endpoint necessita da instalação descrita abaixo; criar uma chave não instala uma função.

## Enviar uma medição ou um lote

Endpoint após instalação: `https://SEU-PROJETO.supabase.co/functions/v1/ingest-v1/observations`.

```http
POST /functions/v1/ingest-v1/observations HTTP/1.1
Host: SEU-PROJETO.supabase.co
Authorization: Bearer SEGREDO_SINTETICO_SUBSTITUIR
Idempotency-Key: 56d63d89-b1ac-47ae-a4ca-a36cf6994931
Content-Type: application/json

{
  "profile_id": "b5f1eed0-0a9b-441e-a1c9-1a477f266c22",
  "source": "synthetic-atlas",
  "coverage": {
    "start": "2026-10-01T00:00:00Z",
    "end": "2026-10-08T00:00:00Z",
    "declared": true
  },
  "rows": [{
    "line": 1,
    "subject_external_ref": "cliente-sintetico-001",
    "indicator_key": "cycle_minutes",
    "observed_at": "2026-10-07T12:00:00Z",
    "value_numeric": "50",
    "unit": "min",
    "idempotency_key": "atlas-measurement-0001"
  }]
}
```

Os IDs são fictícios: use o ID do perfil aprovado e a referência externa real do **cliente sintético** no seu ambiente de teste. Não há campo `tenant_id`: campos desconhecidos são rejeitados. Para enviar um lote, acrescente objetos ao array `rows`.

| Campo | Contrato |
| --- | --- |
| `profile_id` | UUID da versão atualmente aprovada. Versão desatualizada é rejeitada. |
| `source` | Fonte declarada, igual à fonte vinculada à credencial, após remover espaços nas extremidades. |
| `coverage` | `start` e `end` ISO 8601 com fuso; intervalo `[start,end)`, end > start; `declared: true`. Declaração não prova completude. |
| `subject_external_ref` | Referência previamente registada nesta empresa; não identifica clientes de outras empresas. |
| `indicator_key` | Indicador do perfil aprovado; respetivos tipo e unidade são obrigatoriamente respeitados. |
| `observed_at` | ISO 8601 com fuso, dentro da cobertura e sem data futura, segundo C01. |
| `value_numeric` / `value_text` | Um valor do tipo definido pelo indicador. Numérico finito; recomenda-se string decimal para preservar precisão. Para texto use apenas `value_text`. |
| `unit` | Unidade aprovada, comparação segundo C01. |
| `idempotency_key` | Identidade estável da observação (1–300 caracteres segundo C01); não a regenere ao repetir uma medição. |
| `corrects_observation_id` | UUID opcional da observação anterior; correção é uma nova linha, com nova chave, mesmo cliente, indicador compatível, fonte e instante. Sem ramificações. |
| `line` | Número opcional para identificar erros; C01 usa a posição quando não é fornecido. |

Uma medição textual, para um indicador context/text aprovado, seria:

```json
{"subject_external_ref":"cliente-sintetico-001","indicator_key":"workflow_fact","observed_at":"2026-10-07T12:00:00Z","value_text":"integração desativada — informação sintética","unit":"estado","idempotency_key":"atlas-fact-0001"}
```

### Respostas e recuperação

Sucesso HTTP 200:

```json
{"batch_id":"00000000-0000-4000-8000-000000000001","status":"completed","row_count":1,"inserted":1,"duplicates":0,"rejected":0,"errors":[],"code":"completed","request_id":"00000000-0000-4000-8000-000000000002"}
```

A resposta inclui ainda os campos históricos do contrato C01 (perfil/versão). Erros de linhas usam o mesmo formato C01: `errors: [{"line":1,"errors":["unknown_indicator"]}]` — consulte os códigos efetivos em `src/lib/ingest.ts`. Um lote inválido não insere parcialmente observações: guarda um lote falhado quando o motor C01 chegou à validação das linhas. Erros de envelope/perfil/limites podem não ter `batch_id`; ficam no histórico HTTP quando a credencial é reconhecida.

| HTTP | Ação |
| --- | --- |
| 200 | Lote concluído ou repetição do resultado original. Duplicados não criam novas observações. |
| 400 | Envelope, perfil, cobertura, fonte ou limites de linhas inválidos; ou falta UUID Idempotency-Key. Corrija o pedido. |
| 401 | Chave inválida, expirada ou revogada. Não distingue existência de credenciais. |
| 404 / 405 / 415 | Caminho, método ou tipo de conteúdo inválido. Apenas POST JSON sem compressão. |
| 409 | Mesmo identificador de pedido com outro conteúdo, ou conflito de identidade de observação no C01. Não sobrescreve dados. |
| 413 | Pedido demasiado grande. Divida o lote. |
| 422 | Erros C01 por linha (cliente, indicador, unidade, valor, data, correção). Consulte lote e códigos. |
| 429 | Quota excedida. Aguarde `Retry-After` segundos e repita o mesmo pedido. |
| 503 | Serviço indisponível/timeout (30s). Resultado pode ter sido confirmado no servidor; repita os mesmos identificadores, sem gerar novas identidades. |

### Idempotência, concorrência e limites

* **Pedido:** `Idempotency-Key` obrigatório, UUID, âmbito da empresa. Mesmo JSON canónico (ordem de propriedades irrelevante), mesmo resultado/lote, inclusive após rotação na mesma fonte. Alterar conteúdo dá 409; para corrigir um lote falhado use novo UUID. Falhas de envelope reconhecidas também são memorizadas. A chave deve continuar válida mesmo para repetir um resultado.
* **Observação:** `rows[].idempotency_key`, âmbito da empresa, regras existentes C01. CSV e API partilham o mesmo hash de identidade; não se duplicam por mudar de transporte. Correções mantêm o original imutável. O contrato interno histórico continua denominado `centerway_csv_v1`; o transporte/proveniência API é identificado separadamente, sem reescrever hashes históricos.
* Até **1000 linhas**, **2 000 000 bytes** no corpo e na representação JSONB validada no banco (espaços de canonicalização podem aumentar o tamanho), **30 pedidos/minuto UTC por credencial**. Repetições e pedidos inválidos que chegam ao RPC contam. A quota é técnica desta versão, não uma prioridade comercial ou SLA. O limite é transacional e aplica-se também a chamadas diretas ao RPC público, sem possibilidade de o contornar usando JWT humano. Pedidos rejeitados antes do RPC não consomem quota. A plataforma continua responsável por proteção volumétrica geral; esta versão não é um WAF global.
* O mesmo bloqueio da empresa serializa administração, revogação, rotação e importação. Uma revogação impede pedidos autorizados **após** essa transação; não desfaz um pedido já autorizado e confirmado antes dela.
* Chaves desconhecidas não criam histórico atribuível a uma empresa; respostas HTTP de erro emitem somente status e request_id nos logs da função. Chaves reconhecidas geram eventos privados para administradores. Recusas por quota/expiração/revogação são agregadas a um evento/minuto/chave para limitar volume. Não ative logging de Authorization, corpos RPC ou segredos na infraestrutura.

### Revogação e rotação

Revogue na lista para retirar acesso. Para rodar, crie nova credencial indicando o ID anterior e **a mesma fonte**; o servidor cria a nova chave e revoga a anterior atomicamente. Guarde a nova chave imediatamente e atualize o remetente. Não há período de sobreposição automático. Os lotes antigos conservam a identidade da credencial original e permanecem legíveis pelo percurso operacional.

## Instalação posterior no projeto existente (não executada nesta missão)

1. Rever e integrar o PR por decisão humana. Preservar 0000–0017, journal e snapshots; aplicar **somente 0018** pelo processo de migrações gerido da equipa. A migração não copia dados nem altera estados históricos. Confere a equivalência exata do motor C01 instalado, incluindo o reforço de correções da 0004; aborta atomicamente se detetar divergência.
2. Num terminal da equipa com Supabase CLI autenticado e permissão para o projeto correto, executar:
   ```sh
   supabase functions deploy ingest-v1 --project-ref SEU_PROJECT_REF --no-verify-jwt
   ```
   O ficheiro `supabase/config.toml` já define `verify_jwt=false` especificamente para esta função, pois o Bearer é uma credencial de integração, não um JWT de utilizador. **Não desative autenticação das outras funções.**
3. O runtime Edge fornece `SUPABASE_URL` e `SUPABASE_ANON_KEY` públicos. O código usa apenas estes dois valores; **não configurar nem usar service_role nesta função**. Não é necessário alterar variáveis privadas do frontend nem instalar servidor Node/Nitro novo. O gateway Supabase fornece HTTPS para a função.
4. Um administrador cria uma credencial para dados sintéticos na aplicação, envia um pedido ao URL HTTPS do projeto e confirma o lote em Dados. Verificar RLS, revogação e logs sem segredos na instalação real antes de uso continuado.

Esta missão não acedeu à Lovable, não aplicou migrações hospedadas, não publicou o endpoint e não verificou o URL hospedado. Código compatível com Supabase Edge/Deno; os testes HTTP locais executam exatamente o mesmo handler com Bun e TLS próprio. A infraestrutura, limites e disponibilidade efetivos da função hospedada dependem da instalação e validação posteriores pela equipa.

## Reproduzir a validação descartável

Pré-requisitos: Docker, PostgreSQL client (`psql`), Bun 1.3, Node 22, OpenSSL, Chromium/Playwright. Nunca definir credenciais hospedadas.

```sh
python3 scripts/mvp/start-local.py --api
```

O script mostra a pasta isolada criada, instala **todas** as migrações nessa base tmpfs e inicia a aplicação em 127.0.0.1:5173. Noutro terminal, nessa pasta, executar:

```sh
export PGHOST=127.0.0.1 PGDATABASE=cw_e2e PGUSER=postgres CW_LOCAL_MVP=1
python3 e2e/ingestion-api.py
```

O teste inicia automaticamente o endpoint **HTTPS local** em 127.0.0.1:54443, confia exclusivamente no certificado descartável gerado e termina o servidor ao concluir. Exige fixtures operacionais e só aceita a base descartável rotulada ou o job CI GitHub-hosted. Todas as contas e observações são sintéticas; não há envio de email.

A CI executa também a atualização **com dados anteriores** de 0016 → 0017/0018, verifica conteúdo de todas as colunas históricas e ACLs, suites SQL anteriores, concorrência de equipas, testes API, testes de navegador, unitários, tipos e build. O teste de browser cobre criação/cópia/rotação/revogação real e resposta tardia ao mudar de empresa, recarregamento e logout. Os testes unitários de transporte usam upstream controlado e não provam autenticação.

O navegador necessita Playwright instalado: `cd e2e && npm ci && npx playwright install chromium && npx playwright test`. Opcionalmente use `CW_BROWSER_BIN=/usr/bin/chromium` para um Chromium já instalado; CI usa a versão bloqueada pelo Playwright. Para encerrar apenas o ambiente descartável: `python3 scripts/mvp/stop-local.py`.
