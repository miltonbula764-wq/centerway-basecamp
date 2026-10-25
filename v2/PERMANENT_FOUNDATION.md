# Missão 05 — fundação permanente privada

Parte do PR #34, commit `46c07c7`. Não publica, migra dados, instala serviços ou
constrói uma interface. Runtime Python stdlib + SQLite; Caddy continua a terminar
HTTPS e encaminhar `/api/*` para Python também por TLS verificado.

## Modos separados

| Propriedade | Demo privada | Production nesta missão |
| --- | --- | --- |
| Inicialização | Base nova com 150 clientes fictícios | Base nova vazia, apenas identidade e permissões reais |
| Prazo global | Máximo 24 horas; reinício não renova | Sem prazo global de demo |
| Sessões | Uma hora, Secure/HttpOnly/SameSite=Strict | Mesmas proteções e duração; logout/rotação revogam |
| Cookie | `__Host-cw_session` | `__Host-cw_production_session` |
| Contas | Segredos aleatórios privados; contas de teste removidas | Contas explícitas; segredos aleatórios, sem password no manifesto |
| C01–C06 | Sandbox, decisão simulator-v1 | Todas as operações de negócio bloqueadas |
| API view | `sandbox` / `simulator-v1` | `production` / `disabled`, registo vazio |
| Interface incluída | Demo privada existente | Apenas API; assets da demo devolvem 404 |

**Production significa uma fundação permanente de autenticação, não um sistema de
recuperação real já operacional.** Login/logout funcionam. Todas as seis mutações
de negócio devolvem 503 para operadores autorizados, sem criar clientes, evidências,
casos, efeitos ou verificações. Leitores e tenants alheios recebem 403. Consultas
operacionais com cliente/caso também devolvem 503. Não existe flag para desbloquear
simulações em production, nem conta operator capaz de ultrapassar esse bloqueio.

Bases, ficheiros de credenciais, certificados, utilizadores do SO e origens HTTPS
devem ser distintos entre os modos. Cookies distintos também impedem colisões no
mesmo host. Os marcadores da base impedem abrir demo como production ou o inverso;
a abertura não cria nem converte dados. A demo anterior e o laboratório loopback
continuam disponíveis; nenhum deles aceita uma base production.

## Preparação local, sem publicação

Executar a partir de `v2`, com Python 3.11+ e paths privados **fora do checkout**.
Exemplo de preparação de ficheiros, não de instalação de alojamento:

```sh
umask 077
mkdir -p /private/centerway-production
chmod 700 /private/centerway-production
cp infra/production/accounts.json.example /private/centerway-production/accounts.json
chmod 600 /private/centerway-production/accounts.json
```

Substituir `/private/...` por um diretório privado gravável. Editar o manifesto com
as contas e SaaS autorizadas antes de inicializar. Formato:

```json
{"accounts":[{"user":"operations-owner","memberships":[{"tenant":"tenant-one","role":"operator"}]},{"user":"audit-reader","memberships":[{"tenant":"tenant-one","role":"viewer"}]}]}
```

Entre 1 e 100 contas, 1 a 20 memberships por conta, ao menos um operator. IDs usam
letras minúsculas, números, `_` ou `-`, até 64 caracteres, começando por letra ou
número. Não usar contas reservadas da demo nem tenants `atlas`/`nimbus`. Campos extra,
passwords no manifesto, duplicados e roles desconhecidas são recusados.

```sh
python3 -m centerway.runtime init --mode production \
  --db /private/centerway-production/state.sqlite3 \
  --accounts-file /private/centerway-production/accounts.json \
  --credentials-file /private/centerway-production/initial-secrets.json \
  --origin https://app.example.invalid
python3 -m centerway.ops check --mode production \
  --db /private/centerway-production/state.sqlite3 --origin https://app.example.invalid
```

A origem é um exemplo reservado, não um URL disponível. `init` exige ficheiros novos,
gera segredos fortes em ficheiro 0600 e guarda apenas hashes scrypt na base. Não
imprime passwords. Entregar segredos por canal privado; nunca em Git, logs ou
`VITE_*`. O check confirma a fundação com `business_operations: "disabled"` e
`expires: null`; não confirma prontidão de operações reais.

Para demo, usar outro diretório/origem e `init --mode demo`, sem `--accounts-file`;
`--hours 24` é o limite máximo. Segue a operação de [pré-visualização](PRIVATE_PREVIEW.md).

Com certificado e chave próprios, ambos fora do checkout:

```sh
python3 -m centerway.runtime serve --mode production \
  --db /private/centerway-production/state.sqlite3 \
  --certfile /private/centerway-production/backend-cert.pem \
  --keyfile /private/centerway-production/backend-key.pem --host 127.0.0.1 --port 9443
```

