# Orquestração M06–M12 — Missão 13

A [Missão 14](CONTINUITY_CONTRACT.md) substitui a limitação de um único caso contínuo por múltiplos ciclos históricos e um ativo, com encerramento explícito. A descrição abaixo documenta a base M13; API atual é 1.4.0.

Base: PR #42 (`e2026c5`), branch `centerway-v2/missao-13-orchestration`.
Coordena os motores existentes; não reconstrói C01–C06, não altera Core/sandbox,
não cria investigações/autorizações e não prova recuperação real. Os resultados
continuam **inativos**, com operações externas e processamento production bloqueados.

## Funcionamento

Um caso coordenado contínuo por `(tenant, customer)`, identificado também por
`case_id`. IDs de clientes seguem M07 (identidade externa até 128 caracteres);
case IDs seguem M06. O registo só inscreve identidade, não cria clientes sandbox,
contratos, observações ou cenários. Não há qualquer seed no orquestrador.

Um worker local autorizado processa vários casos em cada chamada. Em cada caso,
avança automaticamente até um impedimento ou limite, sem escolher manualmente a
próxima componente:

1. Lê a configuração/últimos critérios explicitamente declarados e evidências M07
   do cliente. Ausência ou critérios incompatíveis com a configuração atual bloqueiam.
2. Executa C02 com cutoff `as_of` explícito. Congela essa avaliação enquanto as
   fontes não mudarem: o relógio sozinho não invalida uma investigação em curso.
   Novas evidências, configurações/critérios ou dados que se tornem elegíveis pelo
   cutoff podem criar outro C02, sem sobrescrever o anterior.
3. Procura a última investigação C03 declarada para **esse** C02. Se faltar,
   aguarda o operador; não copia hipóteses de outro cliente/versão nem fabrica uma
   declaração vazia. Uma revisão C03 válida é consumida na chamada seguinte.
4. Consulta a proposta C04 vinculada deterministicamente a caso+C02+C03, ou usa o
   adaptador M10 configurado para a solicitar. Sem IA autorizada, apenas bloqueia;
   não reserva uma simulação ou resposta fictícia. Pendência/interrupção não
   repete inferência. Recusas/revisão humana não avançam para C05.
5. Uma proposta validada permite preparar a intenção C05 **apenas** quando existe
   adaptador aceite pelo motor. Aguarda a aprovação humana explícita da intenção
   exata, pela interface interna M11 e sessão autenticada. O orquestrador nunca
   chama `approve`, nunca recebe um token de aprovação e não renova autorizações.
6. Só despacha após autorização M11 atual, opção explícita de despacho e adaptador
   permitido. O próprio C05 volta a validar sessão/roles, evidências, versões,
   condições atuais, revisão e garantias atómicas/idempotentes. Nesta missão os
   únicos adaptadores executáveis são os **injetados nos testes**, identificados
   como tal. CLI/HTTP não têm um executor configurado nem uma opção para o ativar.
7. Uma tentativa C05 fixa definitivamente a linhagem prévia do caso. Mesmo que
   cheguem novos dados, não cria outra intervenção: consulta C06 com o plano
   explicitamente declarado e as evidências posteriores. Sem plano/cobertura
   aguarda verificação; incerteza/contradição requerem revisão, nunca nova execução.

Os motores M09/M11/M12 continuam a receber as entradas substantivas autorizadas
(investigação, aprovação, plano). Isto é trabalho humano/configuração exigidos,
**não comandos manuais para escolher ou avançar etapas**. O worker deteta esses
registos quando volta a processar. Não há um daemon/cron instalado ou serviço
ativado nesta missão; o chamador executa os lotes periodicamente. GET nunca dispara
trabalho e o último estado processado pode estar atrás de novos dados recebidos.

## Estados e transições

| Estado | Significado / impedimentos típicos |
| --- | --- |
| `awaiting_data` | Falta configuração, critérios compatíveis, dados ou cobertura C02 |
| `stable` | C02 não demonstrou deterioração nas dimensões completas; não significa recuperação |
| `awaiting_investigation` | C02 demonstrado, falta investigação declarada para o resultado exato |
| `awaiting_ai` | Falta IA autorizada/proposta; inferência pendente ou interrompida fica sem retry |
| `no_action` | C04 validou recomendação sem ação; não declara saúde/recuperação do cliente |
| `awaiting_approval` | Intenção C05 preparada, falta aprovação humana explícita |
| `awaiting_execution` | Falta conector/adaptador, requisito atual ou habilitação de despacho de teste |
| `awaiting_verification` | Tentativa C05 existe; falta plano, evidência posterior ou cobertura C06 |
| `verification_recorded` | C06 registado, inclusive resultado não demonstrado; **não é encerramento ou recuperação real** |
| `needs_review` | Contradição, proposta recusada, aprovação inválida, execução incerta/recusada ou erro de processamento |

