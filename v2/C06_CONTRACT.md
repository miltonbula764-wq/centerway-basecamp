# C06 — verificação de recuperação inativa (Missão 12)

Base: PR #41, commit `062cfc3`. Branch: `centerway-v2/missao-12-recovery`.
Motor interno isolado, sem alteração de Core, C01–C06 sandbox ou M06–M11.
**Só avalia cenários sintéticos de teste. Não prova recuperação real, não executa
intervenções, não encerra casos e não desbloqueia production.**

## Identidade, fontes e critérios

Cada avaliação pertence a `(tenant, customer, execution_id, version)`. Parte de
uma tentativa C05 existente, incluindo pendências. Uma intenção/aprovação sem
despacho não é uma intervenção e não pode adquirir avaliação C06.

O backend verifica permissões atuais, schema/triggers, linhagem e integridade de
C05/C04/C03/C02/configuração/evidências. Fixa hashes da intenção, aprovação,
tentativa, recibo disponível e ponta do diário C05. Alvos e objetivos vêm
**exatamente** da capacidade/configuração fixada na intenção C05; o chamador não
pode fornecer uma meta diferente nem omitir verificações desfavoráveis.

Um plano acrescenta apenas os elementos temporais/computacionais que faltavam ao
catálogo M06: janelas antes/depois, cadência, amostragem, agregação e método de
comparação explícitos. É versionado e limitado à intervenção correspondente.
Declarações de origem e `supplied_by` são fornecidas pelo autor; `actor` regista
separadamente o principal que o Core autorizou. Não são certificação independente
da verdade ou significado comercial das declarações.

Exemplo de plano (`examples/c06/collaboration-plan.json`):

```json
{
  "schema_version": 1,
  "tenant": "collaboration",
  "customer": "fictional-account",
  "execution_id": "exec-1",
  "config_version": 1,
  "capability_id": "reopen-delivery-queue",
  "provenance": {
    "source_ref": "fixture:collaboration:c06-explicit-windows",
    "supplied_by": "synthetic-fixture-author",
    "recorded_at": "2026-01-01T00:06:00Z"
  },
  "checks": [
    {
      "dimension": "operational",
      "criterion_index": 0,
      "sampling": "point",
      "aggregation": "all",
      "method": "transition_to_target",
      "coverage": "aligned_complete",
      "before": {"start":"2026-01-01T00:03:00Z","end":"2026-01-01T00:04:00Z","cadence_seconds":60},
      "after": {"start":"2026-01-01T00:06:00Z","end":"2026-01-01T00:08:00Z","cadence_seconds":60}
    },
    {
      "dimension": "value",
      "criterion_index": 0,
      "sampling": "period",
      "aggregation": "mean",
      "method": "transition_to_target",
      "coverage": "aligned_complete",
      "before": {"start":"2026-01-01T00:02:00Z","end":"2026-01-01T00:04:00Z","cadence_seconds":60},
      "after": {"start":"2026-01-01T00:06:00Z","end":"2026-01-01T00:08:00Z","cadence_seconds":60}
    }
  ]
}
```

**Todas** as verificações de `verification.operational` e `verification.value`
devem aparecer uma vez; omissões ou critérios adicionais são recusados.
Índices são locais à dimensão e à versão da configuração fixada.
Sem critérios de valor declarados, o estado de valor é `insufficient`.

Regras do plano, sem defaults:

- `before.end <= dispatch_at`; `after.start > dispatch_at`. UTC canónico.
- Cada janela tem cadência inteira positiva e número inteiro de intervalos.
  1–1000 intervalos por janela, 2000 no total, 1–100 verificações e 64 KiB por plano.
- `point` para estados/documentos/evidência não métrica; exige observação em cada
  extremo direito dos intervalos `(start,end]`, sem interpolação ou permanência
  inferida. `period` para evidência do tipo metric; cada período tem de coincidir
  exatamente com um intervalo. Não há contagem inferida de eventos.
- `all` exige que cada amostra satisfaça o alvo. `mean`, `sum`, `min`, `max` só
  para campos numéricos e comparação numérica declarada; o plano especifica a
  agregação, sem converter automaticamente taxas/unidades ou inventar métricas.
