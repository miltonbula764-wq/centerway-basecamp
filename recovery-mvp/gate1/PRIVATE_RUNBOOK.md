# T03-G3 — execução privada preparada, sem ativação

Issue #78; base PR #77/fb925f9. Estado informado pelo titular: identidade age testada
no Termux; cópia da identidade cifrada e pasta de backups no Drive privado. Não
repetir geração de chave nem solicitar identidade/passphrase ao agente. Nenhum
backup real foi criado nesta missão. A chave pública concreta não foi fornecida;
a sua correspondência ainda não foi verificada por este agente.

## Bloqueios efetivos

1. Executor com Docker local para restauro e custódia da identidade: Termux/Android
   normal não fornece o daemon Docker exigido por recovery.py. Um terminal privado
   Linux já existente com Docker é o caminho preferido, se disponível. Não assumir
   que existe, não criar servidor pago. O teste sintético no runner não substitui
   o restauro da cópia real.
2. Credencial de export completa e temporária ainda não criada nem validada. Isso
   exige autorização posterior para metadados de segurança Neon; nenhum dado de
   negócio deve mudar. O conector pode criar roles, mas não se deve usar uma role
   recém-criada como prova de permissões suficientes ou de RLS correto.
3. Workflow sensível permanece literalmente bloqueado. Sem revisão independente,
   controlos compensatórios ainda não comprovados não autorizam retirar o bloqueio.
   A exceção TCP não se aplica. A Issue #78 também proíbe execução real nesta missão.
4. Pasta de backups identificada pelo conector com shared=false, separada da pasta
   da identidade. Quota e retorno de download ainda não comprovados. Nenhum
   ficheiro da identidade foi aberto.

## Credencial temporária: procedimento privado, não executar agora

No executor privado aprovado, o administrador prepara uma role exclusiva de export:
LOGIN com password aleatória efémera, VALID UNTIL até uma hora, sem SUPERUSER,
CREATEDB, CREATEROLE ou REPLICATION; sem membership runtime/administrativa e sem
INSERT/UPDATE/DELETE/EXECUTE concedidos pelo procedimento. Conceder só CONNECT na
base alvo, USAGE nos schemas necessários e SELECT nas tabelas presentes. Congelar
migrations durante o export; não usar privilégios automáticos para futuras tabelas.
Não conceder pg_read_all_data globalmente sem necessidade. Inspecionar grants
herdados de PUBLIC, acesso a outras bases e funções SECURITY DEFINER: flags de role
e default_transaction_read_only sozinhos não garantem limitação real.

Como as tabelas usam RLS, SELECT sem bypass não produz export completo. pg_dump
normalmente exige bypass para esse caso. O administrador tem de comprovar que o
Neon permite conceder BYPASSRLS à role temporária **sem** privilégios de escrita ou
membership administrativa ampla. Isto ainda não foi verificado no fornecedor.
Se não permitir, parar: não desligar RLS, não alterar policies, não usar --enable-row-security
para aceitar uma cópia parcial, não reutilizar a conta runtime. Alternativa sujeita
a autorização: executor privado do titular com a identidade owner existente e
exposição controlada; isso tem privilégios maiores e não pode ser descrito como role
limitada. Nenhuma dessas alternativas foi executada ou automatizada neste PR.

No terminal privado, criar source.json 0600 fora do checkout, com DSN apenas em
ficheiro privado: endpoint direto, sslmode=verify-full, CA válida, dbname/user da
role temporária, connect_timeout=10. Não inserir o DSN em argv, shell history,
chat, issue ou Actions neste estado. O export já usa PGSERVICEFILE 0600 e remove-o.
Depois de exportar: revogar LOGIN, terminar sessões residuais, revogar grants e
remover a role temporária; VALID UNTIL não termina conexões já abertas. Não mudar
passwords de utilizadores existentes. Guardar prova privada de criação/expiração/
revogação sem password. O processo atual de export não cria nem revoga roles.

## Conferir destinatário sem expor identidade

Executar **apenas no dispositivo privado** com a identidade já existente:

```sh
umask 077
age-keygen -y /caminho/privado/identity.age > /caminho/privado/recipient.txt
python recovery-mvp/gate1/handoff.py fingerprint --public-key /caminho/privado/recipient.txt
```

