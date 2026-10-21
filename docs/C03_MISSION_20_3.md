# Missão 20.3 — evidências C03 verificáveis e históricas

Base: `main` em `49354db39939d0f4bf828d7a2acaf5d26a656a1f`.
Execução local: 2026-10-21, PostgreSQL 17 tmpfs, GoTrue 2.177.0,
PostgREST 12.2.3, Bun 1.3.0 e HTTPS local com certificado validado.

## Critérios e resultados

Reutiliza o plano versionado `e2e/c02-ingestion-plan.json`: indicador numérico
`cycle_minutes`, média, janelas UTC `[start,end)` de dois dias, cadência diária,
cobertura 100%, denominador mínimo 2 e duas janelas consecutivas >150 min com
referência anterior abaixo do limiar. A/B pertencem à primeira empresa e C à
segunda, ambas com a mesma definição aprovada. Há exatamente três clientes.
As medições entram pelo emissor HTTPS C01 existente; C02 e C03 são executados
pelas RPCs públicas `run_deterioration_analysis` e `build_evidence_bundle`, com
password grants/JWTs reais e papéis admin/operator. Viewer apenas lê a sua empresa.

| Cliente | C02 esperado e obtido | C03 esperado | C03 obtido | Referências |
| --- | --- | --- | --- | ---: |
| A — deterioração | `deterioration_candidate` | `complete` | `complete` | 6 |
| B — oscilação | `no_deterioration` | `complete` | `complete` | 6 |
| C — dados insuficientes | `insufficient_data` | `insufficient` | `insufficient` | 5 |

O contrato `c03-v1` está definido em
`drizzle/migrations/0010_c03_evidence_builder.sql`. `complete` significa que o
pacote tem evidência completa e consistente; B conserva o resultado C02 sem
deterioração. C é construído como evidência insuficiente, com os motivos
`c02_insufficient_data`, `current_1:coverage_below_minimum` e
`current_1:denominator_below_minimum`: não é promovido a completo. A janela
recente de C tem uma observação, valor 210 e cobertura 50%; não se inventa uma
segunda medição nem um zero. Todos os pacotes têm `actionable_case=false`.

## Integridade verificável

Cada pacote é comparado ao run C02 persistido: empresa, cliente, algoritmo,
input hash, data cutoff, ID do resultado, perfil/versão, classificação,
parâmetros, motivos e snapshot completo. Cada referência é comparada à medição
C01 original em identidade, valor, unidade, fonte, datas, payload hash e correção.
O conjunto de IDs, papéis, ordinais e limites de janela deve ser exato; a sentinela
99999 no fim do intervalo e os dados anteriores à referência ficam fora da evidência.

`e2e/c03-verify-content.sql` reconstrói independentemente o endereço SHA-256 do
conteúdo a partir dos pacotes, indicadores e referências materializados. Preserva
a precisão JSONB e o formato UTC, incluindo ligações de correção. Não chama os
helpers privados nem o construtor C03. Os **seis hashes** conferiram.

## Idempotência, falhas e isolamento

- Quatro construções concorrentes de B resultaram em **uma construção e três
  reutilizações**, sempre com o mesmo pacote e sem duplicar referências.
- Repetições de A, C e da nova versão conservaram os IDs, hashes e todas as linhas
  dos pacotes. As tentativas de reutilização são novos registos de auditoria,
  conforme o contrato append-only.
- Uma trigger temporária, exclusiva da base descartável, lançou uma exceção na
  segunda referência de B. A RPC autenticada devolveu `failed / internal_error:P0001`;
  **zero pacotes/indicadores/referências parciais** ficaram persistidos e a tentativa
  falhada conservou o ator real. A mensagem interna não foi exposta. Após remover
  a trigger, o retry construiu o pacote. A função/trigger de injeção foram removidas.
- Pedidos com um run real da outra empresa devolveram `rejected / run_not_found`,
  sem divulgar evidência. RLS ocultou pacotes, indicadores, referências e tentativas
  da outra empresa em ambas as direções. Viewer, outro tenant e anon não puderam
  construir pacotes AB. INSERT/PATCH/DELETE diretos e acesso ao helper privado
  foram recusados; viewer leu somente os cinco pacotes AB autorizados.

## Correções e versões históricas

A medição 170 de A no dia `as_of−1` foi corrigida para 50 pelo C01, numa nova linha
com `corrects_observation_id`. A nova média recente é **110**, com C02
`no_deterioration`. A nova evidência `complete` tem **sete referências**: seis
efetivas e a original substituída, com `superseded_by` a apontar para a correção.
O run C02 e o pacote C03 ligam-se aos anteriores por `revision_of`; o pacote
original conserva valor 170, os seus seis refs e o hash original.

