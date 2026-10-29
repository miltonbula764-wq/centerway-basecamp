# L01 — API HTTP independente para futura interface Lovable

Base: PR #55 (`c4d9756`). Esta entrega acrescenta transporte HTTP sobre F06;
não altera migrações, motores, permissões ou arquitetura F01–F06 e não importa C01–C10.
Não inclui frontend, ligação Lovable ativa, conectores externos ou publicação.

## Execução local reproduzível e dados sintéticos

Requisitos: Docker local, Bash, Python 3.12 com venv e acesso ao índice de pacotes.
Da raiz do repositório:

```sh
./recovery-mvp/api/demo/start.sh
```

O script cria uma base PostgreSQL 17 descartável, aplica 001–008, instala as versões
Python de `requirements.txt` num venv privado e inicia Gunicorn em `127.0.0.1:8080`.
O PostgreSQL também só publica em loopback, com passwords aleatórias e autenticação
host SCRAM. A API nunca recebe a credencial administrativa do container. Ctrl-C remove
o container e os dados; o diretório privado é identificado na saída e pode ser removido
manualmente depois. Nunca apontar provision.py para uma base existente.

O diretório contém `config.json`, `credentials.json`, venv e a base SQLite de sessões,
com ficheiros secretos 0600 e diretório 0700. Para escolher um diretório, criar um
**diretório dedicado privado** e fornecer `CENTERWAY_DEMO_DIR`. Não colocar estes
ficheiros no Git nem copiar a configuração para o navegador. A porta 8080 deve estar
livre. Não é necessário nem permitido fornecer tokens GitHub ou credenciais de produção.

Os utilizadores `alice`, `reviewer`, `reader` e `bob` recebem passwords de login
aleatórias em credentials.json; os seus logins PostgreSQL têm passwords diferentes.
Alice e reviewer pertencem à empresa sintética A; reader apenas pode ler pela API;
Bob pertence à B. Um segundo cliente da A existe mas não está autorizado nos scopes
HTTP, para demonstração de separação por cliente. A demo inclui apenas uma fonte e
um contrato claramente rotulados SYNTHETIC; **não há recuperação ou resultados reais**.
Todas as respostas de dados/sessão da demo indicam `demo: true`.

## Testes e GitHub Actions

```sh
./recovery-mvp/api/test.sh
```

Executa os 60 testes F01–F06 inalterados e, numa segunda base descartável, os testes
HTTP de L01. Estes usam sockets HTTP reais, passwords PostgreSQL reais e principais
não proprietários, sem simular o adaptador de base ou motores. Abrangem sessões,
logout/expiração, CORS, validação, identidade, rejeição de privilégio, scopes por
cliente/empresa/operação, concorrência, auditoria e recibos idempotentes. Uma verificação
adicional de alteração de configuração usa o cliente WSGI com a mesma base de sessões.

`api/test.sh --http-only` repete apenas L01 durante desenvolvimento. CI usa sempre a
suite completa: `.github/workflows/recovery-mvp-api.yml`, job independente da aplicação
antiga, com Python 3.12, Docker e `contents: read`; não precisa de secrets, não faz
provisionamento externo ou deploy. O resultado local não é o resultado remoto do CI:
consultar o check do PR. Não confundir testes aprovados com prontidão para produção.

## Identidade, sessões e permissões

A autenticação L01 é local, com utilizadores provisionados **no servidor**, passwords
scrypt com salt e sessões opacas aleatórias de 256 bits. Só o digest SHA-256 do token
é guardado em SQLite. A sessão tem duração absoluta (900 s na demo; configurável 1–3600),
sem renovação silenciosa. Login cria novo token; não aceita um identificador de sessão
fornecido pelo cliente. Logout revoga o token. No máximo dez sessões por utilizador.
Qualquer alteração de credencial, scope, principal ou DSN na configuração invalida
as sessões antigas quando o serviço é reiniciado; remover o utilizador também as invalida.

O token é enviado **apenas** em `Authorization: Bearer ...`. Não há cookies de sessão,
nem credenciais ambientes, nem token no URL. Uma futura interface deve guardar o token
em memória, usar `credentials: 'omit'`, e pedir novo login após 401. Evitar localStorage,
URLs, histórico de shell, logs e ferramentas de analytics para passwords/tokens.
Não há login federado, OIDC, MFA, reset de password, auto-registo ou gestão de utilizadores.