Sequência normal: `awaiting_data → awaiting_investigation → awaiting_ai →
awaiting_execution → awaiting_approval → awaiting_verification → verification_recorded`.
As transições implementadas estão em `TRANSITIONS` e são validadas na escrita e
leitura. Antes do despacho, alterações das fontes podem regressar aos requisitos
anteriores. C02 completo sem deterioração vai para `stable`; C04 sem ação vai para
`no_action`. Contradição/revalidação recusada vai para `needs_review`.

Após tentativa, só são permitidos `awaiting_verification`, `needs_review` e
`verification_recorded`, com o mesmo C02/C03/C04/tentativa. Uma reserva que apareça
concorrentemente é confirmada dentro da transação do checkpoint, impedindo outro
worker de apagar a linhagem e começar uma segunda intervenção.

Uma aprovação expirada/revogada pede revisão humana. Uma revalidação recusada
não é repetida com fontes iguais. Revisão explícita de investigação/novas fontes
pode exigir outra proposta/intenção/aprovação antes de qualquer despacho. Não há
API para redefinir estados, repetir C05, resolver resultado incerto, renovar
aprovação ou fechar o caso. Um novo `case_id` para contornar o caso contínuo é 409.

## Lotes, interrupções e auditoria

- Até **25 casos** por lote, **1–12 passos** por caso (8 por omissão), orçamento
  **1–60 segundos** (30 por omissão). O orçamento é verificado entre casos/passos;
  uma chamada em curso não é interrompida pelo relógio. O transporte real M10
  mantém o seu próprio timeout até 30 segundos. Não se promete um deadline rígido.
- Paginação keyset por ID de registo: `after` / `next_after`. O cursor é um inteiro
  de continuação na SaaS autorizada, não uma autorização. Se o orçamento terminar,
  devolve o último ID processado; o próximo lote continua daí. Ao terminar uma
  ronda, recomeçar em `after=0` permite consumir atualizações e revisitar bloqueios.
- Cada etapa confirma um checkpoint persistido. IDs C04/C05 derivados das fontes
  são gravados antes de I/O; crash entre efeito e checkpoint retoma por esses IDs.
  Idempotência dos motores impede duplicar C02, inferência ou efeitos C05.
- Não há lock SQLite durante I/O de IA/adaptador. Concorrência dos checkpoints usa
  versão esperada; um worker atrasado não pode substituir uma transição mais nova.
  Uma operação antiga pode deixar um artefacto inativo no motor antes de perder
  a corrida de checkpoint; não recebe autoridade extra e é revalidada pelo motor.
- Erro num cliente é sanitizado (`case_processing_refused`), tenta registar
  `needs_review` se ainda autorizado e permite continuar os restantes. Revogação
  ou falha de integridade não são contornadas para escrever esse estado. Um crash
  de processo não é convertido em sucesso; repetir a ronda retoma os checkpoints.
- Só três tabelas opcionais: `orchestration_metadata`, `orchestration_cases`,
  `orchestration_events`. Append-only, hashes e cadeia por caso, ator, tempo,
  fontes/cutoff, IDs/versões/hashes e impedimentos. Até 1000 transições por caso.
  Setup local explícito; sem seed, migração de dados existentes ou DDL no HTTP.
  Hashes locais não são assinaturas/proteção contra administrador do ficheiro.

C04 utiliza IDs próprios deste fluxo, publicados em `refs`. Não escolhe entre
propostas externas concorrentes nem adota silenciosamente recomendações de outro
pedido/modelo. Resultados pendentes desses IDs e revisões dos motores associados
são consumidos em chamadas seguintes. C06 só é reavaliado quando mudam fontes,
plano/recibo, elegibilidade temporal ou completude das janelas; não cria uma nova
versão só porque passou mais um segundo após a maturidade do plano.

## Consulta autenticada para futura interface

