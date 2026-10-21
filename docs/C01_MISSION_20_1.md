# Missão 20.1 — ingestão contínua C01

## Reprodução isolada

Pré-requisitos: Docker local, cliente PostgreSQL `psql`, Python 3, Bun e OpenSSL.
Usar uma cópia isolada do repositório sem `.env`/`.env.*`, com dependências
instaladas a partir de `bun.lock`. Não usar `start-local.py --api`: os seus seeds
operacionais criam clientes e executam operações fora do âmbito desta missão.

Nessa cópia, sem containers anteriores com estes nomes:

```sh
docker run -d --name cw-mvp-db --label centerway.disposable=mvp \
  -p 127.0.0.1:5432:5432 -e POSTGRES_USER=postgres -e POSTGRES_DB=cw_e2e \
  -e POSTGRES_HOST_AUTH_METHOD=trust --tmpfs /var/lib/postgresql/data postgres:17
export PGHOST=127.0.0.1 PGPORT=5432 PGDATABASE=cw_e2e PGUSER=postgres
export PGPASSFILE=/dev/null PG_CONTAINER=cw-mvp-db CW_LOCAL_MVP=1
# Aguardar pg_isready antes do bootstrap.
python3 e2e/start_backend.py --local-mvp
python3 e2e/c01-continuous.py
python3 scripts/mvp/stop-local.py
```

O cenário exige uma base nova, cria exatamente três clientes por REST sob RLS,
um perfil aprovado pelas RPCs autorizadas e credenciais por administrador com
login/password grant GoTrue real. A confirmação de email é automática apenas
nesta instância sintética, sem SMTP. Aplica todas as migrações locais do journal.
O servidor HTTPS usa o handler partilhado com a função Edge; não prova o gateway
nem a instalação Supabase hospedada.

`e2e/c01_emitter.py` é um emissor independente, apenas com biblioteca padrão
Python. Recebe endpoint HTTPS, ficheiro privado da chave, payload JSON e UUID
do pedido; não consulta clientes, não chama RPCs e não conhece a base de dados.
Em falha de transporte preserva a indicação de repetir o mesmo pedido. O cenário
usa esse emissor para todos os pedidos normais; o teste de resposta perdida usa
uma ligação TLS que fecha depois do commit, sem ler a resposta.

O cenário verifica valores numéricos com nove casas decimais e texto, identidade,
fonte, perfil, cobertura `[start,end)`, proveniência e auditoria de integração,
repetições de pedidos/observações, conflitos, correções sem ramificação, atomicidade,
dados inválidos, quatro reenvios concorrentes, falha real do upstream,
ligação recusada, resposta perdida após commit, expiração, revogação e quota real.
As medições iniciais excedem os limiares de deterioração do perfil. Após cada
pedido compara o conteúdo de todas as tabelas públicas fora das escritas C01 e
auditoria. Não chama operações de análise, decisão, casos ou intervenção.

Os resultados técnicos sem segredos ficam em `e2e/logs/mission20-results.json`;
as contas e chaves descartáveis permanecem em `e2e/private/`, fora do Git.
Reenvios contam como tentativas, nunca como novas observações persistidas.

## Resultado da execução de 2026-10-21

Base: `5ddd8a4b632668f5fd0eb6567d80c8b859bbefd5`. PostgreSQL 17,
GoTrue 2.177.0, PostgREST 12.2.3 e HTTPS local com certificado descartável validado.

| Contagem | Resultado |
| --- | ---: |
| Clientes sintéticos | 3 |
| Tentativas de envio de linhas de medição | 45 |
| Linhas aceites, incluindo repetições | 24 |
| Linhas rejeitadas | 19 |
| Tentativas com falha de ligação/upstream | 2 |
| Observações únicas persistidas | 18 |
| Reenvios idempotentes aceites | 6 |
| Tentativas HTTP, incluindo sondas sem medições | 105 |

As 24 aceitações incluem uma confirmação observada no banco cuja resposta HTTP
foi deliberadamente perdida. As 19 rejeições incluem as duas linhas do lote
atómico inválido. As falhas de ligação foram recuperadas com os mesmos
identificadores. As 61 sondas de quota não contêm linhas de medição.

O cenário principal validou individualmente 17 observações. No ensaio inicial de
quota, as comparações por tabela demoraram o suficiente para atravessar um minuto
UTC: o pedido final foi legitimamente aceite, acrescentando uma 18.ª observação.
Corrigiu-se o **ensaio**, consolidando o snapshot num único statement e separando
as 31 sondas rápidas das comparações do banco. A regressão de quota foi repetida
na mesma base, preservando todos os resultados: 30 respostas 400 e a 31.ª 429 com
`Retry-After`, dentro do mesmo minuto real. Não foi encontrado defeito no produto.
Uma execução nova do cenário corrigido persiste as 17 observações previstas.

Os clientes terminaram com 10, 4 e 4 observações. Originais, correções, identidade,
fonte, perfil, períodos, datas, valores e auditoria foram verificados. As 32 tabelas
fora das escritas C01 mantiveram o conteúdo; não surgiram análises, avaliações,
casos, notificações ou intervenções. O estado de polling criado no onboarding
permaneceu sem tentativas nem execução.

Aprovados: SQL permissões **67**, ingestão **35**, C02 **70**, C03 **40**;
privilégios C01 e privilégios de clientes; **131 testes unitários em 15 ficheiros**
(incluindo seis do transporte C01); `tsc --noEmit`; regressão corrigida de quota.
As suites SQL usam papéis reais e rollback. O transporte isolado unitário é
evidência complementar; a campanha HTTP usou autenticação e banco reais.

Contagens verificadas também em `docs/C01_MISSION_20_1_RESULTS.json`. Sem mudanças
na API, migrações ou C02–C10, sem Lovable/Supabase hospedado, publicação ou merge.
