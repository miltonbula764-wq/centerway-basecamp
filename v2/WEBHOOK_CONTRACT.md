# Missão 15 — entrada SaaS HTTPS/HMAC (API 1.5.0)

Base: PR #44. Integração genérica de **entrada**, sem conector de fornecedor.
Só escreve declarações M07 inativas. Não invoca o orquestrador, C02–C06, IA,
autorizações ou intervenções; todos os bloqueios de production permanecem.
Uma assinatura válida autentica um titular do segredo, **não prova a verdade**
das métricas, a causa de um problema, execução ou recuperação.

## Transporte e autenticação

`POST /api/webhooks/ingest`, exclusivamente no servidor privado HTTPS existente.
Opt-in `--webhook-config /private/webhooks.json` em `centerway.runtime serve`
(demo ou production); também disponível em `centerway.preview serve`.
Sem configuração: 503. Laboratório HTTP e base pública não podem ativá-lo.
Host/HTTPS privado e expiração demo continuam verificados. Não confiar em
`X-Forwarded-*`; Caddy encaminha `/api/*` ao Python por HTTPS com CA verificada,
preservando path, Host e corpo. Templates existentes já são compatíveis.
Nenhuma instância foi publicada nesta missão.

Obrigatórios, cada um exatamente uma vez:

| Header | Valor |
| --- | --- |
| Content-Type | application/json, corpo UTF-8 |
| Content-Length | inteiro positivo, máximo 65536 bytes |
| X-CW-Source | ID de origem configurada, `[A-Za-z0-9_-]{1,64}` |
| X-CW-Key-Id | ID da chave configurada, mesmo formato |
| X-CW-Timestamp | segundos Unix UTC, decimal (1–12 dígitos) |
| X-CW-Nonce | ID aleatório da entrega, `[A-Za-z0-9_-]{16,128}` |
| X-CW-Signature | `v1=` + hex minúsculo HMAC-SHA256 (64 caracteres) |

Não aceita query, Cookie, Origin, Sec-Fetch-Site, compressão ou Transfer-Encoding.
Não oferece CORS/preflight (OPTIONS 403); GET e outros métodos 405. Não utiliza
sessões humanas, bearer tokens nem roles declaradas pelo emissor.

A entrada da assinatura é esta sequência, **sem espaços ou linha final extra
entre o prefixo e o corpo**:

```text
v1\nPOST\n/api/webhooks/ingest\n<SOURCE>\n<KEY_ID>\n<TIMESTAMP>\n<NONCE>\n<ORIGINAL_BODY_BYTES>
```

Os `\n` são bytes LF reais. O segredo é 32 bytes aleatórios, guardados num
ficheiro como 64 caracteres hex minúsculos; o HMAC usa os bytes descodificados.
Comparação em tempo constante. Não reserializar o JSON antes de verificar.
Timestamp dentro de ±300 segundos do servidor; timestamp **e receção** dentro
de `[not_before, expires_at)` da chave. Sincronização segura do relógio é requisito.

Nonce único por origem, persistido e preservado entre reinícios. Repetição exata
assinada e ainda válida devolve o recibo original, sem nova escrita. Mesmo nonce
com timestamp/chave/corpo diferente: 409. Fora da janela ou chave revogada: 401,
mesmo que a mensagem tenha sido aceite antes. Novo nonce com mesmo evento pode
obter `duplicates:1` pelo M07, sem duplicar evidência. Não mudar `event_id` para
contornar conflitos. Retry após timeout requer decisão do emissor; não há retry
automático. IDs de origem são permanentes; não os reutilizar para outra SaaS.

## Configuração privada e mapeamento

[Template demo sem segredos e deliberadamente incompleto](examples/webhooks/demo-source.json).
Copiar para fora do checkout e preencher hash M06, caminhos e janelas; não funciona
com placeholders. Tanto a configuração como cada segredo exigem ficheiro regular,
proprietário igual ao processo e sem permissões de grupo/outros (0600 ou mais
restritivo); symlink final recusado. Diretório privado 0700 e pais confiáveis são
responsabilidade do operador. Nunca servir esses diretórios como ficheiros estáticos.

- `schema_version:1`; `mode:demo|production` tem de coincidir com a base.
- Cada origem fixa `tenant`, `config_version` e `config_hash` atuais M06,
  `mapping_version` positiva, classificação, clientes permitidos, rotas e chaves.