Não existe fallback HTTP, criação de base ou renovação de contas ao arrancar.
Host e Origin têm de corresponder à origem configurada; mantém-se a opção de CORS
HTTPS explícito, same-site, com `credentials: "include"`. Preferir a mesma origem
HTTPS para a futura interface. O contrato [1.1.0](API_CONTRACT.md) adiciona a resposta
production e o cookie próprio; os endpoints e respostas do sandbox são preservados.

## Gerir contas e sessões

A administração é exclusivamente por CLI local, pelo responsável autorizado do
host; não há endpoint de administração exposto. `apply-accounts` aplica o manifesto
completo pretendido, preserva os hashes das contas mantidas, remove as ausentes,
revoga sessões quando as permissões mudam e gera segredos apenas para contas novas.
Usar sempre um novo ficheiro de saída privado, mesmo sem contas novas:

```sh
python3 -m centerway.runtime apply-accounts \
  --db /private/centerway-production/state.sqlite3 \
  --accounts-file /private/centerway-production/accounts.json \
  --credentials-file /private/centerway-production/new-account-secrets.json
python3 -m centerway.runtime rotate-password \
  --db /private/centerway-production/state.sqlite3 --user operations-owner \
  --credentials-file /private/centerway-production/rotated-secrets.json
```

Rotação gera uma password nova e revoga todas as sessões dessa conta. Alterações de
configuração ficam em `production_auth_audit` append-only, sem passwords/tokens.
Falhas normais na escrita do segredo fazem rollback da alteração de contas. Base e
ficheiro de entrega não constituem uma transação atómica perante falha física ou
kill abrupto: verificar os ficheiros e estado antes de repetir; se necessário rodar
novamente para um novo ficheiro. Não apagar/recriar bases para recuperar acesso.
Sessões expiradas são recusadas mesmo após reinício; não há refresh automático.

## Persistência e defesa

O Core e C01–C06 permanecem intactos. Só a criação de uma base production nova
acrescenta metadados próprios, auditoria de configuração e triggers que rejeitam
INSERT/UPDATE/DELETE nas seis tabelas de negócio. O arranque e cada pedido validam
os marcadores, a origem/instância, os triggers exatos e a ausência de dados de
negócio. Contaminação ou remoção de proteções dá recusa/503, sem limpar ou reparar.
As contas e hashes são validados no arranque; a password pública conhecida é
recusada também no login. O proprietário do SO/ficheiro SQLite continua confiável;
estas verificações não substituem isolamento do host e controlo de administradores.

O modelo [production/centerway-production.service](infra/production/centerway-production.service)
usa identidade do SO, estado, configuração e porta separados da demo. São templates
não instalados. Usar [production/caddy.env.example](infra/production/caddy.env.example)
com o mesmo [Caddyfile](infra/Caddyfile); exige certificados, permissões do SO e origem
coerentes. Nenhuma interface de laboratório é encaminhada por Caddy. A rota estática
aguarda um build futuro que reconheça `decision_mode: disabled`.

`centerway.ops backup` continua a produzir snapshot SQLite consistente 0600;
`verify-backup` valida integridade, não restaura nem converte modos. Um backup demo
não é uma base production. Manter snapshots privados e testar uma política de
recuperação antes de qualquer operação real. Não houve migração de dados existentes.

## Verificação e limites

```sh
python3 -m pip install -r tests/requirements.txt
CADDY_BIN=/caminho/para/caddy python3 -m unittest discover -s tests -v
systemd-analyze verify --man=no infra/centerway-backend.service infra/production/centerway-production.service
npm ci --ignore-scripts --no-audit --no-fund
npm run test:browser
npm run test:private-browser
npm run test:cors-browser
```

Verificação executada nesta missão: **61 testes Python passaram, sem skips**,
com Caddy 2.11.7; três ensaios de Chromium passaram (laboratório responsivo, demo
HTTPS com Pixel 7 emulado e CORS same-site). Compilação Python, validação dos dois
templates systemd e `git diff --check` também passaram. Core e assets da interface
permanecem sem alterações relativamente ao PR #34. Não houve teste em Android físico.

Os testes usam bases descartáveis e TLS local: isolamento de modos/cookies/tenants,
permissões, bloqueio das seis operações, revogação/expiração de sessões, falhas de
configuração/segredos, recusa de contaminação, backup e reinício real Python atrás
de Caddy. As regressões do ciclo sandbox e da interface são executadas separadamente.
Sem Caddy instalado/configurado, os testes de proxy são skipped; a CI fornece-o.

Não existem conectores, IA real, importação de clientes reais, intervenções reais,
MFA/SSO, recuperação de password, painel de administração ou interface production.
Limite de login em memória por processo; reinício repõe o contador e Caddy agrupa IPs
no backend. Não há distribuição horizontal, execução de systemd num host real,
renovação ACME, disponibilidade contínua medida ou ensaio com tráfego real. Nenhum
serviço foi contratado, publicado ou ativado e a main não foi alterada.