- O único método é `transition_to_target`: antes não satisfaz o alvo, depois
  satisfaz. Se já satisfazia antes, não se demonstra recuperação. Baseline em
  falta não é deterioração. Números usam frações exatas; delta é apenas
  `after - before` na mesma agregação/campo, não uma nova meta nem causalidade.

## Evidências e tempo

Usa a entrada autenticada M07 existente (`POST /api/evidence`), não uma nova
entrada privilegiada nem os snapshots de efeito do adaptador C05. As mesmas
proteções M07 de escopo, schema, origem, períodos, tamanho e duplicação mantêm-se.
O C06 verifica novamente schema/conteúdo/hashes/proveniência das fontes lidas.

Uma avaliação nova captura **todas** as evidências recebidas nesse cliente até à
transação (`through`). O chamador não escolhe IDs nem um cutoff de ingestão mais
antigo para ocultar contradições. Só a configuração original da intervenção é
usada; IDs de outras versões ficam explicitamente excluídos, nunca convertidos.
`as_of` é um cutoff explícito de acontecimentos/observações, entre o despacho e
o presente. Evidências observadas depois de `as_of` não provam esse resultado.
Dados históricos recebidos tarde só entram numa nova avaliação, sem reescrever
resultados antigos. `through` e hashes permitem reproduzir cada versão.

Para a janela posterior, a fronteira conservadora é o registo do recibo C05,
quando existe, ou o despacho quando ainda não existe recibo. Tanto a ocorrência
como o início de períodos posteriores têm de ser **estritamente posteriores** à
fronteira. Uma janela anterior ao recibo, uma métrica que atravesse a intervenção
ou uma janela ainda não terminada nunca comprovam recuperação. A observação
anterior à intervenção pode servir de baseline; nunca serve como prova posterior.

Amostras em falta, campos opcionais ausentes ou períodos desalinhados dão
`insufficient`. Valores discordantes no mesmo instante/período dão `contradictory`;
não se escolhe a última, a maior ou a mais conveniente. Não há extrapolação,
correção de evidências originais, resolução de contradições ou associação causal.

## Avaliações independentes

| Campo | Estados e significado |
| --- | --- |
| `execution` | `demonstrated`: adaptador reportou efeito **de teste**; `not_demonstrated`: reportou falha sem efeito; `execution_uncertain`: pendente/incerto, recibo posterior ao cutoff ou incoerência temporal |
| `operational_recovery` | `demonstrated`, `not_demonstrated`, `insufficient`, `contradictory`, apenas segundo evidência sintética e critérios operacionais |
| `value_recovery` | Os mesmos estados, apenas segundo evidência e critérios de valor declarados; nunca deriva do estado operacional |

Cada verificação inclui alvo, janelas/amostras/agregados, referências com fonte,
identidade externa, momento, versão/hash e receção, exclusões, lacunas,
contradições e justificação. Não se troca uma das dimensões pela outra.
Todas as verificações de uma dimensão têm de demonstrar a transição para essa
dimensão ser demonstrada. Contradição tem precedência sobre insuficiência;
insuficiência impede uma conclusão positiva.

`summary_state` é conservador: execução incerta prevalece; depois contradição,
insuficiência e não demonstração. Um recibo de falha ou incerto não é promovido
por observações positivas de operação/valor: estas dimensões são **independentes**
e não atribuem a mudança à intervenção. C06 não resolve nem repete C05. Se uma
chamada C05 em curso terminar normalmente e registar o seu recibo, uma nova
avaliação pode consultá-lo; a versão que observou pendência permanece intacta.
Um resultado C05 final incerto continua incerto, mesmo com novos dados positivos.

Todas as respostas de avaliação conservam:

```json
{
  "operational_state": "inactive",
  "assessment_scope": "synthetic_test_only",
  "real_recovery_demonstrated": false,
  "operational_recovered": null,
  "value_recovered": null,
  "causal_attribution": "not_established",
  "execution_authorized": false,
  "core_transition_authorized": false,
  "automatic_closure": false,
  "external_execution": "blocked"
}
```

`demonstrated` neste contrato é demonstração **no cenário sintético fornecido**.
Não é recuperação real de cliente nem autorização para continuidade/encerramento.

## Interface interna, versões e auditoria

`RecoveryRepository` (`centerway.recovery`), principal autenticado por backend
local de confiança; nenhum `user`/role proveniente de IA ou browser é autoridade:

```python
repo.append_plan(user, tenant, customer, execution_id, document, expected_version=0)
run = repo.evaluate(user, tenant, customer, execution_id, plan_version=1,
                    as_of="2026-01-01T00:08:00Z")
history = repo.history(user, tenant, customer, execution_id)
old_run = repo.get(user, tenant, customer, execution_id, version=1)
```

Operator atual para declarar/avaliar, membership atual (incluindo viewer) para
ler. Tenant, cliente e intervenção explícitos em todas as consultas. Alterações
concorrentes do plano usam optimistic version check. Avaliações iguais reutilizam
o resultado; novas evidências, plano, cutoff ou snapshot C05 criam nova versão.
`history` fornece cabeças atuais de evidências, planos, avaliações e diário C05
para um futuro Core decidir quando precisa de reavaliar. `get` é histórico,
nunca afirma que uma versão antiga representa a situação atual.

Setup opcional cria apenas `recovery_metadata`, `recovery_plans` e
`recovery_runs`, com FKs compostas, unicidade, triggers append-only e cadeias de
hashes. Leituras reproduzem deterministicamente as avaliações, incluindo uma
pendência histórica cujo recibo só apareceu depois. Integridade/schema/triggers
inválidos recusam sem reparar. Não há DDL no arranque HTTP, migração de dados do
utilizador ou escrita nos motores anteriores. Hashes locais não são assinaturas
nem proteção contra administrador do ficheiro; backup/segurança do host mantêm-se.

Erros: 403 permissões, 404 escopo/versão inexistente, 409 tentativa ausente ou
conflito de versão do plano, 413 limites, 503 storage/runtime/fontes inválidos ou
produção indisponível. Plano/cutoff malformado dá `ValueError` na interface local;
CLI emite só `c06_refused`, sem eco de dados/segredos. São avaliações inativas,
não há endpoint C06 novo nem mudança no contrato HTTP/OpenAPI existente.

## Exemplos e teste reproduzível

Três pares de ficheiros em `examples/c06/*-plan.json` e `*-after.json`:

- collaboration: transição operacional e de valor demonstradas no cenário;
- billing: transição operacional, sem transição de valor;
- support: alvos de recuperação não demonstrados.

São exclusivamente fictícios. Datas de referência supõem despacho/recibo C05
em `2026-01-01T00:05:00Z`; os testes usam um **relógio de fixture explicitamente
identificado** e o adaptador SQLite de teste M11. Não existe relógio simulado nem
adaptador instalado no runtime. Usar estes dados num C05 com outra data não pode
produzir recuperação indevida; as janelas têm de corresponder à intervenção.

```sh
cd v2
python -m unittest discover -s tests -p test_recovery.py -v
CADDY_BIN=/caminho/caddy python -m unittest discover -s tests -v
```

Os testes criam bases e contas temporárias, percorrem M06–C06 e usam apenas
fixtures C04/test adapter. Não exigem credenciais externas. Setup/CLI para uma
**cópia** já preparada até M11, com tentativa C05:

```sh
python -m centerway.recovery init --db /caminho/copia.sqlite3
python -m centerway.recovery append-plan --db /caminho/copia.sqlite3 \
  --user OPERADOR --tenant SAAS --customer CLIENTE --execution-id ID \
  --file /caminho/plano-explicito.json --expected-version 0
python -m centerway.recovery evaluate --db /caminho/copia.sqlite3 \
  --user OPERADOR --tenant SAAS --customer CLIENTE --execution-id ID \
  --plan-version 1 --as-of MOMENTO_UTC
python -m centerway.recovery history --db /caminho/copia.sqlite3 \
  --user OPERADOR --tenant SAAS --customer CLIENTE --execution-id ID
```

Limitações: somente contratos/intervenções sintéticos; nenhuma verificação real,
conector, certificação da verdade das fontes, prova causal, interface pública,
automação em massa, ação adicional ou encerramento no Core. Só janelas absolutas,
amostras completas e método `transition_to_target`; sem interpolação, tolerância
inventada, migração entre configurações, conversão de unidades ou metas inferidas.
Production e efeitos externos continuam bloqueados; demo mantém a expiração.

Missão 13: [orquestração inativa M06–M12](ORCHESTRATION_CONTRACT.md) consome avaliações C06 sem executar novamente intervenções ou encerrar casos.