Só recipient.txt (público) e o seu SHA256 podem ser transferidos para o executor de
export. Conferir o fingerprint no dispositivo do titular e no executor por canal
confiável; o SHA é sobre o texto ASCII sem newline. O utilitário recusa material
privado; só verifica formato e fingerprint, não substitui a validação criptográfica
age ou o teste local da identidade. Não transferir a identidade ao runner GitHub.

```sh
python recovery-mvp/gate1/handoff.py recipient --public-key /caminho/recipient.txt --expected FINGERPRINT_PUBLICO_CONFERIDO
```

## Controlos sensíveis verificáveis

Preferir execução privada única do código revisto do PR, sem colocar credenciais
no GitHub. Antes da autorização sensível, registar privadamente: SHA exato do código,
versões/checksums das ferramentas, executor local com disco/conta protegidos, ausência
de gravação/debug de terminal, destino privado/quota, fingerprint do destinatário,
janela e privilégios da role, revogação preparada e Docker local confirmado.
Testar o roteiro com dados sintéticos primeiro. Atestados do titular devem aparecer
como tais; não inventar verificação independente. O titular precisa aprovar
explicitamente esta substituição de revisão após ver os controlos e os seus limites.
Se o executor privado não existir, reportar isso como o único passo de ambiente
necessário; não ativar Actions com credenciais por conveniência.

Para eventual Actions, ainda é necessária revisão/autorização específica para remover
if:false, comprovação do ambiente protegido/MFA/restrições sem bypass e da exposição
mínima de secrets. Não executar o workflow atual: o bloqueio é deliberado. Não colocar
backups sequer cifrados em commits, issues ou releases; nenhuma utilização de artifacts
é proposta para este caminho privado.

## Export, transferência e restauro posteriores

Somente após autorização específica, com o terminal privado e a role aprovados:

```sh
python recovery-mvp/gate1/recovery.py export --config /privado/source.json --archive /privado/export-001 --recipient "$(cat /privado/recipient.txt)"
```

O único argumento expandido é a chave pública, nunca password/DSN. Transferir apenas
os três ficheiros do bundle (database.age, manifest.age, checksums.json) para uma
subpasta nova da pasta Drive de backups, separada da cópia cifrada da identidade.
Nunca carregar source.json, identidade ou passphrase. Não criar links partilhados.

Pode-se usar o app Drive no Android para upload/download ou o conector Drive para
upload binário após identificar o ID da pasta e confirmar permissões. O conector
não executa pg_dump, não recebe credenciais PostgreSQL e não transfere ficheiros
automaticamente do runner Actions. A pesquisa de metadados identificou a pasta de backups com shared=false e a pasta
da identidade separada; nenhuma transferência real foi realizada. IDs de pastas
privadas não são publicados no repositório; a identidade não foi aberta.
A API de upload disponível aceita referência de ficheiro; a capacidade concreta de
materializar e reenviar os bytes terá de ser testada com ciphertext autorizado.

Descarregar de novo os três ficheiros para diretório privado diferente, nunca
comparar apenas duas cópias locais anteriores ao upload. Ajustar permissions 0700/
0600 após download (Drive não preserva modes Unix) e executar:

```sh
python recovery-mvp/gate1/handoff.py custody --original /privado/export-001 --download /privado/retorno-001
python recovery-mvp/gate1/recovery.py restore --archive /privado/retorno-001 --identity /privado/identity.age
```

O primeiro comando compara hashes/tamanhos limitados e envelope age, recusando
ficheiros extras, symlinks, plaintext e origem=retorno. Não comprova ACL nem origem
Drive do download e declara isso no resultado. O segundo usa o mecanismo G2 sem
modificações: autentica todo o ciphertext, restauro num PG17 sem rede, dados/sessões/
permissões comparados e sandbox removido. Sessões preservadas em quarentena e roles
NOLOGIN; não ativar runtime. Configuração/segredos Render exigem custódia separada.
Guardar fingerprints e resultado agregado do restauro em registo privado. Confirmar
revogação da role e apagar source.json. Só então propor conclusão do Gate1.

## Intervenção humana mínima pendente

Autorizar uma sessão sensível única num **terminal privado com Docker** que o titular
controle, incluindo credencial temporária e sua revogação, export, cópia privada e
restauro. Identificar esse terminal é indispensável; o Android já preparado não
comprova a disponibilidade de Docker. Nessa sessão só será necessário confirmar o
fingerprint público e a pasta privada existente; nunca fornecer chave privada ou
passphrase ao agente. Sem autorização e capacidade verificadas, tudo permanece em
preparação. Não repetir criação de chaves/pastas já confirmadas pelo titular.
