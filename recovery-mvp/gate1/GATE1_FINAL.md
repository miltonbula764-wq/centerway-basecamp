# Gate 1 — proposta operacional final T03-G5

Base PR #79. Não executar esta sequência antes da autorização única indicada no fim.
Não alterar cloud_admin, PUBLIC/RLS da origem nem workflows bloqueados.

1. **Fixar a cópia.** Reconfirmar Free/quota, criar uma filha normal de
   synthetic-demo com parent_id explícito e compute min=max0,25CU, sem tentar
   configurar suspensão (o plano recusou essa opção no G4.3). Registar ID/LSN/UTC,
   prazo máximo1h e cleanup em finally. Nenhum consumidor público ligado à filha.
2. **Baseline anterior à role.** Na filha ainda intacta, capturar contagens/hashes
   de todas as27 tabelas, incluindo sessões, schema/ACL/owners/RLS/funções/índices,
   roles (atributos, validade, memberships e opções administrativas, SEM passwords),
   extensões e diferenças relativamente ao inventário esperado. Usar inventory e
   structure do módulo G2. Cifrar os metadados em memória com age público, guardar
   como ficheiro privado separado pre-export.age e levar também ao Drive. Não
   meter ficheiros extras no bundle G2 de três ficheiros. Comparar os metadados
   depois dos grants: só a role temporária, os seus grants e membership automática
   de administração pelo criador podem mudar. Dados/RLS/owners/grants de outros
   utilizadores devem coincidir. Não usar contagens antigas como baseline atual.
3. **Role SQL só na filha.** Criar role com nome novo, NOSUPERUSER/NOCREATEDB/
   NOCREATEROLE/NOREPLICATION, sem neon_superuser, password aleatória exclusiva,
   VALID UNTIL<=1h e CONNECTION LIMIT2. Atribuir BYPASSRLS isolado por ALTER ROLE
   sob cw_owner como provisionador (não como identidade de export). Conceder só
   CONNECT na base, USAGE nos schemas e SELECT nas tabelas/sequências necessárias.
   Não conceder memberships de runtime/admin. Conferir atributos, herança e
   effective grants. Testar login real, leitura completa com row_security=off,
   snapshot exportável, negação DML/DDL/admin e autenticação recusada na origem.
   Não invocar funções LO, alterar funções internas ou desativar RLS. Se Neon não
   permitir BYPASSRLS isolado ou a credencial funcionar na origem, parar e limpar.
4. **Export cifrado.** Conferir SHA do código e fingerprint público calculado no
   Android. Guardar source.json0600 fora do checkout via entrada privada sem eco,
   sem DSN em argv/histórico. Endpoint da FILHA, direto, CA/sslmode=verify-full,
   pg_dump17. Exemplo com paths privados e destinatário público:

   ```sh
   umask 077
   ulimit -c 0
   python recovery-mvp/gate1/recovery.py export --config /privado/source.json --archive /privado/export-001 --recipient "$(cat /privado/recipient.txt)"
   ```

   G2 verifica snapshot, limites e ambos os processos pg_dump/age; plaintext do
   dump nunca é gravado. Não tratar sucesso do último processo como sucesso total.
5. **Custódia externa.** Copiar database.age, manifest.age, checksums.json e o
   pre-export.age para a pasta Drive já identificada, separada da identidade.
   Sem links públicos, releases ou Actions artifacts. Download novo para diretório
   privado independente; copiar para o HOME privado do Termux, não trabalhar em
   armazenamento partilhado Android. Aplicar0700/0600 e comparar pelo handoff:

   ```sh
   python recovery-mvp/gate1/handoff.py custody --original /privado/export-001 --download /privado/retorno-001
   ```

   Guardar bundle_fingerprint retornado. Comparar também SHA256 do pre-export.age
   após download. Hash igual prova integridade de transporte, não ACL do Drive;
   confirmar separadamente pasta privada/quota e capacidade de recuperar a cópia.