- Demo só aceita `classification:test` e contrato `synthetic`. Production só
  aceita origem `declared` e contrato `declared`. As verificações production usam
  declarações de teste identificadas em bases descartáveis; nenhum fornecedor
  ou cliente real foi verificado.
- `customers`: mapa exato ID externo → ID interno permitido. Sem criação implícita,
  lookup externo, matching por nome/email ou acesso a outro cliente. O M07 não
  exige uma linha sandbox `environments`; o mapa explícito é o grant de entrada.
- `routes`: nome externo → `kind:event|metric|evidence`, `definition_id`,
  `source_ref` exatos M06 e `fields` (campo universal → seletor).
- Seletores suportados: `$customer` (ID interno autorizado), `$occurred_at`,
  `data.campo` (campo direto). Não há expressões, código, URLs, agregações,
  coerções ou inferência de metas. `data` deve ter exatamente os campos usados.
  Tipos, campos requeridos, fonte, períodos e identidade passam pela validação M07.
- Um `source_ref` contratual pertence a uma única origem autenticada por SaaS
  na configuração ativa e no histórico de receções. Usar referências distintas para origens distintas.
- Mudar clientes/rotas/contrato/classificação exige aumentar `mapping_version`;
  reutilização da versão com conteúdo diferente ou rollback depois de uma
  receção autenticada é recusado. Alteração M06 exige configuração atual explícita.
  Configurações anteriores ficam preservadas com hash e vínculos aos recibos.
- Até duas chaves por origem, com material secreto independente entre chaves/origens, cada uma com ID próprio, caminho privado,
  `not_before` e `expires_at` Unix inteiros explícitos. Sem credenciais predefinidas.

Configuração/chaves são relidas por pedido; não há cache/fallback se ficarem
inválidas. Para rotação: gerar novo segredo/ID, acrescentar com janela de
sobreposição, gravar configuração por substituição atómica, mudar o emissor,
remover a chave antiga. Remoção/expiração revoga novos pedidos e retries antigos;
um pedido que já autenticou pode concluir a transação em curso. Nunca substituir
o segredo mantendo um ID utilizado, nem reutilizar material secreto anterior com novo ID: o fingerprint imutável recusa essa reutilização.
Remover uma origem revoga-a; para desativar toda a entrada, retirar a opção do
servidor e reiniciar. Uma configuração ausente/inválida também falha fechada.
Alterações são feitas pelo administrador local, sem endpoint público de gestão.

## Preparação explícita (sem publicação)

Usar uma base privada já preparada e com configuração M06 autorizada. Para um
ensaio, utilizar **nova demo privada**, nunca dados/contas públicas do laboratório.
O exemplo de colaboração deve ter `tenant:atlas` antes de ser registado pelo
`founder`; guardar essa cópia fora do Git. Contratos de produção devem ser
fornecidos/aprovados pela SaaS, sem converter fixtures fictícias em contratos reais.

```sh
cd v2
# Apenas se M06/M07 ainda não estiverem preparados nesta base:
python -m centerway.integrations init --db /private/demo.sqlite3
python -m centerway.integrations append --db /private/demo.sqlite3 --user founder --tenant atlas --file /private/saas-config.json --expected-version 0
python -m centerway.evidence init --db /private/demo.sqlite3
# Instalação opcional local, uma única vez; nunca no arranque HTTP:
python -m centerway.webhooks init --db /private/demo.sqlite3
python -m centerway.integrations get --db /private/demo.sqlite3 --user founder --tenant atlas
```

Gerar cada segredo em ficheiro novo com `umask 077` e
`secrets.token_hex(32)` do Python, redirecionando diretamente para fora do checkout.
Não copiar segredos para comandos, logs, chat ou ficheiros versionados. Completar
o template privado com o hash devolvido, caminho real e janelas de chave.

```sh
python -m centerway.webhooks check --db /private/demo.sqlite3 --config /private/webhooks.json
python -m centerway.runtime serve --mode demo --db /private/demo.sqlite3 --certfile /private/backend-cert.pem --keyfile /private/backend-key.pem --port 8443 --webhook-config /private/webhooks.json
```

`check` valida ficheiros, modo, esquema e alvos atuais M06 sem escrever; não prova
conectividade externa nem posse de credenciais por um fornecedor. Fazer backup
antes de preparar tabelas opcionais numa base existente. Sem migração/seed/DDL
no HTTP, reparação automática ou alteração dos motores anteriores.

