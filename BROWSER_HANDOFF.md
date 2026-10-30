# CENTERWAY C04-PREFLIGHT — contrato de browser e GO/NO-GO

Base PR #61, 503eb0ea176f0e33ee1f06534a21488de3b60535. Documento para uma
**conexão futura**, sem modificar a Lovable, publicar ou alterar motores. A única correção na API é
a resolução dos métodos OPTIONS descrita abaixo.
A L03-OFFLINE e os 104 testes Lovable foram reportados pelo utilizador; não foram
executados nem verificados independentemente nesta missão. Não somar esses 104 aos
nossos testes backend. Os 71 exemplos sintéticos continuam os do PR #61, inalterados.

## Auditoria e decisões confirmadas

| Componente | Comportamento auditado | Resultado/limite |
|---|---|---|
| Caddy público preparado | ACME/TLS >=1.2, HSTS, admin off | Template validado anteriormente, sem emissão/servidor público |
| Caddy local | CA explícito, localhost/loopback, sem instalação de trust | HTTPS local real, sem prova pública |
| Upstream | TLS com CA e hostname localhost verificados | Não é HTTP mais um header declarativo |
| Forwarding | Remove Forwarded/X-Forwarded-*/X-Real-IP; Gunicorn ignora esquema por headers | Preservado; nenhum ProxyFix/trusted proxy novo |
| PostgreSQL | Logins individuais não privilegiados, verify-full e RLS empresarial | API continua a verificar identidade a cada ligação |
| CORS | Origem exata no servidor, sem wildcard/credentials; decisão só na API | Política preservada; proxy intacto |
| OPTIONS | Sem Bearer; verifica origem, rota, método e headers, não consulta a base | Não é autenticação nem permissão para executar |
| Erros da API | Headers CORS para origem permitida também em 401/403/404/409/422/503 | Browser poderá ler o JSON quando a API responder |
| API parada | Gateway retorna 503 genérico sem Access-Control-Allow-Origin | Browser cross-origin poderá ver só falha de rede; tratar como tal |
| Sessões | Bearer opaco, expiração absoluta, logout e config versionada | Sem cookies/renovação silenciosa; um nó/worker recomendado |

O anúncio Allow-Methods é GET, POST, DELETE, mas o método solicitado no preflight
é também verificado contra a rota Flask. POST em diretório de leitura é recusado.
Não há concessão de acesso por CORS. A auditoria encontrou um defeito no DELETE /v1/session: como GET e DELETE usam
regras Flask separadas para a mesma path, consultar só request.url_rule.methods
recusava o preflight DELETE válido. A correção consulta allowed_methods() do adapter
para a path e interseta com GET/POST/DELETE; não libera HEAD/OPTIONS ou outro método.
As chamadas efetivas mantêm a autenticação e as permissões originais. Não se reconstruiu
autenticação, motores ou arquitetura. Os guards CI de C03/handoff admitem somente esta
substituição exata em app.py (preserve_api.py); qualquer outra alteração falha. O resto
da API e as configurações HTTPS permanecem intactos.

## Origens exatas e configuração pendente

[origins.json](recovery-mvp/browser/origins.json) contém uma lista **vazia** de origens
reais revistas: **NO-GO** para futura publicação. Os URLs publicados/preview exatos não
foram fornecidos no pedido. Não adivinhar domínio Lovable, liberar *.lovable.app,
autorizar todos os previews ou usar api.getcenterway.com como origem da interface.
Origin é a origem da página que chama a API, não a origem da própria API.

A nova ferramenta é uma comparação **offline**, sem escrever configuração, chamar DNS,
publicar, conceder permissões ou provar titularidade dos nomes. Depois de obter a lista
exata aprovada para uma futura ativação, manter version=c04-origins-v1 e preencher
origins. Comparar com o JSON privado L01 (não copiar esse JSON para o Git/browser):

```sh
python3 recovery-mvp/browser/origins.py --config /private/api.json --origins recovery-mvp/browser/origins.json
```

