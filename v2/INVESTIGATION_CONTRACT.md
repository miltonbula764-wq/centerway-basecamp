# Missão 09 — investigação estruturada C03, isolada e inativa

Parte do PR #38 (`56b08a4`). `c03-structured-v1` organiza um resultado C02 específico
e o seu snapshot de evidências. Não substitui C03 sandbox, não investiga causas com
IA, não decide C04 e não ativa intervenções. Não há endpoint novo ou mudança no
contrato HTTP 1.2.0. Core, C01–C06 operacionais e os motores M06–M08 ficam intactos.

**Toda hipótese permanece unconfirmed; causal_status é sempre not_established.**
Um requisito observado como incumprido não se torna causa da deterioração. A origem
é uma declaração autenticada na entrada M07, não atestação externa de verdade.

## Contrato da declaração v1

Documento até 65536 bytes, campos obrigatórios e sem extras:

```json
{
  "schema_version": 1,
  "tenant": "configured-saas",
  "customer": "account-a",
  "c02_run_id": 1,
  "provenance": {
    "source_ref": "supplier:investigation-declaration",
    "supplied_by": "authorized-reviewer",
    "recorded_at": "2026-10-25T00:00:00Z"
  },
  "hypotheses": [],
  "requirements": []
}
```

SaaS, cliente e ID têm de corresponder ao C02 indicado e ao escopo autorizado.
Não existe fallback para o C02 mais recente ou para evidências de outra versão.
provenance segue as regras da Missão 06: referência textual de origem, autor
**declarado** e timestamp UTC. O autor autenticado da revisão e a hora de gravação
são registados separadamente pelo servidor; não se confia num actor no documento.
Listas admitem 0–100 entradas. IDs seguem `[a-z0-9][a-z0-9_-]{0,63}`; declarações/
statements até 2000 caracteres. Valores e campos seguem o contrato versionado da SaaS.

### Hipóteses

```json
{"id":"supplier-hypothesis","statement":"Uma condição pode estar relacionada; causalidade não testada.","support_refs":[{"evidence_id":13,"field":"paused"}],"contrary_refs":[]}
```

São declarações do operador, nunca texto gerado como explicação factual. Cada lado
admite até 100 referências, sem duplicados ou sobreposição entre lados. A evidência
e o campo devem existir no snapshot C02 da SaaS/cliente/configuração. Observações
posteriores a as_of não podem apoiar/refutar uma hipótese desse momento.

support_refs significa **relevância alegada pelo operador**, não uma validação
semântica ou causal. contrary_refs também não é arbitrado. Mesmo com várias citações,
o estado fica unconfirmed e support_scope=operator_declared_references_only.
Hipóteses sem referências são aceites apenas como declarações explicitamente não
sustentadas; não ganham factos ou causas. Campos como confirmed/state/causes são
recusados na entrada. Texto livre, incluindo afirmações causais do operador, continua
uma citação não confirmada e nunca é executado ou promovido a facto.

### Requisitos declarados e impedimentos sustentados

```json
{"id":"supplier-prerequisite","declaration":"Pré-requisito explicitamente declarado pelo fornecedor, não prova causal.","criterion_id":"operational-degradation","window":"current","selector":{"kind":"evidence","definition_id":"operation-state","field":"paused"},"comparison":"eq","expected":false}
```

O critério/janela tem de existir no resultado C02; baseline só é aceite quando o
C02 o tem. selector refere event/metric/evidence e um campo declarado na configuração
fixada. Para metric, o campo é value. expected é obrigatório e do tipo exato declarado;
sem converter strings em números ou booleanos. eq/ne admitem tipos declarados;
lt/lte/gt/gte apenas números/timestamps. Timestamps são normalizados em UTC e a
comparação numérica não acrescenta arredondamentos.

