# Piloto privado de análise — contrato HTTP 1.6.0

Base: PR #45, commit final `31cd4de`. A [CI desse commit](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/40279163056)
foi confirmada como aprovada antes desta missão. Nenhuma interface Lovable,
publicação, migração de dados reais ou serviço externo foi criado.

O piloto utiliza a fundação privada permanente e **declarações** M06/M07.
A autorização é por SaaS e permite apenas configuração, análise C02/C03/C04 e
acompanhamento humano. Não é uma ativação do fluxo operacional de production.
C05, execução externa, C06 novo e alegações de recuperação real ficam bloqueados,
inclusive por triggers nas tabelas de execução/verificação. As APIs sandbox e
os motores anteriores mantêm o comportamento habitual.

## Preparação local autorizada

Utilizar uma base production privada, contas próprias e HTTPS/CA corretos,
segundo [PERMANENT_FOUNDATION.md](PERMANENT_FOUNDATION.md) e os templates Caddy.
Não utilizar a demo pública nem converter fixtures fictícias em dados reais.
O piloto não remove a expiração de 24h da demo; a demo não ativa este modo.

Com backup e serviço parado, preparar os repositórios opcionais que ainda não
existirem, na ordem M06 → M07 → M08 → M09 → M10 → M11 → M12 → M13/M14.
Cada comando `init` é explícito, recusa repetição e não repara esquemas. Não
executar init sobre tabelas já preparadas. Nenhum destes comandos é API do browser:

```sh
cd v2
python -m centerway.integrations init --db /private/pilot.sqlite3
python -m centerway.evidence init --db /private/pilot.sqlite3
python -m centerway.detection init --db /private/pilot.sqlite3
python -m centerway.investigation init --db /private/pilot.sqlite3
python -m centerway.ai_proposals init --db /private/pilot.sqlite3
python -m centerway.controlled_execution init --db /private/pilot.sqlite3
python -m centerway.recovery init --db /private/pilot.sqlite3
python -m centerway.orchestration init --db /private/pilot.sqlite3
python -m centerway.pilot init --db /private/pilot.sqlite3
python -m centerway.pilot authorize --db /private/pilot.sqlite3 --user owner --tenant company-a --enabled yes --allow-ai no --reason 'Autorização explícita para análise e acompanhamento privados, sem execução' --expected-version 0
```

A autorização exige operador Core atual e acesso administrativo local à base;
regista responsável, motivo, versão, data e hash anterior. Para revogar, executar
o último comando com `--enabled no --allow-ai no --expected-version <atual>`.
Não há endpoint para ativar piloto, conceder roles, gerir contas, instalar tabelas,
mudar paths/segredos ou executar comandos. O HTTP nunca executa DDL ou seed.
Uma base M13 antiga exige primeiro o upgrade M14 explícito numa cópia; não o fazer
através deste contrato nem sobre dados reais nesta missão.

Arranque normal, sem interface ou publicação:

```sh
python -m centerway.runtime serve --mode production --db /private/pilot.sqlite3 --certfile /private/backend-cert.pem --keyfile /private/backend-key.pem --host 127.0.0.1 --port 9443
```

Usar o Caddy existente para a futura origem HTTPS: `/api/*` preservado até Python
por TLS verificado. Nenhum serviço deve ser ativado/publicado por estes exemplos.
Configurar origem/Host para a infraestrutura privada realmente autorizada.

## Autenticação e frontend Lovable futuro

Especificação importável: [OpenAPI 3.1](contracts/openapi.json). O browser usa
`POST /api/login` com a conta privada e cookie
`__Host-cw_production_session` Secure/HttpOnly/SameSite=Strict (1h); depois
`POST /api/logout {}`. Não copiar tokens para JS/localStorage, não enviar tokens,
roles ou actor nos corpos e não usar HMAC de SaaS como autenticação do frontend.

Preferir o frontend exportado na **mesma origem HTTPS** que `/api/*`. Se for
necessária outra origem, usar apenas uma origem exata HTTPS do mesmo site,
explicitamente configurada em `--frontend-origin`; cookies Strict não suportam
um frontend cross-site. Não usar wildcard, proxy público ou relaxar cookies para
um domínio temporário Lovable. Esta missão não configura nem testa Lovable real.

