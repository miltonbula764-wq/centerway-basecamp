# C03 — demonstração persistente preparada para uma futura VM gratuita

Base: PR #58, C02 `9d8c124`. [Investigação, recomendação e alternativas](RESEARCH.md).
Tudo é independente da arquitetura antiga C01–C10. Não altera F01–F06, API L01/C02,
SQL existente, configurações C01 ou Lovable. Não existe implantação cloud nesta entrega.

| Âmbito | Estado |
|---|---|
| Preparação | Bootstrap privado, persistência, cenário HTTPS completo e template systemd |
| Validação local | Docker PostgreSQL 17 real + Caddy → Gunicorn TLS + API/motores reais; dados sintéticos |
| Implantação real | **Não**; nenhuma conta/VM/serviço público criado |
| HTTPS externo / domínio | **Não comprovado**; api.getcenterway.com não foi alterado nem contactado pela demonstração |

## Requisitos concretos

Perfil recomendado condicional: VM A1 ARM64 1 OCPU/4 GB, Ubuntu 24.04 LTS, boot 50 GB
em Always Free, apenas uma máquina e um worker API. Reservar pelo menos 10 GB livres
para imagens, atualizações, logs e backup temporário; monitorizar espaço. A proposta
não é benchmark nem garante capacidade gratuita. Para repetir localmente, Linux x86_64
ou ARM64, Docker Engine local ativo, Python 3.12/venv, OpenSSL, Bash e acesso HTTPS aos
índices Python/registries. A execução ARM ainda precisa de validação num host ARM.

PostgreSQL: imagem por digest em versions.json, 128 MB shared_buffers, 30 ligações,
limite de container 768 MB; persistência em volume Docker nomeado. Um segundo volume
contém certificados PG. A API tem um worker/quatro threads conforme C01. Um diretório
privado fora do checkout contém SQLite de sessões, PKI, configuração, passwords e
recibos do cenário. Não há pooling global, HA ou escalabilidade distribuída.

Nenhuma porta escuta em 0.0.0.0. API, gateway de demonstração e mapeamento PostgreSQL
são exclusivamente 127.0.0.1 em portas altas registadas em manifest.json. PostgreSQL
não é exposto à Internet. Sessões e DSNs são os da L01, com logins individuais e
sslmode=verify-full; o login administrativo só é usado no setup pelo operador via
Docker, nunca no processo da API ou no browser. Acesso Docker é equivalente a root:
este perfil requer host dedicado e operador de confiança, não alojamento multiutilizador.

## Instalação reproduzível em ambiente privado

Não criar VM/conta para executar estes passos nesta missão. Numa máquina Linux já
autorizada, a partir da raiz do repositório, escolher um caminho absoluto **novo**, sem
espaços e fora do checkout, cujo pai já exista. O exemplo usa /tmp apenas para repetição
local; num host futuro usar disco persistente, por exemplo /var/lib/centerway/demo.

```sh
./recovery-mvp/cloud-demo/bootstrap.sh /tmp/centerway-c03-demo
```

O bootstrap cria estado 0700/segredos 0600, venv com requirements L01, extrai Caddy C01
fixado, cria volumes/container **locais**, aplica 001–008 e a migração C02 inalteradas,
provisiona só contas/dados sintéticos e uma política F04 limitada. Não descarrega scripts
remotos para executar como root. Não aceita estado existente nem aplica upgrade/reseed
no arranque. Falha parcial conserva manifest initializing e exige inspeção; não apagar
ou reexecutar init sobre dados existentes. A API não recebe postgres.env.

Iniciar o serviço em primeiro plano:

```sh
/tmp/centerway-c03-demo/venv/bin/python -B recovery-mvp/cloud-demo/runtime.py serve --state /tmp/centerway-c03-demo --caddy /tmp/centerway-c03-demo/bin/caddy
```

Noutro terminal, executar **uma vez** a fixture completa através da API autenticada:

```sh
/tmp/centerway-c03-demo/venv/bin/python -B recovery-mvp/cloud-demo/scenario.py --state /tmp/centerway-c03-demo --caddy /tmp/centerway-c03-demo/bin/caddy
```

O serviço mostra a URL localhost. Verificar com `curl --cacert` apontado para
`/tmp/centerway-c03-demo/pki/ca.crt`; nunca usar -k nem instalar o CA automaticamente.
Ler passwords apenas no credentials.json privado com editor seguro; não as enviar por
chat, capturas de ecrã, Git, argumentos de shell, logs ou URLs. O cliente deve enviar
Bearer em Authorization e seguir [README/OpenAPI L01/C02](../api/README.md).

