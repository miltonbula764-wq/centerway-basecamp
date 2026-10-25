# Continuidade e ciclos — Missão 14

Base: PR #43 (`8fb11ac`). Branch: `centerway-v2/missao-14-continuity`.
Reutiliza o orquestrador M13 e os motores C02–C06. Acrescenta um lifecycle
administrativo **active / closed**, separado do estado técnico da última etapa.
Não executa intervenções, não declara recuperação real e não ativa production.

## Regras de continuidade

- Vários casos históricos por SaaS/cliente; no máximo um ativo. A restrição é
  verificada na aplicação **e por trigger SQLite**, dentro da transação.
- Encerramento apenas por operador atual com sessão válida, confirmação humana
  explícita, motivo e disposição. C06 positivo nunca fecha automaticamente.
- Antes de fechar, o operador consulta um snapshot com versão/hash do checkpoint,
  referências C02–C06, intenções/tentativas/recibos, verificações e todas as
  evidências disponíveis daquele cliente (IDs, hashes, origem, tempos e versões).
  O pedido tem de indicar a versão e o hash exatos desse contexto. Também mostra
  `other_prepared_intents`: intenções anteriores do cliente, não atribuídas ao caso,
  cujo despacho futuro será invalidado pelo fecho.
- Novo dado/resultado antes da confirmação torna o contexto obsoleto: 409, sem
  fecho. Actor, sessão **em hash**, decisão, snapshot e timestamp ficam imutáveis.
  Tokens, chaves de IA e passwords não são guardados nestes registos.
- Disposições permitidas: `follow_up_complete`, `no_intervention_needed`,
  `not_recovered`, `cancelled`. São decisões administrativas, não uma conclusão
  do modelo, prova causal ou recuperação de valor. Conserva sempre
  `closure_means_recovery=false`, `real_recovery_demonstrated=false` e
  `value_recovered=null`.

`state` continua a indicar a última etapa M13, por exemplo `awaiting_ai` ou
`verification_recorded`. `lifecycle=closed` indica o encerramento explícito;
`closure.disposition` e `reason` explicam a decisão. Não se sobrescrevem checkpoints
para inventar um estado de recuperação. A mudança administrativa autorizada não
concede autorização para operações de negócio ou transições automáticas no Core.

## Pendência, incerteza e autorizações antigas

Fecho e sucessor são bloqueados se existir tentativa C05 pendente/incerta no
cliente, incluindo intenções antigas que ainda não estejam atribuídas ao caso.
Não se considera timeout como ausência de efeito. Também não se fecha enquanto
uma inferência C04 vinculada ao caso estiver em curso/interrompida sem resultado.

`review` permite registar uma apreciação humana da incerteza, com nota e IDs das
evidências disponíveis. Fica **unresolved**, `allows_closure=false` e
`allows_new_cycle=false`: reconhecer o problema não equivale a resolver o efeito.
Até 100 revisões por caso. Uma chamada C05 ainda em curso pode concluir e registar
o recibo normalmente; um resultado C05 final incerto continua bloqueado. Não há
nesta missão mecanismo para fabricar certeza, alterar recibos ou autorizar retry.

O fecho invalida o uso futuro das intenções/aprovações antigas. Os triggers:

- recusam novos checkpoints no caso fechado;
- recusam revisões C03 e pedidos C04 novos sobre o C02 fechado;
- recusam intenções, aprovações ou reservas C05 que reutilizem a linhagem fechada;
- recusam aprovar/despachar uma intenção do cliente anterior ao fecho, mesmo que
  tenha sido preparada fora do fluxo coordenado;
- impedem reservar outra execução coordenada se há execução incerta no cliente;
- impedem planos/avaliações C06 novos para a intervenção histórica.

Leituras e reenvios que apenas devolvem um recibo/resultado histórico continuam
possíveis: não são outra execução nem renovação da autorização. Motor C05, sua
idempotência e verificações independentes mantêm-se intactos.

A transação serializa a corrida fecho/despacho: se a reserva C05 já existe, o
fecho vê a pendência e recusa; se o fecho vence, a reserva é recusada no storage,
antes do efeito do adaptador. Não se afirma atomicidade distribuída num SaaS real.