Exige demo=false, ficheiro privado e lista não vazia, única e idêntica à configuração.
Recusa HTTP, wildcard, null, credenciais, paths/query/fragment, origens não canónicas,
nomes reservados e IPs na ativação. Portas não padrão só se explicitamente revistas;
não escrever :443 numa origem HTTPS canónica. Domínios com aparência real não são
prova de posse ou aprovação: essa revisão continua a cargo do operador.
O comando é só um gate adicional de origens; os preflights C01 e o checklist completo
continuam necessários. Não é um comando de ativação nem um validador de toda a segurança.

Os testes usam **apenas** https://lovable.example.invalid e
https://preview.example.invalid numa configuração temporária privada. A segunda origem
é um valor de teste, não um preview real autorizado. Nenhuma origem real foi ativada.

## Contrato para a futura interface

Fontes inalteradas: [OpenAPI](recovery-mvp/api/openapi.json),
[API L01/C02](recovery-mvp/api/README.md), [LOVABLE_HANDOFF](LOVABLE_HANDOFF.md),
[F06](recovery-mvp/ORCHESTRATION.md). Sem novos endpoints ou wrappers HTTP.
URL futuro: https://api.getcenterway.com; ainda não publicado nem validado externamente.
Não ativar chamadas da Lovable até cumprir GO e obter autorização específica.

- Usar HTTPS desde o primeiro pedido; nunca enviar credenciais em HTTP esperando redirect.
- Login POST /v1/sessions com JSON {username,password}; sem Bearer. Guardar o access_token
  real apenas em memória; não persistir em localStorage, URL, logs ou analytics.
- fetch deve usar credentials: 'omit'. Enviar Authorization: Bearer apenas em chamadas
  autenticadas; nenhum cookie, DSN, chave administrativa ou principal escolhido pelo cliente.
- Browser define Origin e faz OPTIONS automaticamente. Não definir Origin manualmente
  no frontend nem enviar cookies/headers X-Tenant-Id/X-Admin. Content-Type: application/json
  nos pedidos JSON; Authorization e Content-Type são os únicos headers custom permitidos.
- GET /v1/session confirma identidade/scopes, GET /v1/tenants/{tenant}/clients lista apenas
  client_id/display_name, com limit 1–100/default 50 e cursor after/next_cursor até null.
- GET .../clients/{client}/journey retorna envelope {data,demo} com f06-v1. Manter versões,
  evidências, hipóteses, lacunas e referências exatas. Scopes não são políticas F04.
- POST .../operations envia request_id, operation, arguments. Conservar a chave antes
  de enviar e repetir **a mesma chave/corpo/identidade** após resposta incerta; nunca
  disparar outra intervenção automaticamente. Separar HTTP, receipt e business result.
- DELETE /v1/session retorna 204 **sem JSON**. Limpar token e dados visíveis. 401 por
  expiração/logout/configuração alterada exige novo login, sem renovação silenciosa.
- 403 não autoriza testar outras empresas; 404 não prova eliminação de cliente;
  409 exige resolver conflito de chave; 422 pode ser error HTTP ou recibo persistido error.
- 503 produzido pela API inclui CORS para origem permitida. Gateway/TLS/rede/CORS podem
  produzir uma rejeição fetch sem status legível. Não converter falha em lista vazia,
  recuperação, sessão válida ou novo request_id. Mostrar indisponibilidade e preservar contexto.
- HTTP 200, execução bem-sucedida e recuperação são níveis separados. Manter
  causal_attribution/independent_verification=not_established. demo=false na prova TLS
  não converte dados SYNTHETIC em dados reais. work_items históricos não autorizam ações.

## OPTIONS verificável e matriz de validação

Sem token e sem corpo. Exemplo exclusivamente local, substituir PORT e CA pelo estado
privado da demo C01; este pedido não contacta qualquer domínio real:

```sh
curl --cacert /private/demo/pki/ca.crt -i -X OPTIONS https://localhost:PORT/v1/session \
  -H 'Origin: https://lovable.example.invalid' \
  -H 'Access-Control-Request-Method: DELETE' \
  -H 'Access-Control-Request-Headers: Authorization'
```

