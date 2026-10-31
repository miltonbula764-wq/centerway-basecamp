# Missão 67 — backend público sintético

Verificação em 2026-10-31. Estado: **backend público funcional para demonstração sintética**. Frontend hospedado ainda desligado; piloto real e produção não aprovados.

## Publicação confirmada

- API: https://centerway-synthetic-m67.onrender.com
- Liveness: https://centerway-synthetic-m67.onrender.com/health — HTTP 200, `synthetic_only=true`, `readiness=not_assessed`.
- Verificação TLS externa com curl: `ssl_verify_result=0`. HTTP redirecionou para HTTPS com 301.
- Render: serviço `srv-dbisih6c6qcc739irri0`, Frankfurt, plano **free**, auto-deploy **no**, Python 3.12.15. Deployment `dep-dbissi7lk1mc73fl1qh0` terminou **live** no commit `1a15ea778240c1a4c47e7a8909c718457c03c810`.
- Neon: projeto `calm-art-16243825`, branch `br-gentle-sky-b9z072su`, PostgreSQL 17, organização confirmada **free**, Frankfurt. Compute fixo 0,25 CU; quotas adicionais: 360000 segundos de compute, 1000000000 bytes de transferência e 500000000 bytes de tamanho lógico.
- Nenhum upgrade, cartão, serviço pago, conta nova ou aceite de termos foi executado. O titular confirmou o workspace Render e ausência de método de pagamento. **Zero utilização Lovable** nesta missão; o saldo informado de 38,6 créditos não foi confundido com o saldo Work/Codex.

## Implementação

Sessões PostgreSQL guardam apenas digests de tokens; preservam TTL, logout, revogação e invalidação por alteração de configuração. Lock transacional por username limita sessões concorrentes. Role separada de sessões sem acesso ao negócio; quatro logins de negócio sem superuser, BYPASSRLS, CREATEDB, CREATEROLE ou REPLICATION. Nenhum DSN administrativo está na configuração de runtime. SQLite permanece como modo local.

O entrypoint Render confia apenas no limite de rede/TLS documentado da plataforma, verifica o hostname atribuído e ignora cabeçalhos de encaminhamento. Não representa TLS nativo no socket Gunicorn. Há um limiter conservador global por processo; não é proteção distribuída de produção. `GUNICORN_CMD_ARGS=--access-logfile /dev/null` desativa o access log predefinido da plataforma. Sem logs de corpos, credenciais ou tokens nos probes.

Backup lógico cifrado com age, verificação de integridade/migrações e restauro transacional em base nova. Exclui sessões do arquivo: o destino exige nova autenticação e credenciais próprias. Não depende de snapshots ou backups pagos do fornecedor.

Motores SQL, migrações F01–F06, suites anteriores e infraestrutura TLS local preservados. PRs #64–#67 continuam empilhados; não houve merge nem alteração a main.

## Evidências automatizadas do código publicado

Os **oito workflows** do SHA publicado terminaram com success:

| Validação | Evidência |
| --- | --- |
| 97 regressões anteriores: 60 + 11 + 8 + 4 + 7 + 7 | [Backend e transporte](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/41196113207) |
| 8 testes Chromium, duas execuções | Mesmo workflow, job chromium-transport |
| 10 testes novos: sessões, concorrência, RLS/TLS, falhas, restauro F01–F06, CLI Gunicorn e não encaminhamento de bearer em redirects | [Managed security](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/41196113155) |
| Recuperação operacional anterior | [Recovery](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/41196113148) |
| API, HTTPS, demonstração persistente, handoff e preflight | [API](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/41196113184), [HTTPS](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/41196113149), [persistência](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/41196113183), [handoff](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/41196113178), [preflight](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/41196113152) |

O restauro lógico foi ensaiado contra PostgreSQL 17 real com TLS e roles reais em CI, incluindo adulteração/chave errada, histórico preservado e replay de intervenção sem duplicação. Isso **não equivale a exportação/restauro do projeto Neon publicado**.

## Evidências contra a URL pública

