# CENTERWAY C01 — preparação HTTPS

Base PR #56, L01 `d32c6e8`. Configuração independente da arquitetura antiga C01–C10.
[Comparação e justificação](RESEARCH.md): Caddy num host estável, sem compra ou publicação
nesta missão. A API L01, OpenAPI, F06 e todos os motores são reutilizados sem alterações.

## Âmbito efetivamente validado

| Item | Estado nesta entrega |
|---|---|
| Infraestrutura preparada | Caddy, Gunicorn TLS, certificados locais, templates systemd, preflight e CI |
| Infraestrutura testada localmente | Cliente HTTPS → Caddy real → Gunicorn HTTPS → PostgreSQL verify-full; dados sintéticos |
| Infraestrutura publicada | **Não** |
| Conectividade HTTPS externa comprovada | **Não** |

O certificado local tem cadeia, validade e nomes verificados por clientes que confiam
**explicitamente** no CA local. Não é um certificado de uma autoridade pública nem
uma prova de conectividade pela Internet. A configuração pública usa ACME automático,
mas nenhum certificado público foi pedido, emitido ou testado nesta missão.

## Demonstração local, só dados sintéticos

Requisitos: Docker local, Python 3.12/venv, OpenSSL, Bash e acesso ao índice de pacotes
e à imagem oficial Caddy fixada por digest. Na raiz do repositório:

```sh
./recovery-mvp/infra/demo.sh
```

A saída identifica URL `https://localhost:<porta>` e diretório privado temporário.
O script cria a base descartável e contas aleatórias através do provisionador L01;
nenhuma credencial administrativa é fornecida à API. Configura **demo=false** para
exercitar os guardas reais de HTTPS e PostgreSQL verify-full. Os dados continuam
inteiramente sintéticos, rotulados SYNTHETIC nos contratos/fontes. `demo=false` nesta
prova significa que os guardas de transporte estão ativos, não que os dados são reais
ou que o ambiente está em produção. Não inserir dados de clientes reais.

Os três certificados separados (edge, API e PostgreSQL) são assinados por um CA local
descartável com validade de dois dias. Chaves e credenciais ficam em diretório 0700,
ficheiros privados. O CA nunca é instalado automaticamente no sistema ou navegador.
Gunicorn e Caddy ligam apenas em 127.0.0.1, em portas altas; PostgreSQL tem mapeamento
**apenas loopback** para permitir a API local de teste. Nenhuma porta fica em 0.0.0.0.
Ctrl-C termina os processos, remove o container e apaga estado e chaves.

Exemplo de verificação local (substituir pelos caminhos/porta que o script mostrou):

```sh
curl --fail --cacert /private/temp/pki/ca.crt https://localhost:PORT/health
```

Não usar `-k`, contextos TLS sem verificação ou noTLSVerify. O endpoint health indica
liveness e `readiness=not_assessed`; não garante disponibilidade da base. Para o login,
usar as passwords aleatórias no credentials.json privado e o contrato L01. Guardar
pedidos/respostas de login em ficheiros 0600, nunca no Git ou histórico de shell.
Tokens pertencem ao cabeçalho Authorization e não ao URL. O README e OpenAPI L01
continuam a ser o contrato de autenticação e operações; nenhuma rota foi reconstruída.

A origem de teste é `https://lovable.example.invalid`, um identificador reservado usado
apenas como valor de Origin em testes; não é uma interface publicada. As origens reais
Lovable L02.2 não foram fornecidas nem alteradas. Antes de ativar um host público,
substituir pela lista exata de origens autorizadas no config.json L01, sem wildcard,
sem `null`, sem liberar todos os subdomínios lovable.app e sem concessão automática a
URLs de preview. Caddy encaminha OPTIONS, Authorization e Origin; CORS é decidido só
pela API, sem duplicar ou enfraquecer a política. Nenhum segredo vai para o frontend.

## Estrutura e fronteira de confiança

- `Caddyfile.loopback`: teste local com certificado explícito e bind loopback.
- `Caddyfile`: template público com hostname/email fornecidos pelo operador, HTTPS
  automático e HSTS inicial de um dia, sem preload/includeSubDomains.