A origem CORS inicial é exclusivamente https://lovable.example.invalid, um placeholder
usado em testes. Nenhum projeto Lovable foi alterado ou ligado. Pedidos não-browser
sem Origin continuam a precisar de sessão. OPTIONS mantém o comportamento L01/C01.
Config demo=false ativa os guardas reais de transporte; **todos os dados continuam
sintéticos** e rotulados SYNTHETIC. O indicador demo não certifica autenticidade de dados.

## Contas e percurso demonstrativo

| Conta | Permissão demonstrativa |
|---|---|
| alice | Empresa A, cliente A; operações L01; uma pré-autorização sintética limitada |
| reviewer | Empresa A, cliente A; append_investigation/investigate; login PG separado |
| reader | Leitura de diretório/journey da A; sem operações de escrita |
| bob | Empresa B, cliente B; sem visibilidade da A |

Existe outro cliente da A fora do scope HTTP, para demonstrar recusa. Cada conta recebe
password aleatória de login e password PostgreSQL distinta. Não existem credenciais
fixas de demonstração publicadas. Alterar scopes/credenciais invalida sessões após
restart conforme L01. O diretório devolve nomes persistidos, não placeholders criados
pelo transporte.

A fixture fornece ao motor contratos e resultados declarados sintéticos (9 e 8), duas
janelas contíguas anteriores e um fator com evidências explicitamente sintéticas. Um
login de teste separado regista verificações de fixture: **não são verificações humanas
ou independentes**. A F03 conserva essa distinção. O setup administrativo autoriza
somente set_synthetic_flag, num recurso isolated_synthetic, principal http_alice,
risco máximo 1, uma tentativa, validade 24 h, idade de relatório/observação até uma hora.
Não há endpoint para conceder políticas ou efeito fora desse recurso.

A F04 executa o flag reversível e a F05 recebe janelas iguais anteriores/posteriores
à execução. Primeiro avalia dados ausentes (inconclusivo); depois recebe o valor de
fixture 15 e avalia a recuperação. Os intervalos são deliberadamente comprimidos para
teste; não modelam duração real de negócio. A fixture não altera resultados dos motores
nem infere causalidade. O resultado e o pedido idempotente F06 ficam em
scenario-result.json, privado, com synthetic_only=true e causal_attribution=not_established.
Não é um simulador de clientes reais.

scenario-started.json impede repetir o cenário após início/interrupção. Se houver falha,
consultar o journey e os recibos com os IDs/request_id persistidos pelos motores; não
iniciar outra intervenção para compensar uma resposta perdida. Não há retoma automática
do script de fixture parcial nem reautorização automática após 24 h. Não renovar políticas
para contornar limites. Para uma nova demonstração, preparar **outro estado sintético**.

## Reinício, persistência e falhas

Ctrl-C termina API/gateway e preserva dados, sessões, PKI, volumes e container PG. Serve
relê manifest/config e reabre os mesmos recursos; não executa migrações/seed. Docker
restart policy é unless-stopped. Para parar também a base privada:

```sh
/tmp/centerway-c03-demo/venv/bin/python -B recovery-mvp/cloud-demo/runtime.py stop-db --state /tmp/centerway-c03-demo --caddy /tmp/centerway-c03-demo/bin/caddy
```

O próximo serve inicia o mesmo container. Divergência dos hashes de migração ou imagem,
estado incompleto ou binding PG diferente de loopback bloqueiam o arranque. Um upgrade
futuro exige procedimento administrativo próprio. Não usar docker system prune --volumes
nem apagar diretórios/volumes para resolver indisponibilidade.

Base indisponível: chamadas de dados falham fechadas com 503; health continua apenas
liveness, sem prova de readiness. API indisponível: Caddy responde erro genérico 503.
Falha do gateway resulta em perda de transporte. Repetir comandos com request_id original
conforme F06, nunca gerar nova chave automaticamente. Sessões não expiradas sobrevivem
reinícios; logout revoga-as e expiração absoluta continua a aplicar-se. Sem TLS verificado
não efetuar login.

## Operação futura pelo telemóvel — guia preparado, não executado

Usar cliente SSH com chave protegida/biometria, verificar fingerprint por canal confiável
e MFA na conta cloud. Um futuro host deverá ser criado pelo titular numa missão autorizada,
com perfil/custos confirmados. Em Ubuntu 24.04, instalar por repositórios oficiais Git,
Python 3.12/venv, OpenSSL e Docker Engine; confirmar `python3 --version` e `docker info`.
Clonar este PR em /opt/centerway-basecamp e manter uma cópia da revisão utilizada.