O motor consulta todas as observações elegíveis desse selector no snapshot e janela.
Pontos usam `(início,fim]`; períodos devem estar contidos na janela e occurred_at ≤
as_of. Não escolhe a última observação e não extrapola a situação até ao presente.
A comparação aplica-se a **cada observação**, não à soma/média de uma janela. A
relação de pré-requisito é declarada pelo fornecedor, não descoberta ou confirmada
pelo motor.

| Resultado do requisito | Significado |
| --- | --- |
| supported | Existe observação não disputada que viola a condição declarada |
| not_observed | As observações avaliáveis não violam a condição; não prova ausência universal de impedimentos |
| insufficient | Falta observação/campo/período compatível para avaliar, sem substituir ausência por false/zero |
| contradictory | O campo relevante tem afirmações incompatíveis; nenhuma delas é escolhida como verdadeira |

Só supported entra em supported_impediments, com claim_type=
observed_requirement_noncompliance e support_scope=observed_condition_only. Inclui
violation_refs, compliant_refs e checked_refs, com momentos/versões acessíveis nos
factos citados. O resultado **não prova causalidade, persistência do impedimento ou
necessidade de uma intervenção**. Lacunas continuam registadas mesmo quando há um
incumprimento observado. Sem requisitos declarados, não se fabricam impedimentos
por nomes de campos, correlação ou por o C02 ter demonstrado deterioração.

## Resultado e rastreabilidade

A resposta mantém grupos distintos:

- facts: observações originais, payload e proveniência por registo (SaaS/cliente,
  origem, ID externo, momentos, autor M07, versão/hash da configuração e hash do
  registo). claim_scope=recorded_observation, sem reinterpretar texto como verdade
  independente. Campos em disputa são marcados; observações posteriores a as_of
  são identificadas como after_c02_as_of, sem as usar como suporte atual.
- c02_findings: resultados reproduzidos e critérios/janelas originais do C02,
  preservando a separação entre operação e valor. Não são causas.
- hypotheses: declarações, referências a favor/contrárias e eventuais referências
  disputadas, sempre não confirmadas.
- supported_impediments: apenas incumprimentos observados de requisitos declarados,
  limitados às observações referenciadas.
- missing_information: lacunas de amostras utilizáveis reportadas pelo C02, dimensão
  sem critérios, ou selector sem observações/campos/períodos avaliáveis. São lacunas
  **neste snapshot**, não uma afirmação de inexistência de dados no fornecedor.
- analysis_limitations: limitações C02 como baseline relativo zero/amostragem
  incompatível; não são fabricadas como falta de observações ou impedimentos de negócio.
- contradictions: referências aos campos/afirmações incompatíveis e deteção por
  snapshot ou pelo C02. Inclui conflitos de contexto que o C02 não usou nos cálculos.

As referências `{evidence_id,field}` resolvem-se nos facts, com toda a proveniência.
Lacunas/limitações apontam para o critério/janela e para o C02 fixado na raiz. O
resultado inclui IDs/hashes C02, configuração e critérios, as_of, through, classificação
synthetic/declared, versão C03 e proveniência da declaração. operational_state é
sempre inactive; não existe uma lista de causas confirmadas ou uma decisão C04.

## Versões, integridade e consulta interna

Instalação opcional e explícita, com base M06–M08 já preparada:

```sh
cd v2
python3 -m centerway.investigation init --db /private/runtime.sqlite3
python3 -m centerway.investigation append --db /private/runtime.sqlite3 \
  --user authorized-operator --tenant configured-saas --customer account-a \
  --c02-run-id 1 --file /private/investigation-declaration.json --expected-version 0
python3 -m centerway.investigation get --db /private/runtime.sqlite3 \
  --user authorized-reader --tenant configured-saas --customer account-a \
  --c02-run-id 1 --version 1
```

São caminhos/contas ilustrativos, não credenciais. init recusa estrutura existente/
parcial; não cria uma base ausente, não repara, não migra no arranque HTTP. Fazer
backup antes de preparação futura. Só bases temporárias foram usadas nesta missão.
CLI é administração local confiável: user seleciona um principal existente, não
constitui autenticação remota. Não expor a CLI nem os seus resultados privados como
serviço público.

