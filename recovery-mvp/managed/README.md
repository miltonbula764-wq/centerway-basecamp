# M67 — demonstração sintética Render Free + Neon Free

Este perfil mantém F01–F06 e o transporte HTTP. Não substitui a autenticação por Neon Auth. SQLite e TLS direto continuam disponíveis nos entrypoints locais anteriores.

## Execução e limites

- Um serviço Render `free`, runtime Python, branch da missão; auto-deploy desligado.
- Build: `pip install -r recovery-mvp/api/requirements.txt`.
- Start: `gunicorn --chdir recovery-mvp/managed -c gunicorn.conf.py 'render_app:load_render_app()'`.
- `PYTHON_VERSION=3.12.14`; `CENTERWAY_MANAGED_CONFIG` é JSON secreto apenas no serviço, nunca em Git. Contém logins PostgreSQL individuais limitados, hashes de passwords e DSN separado das sessões. Não contém DSN administrativo.
- Origem CORS inicial: `https://getcenterway.com`, provisória, não prova frontend ligado. Substituir pela origem hospedada efetivamente verificada na missão de integração.
- `/health` é apenas liveness, sem consulta PostgreSQL: os probes da plataforma não devem consumir o compute gratuito do banco continuamente. Login, `/v1/session` e jornada verificam dependências. Não criar cron de keep-alive.
- Render termina TLS e redireciona HTTP para HTTPS antes da aplicação. O adapter exclusivo de Render verifica contexto de deployment e hostname atribuído, ignora todos os cabeçalhos Forwarded/X-Forwarded e fixa o esquema nesse limite de confiança. Não utilizar noutro host. Não é TLS nativo no socket Gunicorn. Não confiar em IP fornecido pelo cliente: limiter conservador único, dez tentativas/minuto por processo, sem garantia distribuída ou persistente após restart.
- Operações não recebem retry automático. Após suspensão, repetir GET autorizado pode ser seguro; POST só com o mesmo request_id e após inspeção do recibo. O contrato de idempotência permanece no banco.
- Quotas limitam disponibilidade; não prometem disponibilidade contínua. Não fazer upgrade, acrescentar pagamento ou habilitar recursos pagos.

## Provisionamento

`provision.py` aceita ficheiro privado com DSN administrativo direto (`verify-full`, CA confiável) e recusa schemas/roles existentes. Usa PostgreSQL 17, migrações originais, migração aditiva das sessões e quatro logins sintéticos. Saída em diretório privado fora do checkout. Não executar no build/start do Render e não repetir automaticamente após falha. O bootstrap é administrativo; runtime usa apenas roles próprias.

O conjunto de migrações também pode ser aplicado diretamente pela integração Neon, em ordem, no projeto novo: verificar frescura antes; proteger passwords e config; gravar o progresso sem dados sensíveis. As roles de runtime são criadas por SQL, não pelo painel Neon, e não têm BYPASSRLS, superuser, CREATEDB ou CREATEROLE.

Não existe endpoint público de registo/seed. Credenciais da demonstração são privadas. A aplicação deve recusar credencial administrativa. As autorizações de intervenção são configuradas separadamente pelo operador, com limites e validade; nenhuma autorização implícita é criada no arranque.

## Sessões

`session_store=postgres`, `session_postgres={principal,dsn}`. Migração `sql/001_sessions.sql`, login em `cw_session_store` sem acesso ao schema de negócio. Apenas digests SHA-256 de tokens aleatórios são persistidos. TTL, logout e hash de configuração continuam aplicáveis entre reinícios. Um lock transacional por username mantém o limite de dez sessões mesmo com logins concorrentes. Falhas de banco fecham o acesso com 503; não viram 401 nem provocam replay de operações.

## Backup lógico cifrado

Operador confiável com `pg_dump`/`pg_restore` 17 e `age`, fora do processo web. Config privado deve conter `dsn` direto com TLS verificado e `synthetic_only: true`. Não inclui passwords no argv; usa serviço libpq temporário 0600. Dumps contêm histórico e recibos, sem passwords de roles e sem linhas de sessão.

`backup.py backup --owner-config /caminho/owner.json --archive /caminho/copia.age --recipient age1...`

`backup.py restore --owner-config /caminho/owner-destino.json --archive /caminho/copia.age --identity /caminho/chave-age`

Só restaurar cópias de origem confiável: pg_restore executa SQL. Encriptação age verifica adulteração, mas não identifica o produtor. O envelope verifica formato, versão, migrações e SHA-256 do dump; limite de 32 MiB, apropriado apenas a esta demonstração. Config, arquivo e chave exigem permissões privadas; destinos existentes são recusados. Limite protege a aceitação do arquivo, não é quota de memória durante pg_dump/desencriptação: operador deve verificar o tamanho do banco antes da cópia.

Destino obrigatoriamente diferente e sem os schemas. Provisionar antes somente as roles compatíveis, sem migrações nem seed; restaurar preserva ACLs e identidade dos atores. Restaurar NÃO repõe passwords nem a configuração da aplicação: voltar a emitir/bindar configuração de runtime com as credenciais do destino. Sessões ficam vazias e os utilizadores autenticam-se novamente. Verificar jornada, isolamento e replay de intervenção antes de promover qualquer restauro. Nunca restaurar por cima da instalação ativa.

Backups lógicos não dependem de funcionalidades pagas Neon. Não existe agendamento, cópia externa durável ou custódia de chave configurados automaticamente. Temporários privados são removidos, sem promessa de apagamento físico. O restauro é transacional; em falha não fazer limpeza destrutiva automática.

## Validação

`bash recovery-mvp/managed/test.sh` usa PostgreSQL 17 Docker com TLS real, roles reais e age; cobre sessões entre instâncias, expiração/revogação, concorrência, RLS, permissões, falhas, cabeçalhos e backup/restauro de F01–F06 com replay de intervenção sem duplicação. O wrapper pg_dump/restore existe apenas no teste para usar clientes 17 no container. Reexecutar as suites anteriores em CI. Testes locais/Actions não comprovam URL pública ou frontend hospedado.

Fontes: [Render HTTP/TLS](https://render.com/docs/web-services#https), [limites Free](https://render.com/docs/free), [Neon planos](https://neon.com/docs/introduction/plans).
