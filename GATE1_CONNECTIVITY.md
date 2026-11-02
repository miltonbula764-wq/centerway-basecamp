# T03-G1: preparação do diagnóstico GitHub Actions → Neon

Issue [#74](https://github.com/miltonbula764-wq/centerway-basecamp/issues/74).
Base: T02/PR #72, `aecc8aca64a9d7ce333dc1a907b5661132ba1ccd`.
Esta entrega prepara exclusivamente a fase 1. Não executa T03, backup, restauro,
login PostgreSQL, SQL, deploy, alteração de configuração ou criação de recursos.
O repositório é público: considerar todos os logs e ficheiros publicados como públicos.

## Dois workflows, autoridades distintas

- `recovery-mvp-neon-connectivity-ci.yml`: abre automaticamente no PR; não recebe
  secrets nem ambiente protegido. Executa actionlint 1.7.7 com checksum fixado,
  valida os contratos YAML e testes de segurança com DNS/TCP simulados. Os testes
  não fazem ligações externas; o caso de processo real usa hostname ausente.
- `recovery-mvp-neon-connectivity.yml`: **apenas** `workflow_dispatch`, em
  `ubuntu-24.04`, dois minutos de limite do job, concorrência máxima de uma execução.
  Exige SHA integral igual ao commit selecionado, checkout fixado e sem persistir
  token. O hostname vem exclusivamente do secret de ambiente
  `CENTERWAY_NEON_DIAGNOSTIC_HOST`; não há hostname de produção no código, input,
  argumento de processo, output ou artefacto. Não aceita DSN, URL, IP ou pooler.

O script resolve DNS, recusa endereços privados/reservados (inclusive respostas
mistas), e tenta até oito endereços públicos na porta fixa 5432. Fecha a primeira
ligação bem-sucedida sem enviar dados da aplicação: nenhum TLS/StartupMessage,
credencial, SQL ou `pg_dump`. O DNS corre num processo separado; o processo pai
interrompe-o após 15 segundos. TCP tem orçamento adicional interno de oito segundos,
dentro desse teto global, e até três segundos por tentativa. Não usa relay nem
altera firewall, allowlist, proxy ou TLS. Apenas códigos constantes são publicados;
exceções, stderr do filho, hostname e IPs nunca são encaminhados ao log.

## Execução futura e auditoria pelo telemóvel

**Não configurar secrets ou executar o diagnóstico nesta missão.** A Issue #74
autoriza preparação e CI sem secrets. O titular deverá autorizar a execução real
separadamente; a autorização da T03 não substitui este limite específico.

1. Rever o diff e o SHA integral do PR. Confirmar a visibilidade pública do repo e
   o orçamento Actions: runner standard Linux, sem larger runner, sem artefactos,
   caches ou serviços pagos. Em repositórios públicos os runners standard são
   gratuitos; políticas da organização, disponibilidade e quotas podem limitar
   a execução. Não mudar para uma modalidade paga para contornar uma falha.
2. Em GitHub → Settings → Environments, configurar previamente
   `centerway-gate1-diagnostic`: required reviewers, prevent self-review, impedir
   bypass administrativo quando disponível e permitir apenas a branch revista.
   **O nome no YAML não comprova proteção**: GitHub pode criar automaticamente um
   ambiente sem regras se ele não existir. Não executar nesse estado. Se o plano
   não permitir os controlos, parar e usar um terminal privado autorizado.
3. Após autorização, guardar nesse ambiente somente o hostname direto Neon no
   secret `CENTERWAY_NEON_DIAGNOSTIC_HOST`. Sem porta, password, DSN, nome de base
   ou utilizador. Não criar secret de credencial PostgreSQL para esta fase. Não
   ativar `ACTIONS_STEP_DEBUG`/`ACTIONS_RUNNER_DEBUG`; nunca usar `set -x`, `env`,
   `printenv`, `nslookup`, `dig` ou dumps de exceções para investigar este job.
4. Resolver a restrição de registo do GitHub: `workflow_dispatch` exige que o
   ficheiro exista na branch predefinida. Um novo workflow apenas neste PR pode
   não aparecer na aba Actions e não aceitar dispatch, mesmo com `--ref`.
   **Este PR não altera `main` e não tenta dispatch/API/trigger alternativo.**
   Um registo mínimo posteriormente revisto e explicitamente autorizado na branch
   predefinida, ou um terminal privado já autorizado, é uma dependência pendente.
   Não fazer merge da cadeia T02 apenas para registar este diagnóstico.
5. Quando registado/autorizado: Actions → “CENTERWAY Gate 1 manual DNS and TCP
   diagnostic” → Run workflow → selecionar a branch revista → preencher
   `reviewed_sha` com o SHA integral dessa branch. O aprovador deve confirmar o
   mesmo SHA antes de libertar o ambiente. Um novo push invalida a revisão anterior.
6. Guardar URL da execução, run ID, attempt, SHA, actor/aprovador, horário e o
   pequeno JSON de resultado, sem copiar configurações privadas. Rever os logs
   públicos. A CI do PR e o diagnóstico real são provas diferentes.

Referências: [workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch),
[environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments),
[billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

## Resultados e interpretação

Exemplo de formato, **não resultado medido contra Neon**:

```json
{"application_bytes_sent":0,"database_login_attempted":false,"port":5432,"result":"tcp_reachable","schema_version":1}
```

| Código | Significado / próxima ação |
|---|---|
| `tcp_reachable` | DNS resolveu para IP público e um TCP abriu/fechou. Não prova TLS, identidade, permissões, dump, restauro ou acesso futuro. |
| `invalid_configuration` | Secret ausente ou hostname inválido; falha antes de DNS. Rever configuração em privado. |
| `dns_failed` | Resolução falhou ou não devolveu endereços. Rever DNS/egress legítimos. |
| `non_public_address` | Resolução inclui endereço não público; nenhuma ligação TCP é tentada. |
| `tcp_unreachable` | Tentativas recusadas/expiradas; nenhuma ligação confirmada. |
| `timeout` | Prazo global ou orçamento TCP excedido; sem diagnóstico adicional público. |
| `internal_error` | Falha inesperada ou resposta do filho inválida; rever código sem imprimir secrets. |

Só `tcp_reachable` termina com exit 0. Qualquer outro resultado bloqueia avanço.
Runners hosted são efémeros, IPs/rotas podem mudar entre jobs e tentativas; um sucesso
pontual não garante disponibilidade para exportação posterior. Uma conexão TCP pode
ser aceite por um intermediário: não comprova o servidor PostgreSQL nem o seu TLS.
Pode haver tráfego de infraestrutura e eventos de conexão no fornecedor; não há
escritas na base. Não modificar Neon para facilitar o teste.

Se TCP falhar, usar apenas runner existente autorizado com egress permitido ou
terminal privado autorizado. Não abrir o banco indiscriminadamente à Internet,
contratar runner, criar relay, contornar firewall ou enfraquecer validação TLS.

## Plano posterior de backup (não implementado nem autorizado aqui)

Após TCP real e nova autorização para operações sensíveis:

1. Definir o destino **privado durável externo ao GitHub e ao Neon**, custódia,
   retenção, espaço, integridade e método de transferência já existente e gratuito.
   Actions artifacts expiram e não são custódia durável.
2. O titular gera/guarda a chave privada `age` no seu equipamento seguro; fornecer
   somente a chave pública `age1…`. Nunca gerar a chave privada no runner nem
   enviá-la ao repo, PR, logs ou chat. Testar a capacidade de decifrar em privado.
3. Rever escopo completo do export: dados A/B, histórico, auditoria, recibos,
   sessões, esquemas, ownership e grants necessários à recuperação. A rotina
   `recovery-mvp/managed/backup.py` exclui sessões; não a chamar de backup completo
   T03 sem resolver essa diferença. Papéis/configuração de runtime exigem estratégia
   de restauro e custódia separada; nenhum segredo de configuração vira output.
4. Credentials de leitura/export mínimas e separadas do runtime, somente em
   Actions Secrets do ambiente protegido. PostgreSQL17 `pg_dump` compatível,
   endpoint direto, hostname e CA com `sslmode=verify-full`, timeouts e revisão
   das permissões. Não usar conta runtime para tarefas administrativas. Não
   disponibilizar secrets a código de PR não revisto ou a `pull_request_target`.
5. Export consistente → stream `age` → ciphertext, sem dump em claro no workspace,
   log ou artefacto. Verificar sucesso de **ambos** os processos, integridade e
   checksum do ciphertext. Se artefacto cifrado temporário for necessário, rever
   acesso/retenção e confirmar transferência/custódia externa antes de o apagar.
6. Restauro completo somente em PostgreSQL17 isolado, autorizado e gratuito, com
   credenciais exclusivas, sem rotas/escritas para a origem. Comparar referências,
   contagens e hashes do baseline real obtido no export: as 25 operações observadas
   anteriormente são referência histórica, não valor a forçar se a origem mudou.
   Verificar A/B, recibos, auditoria e política das sessões sem revelar tokens.
   Destruir o ambiente efémero após preservar a prova segura e a custódia externa.

Nenhum workflow de backup/restauro, secret, destino ou chave é criado nesta fase.
Snapshot/clone Neon e CI local não substituem o backup externo e restauro comprovado.
Gates 2–5 continuam bloqueados. Não há publicação, ativação T01, consumo Lovable ou
prontidão de produção nesta entrega.

## Validação desta preparação

Localmente: actionlint 1.7.7 aprovou os dois workflows; 15 testes passaram com
Python3.12/PyYAML6.0.3, incluindo falhas DNS/TCP, IP privado, fallback IPv6, timeout,
sanitização, ausência de envio de dados, separação de secrets/CI e entrypoint real
sem hostname. `git diff --check` aprovado. Não foram repetidos motores F01–F06 ou
testes T02: nenhum deles mudou. O check independente do PR repete esta validação;
consultar o seu resultado no SHA exato. Nenhum destes testes prova TCP para Neon.