## Novo ciclo

Abertura explícita por operador/sessão atuais, `human_confirmed=true`, motivo,
ID novo, `request_id` e `previous_case_id` exato (null na primeira inscrição).
O predecessor tem de ser o último caso e estar fechado; não basta fornecer um
caso fechado mais antigo. Uma primeira inscrição pode aguardar dados.

Um sucessor exige evidência M07 **nova, posterior ao encerramento e na configuração
atual**: ID maior que o watermark fechado, acontecimento posterior e, em métricas,
período inteiramente posterior ao fecho. Reenvio de dados antigos ou receção tardia
de uma observação antiga não abre outro ciclo. Isto permite inscrever o novo
incidente; só C02 decide se a deterioração fica demonstrada.

O worker exige cutoff posterior ao fecho e pelo menos uma dessas evidências já
elegível. C02 recebe outro snapshot de entrada; C03 precisa de investigação para
esse resultado. IDs C04/C05 incluem a identidade/hash do novo caso. Decisões e
aprovações antigas não são copiadas. O vínculo de uma fonte C02/C04/C05 a um caso
é único por cliente e validado no storage. Cada novo despacho exige a sua própria
aprovação M11 e todas as condições atuais.

Fecho e abertura usam `request_id` idempotente e contexto/actor vinculados. O mesmo
pedido devolve o mesmo registo; outro conteúdo não substitui a decisão anterior.
Dois pedidos concorrentes não criam dois ciclos ativos. Casos fechados saem dos
lotes, não adquirem novas verificações e continuam consultáveis com os snapshots
originais, mesmo depois de chegarem dados de ciclos posteriores.

## API 1.4.0 — sessão privada, sem Lovable implementada

Reutiliza cookies HttpOnly/Secure/SameSite, autorização por membership, proteção
de origem/CSRF, HTTPS e limites JSON existentes. `user`, `actor`, roles e tokens
no corpo são recusados. JSON até 64 KiB; motivo/nota até 1000 caracteres.

| Método / caminho | Função |
| --- | --- |
| GET `/api/orchestration/cases?tenant=…&lifecycle=active` | Caso atual por cliente; default active, paginação 1–50 |
| GET `/api/orchestration/cases?tenant=…&customer=…&lifecycle=closed` | Casos históricos; `all` inclui ativos e fechados |
| GET `/api/orchestration/cycle?tenant=…&customer=…&case_id=…` | Ciclo exato, abertura, fecho, revisões e contexto revisto/fixo |
| POST `/api/orchestration/close` | Encerramento explícito autorizado |
| POST `/api/orchestration/open` | Inscrição inicial ou novo ciclo autorizado |
| POST `/api/orchestration/review` | Reconhecimento auditável de incerteza, sem resolução/grant |

GET exige membership atual; viewer pode consultar. POST exige operador e sessão
válida do actor. Não se aceita um token em JSON: o servidor usa o cookie da sessão.
Um booleano não prova presença biométrica; é confirmação explícita num pedido
já autenticado e vinculado ao contexto. Uma futura UI deve apresentar essa decisão
humana e não ligar automaticamente o fecho a C06.

Exemplo, após consultar o contexto do caso:

```json
{
  "tenant": "saas-one", "customer": "account-1", "case_id": "case-1",
  "request_id": "close-1", "reason": "Acompanhamento terminado sem valor comprovado.",
  "disposition": "not_recovered", "expected_version": 7,
  "expected_context_hash": "HASH_DEVOLVIDO_PELO_GET", "human_confirmed": true
}
```

O hash ilustrativo deve ser substituído pelos 64 caracteres hex do GET. O servidor
não aceita escolher evidências de outra SaaS/cliente ou afirmar recuperação real.
A resposta é um `ContinuityRecord` com escopo, actor, timestamp, hash e payload
imutável. `CycleContext` fechado devolve o snapshot gravado, não novos dados como
se fizessem parte da decisão passada. `reviews` mostra o reconhecimento da incerteza.

Abertura de sucessor (depois de nova evidência recebida pelo endpoint M07):