Extensão aditiva HTTP **1.3.0**, com OpenAPI atualizado. Endpoints anteriores e
regras de cookies, TLS, CORS, expiração, isolamento e bloqueios permanecem.

```http
GET /api/orchestration/cases?tenant=atlas&state=awaiting_ai&limit=25
```

Sessão atual e membership na SaaS; viewer pode ler. Query aceita apenas `tenant`
(obrigatório), `customer`, `case_id` (exige customer), `state`, `after` e `limit`
(1–50). Campos repetidos/vazios/desconhecidos e números não ASCII são 400.
`next_after: null` termina a página. Cada item fornece `registry_id`, escopo,
versão, `updated_at`, estado, `blockers` e `refs`; não envia chaves de IA, tokens,
contexto do modelo, evidências completas ou autorização executável.

Exemplo de resposta após inscrição, antes de processar (IDs ilustrativos):

```json
{"tenant":"atlas","items":[{"registry_id":1,"tenant":"atlas","customer":"client-1","case_id":"case-1","version":1,"updated_at":"2026-10-25T00:00:00+00:00","state":"awaiting_data","blockers":["not_processed"],"refs":{},"operational_state":"inactive","real_recovery_demonstrated":false,"core_transition_authorized":false}],"next_after":null,"operational_state":"inactive","external_execution":"blocked"}
```

401 sem sessão; 403 sem membership/origem permitida; 405 para mutações;
503 sem preparação/integridade ou demo expirada. Respostas `no-store` e mesmas
proteções HTTPS/CORS existentes. Production pode consultar um registo inativo
vazio, mas inscrição/processamento (até lote vazio) são recusados com 503.
**Não há endpoint novo de processamento, IA, aprovação, execução ou gestão.**

## Preparar e testar

Numa cópia privada já preparada explicitamente até M12:

```sh
cd v2
python -m centerway.orchestration init --db /caminho/copia.sqlite3
python -m centerway.orchestration register --db /caminho/copia.sqlite3 \
  --user OPERADOR --tenant SAAS --customer CLIENTE --case-id CASO
python -m centerway.orchestration run-batch --db /caminho/copia.sqlite3 \
  --user OPERADOR --tenant SAAS --as-of MOMENTO_UTC --limit 25 --budget-seconds 30
python -m centerway.orchestration list --db /caminho/copia.sqlite3 \
  --user OPERADOR --tenant SAAS
python -m centerway.orchestration history --db /caminho/copia.sqlite3 \
  --user OPERADOR --tenant SAAS --customer CLIENTE --case-id CASO
```

A única opção de IA é `run-batch --ai-config /ficheiro/privado.json`, com a
configuração segura/consentimentos M10. Nenhuma chave do ambiente é usada por
omissão. Sem configuração, fica `awaiting_ai`. Sem conector, `awaiting_execution`.
Não há flag CLI de fixture, adaptador simulado ou desbloqueio de production.
Parâmetros `user` internos exigem um chamador local de confiança; o HTTP deriva a
identidade da sessão, nunca aceita user/role fornecido pelo browser.

Testes técnicos reproduzíveis, sem credenciais externas:

```sh
python -m unittest discover -s tests -p 'test_orchestration*.py' -v
CADDY_BIN=/caminho/caddy python -m unittest discover -s tests -v
```

Só nos testes: fixtures C04 explicitamente identificadas, relógio e adaptador
SQLite de teste M11; 150 clientes em duas SaaS com dados insuficientes, estáveis e
em deterioração. Testam encaminhamento completo, bloqueios legítimos, aprovação,
concorrência, crash/reenvio, corrida de despacho, permissões, isolamento, limites,
integridade, preservação do Core/sandbox, HTTPS privado e contrato real das respostas.
Não houve inferência/integração/recuperação real ou teste em Android físico.

Limitações: worker local por polling, sem agendamento/serviço ativado; inscrição
explícita e um caso contínuo por cliente, até 1000 transições. C03 e planos C06
continuam declarados por pessoas autorizadas; aprovação humana é exclusivamente
M11. C04 pendente/falhado não faz retries automáticos. Conectores reais continuam
inexistentes e bloqueados; C06 só verifica cenários sintéticos. Não confundir
`verification_recorded`, uma conclusão técnica ou operação recuperada no teste
com recuperação de valor real ou autorização de encerramento no Core.
