# Equipas e convites — missão 13

Base main `d389f2d`, incluindo a navegação de Casos da Lovable e a 0015 instalada. A migração 0016 é aditiva: tabela de convites, índices, RLS, RPCs e triggers de auditoria/revogação. 0000–0015 e snapshots existentes não foram reescritos; o journal tem apenas mais uma entrada. Nenhuma migração desta missão foi executada no backend hospedado.

## Utilização

Em `/app/configuracoes`, um administrador vê os emails dos membros, altera papéis e remove um membro após confirmação. Leitores/operadores consultam identificadores e papéis, sem emails privados da equipa ou convites. As permissões são verificadas no PostgreSQL.

O formulário exige email, papel e validade explícita de até 30 dias (limite técnico de segurança desta versão, sem validade comercial presumida). O servidor gera 32 bytes criptograficamente aleatórios. A ligação `/convite#token=...` é apresentada uma única vez para copiar e partilhar manualmente: **não há envio automático de email**.

A pessoa abre a ligação, entra/cria uma conta pela autenticação existente, e confirma o email através do mecanismo de Auth existente. Só uma conta com `auth.users.email_confirmed_at` comprovado no servidor e email atual correspondente pode consultar o convite e aceitá-lo. A pessoa vê a empresa, o papel proposto e a validade antes de confirmar a aceitação. Não é preciso criar uma empresa própria nem passar pelo onboarding primeiro.

Se a conta precisar de confirmar o email, deve confirmar e reabrir a ligação original. O token é retirado do endereço por `replaceState` e fica apenas na memória da página; não é guardado em localStorage, sessionStorage, query keys ou tabelas. Recarregar a página de aceitação antes de aceitar exige reabrir a ligação original. Não se coloca o token em parâmetros do login ou pedidos GET/referrers. A aplicação não recupera links antigos: se o administrador perder a ligação, revoga o convite e cria outro.

## Contrato de segurança

- Só admin atual da empresa cria/revoga. Lock da empresa antes da autorização definitiva e da alteração; mantém-se a proteção existente contra remover/despromover o último admin. Reutilizam-se `add_tenant_member`, `set_member_role`, `remove_tenant_member`; a 0016 corrige a janela de autorização antes do lock e torna a atribuição repetida do mesmo papel uma operação sem escrita.
- Apenas o hash SHA-256 do token é persistido; nem o hash nem o payload de idempotência têm grants SELECT para clientes. RLS dos metadados de convites exige admin da própria empresa. A auditoria usa a allow-list existente: não grava emails, tokens ou hashes.
- Convites expirados/revogados/consumidos não concedem acesso. Erros de token desconhecido, outro email, expiração/revogação/consumo são genéricos; não há procura pública de contas por email. A normalização é apenas trim + lowercase; não se equiparam aliases, pontos ou sufixos `+`.
- Aceitação recebe token e UUID da operação, nunca uma empresa/papel escolhidos pelo destinatário. Empresa, email e papel vêm exclusivamente do convite persistido. Lock tenant → convite → utilizador Auth; email é revalidado no servidor. Membership única impede duplicados.
- Aceitar um convite para alguém já membro não muda o seu papel: consome o convite e preserva o papel atual. Alterações de papel pertencem à operação administrativa explícita.
- Criação idempotente por empresa/UUID e hash do pedido. Replay devolve identidade sem token, porque só o hash existe. Se a primeira resposta se perder, revogar e criar outro é a recuperação segura. Revogação pendente já revogada é idempotente. Replay exato de aceitação só devolve a empresa se o mesmo utilizador continuar membro; nunca recria acesso removido. Outro UUID não reutiliza convite aceite.
- Demover/remover um administrador revoga definitivamente os convites pendentes emitidos por ele. Remover um membro revoga também convites pendentes anteriores para o seu email atual; um novo acesso exige nova decisão administrativa.
- Remoção retira imediatamente acesso às consultas/RPCs sob RLS, mesmo com JWT ainda válido. Memberships são revalidadas ao focar a aplicação e a cada 30 segundos enquanto ativa; a UI não recebe push de revogação. Dados já exibidos só podem ser retirados após essa atualização. Role changes limpam cache privada da equipa; mudança de empresa/logout removem caches da empresa e cancelam pedidos. Os tokens nunca entram no cache de consultas.

As listas de membros e convites usam cursor UUID, 50 entradas por página, ordem estável; a listagem inclui convites pendentes e histórico aceite/revogado/expirado. O estado expirado é calculado com relógio do servidor, sem jobs que alterem o histórico.

## Executar numa base descartável

Com Docker, Python 3.12+, psql, Node 22 e Bun 1.3, após commit:

```sh
python3 scripts/mvp/start-local.py --team
```

A receita existente exporta HEAD sem .env, cria base própria em loopback e aplica 0000–0016. Credenciais sintéticas de equipa ficam apenas no ficheiro privado indicado no arranque (`e2e/private/team-users.json`). Entrar como `team-admin@example.invalid` em `/app/configuracoes`, convidar `team-invitee@example.invalid` e abrir a ligação noutro contexto de navegador. Atlas, FlowReports e a central permanecem disponíveis.

No diretório isolado, com `CW_LOCAL_MVP=1 PGHOST=127.0.0.1 PGDATABASE=cw_e2e`:

```sh
python3 scripts/mvp/review-database.py --team
python3 e2e/team-concurrency.py
```

SQL usa papéis/JWT claims reais e rollback incondicional. Concorrência usa sessões GoTrue/PostgREST reais e transações PostgreSQL distintas, verifica espera efetiva no lock e compara hashes dos dados C01–C10. Browser cobre criação/cópia, login/aceitação, papéis, remoção, revogação, navegação, reload, logout e troca durante pedido pendente. Testes controlados de UI são reportados separadamente da prova real de Auth/RLS.

O workflow existente testa upgrade 0016 sobre base não vazia, preservação de linhas/grants anteriores, SQL, concorrência HTTP, browser, regressão unitária, tipos e build. GoTrue descartável usa confirmação automática **apenas como fixture de teste**. Um JWT real ativo é também testado com o email desconfirmado no servidor para provar rejeição. Isso não prova envio/receção de emails, nem testa o fornecedor de email hospedado; não se alteram configurações de Auth hospedadas para contornar a confirmação.

Limites: partilha manual, sem remetente próprio, convites bulk, SSO, MFA novo ou recuperação de token antigo; a criação/confirmação de contas continua a depender da configuração de Auth existente. Não se pretende apagar dados já consultados por um ex-membro. Nenhum serviço pago, publicação ou merge automático faz parte desta entrega. Resultados efetivos e commit validado constam do PR.