```json
{"tenant":"saas-one","customer":"account-1","case_id":"case-2","request_id":"open-2","reason":"Novo episódio sustentado por observação recente.","previous_case_id":"case-1","human_confirmed":true}
```

Revisão:

```json
{"tenant":"saas-one","customer":"account-1","case_id":"case-1","request_id":"review-1","note":"Efeito ainda não confirmado; manter bloqueio.","evidence_ids":[12],"expected_context_hash":"HASH_DEVOLVIDO_PELO_GET","human_confirmed":true}
```

Schemas completos e erros no [OpenAPI](contracts/openapi.json). 400 formato/claims
inválidos; 401 sem sessão; 403 permissão/sessão/evidência fora de escopo; 404 ciclo
inexistente; 409 conflito, snapshot obsoleto, falta de evidência nova, ciclo ativo
ou incerteza; 413 limites; 503 modo/storage/integridade. Production recusa todos
os novos POST, inclusive de operador; GET só consulta dados inativos existentes.
Nenhum endpoint de execução, conector, aprovação C05 ou automação foi acrescentado.

## Armazenamento e atualização explícita

As tabelas novas são `continuity_metadata`, `continuity_openings`,
`continuity_closures`, `continuity_reviews`, `continuity_bindings`. Append-only,
hashes, FKs compostas e guards. As tabelas C02–C06 não são reconstruídas; apenas
recebem fences de continuidade para recusar novas escritas após o fecho.
Os hashes não são assinaturas nem proteção contra administrador do ficheiro.

A restrição antiga `UNIQUE(tenant,customer)` do registo M13 precisa de ser removida;
`UNIQUE(tenant,customer,case_id)` e a guarda de um ativo mantêm o isolamento.
**Não há migração no arranque HTTP.** `orchestration init` cria o schema novo numa
base explicitamente preparada até M12. Para uma base M13, parar o worker/servidor,
fazer backup e atualizar uma cópia privada, verificando-a antes de a usar:

```sh
cd v2
python -m centerway.ops backup --db /caminho/original-m13.sqlite3 --out /caminho/copia-m13.sqlite3
python -m centerway.continuity upgrade --db /caminho/copia-m13.sqlite3
python -m centerway.orchestration list --db /caminho/copia-m13.sqlite3 \
  --user OPERADOR --tenant SAAS --lifecycle all
```

`upgrade` só aceita o schema M13 exato e íntegro. Uma transação copia as linhas de
casos sem alterar valores/hashes, mantém os eventos e motores, cria proveniência
`legacy_upgrade=true` e liga as fontes históricas. Faz `foreign_key_check`; falha
ou interrupção reverte tudo. Schema parcial/adulterado ou upgrade repetido recusam,
sem reparação automática. Nenhuma base existente do utilizador foi migrada nesta
entrega; os ensaios usam exclusivamente ficheiros temporários.

`Orchestrator.register` continua idempotente para o primeiro caso, mas não é um
atalho para sucessores; estes passam por `Continuity.open`. O worker M13 e a sua
paginação/limites mantêm-se, processando somente ciclos ativos. Não há scheduler
ou serviço instalado/publicado nesta missão.

## Verificações e limites

```sh
python -m unittest discover -s tests -p 'test_continuity*.py' -v
CADDY_BIN=/caminho/caddy python -m unittest discover -s tests -v
```

Testes com fixtures explícitas: dois ciclos sucessivos, cada um com C02/C03,
proposta, aprovação própria, efeito persistido de teste e C06; fecho não automático,
nova evidência, decisões não reutilizadas, histórico intacto, concorrência,
pendência/incerteza inclusive legada, autorizações antigas bloqueadas no C05,
revisão sem desbloqueio, snapshot obsoleto, sessão/permissões/isolamento,
HTTPS/OpenAPI, demo expirada, production, backup e upgrade/rollback preservando hashes.

Limitações: incerteza final C05 não pode ser resolvida nesta missão; apenas
reconhecida e mantida bloqueada. Sem conectores reais, prova causal, recuperação
real, novos modelos, frontend, publicação ou alterações na main. A evidência nova
não prova por si só deterioração; o fecho não prova recuperação. Todas as avaliações
de intervenção/verificação continuam de teste/inativas, com as proteções anteriores.