```js
// Apenas exemplo de integração, não uma interface implementada.
async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    credentials: 'include',
    headers: body === undefined ? {} : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const result = await response.json();
  if (!response.ok) throw {status: response.status, ...result};
  return result;
}
```

O browser fornece Origin automaticamente. Escritas exigem Origin exata permitida,
rejeitam Sec-Fetch-Site cross-site, sessão atual e role operator. Viewer pode ler
apenas as SaaS às quais pertence. JSON estrito, sem chaves duplicadas, limite de
64 KiB, um Content-Length, sem compressão/Transfer-Encoding. Sem CSRF por cookie
isolado de verificação de origem. Os erros têm `{error,code}`; nunca renderizar
strings recebidas como HTML nem inferir factos a partir de mensagens de erro.

## Endpoints do piloto

Todos exigem cookie production e SaaS explícita; exceto `status`, exigem também
piloto atualmente autorizado. GET não processa nem escreve.

| Método/path | Pedido e finalidade |
| --- | --- |
| GET `/api/pilot/status?tenant=...` | Autorização/consentimento, versões, número de clientes, blockers e analysis_ready. Não afirma conectividade externa. |
| GET `/api/pilot/context?tenant=...&after=0&limit=25` | Configuração e critérios atuais completos, metadados de versões anteriores e next_after. |
| GET `/api/pilot/configuration?tenant=...&version=1` | Snapshot M06 histórico exato. |
| GET `/api/pilot/criteria?tenant=...&version=1` | Snapshot M08 histórico exato. |
| POST `/api/pilot/configure` | `{tenant, config, expected_version}`; documento M06 completo declarado. |
| POST `/api/pilot/criteria/append` | `{tenant, document, expected_version}`; critérios M08 completos e explícitos. |
| GET `/api/pilot/customers?tenant=...&after=0&limit=25` | Última revisão de cada cliente, cursor id; `customer=...` consulta histórico desse cliente, cursor version. |
| POST `/api/pilot/customers/append` | `{tenant, customer, name, context, expected_version}`; registo/revisão de cliente, sem ambiente sandbox ou efeitos. |
| GET `/api/pilot/analysis?tenant=...&customer=...&case_id=...` | Checkpoint atual, C02, C03, cartão C04 sanitizado, revisões humanas, explicações e histórico paginado. |
| POST `/api/pilot/investigate` | `{tenant, customer, case_id, c02_run_id, document, expected_version}`; declaração C03 explícita ligada ao C02 atual. |
| POST `/api/pilot/review` | `{tenant, customer, case_id, request_id, expected_checkpoint_hash, note}`; acompanhamento humano explícito, sem autorizar ou simular IA. |
| POST `/api/pilot/process` | `{tenant, customer, case_id, request_id, as_of}`; regista primeiro caso se necessário e executa percurso limitado do orquestrador de análise. |

GET analysis aceita `after`, `limit` (1–50) para checkpoints e `version` para
selecionar fontes de um checkpoint histórico. Os refs e hashes identificam versões
C02/C03/C04 consultadas. Não retorna contexto interno C04, endpoint, paths de
credenciais ou configuração privada do modelo. `receipt.inference_kind`, modelo
pedido/reportado e resultado da validação distinguem inferência e indisponibilidade.
`not_requested` significa que não existe pedido IA; `pending_or_interrupted`
significa reserva sem conclusão e nunca autoriza um retry automático.

O frontend deve apresentar `explanation`, `interpretation`, estados, blockers,
refs e critérios do backend. Não recalcular deterioração, inferir causas, escolher
entre contradições ou equiparar `proposal_validated` a autorização. Factos, hipóteses,
impedimentos e lacunas mantêm os campos distintos do C03. `real_recovery_demonstrated`
permanece false. Revisões humanas são notas assinadas pela sessão no servidor,
não propostas C04 nem resoluções de execuções incertas.