Esperado: 204 vazio, Access-Control-Allow-Origin igual à origem exata, Vary contendo
Origin, Allow-Methods incluindo DELETE, Allow-Headers Authorization/Content-Type,
Max-Age=300, Cache-Control=no-store, sem Allow-Credentials. Não usar -k.
Um preflight 204 não comprova validade de sessão, acesso ao cliente ou disponibilidade
PostgreSQL: estes requisitos são verificados na chamada efetiva. Preflight continua
204 com a base parada; com a API parada, o gateway falha fechado.

| Teste novo | Cobertura verificável |
|---|---|
| all_route_preflights | 7 combinações rota/método, 2 origens de teste, headers case-insensitive; nenhum evento de auditoria novo |
| unreviewed_origins | null/wildcard/HTTP/lookalike/subdomínio/porta/path; métodos/headers recusados; CORS não substitui Bearer |
| sessions_directory | 4 principais, leitura por scope/empresa, logout/expiração, origem secundária |
| operations | Escrita por alice, reader/reviewer recusados, replay, conflito 409, erro persistido 422, auditoria única e RLS bob |
| http_errors | CORS legível em 401/404/422 e login errado |
| offline_origin_review | Lista vazia e desvios bloqueados; comparador não concede autorização |
| database_gateway_failure | Base parada: 503 API e 204 OPTIONS; API parada: 503 gateway sem CORS |

Executar `./recovery-mvp/browser/test.sh`: 90 regressões anteriores + sete novos testes
= **97 testes backend**. --browser-only limita a repetição à nova suite. Os 14 pares
OPTIONS são subcasos, não 14 testes adicionais. Cinco workflows independentes executam
as suites no PR, sem deploy/secrets cloud/upload de estado privado. Nenhum teste abre
servidor público ou consulta DNS da Lovable. Ferramentas fazem downloads de dependências.

**Limite da prova:** são sockets HTTPS reais com headers de browser, usando http.client;
não é Chromium/Firefox nem um browser hosted a aplicar CORS. O comportamento de erros
opacos descrito é o contrato esperado para browser; a ausência/presença dos headers e
as respostas de rede foram medidas. L03-OFFLINE/104 testes são resultado externo reportado.
Testes positivos não demonstram readiness de produção.

## Checklist GO/NO-GO para publicação futura

Estado desta entrega: **NO-GO para publicação / integração live**. GO local significa
apenas que os testes e os contratos desta preparação passam, nunca autorização para publicar.

| Gate | Prova exigida antes de GO público | Estado atual |
|---|---|---|
| Autorização | Missão explícita para recursos/ativação; orçamento e operador definidos | Pendente; C04 proíbe publicação |
| Origens | URLs publicados/preview exatos aprovados, origins.json preenchido e comparação privada aprovada | Pendente, lista vazia |
| Infraestrutura | Host elegível disponível, custos reais/quotas/backup aprovados | Não provisionada |
| DNS/TLS público | DNS autorizado, cadeia pública/hostname/renovação comprovados desde rede externa | Não executado |
| Rede privada | Firewall/NSG: só entrada necessária; PG e Gunicorn inacessíveis externamente | Só loopback local testado |
| Identidade | Principais individuais sem privilégios, RLS/scopes e revogação confirmados no destino | Local validado; destino pendente |
| Sessões/segredos | Discos/configs privados, expiração/logout, rotação e recuperação de conta | Local validado; operação/rotação pendentes |
| CORS externo | OPTIONS e chamadas reais desde cada origem autorizada, negativas e erro opaco | Só prova local por headers |
| Browser real | fetch real em frontend hosted, sem cookies, sem mixed content, tratamento 401/403/503/rede | Não executado nesta missão |
| Funcional | Percurso sintético completo e não duplicação no destino; sem efeitos reais | Regressão local; destino pendente |
| Operação | Backup/restauro, certificados internos, logs, monitorização, rollback/corte do gateway | C03 mantém pendências |
| Evidência final | SHA/testes, origens e prova externa registados; revisão GO separada | CI desta preparação não substitui prova externa |

Se algum gate estiver pendente: NO-GO. Não ativar Bearer/login frontend, alterar DNS,
abrir portas ou publicar para contornar a falta de prova. Um futuro proxy/CDN exigirá
revisão própria da fronteira de confiança; não confiar indiscriminadamente em headers.
Sem compra, cloud, DNS, email, Lovable ou main modificados nesta missão.
