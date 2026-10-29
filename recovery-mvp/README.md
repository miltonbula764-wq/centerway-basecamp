# CENTERWAY MVP — F01: fundação e contrato de valor

Implementação independente, exclusivamente neste diretório. Não importa código,
perfis, observações, autenticação ou regras da engenharia anterior. Não contém
frontend, IA, intervenções, deteção automática ou simulador. Não há dados reais,
objetivos predefinidos ou configuração específica de um nicho.

## Executar os testes técnicos

Requisitos: Docker, Bash e Python 3.12+; a imagem usada é PostgreSQL 17 Alpine.
A partir da raiz do repositório:

```sh
./recovery-mvp/tests/run.sh
```

O script cria uma base descartável, aplica apenas `sql/001_foundation.sql` e
`sql/002_internal_read_port.sql`, testa e remove o contentor mesmo em caso de erro.
Não publica portas, não usa credenciais externas e não aplica migrações ao projeto
antigo. O modo `trust` existe apenas neste contentor descartável de testes.

Os testes usam ligações reais como `tenant_a`, `tenant_b` e `outsider`, sem
superuser ou propriedade das tabelas. Os casos normais são transações revertidas.
Fixtures e o teste de concorrência fazem commit apenas na base descartável, porque
é necessário verificar exclusão entre transações independentes.

Cobertura: ambos os sentidos e limites dos quatro estados; ausência, utilização,
qualidade parcial/disputada e cobertura incompleta; tipos e campos obrigatórios;
proveniência e compatibilidade; isolamento de empresas e referências de clientes;
ausência de acesso anónimo; proibição de escrita direta; versões, autoria, auditoria,
rollback, contexto histórico e concorrência na criação/correção.

## Instalação isolada

Usar uma **nova base PostgreSQL 17**, com administrador próprio; aplicar os dois
ficheiros SQL, por ordem, uma única vez, com `psql -X -v ON_ERROR_STOP=1`.
Não adicionar estes SQL à cadeia de migrações antiga. Nenhuma instalação em ambiente
partilhado ou produção foi realizada nesta missão.

O administrador provisiona `companies`, `clients` e `memberships`, bem como logins
PostgreSQL `NOSUPERUSER NOBYPASSRLS` membros do grupo `centerway_api`. Cada principal
recebe apenas as empresas autorizadas. As credenciais são geridas fora desta
fundação. O principal é sempre `session_user`, nunca um campo JSON, cabeçalho,
`SET app.tenant_id` ou resultado de `SET ROLE`.

Não partilhar um login entre empresas sem autorização para ambas. Um futuro
adaptador HTTP terá de autenticar o utilizador e manter esta fronteira; simplesmente
ligar como administrador e passar um tenant não é suportado. Esta F01 não implementa
integração com JWT/Supabase nem altera o login da aplicação antiga.

## Conteúdo

- [Contrato e interfaces internas](CONTRACT.md): campos, semântica e limites.
- `sql/001_foundation.sql`: modelo, validação, versões, RLS, auditoria e escrita.
- `sql/002_internal_read_port.sql`: leitura de contexto por versão exata.
- `tests/`: integração real com PostgreSQL, sem dependências Python externas.

## Limitações assumidas em F01

- Um indicador numérico por contrato; vários objetivos exigem contratos distintos.
  Não há agregações entre indicadores, inferência causal, significância estatística,
  normalização de unidades, taxas com denominador, sazonalidade ou séries temporais.
- A comparação é absoluta e determinística, com sentido `higher` ou `lower`.
  Baseline, mínimo e alvo são fornecidos explicitamente; não são inferidos.
- Uma avaliação referencia no máximo uma evidência consolidada. Evidências em conflito
  não são reconciliadas automaticamente. O produtor deve declarar `disputed` quando
  não puder sustentar a qualidade, e a avaliação será inconclusiva.
- `verified` é uma declaração do produtor autorizado, não uma verificação independente.
  Os localizadores e hashes são registados; os documentos externos não são obtidos,
  armazenados ou autenticados. O hash não é calculado sobre ficheiros nesta camada.
- O esquema conserva o histórico e rejeita mutações, mas um administrador/superuser
  pode alterar o esquema ou desativar proteções. Não é um arquivo WORM nem uma
  auditoria criptográfica. Falhas/rejeições não persistem no log transacional; o futuro
  serviço deve registá-las no seu log operacional.
- O provisionamento é administrativo e append-only. Não há gestão de utilizadores,
  papéis funcionais ou revogação de memberships por API. Para suspender um principal,
  o administrador deve revogar o seu acesso à base/role e terminar as sessões ativas.
- `read_contract_context` devolve todo o histórico do contrato pedido, sem paginação.
  A F01 não define SLA, retenção, idempotência de pedidos ou migração de dados antigos.
  Uma repetição de escrita recebe conflito de revisão; o chamador deve consultar a
  versão gravada antes de decidir repetir.

A entrega termina em F01. Nenhum motor futuro foi implementado.