Os documentos M06/M08/C03 têm schemas no OpenAPI; regras de referências, unidades,
tipos, cobertura e proveniência continuam nos validadores dos motores. Atualizar
contexto/métricas/goals exige nova configuração M06 inteira, preservando anterior.
`expected_version:0` cria a primeira versão. Uma versão esperada desatualizada
retorna 409, sem duplicar configuração/critérios. Clientes e C03 reutilizam revisões
exatas; request_id de processo/revisão não pode ser reaproveitado para outro conteúdo.
Não há PATCH parcial ou defaults de metas. Contexto textual individual do cliente
é metadado do registo, não nova evidência nem objetivo individual inferido; os goals
atuais continuam a ser os da SaaS aplicados ao cliente selecionado.

## Percurso privado reproduzível

1. Preparar base privada e autorização local acima; entrar com a conta privada.
   `GET status` mostra blockers sem inventar configuração.
2. Enviar configuração M06 fornecida/aprovada pela SaaS em `POST configure`.
   Definir produto, identidade de clientes, goals, métricas, eventos/evidências e
   capacidades declaradas. Catálogo não desbloqueia execução.
3. Enviar critérios M08 em `POST criteria/append`, fixando `config_version`,
   métrica, goal/evidence refs, método, comparação, limite, unidade, janela,
   cadência e cobertura explícitos. Registar cliente com `customers/append`.
4. Inserir declarações por `POST /api/evidence` M07 autenticado; ou, se a origem
   SaaS estiver preparada/autorizada separadamente, pela [entrada HMAC M15](WEBHOOK_CONTRACT.md).
   Consultar `/api/evidence/view?tenant=...&customer=...&config_version=...`
   com paginação para qualidade/proveniência. O grant do webhook é separado do
   grant do piloto; nenhum deles concede autoridade de intervenção.
5. Chamar `POST process` com request_id novo e cutoff `as_of` explícito e não futuro.
   Deterioração demonstrada leva a `awaiting_investigation`; dados insuficientes
   mantêm `awaiting_data`, contradições levam a `needs_review`, sem C03 fabricado.
6. Consultar `GET analysis`; registar documento C03 **do operador**, com o run ID
   atual e referências de evidências realmente existentes, através de `investigate`.
   Não preencher automaticamente hipóteses ou requisitos para avançar o fluxo.
7. Processar novamente. Sem IA autorizada, fica `awaiting_ai` sem chamada nem
   proposta simulada. O operador pode submeter `review`, fixando o hash do
   checkpoint que reviu e a sua nota, e processar para `needs_review` com blocker
   `human_follow_up_recorded`. Com IA preparada e consentida, C04 valida a resposta;
   proposta ou revisão leva a acompanhamento humano, nunca a C05.
8. Novas evidências, critérios ou revisões C03 exigem novo request_id de processamento.
   O orquestrador atualiza fontes/checkpoints sem destruir anteriores; revisões
   humanas antigas não se aplicam a outra linhagem C02/C03. Consultar histórico
   com version/after/limit. Não interpretar estabilidade técnica como recuperação.

Para repetir **apenas o ensaio técnico sintético**, sem dados reais ou publicação:

```sh
CADDY_BIN=/path/to/verified/caddy python -m unittest discover -s tests -p test_pilot.py -v
```

Os testes criam bases descartáveis e declarações explicitamente identificadas
como TEST, incluindo um endpoint IA HTTPS **de teste local**, sem modelo real.
Não importar essas declarações num piloto real. Não há fornecedor real ou inferência
real validada nesta missão; o caminho sem IA e com acompanhamento humano é funcional.

## IA opcional e consentimento

Sem `--pilot-ai-config`, não há inferência, mesmo com variáveis de ambiente de IA.
A permissão local `--allow-ai yes` sozinha também não a ativa. Para o futuro, são
necessários **ambos**: grant explícito da SaaS e configuração M10 privada do modelo
em `--pilot-ai-config /private/provider.json`, fora do Git, com allowlist da SaaS,
classe declared, `allow_production_inference:true`, TLS verificado, segredo privado,
limites e timeout de no máximo 5s. Nenhuma opção de modelo/URL/path/segredo vem do
browser. Sem configuração válida: indisponível, sem fallback simulado.