## Mensagem, recibo e erros

[Mensagem sintética de exemplo](examples/webhooks/test-event.json):

```json
{"mapping_version":1,"config_version":1,"customer_id":"external-account-001","event_type":"completed","event_id":"explicit-test-event-001","occurred_at":"2026-01-02T00:00:00Z","period":null,"data":{}}
```

Exige exatamente esses campos. Para métricas, `period:{"start":...,"end":...}`
explícito e UTC; período inteiro termina até ao acontecimento, que não pode estar
no futuro. Não existe campo `tenant`, `source_ref` ou autorização no payload.
Fonte e cliente universais são determinados exclusivamente pelo grant autenticado.

```json
{"status":"accepted","receipt_id":1,"inserted":1,"duplicates":0,"claim_classification":"source_claim","source_classification":"test","operational_state":"inactive"}
```

`accepted` significa persistência ou replay técnico, nunca verdade/recuperação.
Recibos não expõem payloads, clientes, configuração ou IDs de evidência.
Erros seguem `{error,code}` do contrato HTTP: 400 formato/tipos/fonte incompatível,
401 autenticação/freshness/chave/origem desconhecida, 403 cliente/browser fora do
âmbito, 409 versões/identidade/nonce conflitante, 413 limite, 415 tipo/compressão,
421 Host, 429 quota e 503 entrada/configuração/integridade indisponível.
Falha inesperada: 500 genérico e rollback, sem afirmar aceitação.

```sh
python examples/webhooks/send.py --url https://localhost:8443/api/webhooks/ingest --source test-collaboration --key-id key-2026-01 --secret-file /private/source.key --body-file examples/webhooks/test-event.json --ca-file /private/test-ca.pem
```

O emissor de exemplo assina o ficheiro original, valida TLS/CA, recusa redirects,
não imprime headers/segredos/corpo/resposta externa e não tenta novamente sozinho.
Omitir `--ca-file` para usar CAs padrão. Não há opção TLS insegura.

## Persistência, segurança e limites verificados

M07 partilha a mesma função de validação/persistência entre entrada humana e
serviço, sem impersonar operador. Validações humanas anteriores mantêm-se.
`actor:webhook:<source>` e os recibos ligam origem/chave/versão/hash do mapeamento,
configuração M06, hash do corpo original e IDs M07. Receções autenticadas aceites
ou rejeitadas são append-only. Rejeição contratual também consome o nonce;
reenvio exato mantém a rejeição. Assinaturas inválidas não ocupam a base.
Evidência, lote M07 e recibo commitam na mesma transação SQLite; falhas inesperadas
revertem todos. UNIQUE serializa duplicados concorrentes. Contradições permanecem
como declarações distintas, consultáveis pelo M07 autorizado.

Logs HTTP registam apenas método/path conhecido/status (e metadados normais do
servidor como IP/tempo); nunca query, headers, nonce, assinatura, segredo, corpo
ou detalhes de exceção. Rejeições pré-autenticação só ficam nesses logs sanitizados,
para não permitir encher SQLite sem credenciais. Recibos internos não são API de
consulta e exigem acesso local privado à base. Evidências operacionais e mapas de
clientes podem ser sensíveis: proteger ficheiros e backups; não há cifragem em
repouso implementada nesta missão. Hashes locais não são assinaturas de auditoria.

Limites explícitos: 1 registo/pedido, 64 KiB/corpo, 100 origens, 100 rotas/origem,
10000 aliases de cliente/origem, 2 chaves/origem, 120 novas entregas autenticadas
por minuto/origem e 100000 recibos/origem. Replays exatos não consomem novos
recibos. Mantêm-se 8192 bytes/registo, 1000 evidências e 5000 lotes por cliente M07.
Ao esgotar, bloquear e rever localmente; não apagar histórico ou liberar retries
incertos. SQLite/um serviço, sem fila, cluster, scheduler ou proteção DDoS de borda.

Verificações locais usam HTTPS com CA de teste confiada, mensagens assinadas,
origens identificadas como teste, duas SaaS/clientes, rotação/revogação, replay,
concorrência/rollback, contrato OpenAPI, isolamento, limites, segredos/logs e demo
expirada. O script emissor é executado de ponta a ponta numa demo descartável; Caddy → HTTPS Python também recebe e valida mensagens assinadas de teste.
Sem fornecedor real, tráfego externo, publicação ou recuperação real verificada.
