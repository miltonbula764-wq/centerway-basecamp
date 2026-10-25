# Missão 08 — C02 adaptável e inativo

Parte do PR #37 (`f5fc63c`). Motor isolado `c02-adaptive-v1`, sem substituir o C02
sandbox ou alterar Core, C01–C06, API HTTP 1.2.0, contratos de integração/evidências
ou a interface. Não há deteção automática ao receber um lote, ações, investigação,
IA, endpoint novo ou ativação de production.

O resultado demonstra uma comparação **nos dados e critérios declarados**. Não
atesta independentemente a veracidade do fornecedor, perda financeira, churn ou
retenção real. Toda avaliação tem `operational_state: inactive` e
`proof_scope: declared_criteria_and_supplied_evidence`; classification vem da
configuração original (synthetic/declared), sem promoção automática a operação real.

## Contrato dos critérios v1

Documento obrigatório, sem campos extra/defaults:

```json
{
  "schema_version": 1,
  "tenant": "configured-saas",
  "config_version": 1,
  "provenance": {
    "source_ref": "supplier:explicit-criteria-declaration",
    "supplied_by": "authorized-supplier",
    "recorded_at": "2026-10-25T00:00:00Z"
  },
  "criteria": [
    {
      "id": "supplier-rule",
      "description": "Critério explicitamente fornecido, não inferido pelo motor",
      "dimension": "operational",
      "metric_ref": "declared-metric",
      "goal_refs": ["declared-goal"],
      "evidence_refs": ["declared-evidence"],
      "source": {"kind": "metric", "definition_id": "declared-metric", "field": "value"},
      "method": "threshold",
      "aggregation": "mean",
      "comparison": "gt",
      "threshold": 10,
      "threshold_unit": "seconds",
      "window_seconds": 120,
      "cadence_seconds": 60,
      "coverage": "aligned_complete"
    }
  ]
}
```

É um exemplo sintético de estrutura; **10 não é um limite recomendado nem predefinido**.
Métrica, objetivo, fonte, evidências, unidade e limiar têm de existir/ser declarados
para a SaaS. O motor nunca preenche estes campos, cria objetivos ou escolhe limites.

| Campo | Regras |
| --- | --- |
| schema_version / config_version | Contrato inteiro 1; versão de configuração explícita e imutável |
| tenant / provenance | Mesmas regras de IDs, origem declarada, autor declarado e timestamp UTC da Missão 06 |
| criteria | 1–100 entradas com IDs únicos; documento até 65536 bytes |
| dimension | operational ou value, sem conversão entre elas |
| metric_ref / goal_refs | Métrica configurada; objetivos explícitos que referenciam essa métrica |
| evidence_refs | Não vazio, sem duplicados; evidências declared que referenciam a métrica |
| source | metric/value ou evidence/campo numérico configurado; nunca eventos transformados em contagens implícitas |
| threshold / threshold_unit | Número finito explícito até ±(2^53−1); unidade da métrica, ou ratio para mudança relativa |
| window_seconds / cadence_seconds | Inteiros positivos até 2^31−1; janela múltipla da cadência; até 1000 buckets usados por critério |
| coverage | Apenas aligned_complete: não existe política de preencher lacunas com zero ou escolher amostras por proximidade |

Uma regra value exige **fonte evidence numérica, de tipo metric, referenciada
diretamente nos objetivos declarados**. Um sinal operacional ou métrica de uso não
é promovido a prova de perda de valor. Cada dimensão mantém o seu próprio estado;
ausência de critérios de valor significa valor insuficiente, não estável.

## Métodos e amostragem

As janelas são ancoradas no `as_of` UTC explícito. A janela atual termina em as_of;
quando necessário, o baseline é a janela imediatamente anterior de igual duração.
Não há relógio, janela, cadência, meta ou baseline escolhido automaticamente.

- threshold: compara o agregado atual com threshold.
- absolute_change: compara `atual − baseline` com threshold, na unidade declarada.
- relative_change: compara `(atual − baseline) / abs(baseline)` com threshold em ratio.
  0.5 significa 50%; não se convertem percentagens implicitamente. Baseline zero
  devolve insuficiente, sem infinito, substituição de denominador ou método alternativo.