Antes/depois de cada chamada, revalidam-se grant/versão, consentimento, sessão e
permissões. Revogação durante inferência resulta em recusa/indisponibilidade auditada;
nenhuma recomendação é promovida a autorização. M10 também revalida evidências,
versões e capacidades. Reservas C04 pendentes não são repetidas automaticamente.
Não fornecer credenciais de serviços pagos ou configurar chamadas reais nesta missão.

## Limites, falhas e prontidão

- Até 100 versões M06 e de critérios por SaaS pela API; 1000 clientes, 100 revisões
  por cliente/C03, 100 revisões humanas por caso. Páginas até 50; analysis até 1 MiB,
  recusando excesso em vez de truncar silenciosamente. M07 mantém os seus limites.
- Processamento de **um cliente por pedido**, até 8 passos, orçamento entre passos
  de 10s; chamada IA até 5s. Não é SLA rígido de wall time (inclui SQLite/transporte).
  Até 10 pedidos novos/minuto/SaaS e 10000 registos de processamento/SaaS.
- Reserva SQLite impede duplicados de request_id e processamento concorrente da
  SaaS durante 60s. Após interrupção, consultar primeiro o caso; um pedido novo
  depois desse intervalo retoma checkpoints. Uma reserva antiga mantém-se pendente,
  não é apagada ou simulada como concluída. Reservas C04 continuam sem retry.
- Repetição exata de processamento concluído devolve o recibo original, sem
  reprocessar dados novos. Para os considerar, enviar novo request_id. Preservam-se
  responsável, grant, request hash/cutoff, checkpoint, versões e histórico.
- Sem scheduler/polling automático HTTP, fila ou automação em massa. A futura UI
  pode pedir processamento e depois consultar; GET nunca avança estados.
- O piloto acompanha o primeiro ciclo ativo. Fecho/sucessor de production continuam
  bloqueados nesta missão; não contornar o acompanhamento com IDs de caso novos.
- Erros: 401 sessão, 403 role/SaaS/piloto/CSRF, 404 escopo inexistente, 409 versão,
  checkpoint ou reserva, 413 limite, 429 quota, 503 preparação/integridade/modo,
  500 falha sanitizada. Não assumir sucesso após timeout ou erro.

Critérios objetivos para o primeiro teste privado:

| Critério | Evidência necessária |
| --- | --- |
| Backend técnico | CI verde, ensaio HTTPS autenticado, M07→C02→C03→review/proposta→caso verificável e sem C05. |
| Infraestrutura privada | HTTPS/Host/CA verificados no endereço privado real, contas próprias, ficheiros/backups privados, mesma origem ou CORS same-site exato. Ainda não publicado/verificado nesta missão. |
| Consentimento | Grant da SaaS enabled com responsável/motivo/version; allow_ai false por omissão. |
| Declarações | Contexto, clientes, métricas, metas e critérios fornecidos/aprovados pela SaaS; sem fixtures, sem limites inventados. |
| Preparação de análise | GET status com analysis_ready true; confirma configuração/critérios atuais e pelo menos um cliente, não prova qualidade/veracidade nem disponibilidade de IA. |
| Dados | Evidências de origem permitida, timestamps/períodos e versão corretos; insuficiência/contradições apresentadas sem conclusão inventada. |
| Segurança | Viewer não escreve, outra SaaS não lê/escreve, logout/revogação bloqueiam, CSRF negado, C05 e recuperação real bloqueados. |
| Interface futura | Consumir schemas/estados/explicações sem lógica paralela; validar login, envio, revisão e histórico através da origem privada escolhida. Lovable real permanece por integrar/testar. |

O backend pode satisfazer os critérios técnicos localmente; a prontidão de um
piloto real também depende das autorizações, declarações, infraestrutura e interface
privada acima. Nenhum cliente real foi acompanhado nem recuperação real afirmada.