- `gateway.caddy`: políticas comuns, rotas /health e /v1/*, TLS de upstream com CA e
  nome localhost verificados, timeouts e erro genérico 503. Sem acesso a ficheiros.
- `gunicorn.conf.py`: TLS real em loopback, mínimo TLS 1.2, headers de esquema vazios,
  sem Proxy Protocol, sem confiança em forwarding nem access log de credenciais.
- `preflight.py`: rejeita placeholders no modo público e configuração insegura;
  não consulta DNS, liga à base, publica ou garante prontidão.
- `systemd/`: units/env de preparação; **não instalados nem ativados** pelos scripts.
- `versions.env` / `fetch-caddy.sh`: imagem oficial por digest; extraem apenas o binário
  para testes/instalação futura. Não inicia servidor nem publica portas.

Caddy é a primeira terminação TLS; não se deve colocá-lo atrás de outro CDN/proxy sem
rever explicitamente a fronteira. Remove Forwarded/X-Forwarded-*/X-Real-IP e
CF-Connecting-IP. Gunicorn ignora ainda os headers de esquema, incluindo os que não
forem removidos. Um header `X-Forwarded-Proto: https` num socket HTTP não ativa HTTPS:
a API não-demo recusa-o. O cliente não escolhe o principal PostgreSQL: L01 continua a
confirmar o login individual em cada ligação e a aplicar scopes, RLS e políticas F04.

A API vê loopback como peer. Isso mantém o limiter L01 seguro contra falsificação de
IP, mas agrega o limite de login no proxy. Não reivindicamos rate limiting por cliente
externo, WAF ou defesa DDoS. A infraestrutura preserva sessões, expiração, logout,
permissões e recibos idempotentes; não cria verificações, resultados ou novas ações.

## Falhas e retoma

API parada, certificado de upstream não confiável ou erro de proxy retornam 503
`gateway_unavailable`, sem fallback HTTP/inseguro. Base indisponível retorna o 503
sanitizado L01; health pode continuar a responder 200 porque é apenas liveness.
Proxy parado causa falha de ligação TLS, não um sucesso simulado. Erros do gateway não
inventam headers CORS: um browser cross-origin pode vê-los como erro de rede, em vez
de conseguir ler o JSON 503; a retoma conserva a mesma chave de operação. Não há política de
retry de mutações no gateway. Após timeout/perda de resposta, repetir o mesmo request_id,
corpo e principal conforme F06; não gerar uma nova intervenção às cegas.

Sem access log HTTP ativo no Caddy; logs operacionais não devem ser enviados para
sistemas públicos. Os testes procuram passwords, DSNs e Bearers nos logs privados,
mas isso não é prova universal de ausência de fugas. Se for necessário acesso logado,
projetar redação de headers, corpos, query strings e retenção antes de o ativar.

## Preparação de host real — sem ativação automática

Pendentes: host autorizado sempre ligado, domínio controlado, DNS A/AAAA correto,
email ACME, origens Lovable exatas, firewall, certificados internos, PostgreSQL privado
com TLS validável e contas individuais L01, configuração privada, backups e operador.
Não há credenciais/domínio reais fornecidos nesta missão. Não comprar nem criar um
recurso pago sem autorização específica. O túnel alternativo também requer host e
configuração/credencial próprios, não provisionados aqui.

1. Num host **já autorizado**, preparar utilizadores de serviço `centerway` e `caddy`,
   repo somente leitura em /opt/centerway-basecamp e venv /opt/centerway-venv com os
   requirements L01. Não dar acesso de administração PostgreSQL ao utilizador da API.
2. Preparar /var/lib/centerway (0700 centerway), /var/lib/caddy (0700 caddy), api.json
   (0600 centerway) e envs privados em /etc/centerway. Usar os exemplos, preencher
   valores reais e configurar `demo=false`, origens exatas e DSNs `verify-full`.
   Permissões sugeridas: /etc/centerway e tls com root:root 0755 (apenas nomes/certificados
   públicos são visíveis); api.env root:centerway 0640; gateway.env root:caddy 0640;
   api.json e sessões dentro de /var/lib/centerway 0700. Chaves continuam 0600 do serviço
   respetivo; não dar a caddy leitura do api.json ou da chave TLS da API.
3. Provisionar certificado/chave para upstream localhost e CA confiável. A chave API
   é 0600 centerway; Caddy só precisa do certificado do CA, **não da chave desse CA**.
   Proteger/renovar os certificados; não reutilizar os certificados de dois dias da demo.
   Se PG for remoto, usar rede privada e CA/hostname corretos; nunca abrir 5432 à Internet.
4. Obter o binário Caddy fixado com fetch-caddy.sh num diretório privado e instalar
   como /usr/local/bin/centerway-caddy (root-owned, executável). Revisar atualizações
   e CVEs regularmente; pin não significa ausência de vulnerabilidades.