Agregação obrigatória: sum, mean, min ou max. Comparação obrigatória: lt, lte, gt ou
gte. A comparação verdadeira demonstra deterioração nessa dimensão; falsa significa
estável apenas face aos critérios/janelas declarados e com cobertura completa.

Cada bucket tem exatamente cadence_seconds. Métricas e evidence de tipo metric
exigem período exatamente igual ao bucket; outras evidências numéricas são snapshots
no instante final exato do bucket. A janela de pontos é `(início, fim]`; não se
interpola ou desloca amostras. Períodos parcialmente sobrepostos, outra cadência ou
pontos não alinhados impedem uma conclusão, mesmo existindo outras amostras válidas.

Todos os buckets da fonte primária **e de cada evidência referenciada** são exigidos.
Essas referências constituem proveniência/cobertura explícita; o motor não inventa
relações aritméticas entre campos de definições distintas. Agrega-se apenas o campo
numérico da source. Um campo opcional sem valor fornecido é ausência, nunca zero.

Afirmações iguais para um mesmo bucket não pesam duas vezes. Valores diferentes
em campos sobrepostos da mesma fonte/bucket são contraditórios, incluindo alegações
mais tardias sobre o mesmo período. Não se usa "o último vence" nem a média entre
afirmações em disputa. Campos complementares não são por si só um conflito.

A observação deve ter occurred_at ≤ as_of. Uma alegação sobre o baseline registada
mais tarde, mas ainda até as_of, é considerada e pode contradizer a primeira.
Receção posterior é permitida em avaliação retrospetiva se o seu ID estiver no
snapshot through; o resultado guarda esse corte e a hora da avaliação. Afirmações
posteriores a as_of não provam o passado. Dados de outras versões nunca são usados.

A aritmética usa frações exatas dos valores numéricos normalizados/persistidos, sem
arredondamentos novos em C02. Medidas calculadas são `{numerator: "…", denominator:
"…"}`; por exemplo 0.1 + 0.2 = 3/10 não excede indevidamente um limiar de 0.3.
Isso não recupera precisão já perdida antes da persistência da evidência.

## Estados, prova e histórico

Cada critério e cada dimensão têm quatro estados:

| Estado | Significado |
| --- | --- |
| demonstrated | Deterioração operacional ou perda de valor demonstrada pela comparação explícita, limitada aos dados fornecidos |
| stable | Cobertura completa e sem conflito; a comparação de deterioração não se verifica |
| insufficient | Falta critério/dado/campo/cobertura, amostragem incompatível ou baseline relativo zero |
| contradictory | As afirmações relevantes são incompatíveis; não há medida/conclusão arbitrada |

O resumo de uma dimensão é conservador: contraditório prevalece; depois insuficiente;
com todos os critérios completos, qualquer demonstração prevalece sobre estável.
Os resultados individuais permanecem disponíveis. Não existe um estado global que
confunda deterioração operacional com perda de valor, nem pesos inventados.

A avaliação guarda algoritmo, SaaS/cliente, versão/hash da configuração, versão/hash
e snapshot dos critérios, as_of, through, IDs/hashes das evidências, janelas,
agregados, critérios aplicados, lacunas, conflitos, autor e momento do servidor.
O recibo do resultado e versões dos critérios são append-only, com hashes. Mesmo
input gera o mesmo run_id; nova evidência/critério/corte pode criar outro resultado,
sem recalcular ou alterar o anterior. `get` verifica hashes e reproduz a avaliação
original com os inputs fixados antes de a devolver. Mudanças semânticas futuras
exigem outra versão de algoritmo; não se reinterpretam resultados históricos.

## Preparação e interface interna para futuro C03

Requer base já provisionada e armazenamento das Missões 06–07. Apenas o responsável
local instala a estrutura opcional; o servidor HTTP não faz setup/migração:

```sh
cd v2
python3 -m centerway.detection init --db /private/runtime.sqlite3
python3 -m centerway.detection append-criteria --db /private/runtime.sqlite3 \
  --user authorized-operator --tenant configured-saas \
  --file /private/supplier-criteria.json --expected-version 0
python3 -m centerway.detection evaluate --db /private/runtime.sqlite3 \
  --user authorized-operator --tenant configured-saas --customer account-a \
  --criteria-version 1 --as-of 2026-01-01T00:04:00Z
python3 -m centerway.detection get --db /private/runtime.sqlite3 \
  --user authorized-reader --tenant configured-saas --customer account-a --run-id 1
```

Caminhos/contas são marcadores, não credenciais. Setup recusa estrutura existente ou
parcial, sem reparação; fazer backup antes de preparar uma base futura. Só bases
novas temporárias foram usadas nesta missão. expected-version impede substituir
critérios concorrentes; config_version no documento fixa o contrato da SaaS.
O CLI é local confiável: user seleciona uma conta existente, não constitui login ou
prova remota. Não expor este comando como serviço. Não há endpoints novos nesta missão.

```python
from centerway.detection import DetectionRepository
repository = DetectionRepository(existing_store)
run = repository.evaluate(authenticated_operator, tenant, customer, criteria_version=1, as_of=explicit_utc_time)
# O futuro C03 recebe o ID e consulta o resultado, sem ativar operações:
auditable = repository.get(authenticated_member, tenant, customer, run['id'])
```

Memberships atuais são verificadas na transação: só operadores criam critérios e
avaliações; membros consultam critérios/resultados da sua SaaS. Cliente, versão e
run_id nunca autorizam acesso por si. O prazo da demo continua obrigatório. Production
continua com as seis tabelas/endpoints antigos bloqueados, mesmo após um resultado
demonstrated; não há flag ou endpoint de ativação. Evidências originais e Core.history
não são escritos pelo motor.

## Exemplos sintéticos e limites

Há três conjuntos completos em [examples/detection](examples/detection): colaboração,
faturação e suporte, cada um com `*-config.json`, `*-criteria.json` e `*-evidence.json`.
Os limiares/objetivos/medidas foram declarados pelo autor das fixtures para QA, não
inferidos de empresas reais ou recomendados por nicho. Nenhum nome de SaaS entra na
lógica do motor. A avaliação dos exemplos usa as_of `2026-01-01T00:04:00Z`.

```sh
python3 -m centerway.detection validate --config-file examples/detection/collaboration-config.json \
  --file examples/detection/collaboration-criteria.json
python3 -m unittest discover -s tests -p test_detection.py -v
CADDY_BIN=/caminho/para/caddy python3 -m unittest discover -s tests -v
```

Production continua a recusar configurações synthetic; trocar apenas a classificação
não transforma uma fixture em dado real. Mesmo declarações privadas não são verificadas
externamente. O administrador do SQLite/SO continua confiável; hashes não são assinaturas.

V1 suporta agregados numéricos em cadência fixa, limites e diferenças absolutas/relativas.
Não há contagens implícitas de eventos, percentis, ML, sazonalidade, contradições semânticas
entre definições distintas, descoberta de limiares, interpretação de métricas cumulativas,
causas ou agendamento. Leituras validam o histórico e o cálculo decorre numa transação
SQLite; não há distribuição ou ensaio de carga de produção. Mantêm-se os limites de
1000 evidências por cliente da Missão 07. A versão de configuração deve ser igual em
todos os dados usados; não se inferem equivalências entre versões nem entre unidades.
Sem Lovable, conectores, serviços pagos, publicação ou alterações na main.

## Verificação executada

111 testes Python passaram sem skips, incluindo 22 novos testes C02: três SaaS e
métodos, quatro estados, separação operação/valor, cobertura e campos ausentes,
contradições atuais/tardias, baseline zero, precisão/comparações, alinhamento,
permissões/isolamento, versões, concorrência, rollback, integridade, backup e recusa
de ativação em production. Três ensaios Chromium passaram (sandbox de 150 clientes
responsivo, HTTPS privado com Pixel 7 emulado e CORS); Caddy real em loopback passou
na regressão. Compilação Python, validação systemd e git diff --check passaram.
Não houve teste de conectores, tráfego real, Android físico ou recuperação real.