Cada revisão pertence a `(tenant, customer, c02_run_id, version)` e guarda declaração,
resultado, autor, hora, hashes do C02/input/recibo e da revisão anterior. expected-version
é obrigatório; 0 cria a primeira revisão. Um reenvio exato com a mesma versão esperada
reutiliza a revisão originalmente criada, **que pode já não ser a mais recente**.
Outro conteúdo com versão desatualizada dá 409; não se faz overwrite ou merge implícito.
Sem version, get lê a mais recente; para auditoria/consumo, fixar a versão recebida.

C02 e todas as evidências são verificados/reproduzidos antes de reconstruir as revisões
C03. Novas evidências não entram num C02 antigo; exigem novo C02 e outra investigação.
Triggers impedem UPDATE/DELETE e associação a um C02 de outro escopo. Falha de escrita
reverte a revisão; corrupção/proteções ausentes dá recusa/503, sem reparação. Hashes
locais não são assinaturas e não substituem controlo do proprietário do SQLite/SO.

Interface para futuro motor de IA/C04, ainda **sem essa integração**:

```python
from centerway.investigation import InvestigationRepository
repository = InvestigationRepository(existing_store)
review = repository.get(authenticated_member, tenant, customer, c02_run_id, version=1)
# review['payload'] separa factos, hipóteses, impedimentos, lacunas e contradições.
# Nenhum desses campos autoriza confirmação causal, decisão ou execução.
```

Só operadores criam revisões; membros consultam resultados da própria SaaS. Memberships
atuais, SaaS, cliente e C02 são verificados na mesma transação. A expiração da demo
continua obrigatória. Production mantém os endpoints e tabelas de negócio bloqueados,
mesmo quando a investigação contém supported_impediments.

## Exemplos e limites

[examples/investigation](examples/investigation) contém declarações e lotes de contexto
sintéticos para colaboração, faturação e suporte, reutilizando os dados/configurações
M08. Não são causas descobertas ou requisitos recomendados por nicho. Os IDs dos
exemplos correspondem à ordem de preparação dos testes (C02 1/2/3 e observações de
contexto 13/26/39); noutro ambiente, usar os IDs efetivamente devolvidos, sem inventar
referências ou reclassificar fixtures synthetic como dados reais em production.

```sh
python3 -m unittest discover -s tests -p test_investigation.py -v
CADDY_BIN=/caminho/para/caddy python3 -m unittest discover -s tests -v
```

Não há confirmação/descoberta de causas, teste de hipóteses, IA, scoring de confiança,
C04, intervenções, conectores ou HTTP novo. Não se deduzem contradições semânticas
entre definições/origens/momentos distintos; mantêm-se citações humanas sem as julgar.
A leitura reconstrói o histórico, com custo linear nas revisões e nos dados limitados
pela Missão 07; não é ensaio de escala de produção. Sem publicação, Lovable, serviços
pagos ou alterações na main. Fluxo operacional e aprovação ficam para missões futuras.

## Verificação executada

131 testes Python passaram sem skips, incluindo 20 novos testes C03: três SaaS,
proveniência, hipóteses não confirmadas, ausência sem impedimentos fabricados,
contradições de contexto/C02, corte temporal, revisões/reenvios concorrentes,
permissões/isolamento, integridade/rollback, backup e inatividade de production.
Três ensaios Chromium passaram (sandbox responsivo/150 clientes, HTTPS privado com
Pixel 7 emulado e CORS); a regressão Caddy em loopback passou. compileall, verificação
systemd e git diff --check passaram. Não é prova de causas ou integração real.

A [Missão 10](C04_CONTRACT.md) usa uma revisão C03 fixada como contexto de propostas
IA/C04 inativas, sem promover hipóteses a causas nem ativar o Core.
