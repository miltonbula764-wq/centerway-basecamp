# Missão 20.2 — C01 → C02

Base: `main` em `cfbf4413267d4ce75d9b550133865d3fd3408fab`. Execução local em
2026-10-21, PostgreSQL 17 descartável em tmpfs, GoTrue 2.177.0, PostgREST 12.2.3,
Bun 1.3.0 e HTTPS local com certificado validado. Sem acesso hospedado.

## Critérios definidos antes da ingestão

O plano versionado `e2e/c02-ingestion-plan.json` contém as medições e resultados
esperados. Os três clientes partilham um único indicador numérico aprovado,
`cycle_minutes`, unidade `min`, classificação `outcome`, direção
`lower_is_better`. Regras: média, baseline fixo 100, janela de dois dias,
cadência diária, cobertura mínima 100%, denominador mínimo duas observações,
limiar absoluto **>150**, duas janelas consecutivas, alvo numérico 120.

Contrato: `supabase/tests/c02_semantics.md`, algoritmo `c02-v2`. Com `as_of` em
2026-10-21 00:00 UTC, os intervalos são fechados à esquerda e abertos à direita:
referência `[15,17)`, janela anterior `[17,19)`, janela recente `[19,21)` de outubro.
Um candidato exige ambas as janelas correntes acima de 150 e referência abaixo
do limiar. `persistent_condition` significa que a referência também já estava
acima; não é o estado esperado de A neste ensaio de transição.

## Resultados esperados e obtidos

| Cliente | Referência | Janela anterior | Janela recente | Cobertura recente | Esperado | Obtido |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| A — deterioração persistente nas duas janelas | 100 | 160 | 170 | 100% | `deterioration_candidate` | igual |
| B — oscilação temporária | 100 | 170 | 100 | 100% | `no_deterioration` | igual |
| C — dados insuficientes | 100 | 160 | 210, uma observação | 50% | `insufficient_data` | igual |

C conserva o valor observado 210; não inventa zero nem confirma deterioração.
Os motivos são `current_1:coverage_below_minimum` e
`current_1:denominator_below_minimum`. A declaração de cobertura no C01 não
substitui a cobertura calculada pelo C02.

B tem `below_target=false`, mas isso é apenas uma comparação numérica com 120:
não constitui declaração de cumprimento de objetivo. As saídas foram verificadas
contra o contrato de campos, sem conclusões causais ou de cumprimento, com
`actionable_case=false`. O conteúdo das **30 tabelas públicas fora de C01/C02 e
auditoria**, incluindo C03–C10, objetivos e casos, ficou inalterado.

## Evidência adicional

- **C01 real:** quatro pedidos HTTPS, 21 medições enviadas e aceites, zero
  rejeitadas. As primeiras 20 incluem dados históricos e uma sentinela 99999
  exatamente em `as_of`; a 21.ª é o dado tardio. Sem INSERT direto de medições.
- **Fronteiras e isolamento:** IDs de evidência exatos por cliente/janela; medições
  exatamente nos inícios pertencem à janela seguinte; a sentinela no fim e os
  dados anteriores à referência ficam fora da análise corrente.
- **Histórico:** em `as_of=2026-10-19`, A tem médias correntes 160 e 100, referência
  100: `no_deterioration`, pois apenas uma janela ultrapassa o limiar. Mesmo input
  reutiliza o run e o cutoff originais, sem escrever outro histórico.
- **Dado tardio:** A recebe 190 em 2026-10-20 12:00, depois do primeiro cutoff. O
  C01 não executa C02. Uma nova operação humana cria uma revisão ligada ao run
  anterior, com nova identidade de input, média recente `530/3 ≈176,6667`, três
  observações e os mesmos dois slots de cadência: cobertura 100%. O run antigo
  permanece idêntico; B e C reutilizam os seus runs originais.
- **Autenticação/RLS:** password grants e JWTs reais; admin/operator executam,
  viewer lê mas não executa; utilizador de outra empresa e anon são recusados.
  A outra empresa não tem clientes adicionais. Perfis/cliente inexistentes e
  `as_of` futuro são recusados; INSERT/PATCH diretos de runs/resultados são negados.
- **Conclusão da base:** três clientes, 21 observações, cinco runs C02 criados
  apenas pelas operações humanas previstas. Nenhuma causa inventada, declaração
  de cumprimento, abertura de caso ou intervenção automática.

Passaram **133 verificações** do cenário e as suites SQL de permissões **67**,
C01 **35** e C02 **70**, com `fail=0`. As suites usam papéis reais e rollback;
o ensaio verifica que não deixam clientes ou histórico adicionais. Não foi
encontrado defeito no produto; nenhuma lógica C01/C02 ou C03–C10 foi alterada.
Resumo verificado: `docs/C02_MISSION_20_2_RESULTS.json`.

## Reprodução e CI

Pré-requisitos: Docker local, `psql`, Python 3, Bun 1.3.0 e OpenSSL. Preparar uma
cópia isolada do commit, sem `.env`/`.env.*`, e sem containers anteriores com os
nomes reservados pelo ensaio. Não executar os seeds operacionais de outras missões.

```sh
CW_MISSION_STAGE="$(mktemp -d /tmp/centerway-mission20-2-XXXXXX)"
git archive HEAD | tar -x -C "$CW_MISSION_STAGE" --exclude='.env' --exclude='.env.*'
cd "$CW_MISSION_STAGE"
export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=postgres PGDATABASE=cw_e2e
export PGPASSFILE=/dev/null PG_CONTAINER=cw-mvp-db CW_LOCAL_MVP=1
docker run -d --name cw-mvp-db --label centerway.disposable=mvp \
  -p 127.0.0.1:5432:5432 -e POSTGRES_USER=postgres -e POSTGRES_DB=cw_e2e \
  -e POSTGRES_HOST_AUTH_METHOD=trust --tmpfs /var/lib/postgresql/data postgres:17
# Aguardar pg_isready antes do bootstrap.
python3 e2e/start_backend.py --local-mvp
python3 e2e/c02-ingestion.py
python3 scripts/mvp/stop-local.py
```

O job independente `c02-ingestion` em `.github/workflows/browser-e2e.yml` aplica
todas as migrações da main numa base vazia, executa o mesmo cenário e regressões,
guarda apenas os logs/resultados técnicos e remove os recursos rotulados mesmo
em falha. O emissor usa a biblioteca padrão Python e o servidor importa o mesmo
handler da função Edge. Não é necessário instalar dependências da aplicação.

Resultados completos em `e2e/logs/mission20-2-results.json`, pedidos sem segredos
em `mission20-2-c01-requests.json` e logs SQL no artefacto `c02-ingestion` do Actions.
As contas sintéticas ficam apenas em `e2e/private/`. O GoTrue local confirma email
sem SMTP; isto prova autenticação por palavra-passe/JWT, não entrega de emails.
O gateway e a instalação Supabase hospedados não são exercitados.