Uma nova versão do perfil foi criada, editada em draft e aprovada pelas operações
autorizadas. O limiar passou de 150 para 155; unidade, indicador e fingerprint da
medição mantiveram-se compatíveis. O novo run/pacote ancora perfil versão 2 e
limiar 155. Os snapshots anteriores conservam perfil versão 1 e limiar 150.
A mudança de perfil cria um run separado: o contrato C02 liga revisões dentro do
mesmo perfil/as_of, por isso não se inventa uma ligação `revision_of` entre perfis.

Outro run A, com `as_of` uma hora anterior, foi guardado antes da correção e só
teve C03 construído depois da correção e da aprovação do perfil 2. Continuou a
produzir evidência `complete` com seis refs, média 170, perfil 1 e limiar 150,
respeitando o cutoff antigo e excluindo a correção posterior.

Os pacotes originais de A, B e C, incluindo todas as colunas e referências,
permaneceram idênticos após estas operações. As **24 tabelas fora de C01–C03,
auditoria e das transições intencionais de perfil** mantiveram o conteúdo;
C04–C10, objetivos, casos e intervenções não foram alterados.

## Resultado e testes

- **21 medições C01 aceites**, zero rejeitadas, em quatro pedidos: 20 do plano
  reutilizado e uma correção; três clientes em duas empresas.
- **Seis runs C02**, seis pacotes C03, seis indicadores materializados e **37 refs**.
- Tentativas C03: seis `built`, sete `reused`, uma `failed` e duas `rejected`.
- **220 verificações do cenário aprovadas**, incluindo seis content hashes,
  concorrência real, autenticação/RLS, rollback parcial e preservação histórica.
- Suite SQL C03 existente: **40 pass / 0 fail**. Executada numa transação
  revertida; abrange também incoerências de cálculo/hash/refs, cutoff, budget,
  contexto/legacy e imutabilidade. O cenário confirma que os fixtures não deixam
  alterações. Estes testes SQL com papéis/claims são evidência complementar ao
  percurso HTTP com GoTrue real.

**Nenhum defeito de produto encontrado.** Nenhuma lógica C03, migração ou C04–C10
foi modificada. O SQL elevado específico do cenário instala/remove apenas a
injeção de falha; os dados e construções de negócio usam as operações públicas.
Resumo da execução: `docs/C03_MISSION_20_3_RESULTS.json`.

## Reproduzir e executar no GitHub Actions

Pré-requisitos: Docker local, `psql`, Python 3, Bun 1.3.0 e OpenSSL. Numa cópia do
commit sem ficheiros de ambiente e sem containers anteriores com os nomes do ensaio:

```sh
CW_MISSION_STAGE="$(mktemp -d /tmp/centerway-mission20-3-XXXXXX)"
git archive HEAD | tar -x -C "$CW_MISSION_STAGE" --exclude='.env' --exclude='.env.*'
cd "$CW_MISSION_STAGE"
export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=postgres PGDATABASE=cw_e2e
export PGPASSFILE=/dev/null PG_CONTAINER=cw-mvp-db CW_LOCAL_MVP=1
docker run -d --name cw-mvp-db --label centerway.disposable=mvp \
  -p 127.0.0.1:5432:5432 -e POSTGRES_USER=postgres -e POSTGRES_DB=cw_e2e \
  -e POSTGRES_HOST_AUTH_METHOD=trust --tmpfs /var/lib/postgresql/data postgres:17
# Aguardar pg_isready antes do bootstrap.
python3 e2e/start_backend.py --local-mvp
python3 e2e/c03-evidence.py
python3 scripts/mvp/stop-local.py
```

O job independente `c03-evidence` em `.github/workflows/browser-e2e.yml` executa
estes passos numa base vazia e guarda logs/resultados no artefacto `c03-evidence`.
Remove os recursos rotulados mesmo em falha. O cenário lê apenas o plano da
Missão 20.2; não executa o script daquela missão. Não precisa das dependências da
aplicação: emissor Python padrão e handler Edge partilhado executado localmente em Bun.

Resultados completos em `e2e/logs/mission20-3-results.json`, chamadas técnicas sem
segredos em `mission20-3-calls.json` e regressões em `mission20-3-sql.log`.
As contas/chaves ficam em `e2e/private/`, fora dos artefactos. Confirmação de email
é automática apenas no GoTrue local, sem SMTP. Nenhum acesso à Lovable ou ao
Supabase hospedado, NEXORA LAB, publicação ou merge.