- Percurso F01–F06 executado pela API com credenciais reais da demonstração, usando a fixture sintética anterior: investigação, autorização administrativa limitada, uma intervenção sintética e reavaliações inconclusiva/completa. Recuperação observada sintética; causalidade não estabelecida.
- **16 verificações antes** do novo deployment: login Alice/Bob/reader, identidade, diretório, isolamento nos dois sentidos, CORS/preflight, cabeçalhos hostis, permissões de escrita, escrita/replay e logout.
- **9 verificações depois**: sessão e jornada preservadas, mesmo recibo de escrita, revogação mantida, isolamento e logouts finais.
- Credenciais inválidas receberam 401. Cabeçalhos Forwarded falsificados, enviados com curl e bearer privado, mantiveram identidade correta; nenhum redirect foi seguido.
- Compute Neon suspenso explicitamente para ensaio. O novo `started_at` confirmou reativação; a mesma sessão recebeu 200 e a jornada permaneceu igual. Também foi observado idle por inatividade antes da publicação.
- Replay público da intervenção após deployment comparou **exatamente o recibo original** e manteve uma execução. Contagens antes/depois: **22 recibos, 1 execução, 61 linhas de auditoria**.
- Os probes recusam redirects e guardam request_id antes da escrita. O caminho urllib devolveu 503 text/plain para cabeçalhos hostis antes da aplicação; curl nativo validou o GET autenticado. Não se introduziu retry automático de POST. Falhas de transporte foram inspecionadas antes de replays explícitos com o mesmo request_id.

## Handoff e limites restantes

1. A origem CORS é provisoriamente `https://getcenterway.com`; não prova frontend hospedado funcional. Verificar a origem publicada exata e só depois configurar Lovable. O transporte existente está preparado, mas a UI live continua desligada. Não consumir créditos sem estimativa e preservar pelo menos 30.
2. `demo=false` identifica proteções de transporte, **não proveniência real**. O perfil é exclusivamente sintético; respostas autenticadas incluem `X-Centerway-Data: synthetic-only`. Manter rótulos na futura interface.
3. O caso público tem autorização de intervenção finita, sintética, com limite de uma execução e validade de 24 horas. Não renovar, resetar ou inventar autorização automaticamente.
4. Health check Render disponível nesta integração: TCP. `/health` é só liveness; autenticação/jornada verificam dependências. Não há alertas externos ou keep-alive configurados. Restart/redeploy Render e suspensão/reativação Neon foram testados; cold start Render após 15 minutos ocioso ainda não foi medido.
5. **Falta cópia externa durável, custódia de chave e exportação/restauro real do Neon.** O executor desta sessão não resolve o hostname PostgreSQL para ligação TCP direta (`Temporary failure in name resolution`) e não dispõe de cliente pg_dump 17/Docker. A integração SQL foi suficiente para provisionar e verificar, não para executar pg_dump. Não publicar credenciais em Actions como alternativa.
6. Não ativar snapshots apenas por existir limite de um no Free: a [documentação específica](https://neon.com/docs/guides/backup-restore) também apresenta cobrança de armazenamento. Nenhum snapshot ou agendamento foi criado. O procedimento lógico está em `recovery-mvp/managed/backup.py` e o runbook em `recovery-mvp/managed/README.md`.
7. Credenciais/configuração ficam privadas no serviço e nos ficheiros operacionais; não existem passwords ou tokens neste handoff. Não presumir durabilidade dos ficheiros temporários do executor. A custódia das credenciais sintéticas de login deve ser resolvida por canal seguro antes da missão da interface; se necessário, emitir novas credenciais sintéticas pelo operador sem expor DSNs administrativos.
8. Nenhuma validação comercial, utilização de clientes reais, disponibilidade de produção ou integração Lovable hospedada é afirmada.

Próxima missão: ligar o frontend hospedado à API já publicada, com origem exata, sessões e isolamento testados no browser; manter a demonstração sintética. Resolver a cópia externa/restauro Neon e monitorização antes de qualquer piloto com dados reais.