5. Rever as units fornecidas para paths/OS, permissões e conflitos com um Caddy já
   instalado. Gateway escuta publicamente apenas quando a unit for **explicitamente**
   iniciada depois de autorização; API fica em loopback. Firewall permite só os serviços
   aprovados, normalmente 443 e 80 para ACME/redirect; 8444/5432 nunca públicos.
6. Antes de iniciar, executar preflight e `caddy validate` com os envs privados da unit.
   Placeholders example.invalid são rejeitados. A validação sintática não emite um
   certificado público nem prova DNS ou alcance da rede. As units não têm reload via
   API administrativa Caddy (admin off); validar e fazer restart controlado.
7. A ativação real, DNS e emissão ACME são uma operação futura autorizada. Nessa altura,
   testar de uma rede externa com cadeia pública, Origin real e credenciais sintéticas,
   confirmar portas fechadas e documentar o resultado. Até lá, conectividade externa
   e certificado público permanecem **não comprovados**. Não configurar a Lovable
   para um endpoint não validado nem alterar o projeto nesta missão.

O URL base futuro será `https://<dominio-da-api>`. A interface deve usar esse URL
HTTPS desde o primeiro pedido; o redirect de porta 80 não protege credenciais que um
cliente já tenha enviado em HTTP. Não copiar DSNs, passwords PG, tokens de túnel ou
chaves TLS para variáveis de frontend. A manutenção dos termos/L01 e privacidade é
independente de o TLS funcionar.

## Administração pelo telemóvel

Usar um cliente SSH com chave protegida pelo dispositivo e, se já existir, acesso
administrativo privado/VPN aprovado. Não expor shells ou painéis de gestão na API.
A criação de VPN/contas não faz parte desta missão. Com o host já aprovado:

- Consultar `systemctl status centerway-api centerway-gateway` e os journals privados;
  não colar a saída de configurações/credenciais em chats públicos.
- Atualizar origens/envs através de editor SSH privado, validar e reiniciar apenas o
  serviço necessário. Não manter tokens/passwords em notas ou histórico do terminal.
- Parar `centerway-gateway` para cortar acesso público; isso não apaga evidências ou
  sessões na base. A retomada usa os mesmos recibos de operação.
- Para a demo sem publicar, usar forwarding SSH local para a porta localhost que o
  script mostrou. Num terminal móvel com curl, copiar **apenas ca.crt** por SSH e usar
  `--cacert`. A chave ca.key nunca sai do diretório privado. Um browser móvel sem
  confiança nesse CA não validará a demo; não desativar a verificação para contornar.

Nenhum destes comandos foi executado num host remoto nesta entrega. A administração
pelo telemóvel é um runbook preparado, não um ensaio com um dispositivo real.

## Testes e CI

```sh
./recovery-mvp/infra/test.sh
```

Executa as 67 verificações F01–F06/L01 originais e sete testes C01 de sockets reais.
`--tls-only` é uma repetição dirigida durante desenvolvimento. A suite C01 inclui
cadeia/hostname TLS, recusa de TLS legado, PostgreSQL TLS, CORS/OPTIONS, autenticação,
logout/expiração, empresas, headers forjados, idempotência concorrente/auditoria,
validação do template público sem ativação, paths secretos e indisponibilidade de
API/proxy/base, incluindo CA de upstream errada. Não usa TLS inseguro nem rede externa
para a demonstração. As dependências/imagens podem ser descarregadas durante setup;
isso não é um teste externo da API.

O workflow novo `recovery-mvp-https.yml` testa C01 e verifica que motores e L01 estão
intactos. O workflow L01 existente executa as 67 verificações; nenhum tem secrets de
produção ou passos de publicação. Resultados locais e GitHub Actions são reportados
separadamente. O job TLS precisa de Docker Linux, OpenSSL e rede de instalação.

Limites: um host, sem HA/SLA/load test, sem prova de firewall externo, DNS, emissão ou
renovação ACME pública, administração móvel ou integração Lovable externa. Os templates
systemd não foram ativados num host real e precisam de revisão de OS/paths/permissões.
Não houve teste de penetração independente ou auditoria completa de dependências.
PostgreSQL/image/tag e ações conservam os limites L01; Caddy está fixado por digest.
Os guardas de ativação são offline e não substituem revisão operacional.

A missão termina na infraestrutura preparada e na prova local sintética. Não declara
prontidão para produção e não avança para C02/L03.

Resultados locais: 74 verificações aprovadas (60 motores + sete L01 + sete C01). A suite TLS final foi repetida após o endurecimento do bind loopback; CI remoto tem resultado próprio e não é substituído por este registo local.