6. **Restauro sem chave remota.** Android autentica ambos os ciphertexts e só então
   emite manifest/dump em memória. Enviar por SSH autenticado do titular, sem PTY,
   sem tee, gravação de terminal, debug ou redirecionamento de plaintext para disco.
   O Codespaces recebe em RAM, verifica frame, hashes, tamanho e fingerprint; só
   então inicia o mesmo restauro G2 em PostgreSQL17 network=none/tmpfs, sem portas.
   Não copiar a identidade nem passphrase para o Codespaces. No Termux, com gh e
   o acesso ao Codespaces já autenticados, substituir apenas nome/paths/hash:

   ```sh
   set -o pipefail
   python recovery-mvp/gate1/android_stream.py send --archive /privado/retorno-001 --identity /privado/identity.age |
     gh codespace ssh -c NOME_DO_CODESPACE -- -T 'cd /workspaces/centerway-basecamp && /tmp/cw-g2-venv/bin/python recovery-mvp/gate1/android_stream.py receive --expected FINGERPRINT_DO_BUNDLE'
   ```

   O código deve existir no MESMO commit revisto nos dois dispositivos. O helper
   send requer só Python stdlib, handoff.py e age no Android; psycopg/Docker ficam
   no Codespaces. Não usar um bearer URL ou SSH com verificação de identidade
   desativada. Ambos os exit statuses têm de ser zero. A ligação SSH real Android
   → Codespaces ainda não foi testada por este agente: validar antes com dados
   sintéticos, dentro da sessão autorizada, e parar se houver falha de transporte.
   Saída esperada: isolated_restore_verified, runtime_ready=false. Sessões em
   quarentena, roles NOLOGIN, comparações G2 de dados/estrutura/permissões/identidade.
7. **Fechar e comprovar.** NOLOGIN na role, terminar apenas as suas sessões,
   revogar grants/remover role e testar login recusado. Eliminar compute/filha e
   verificar listagens. Comparar hashes da origem antes/depois; apagar source.json
   e temporários privados. Guardar provas agregadas e custódia; nunca secretos.

## Riscos e fidelidade

Aceitação proposta: CONNECT/TEMPORARY e criação de LO persistentes APENAS na filha
que será apagada. A role não é estritamente read-only. Não aceitar membership
administrativa, DML de negócio, uso na origem, privilégio de export cw_owner,
exposição de credenciais, chave remota ou ficheiros públicos. A cópia contém dados
sensíveis mesmo sendo sintéticos: não divulgar passwords herdadas da origem.

pg_dump exporta uma base, não passwords/roles globais, outras bases, configuração
Render, PKI ou segredos de runtime. G2 guarda nomes/memberships, recria roles
limitadas NOLOGIN e preserva sessões; não recupera automaticamente contas operáveis.
pre-export.age documenta atributos/ACL anteriores sem passwords, para identificar
os grants adicionados. O dump da filha terá grants da role de export: não declarar
permissões idênticas à origem sem reconciliar/verificar esse delta num restauro
posterior. Não promover este restauro de validação para produção.

O recebimento em RAM evita dump plaintext em disco, mas não torna um executor
comprometido seguro: o Codespaces autorizado recebe os dados decifrados. A chave
permanece Android. Integridade do canal depende da autenticação SSH e do código
revisto; os hashes do frame não são assinatura de produtor. Free é quota partilhada
com a origem: revalidar limites reais e abortar antes de risco de esgotamento.

## Validação realizada nesta preparação

Dois testes novos de frame/corrupção/destinatário e falha age sem emissão passaram.
Um teste integrado novo autenticou um bundle age sintético, passou o payload sem
chave e concluiu o restauro PostgreSQL17 G2. Não repetimos manualmente as suites
anteriores; a CI do PR executa as regressões obrigatórias automaticamente.
Nenhuma branch/role Neon, export real ou transferência de dados reais foi criada.

## Única autorização adicional

Autorizar UMA sessão Gate1 com a aceitação explícita do risco LO exclusivamente na
filha: criar filha/compute Free0,25CU, provisionar/testar role SQL limitada e BYPASSRLS,
export cifrado, custódia/download Drive, decifragem no Android e streaming SSH para
restauro isolado no Codespaces, revogação e remoção completa. Qualquer falha fecha
os passos seguintes e aciona limpeza. Não inclui deploy, T01, Render ou Lovable.
O fingerprint da chave pública e do bundle serão conferidos nessa mesma sessão;
não solicitar chave privada nem recriar a chave/pastas já preparadas.