Cada utilizador provisionado contém principal esperado, DSN exclusivo não privilegiado,
clientes autorizados por empresa, operações permitidas e empresas explicitamente
permitidas para `discover_company`. O DSN fica no servidor. Cada chamada abre uma
ligação **autenticada como esse login**: não usa `SET ROLE`, identidade do corpo,
claims arbitrárias, login administrativo ou um login comum elevado. A API verifica
session_user/current_user e rejeita superuser, BYPASSRLS, CREATEDB, CREATEROLE,
replicação, proprietários da base/schema/tabelas do MVP, CREATE no schema e permissão
direta de INSERT em políticas. O login precisa de membership em centerway_api.

RLS e session_user continuam como nos motores. A API acrescenta scopes exatos por
cliente e allowlist de operações; membership da empresa por si só não concede todos
os clientes na HTTP API. Leituras/escritas confirmam a visibilidade atual do cliente;
replays também passam por essa verificação. Políticas F04, catálogo e recursos não
podem ser concedidos via HTTP. Um utilizador com permissão HTTP `intervene` ainda
precisa da política administrativa F04 válida — transporte não concede autorização.

`discover_company` é uma operação empresarial que pode afetar vários clientes.
Além de aparecer em operations, exige o tenant em company_tenants; esse grant concede
explicitamente descoberta em toda a empresa, inclusive clientes fora do scope de leitura.
A demo não concede essa permissão. A API não expõe SQL arbitrário nem endpoints de
provisionamento, catálogo, políticas, credenciais ou concessão de permissões.

## Configuração do serviço

`CENTERWAY_API_CONFIG` aponta para JSON privado (0600); `app:load_app()` recusa ficheiro
público. Modelo **com placeholders**, não credenciais utilizáveis:

```json
{
  "demo": false,
  "origins": ["https://interface.example.invalid"],
  "session_db": "/private/centerway/sessions.sqlite",
  "session_ttl": 900,
  "users": {
    "operator": {
      "principal": "centerway_operator",
      "dsn": "host=db.example.invalid dbname=centerway user=centerway_operator password=<server-secret> sslmode=verify-full",
      "password_hash": "<salt-hex>:<scrypt-digest-hex>",
      "clients": {"<tenant-uuid>": ["<client-uuid>"]},
      "operations": ["append_value", "detect", "investigate"],
      "company_tenants": []
    }
  }
}
```

Gerar hashes com `app.password_hash` num ambiente privado, lendo a password com getpass,
nunca como argumento de shell. Provisionar logins `LOGIN NOSUPERUSER NOBYPASSRLS
NOCREATEDB NOCREATEROLE NOREPLICATION IN ROLE centerway_api`, memberships F01 e passwords
SCRAM através do administrador fora da API. Não reutilizar passwords HTTP e PostgreSQL.

Fora de demo, a API exige HTTPS observado pelo WSGI e `sslmode=verify-full` nas ligações
PostgreSQL. Configurar certificados/CA confiável; não desativar TLS. A demo permite
HTTP apenas com origens loopback explícitas e Gunicorn ligado em loopback. O código
não confia automaticamente em X-Forwarded-For/Proto. Um proxy/TLS futuro exige desenho
e configuração explícitos; este PR não instala nem publica esse ambiente.

Gunicorn demo: um worker, quatro threads, timeout 30 s, sem debug ou access log de
corpos/cabeçalhos. Cada ligação tem connect_timeout 5 s, statement_timeout 15 s e
lock_timeout 3 s. Estes limites podem interromper operações caras; repetir o mesmo
request_id após erro de transporte, conforme F06, para descobrir o resultado confirmado.

## Contrato HTTP para Lovable

Base `/v1`. Content-Type `application/json`; limite de corpo 64 KiB. IDs UUID; tipos
JSON e campos obrigatórios/extra são validados. Timestamps de operações devem indicar
fuso. JSON duplicado, NaN/Infinity e parâmetros extra são rejeitados. Campos de negócio
aninhados são validados pelos motores originais, sem uma nova lógica de negócio na API.
O documento `openapi.json` descreve o contrato de transporte.

| Método e rota | Autorização | Resposta |
|---|---|---|
| GET /health | Nenhuma | Alive, demo e readiness=not_assessed; não prova disponibilidade da base |
| POST /v1/sessions | Username/password | 201: access_token, token_type, expires_in, demo |
| GET /v1/session | Bearer | Username, principal confirmado, clients, operations, company_tenants |
| DELETE /v1/session | Bearer | 204: sessão revogada |
| GET /v1/tenants/{tenant}/clients/{client}/journey | Bearer + scope + RLS | 200: data=projeção F06, demo |
| POST /v1/tenants/{tenant}/clients/{client}/operations | Bearer + scope + operação + motores | 200 ou erro com recibo F06 |

Login (preencher a password do ficheiro privado; não gravar no repositório):

```json
{"username":"alice","password":"<demo-login-password>"}
```