Na futura máquina autorizada, com Docker instalado conforme a
[documentação oficial Ubuntu](https://docs.docker.com/engine/install/ubuntu/), os passos
abaixo preparam o operador e a instalação privada. Não foram executados num servidor
real nesta missão; não abrem o gateway público:

```sh
sudo apt-get update
sudo apt-get install -y git python3 python3-venv openssl
sudo useradd --system --user-group --create-home --home-dir /var/lib/centerway --shell /usr/sbin/nologin centerway
sudo usermod -aG docker centerway
sudo install -d -o centerway -g centerway -m 0700 /var/lib/centerway
cd /opt/centerway-basecamp
sudo -u centerway ./recovery-mvp/cloud-demo/bootstrap.sh /var/lib/centerway/demo
```

Não executar useradd se a conta já existir; rever a identidade e o dono dos ficheiros.
O checkout deve ser legível pelo operador, sem permissão de alterar código pela API.
O template systemd fornecido assume
esses caminhos e acesso Docker; rever permissões antes de o instalar. Não está instalado
nem foi testado sob systemd real nesta entrega. Depois de uma futura aprovação de uso
nesse host, o operador pode instalar a unit local, daemon-reload e ativá-la. A unit só
inicia loopback, não publica o gateway. Consultar estado/reiniciar com:

```sh
sudo systemctl status centerway-demo --no-pager
sudo systemctl restart centerway-demo
sudo journalctl -u centerway-demo -n 30 --no-pager
```

Não partilhar journal/ficheiros de estado sem revisão. Usar sessões SSH separadas ou
um terminal persistente para a fixture; o script não precisa de guardar passwords no
telemóvel. Não há prova nesta missão de acesso SSH móvel, reboot do SO ou cloud.

## api.getcenterway.com — apenas ativação futura

future-gateway.env.example fornece o hostname pedido, sem ser carregado pelo runtime.
Reutilizar exclusivamente Caddyfile/gateway/preflight/systemd C01 após autorização
explícita. Pré-requisitos pendentes: host elegível disponível, controlo de DNS, registo
A/AAAA correto, firewall/NSG revistos, entrada 80/443 para ACME/gateway e SSH restrito,
origens Lovable reais exatas, contacto ACME autorizado, proteção dos ficheiros TLS,
backups e plano de recuperação. Não abrir 5432 nem a porta Gunicorn. Não confiar em
X-Forwarded-*; a C01 estabelece TLS real até Gunicorn.

Não copiar o certificado localhost como certificado do domínio. O gateway público
futuro precisa de certificado público ACME válido e armazenamento Caddy persistente;
nenhum pedido ACME foi feito. Separar/desativar o gateway de teste antes de configurar
o público; não interpretar validar a sintaxe como testar emissão, DNS ou conectividade.

## Testes e limitações

```sh
./recovery-mvp/cloud-demo/test.sh
```

Executa os 79 testes anteriores e quatro novos. --persistent-only limita uma repetição
à nova suite. Usa conexões HTTPS reais com CA explícito, PG TLS, contas não privilegiadas,
cenário F01→F02→F03→F04→F05 por F06/L01, C02, sessão, permissões, isolamento, reinício
PG/API/gateway, persistência, replay sem duplicação/auditoria, falha PG/API, segredos e
recusa de init/seed repetidos/drift. O workflow cloud-demo é independente e sem secrets
cloud; os workflows anteriores permanecem intactos. Nenhum faz deploy.

Limitações: host único, sem SLA, limitação de login agregada no proxy, scopes estáticos,
sem SSO/MFA na API, sem backup/restore automatizado ou ensaio de recuperação de VM,
sem monitorização operacional completa nem benchmark no perfil proposto. Persistência
em disco não é backup. Antes de qualquer exposição futura, preparar cópias privadas
cifradas de PostgreSQL, configuração/PKI e SQLite consistente, fora do host e dentro
das quotas; verificar restauro. A perda/reclamação da VM não foi simulada aqui.

Certificados internos: CA local de 90 dias, folhas 30 dias. Expiração exige renovação
planeada e reinício; não há automação de renovação interna, rotação de segredos ou
extensão da autorização F04. Não prolongar demonstrações além destes limites sem nova
revisão. Os logs de processo não têm rotação automática; controlar crescimento. Caddy
e PG são fixados por índice digest multiarch; pacotes Python estão fixados, sem hashes;
updates exigem revisão. Execução ARM, instalação num host Oracle e systemd ainda pendem.
Aprovação de testes não é prontidão para produção. Nenhum serviço foi publicado e
nenhuma conectividade HTTPS externa foi comprovada.
