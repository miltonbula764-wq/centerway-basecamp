# M01 — PostHog outcome-event intake (primeiro conector)

## O que foi implementado

Integração **somente de leitura** com a API privada do PostHog (US/EU)
para uma empresa SaaS autorizada. Consulta uma vez por dia os eventos de
**operação concluída** explicitamente escolhidos pela própria SaaS,
agregados por identificador de **grupo/conta** (PostHog Group Analytics).

Guarda snapshots de contagens diárias na tabela append-only
`centerway.outcome_imports` (migração `intake/001_posthog_outcome_intake.sql`),
com empresa, projeto, evento, índice de grupo, janela UTC, contagens,
hash de dados, produtor e instante de receção. **Não** muda F01–F06, não
fabrica contratos nem intervenções e não expõe dados ao frontend.

**Atenção:** operação concluída na SaaS ≠ benefício empresarial externo,
utilização ≠ valor e contagem inferior ≠ deterioração. A M02
terá de escolher o indicador, validar a suficiência de prova e explicar
os limites da inferência. `verified` do produtor não é prova independente.

## Contrato da SaaS piloto

1. Ter um projeto PostHog com **Group Analytics**, grupos por cliente,
   onde o identificador do grupo corresponde a um ID estável do cliente.
2. Produzir no **backend** um evento específico de sucesso de operação
   (ex.: `workflow_completed`) depois de o trabalho realmente terminar.
   Não utilizar `$pageview`, logins, cliques, início de tarefa ou mera
   atividade. Evitar informação pessoal e dados de negócio sensíveis.
3. Fornecer autorização de leitura de consultas do projeto, âmbito mínimo,
   com credencial mantida **fora de Git, UI e logs**.
4. Confirmar a definição do evento, grupo e período. Sem evento fiável,
   o CENTERWAY deixa os resultados como **inconclusivos**.
5. Histórico anterior é importado por janelas diárias. Cada execução
   processa no máximo 7 dias; reexecuções retomam dias não importados e
   reconsultam os 2 dias finais para corrigir atrasos. Um atraso superior
   a esse período exige reimportação explícita desde a data afetada.

## Instalação e execução — apenas ambiente autorizado

A migração `009` é aditiva a F01–F06; **não aplicar diretamente a uma
base existente sem auditoria de compatibilidade, backup e autorização**.
O acesso PostgreSQL deve ser um login de `centerway_api`, membro apenas
da empresa autorizada, sem proprietário da base, sem BYPASSRLS e com
`sslmode=verify-full` para Neon remoto. O PostHog deverá permitir
consultas de projeto em modo read-only; nunca usar o token público
de captação para consultar dados privados.

O operador define **no ambiente privado do processo**:

```text
CENTERWAY_TENANT_ID=<tenant-uuid-autorizado>
CENTERWAY_INTAKE_DB_DSN=<dsn-nao-privilegiado-com-sslmode-verify-full>
POSTHOG_REGION=eu
POSTHOG_PROJECT_ID=<project-numeric-id>
POSTHOG_GROUP_INDEX=0
POSTHOG_OUTCOME_EVENT=workflow_completed
POSTHOG_PERSONAL_API_KEY=<segredo-read-only>
```

Depois executa:

```bash
python3 recovery-mvp/intake/posthog.py --since 2026-01-01 --max-days 7
```

O `--since` define o início histórico UTC **inclusive**.
`--through` (se fornecido) é **exclusivo**, por omissão hoje UTC.
Não recolhemos o dia ainda em curso. Cada lote diário só é gravado
depois de a resposta completa passar a validação; se falhar, não avança.
As duas últimas datas importadas são revistas quando não há dias
históricos por preencher. Repetir a mesma resposta reutiliza o
mesmo identificador; contagens corrigidas geram nova revisão imutável.

**Sem login PostHog autorizado não é possível afirmar que recebemos
dados reais.** A implementação está pronta para teste integrado;
esta missão não ligou uma conta externa, não utilizou credenciais reais
nem iniciou o cron. A M06 cuidará do agendamento após piloto.

## Regras de integridade e segurança

- Apenas `us.posthog.com` e `eu.posthog.com`; bloqueia redirects
  e respostas acima de 1 MB; timeout curto; nunca inclui API key na URL.
- O evento tem nome validado e não aceita SQL arbitrário do founder.
- Resultado máximo 200 grupos/dia; acima disso **falha fechado** em
  vez de importar dados truncados. A API `/query/` é usada para pequenas
  agregações, não exportação massiva; futuros volumes exigem pipeline próprio.
- Dados ausentes não viram zeros para cada cliente. Sem grupo associado
  ou sem evento, o valor empresarial permanece **desconhecido**.
- Sem emails, identificadores de pessoas, dados brutos de sessões,
  gravação de senhas, chamadas de intervenção ou ações externas.
- `centerway.outcome_imports` é append-only para o login da aplicação:
  só SELECT por RLS; escritas passam pela função controlada, que verifica
  `session_user` e pertença à empresa. Mesmo import_id com conteúdo
  diferente é conflito; histórico preservado.
- Para reconsultas corrigidas, M02 deverá selecionar a **última revisão
  completa** do dia, sem somar várias importações do mesmo intervalo.
  Conserva-se a cadeia de revisões para auditoria.
- O processo escreve apenas o resumo operacional (número de dias).
  Nunca imprime dados de clientes nem valores de tokens.

## Validação automatizada

`bash recovery-mvp/intake/test.sh` inclui: mocks do PostHog (sem Internet),
backfill, reconsulta, tipos/colunas inválidos, limites de grupos,
idempotência e testes PostgreSQL17 usando logins não privilegiados e
isolamento entre SaaS. Os testes não provam disponibilidade nem
autorização do projeto PostHog real.

## Por que este conector?

A engenharia antiga tinha um adaptador PostHog OAuth/Group Analytics
(`src/server/connected/posthog.ts`, PR #29), mas pertence ao produto
legado, com outra stack. Reutilizamos **a seleção de grupos, o padrão
HogQL e a postura de segurança**, sem copiar o backend antigo nem
transportar segredos; a credencial deste piloto fica do lado servidor.

Referências oficiais: https://posthog.com/docs/api ,
https://posthog.com/docs/sql ,
https://posthog.com/docs/product-analytics/group-analytics .