Resposta ilustrativa, com token fictício explicitamente placeholder:

```json
{"access_token":"<opaque-session-token>","token_type":"Bearer","expires_in":900,"demo":true}
```

Pedido de operação, com IDs ilustrativos. Gerar/persistir request_id antes de enviar:

```json
{
  "request_id":"b32bb363-a660-422d-baf7-66a498f18d76",
  "operation":"detect",
  "arguments":{
    "contract_id":"a4000000-0000-0000-0000-000000000001",
    "revisions":[1],
    "as_of":"2026-10-29T12:00:00Z",
    "required_periods":2
  }
}
```

As dez operações e schemas de arguments são os da F06 em `../ORCHESTRATION.md`.
`data` pode ser um recibo completed com resultado de negócio blocked/failed/inconclusivo;
HTTP 200 não significa execução autorizada nem recuperação de valor. Exibir estados,
bloqueios, lacunas e hipóteses dos motores sem os reinterpretar.

Respostas de erro usam `{"error":{"code":"..."}}` para erros HTTP ou `{"data":
<receipt>,"demo":true}` quando o motor guardou um recibo de erro. Neste último,
result contém apenas sqlstate e `code=engine_rejected`; a API não devolve mensagens
internas PostgreSQL, inclusive nos recibos da projeção journey. A auditoria original
F06 não é modificada. Não usar sqlstate como prova de execução parcial.

| HTTP | Semântica |
|---|---|
| 400 | JSON inválido/duplicado; HTTPS obrigatório fora de demo |
| 401 | Login inválido, Bearer ausente ou sessão expirada/revogada |
| 403 | Origem, scope, operação ou autorização recusados |
| 404 | Rota ou cliente visível inexistente |
| 409 | Chave F06 reutilizada com outro conteúdo/principal; conflito de revisão |
| 413 / 415 / 422 | Corpo excessivo / formato errado / parâmetros ou motor rejeitados |
| 429 | Limite de tentativas de login por endereço |
| 503 | Base indisponível/timeout/configuração de identidade ou TLS rejeitada |
| 500 | Erro interno sem detalhes sensíveis |

Manter o mesmo request_id, corpo e identidade após perda de resposta; a F06 preserva
idempotência. Após corrigir um erro guardado pelo motor, usar outro request_id. Não há
retry de intervenção em loop. Configuração inválida no HTTP é recusada antes de gerar
recibo; um erro de transporte pode ter ocorrido depois do commit: consultar/repetir
com a chave original antes de decidir outra tentativa.

CORS usa origens exatas provisionadas, métodos das rotas e headers Authorization e
Content-Type; rejeita '*' e 'null', sem Access-Control-Allow-Credentials. Requisições
sem Origin de clientes não-browser continuam a exigir Bearer. CORS não substitui
autenticação. Respostas usam no-store, nosniff e CSP sem conteúdo ativo.

## Limitações restantes — não é prontidão para produção

- Provisionamento estático de contas e DSNs por principal: sem SSO/MFA/recuperação,
  gestão administrativa, secret manager ou rotação automatizada. Alterações exigem
  restart. Credenciais comprometidas exigem revogação de sessões e logins pelo operador.
- SQLite e limiter em memória: um nó/worker recomendado, sem sessões distribuídas,
  rate limit global ou defesa completa contra ataques distribuídos. O limiter considera
  apenas o peer direto e é limitado a 2048 endereços; proxy exige revisão própria.
- Sem pool por principal, paginação/limite de tamanho da projeção, streaming, métricas,
  gestão operacional de incidentes ou SLA de carga. Uma projeção grande pode exceder
  memória/tempo; o limite de pedido não limita a resposta. Configuração contém DSNs
  secretos no servidor; precisa de disco privado, controlo de acesso e backups adequados.
- Não há testes de penetração independentes, fuzzing completo, auditoria de supply chain,
  prova de hardening de infraestrutura nem ensaio de restauro. Versões Python estão
  fixadas, mas sem lock por hash; imagem postgres:17-alpine e ações GitHub usam tags.
- Os motores mantêm as suas limitações: evidências declaradas, verificação humana
  registada não certificada, comparação numérica sem causalidade e execução só sintética.
  A API não converte dados sintéticos em prova real e não autoriza ações reais.
- Sem gateway HTTP publicado, TLS de produção configurado, integração Lovable ativa,
  frontend ou deploy. L02 requer outra missão explícita.

Resultados locais desta entrega: 60 testes F01–F06 e sete testes L01 aprovados (67 no total). A suite HTTP final foi repetida após o hardening, com as versões fixadas. O CI verifica também que SQL e testes de regressão existentes não foram alterados.
