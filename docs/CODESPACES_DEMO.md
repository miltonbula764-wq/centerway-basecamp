# Abrir o verdadeiro CENTERWAY no Android — demo privada

Esta entrega usa a main `d465943`, preservando migrações 0000–0014, journal, snapshots e ajustes da Lovable. Não instala nada no backend hospedado. O devcontainer tem Docker próprio, PostgreSQL 17, GoTrue, PostgREST, gateway e a aplicação existente. A porta 8080 serve frontend e API na mesma origem. Não é o mapa ilustrativo.

## Abrir no telemóvel

1. No GitHub, abrir este PR/branch `feat/codespaces-demo` → **Code → Codespaces → Create codespace on this branch**. Depois de eventual merge autorizado, pode usar main. Escolher a máquina **2 cores**. Verificar primeiro a quota gratuita disponível da conta; não ativar faturação ou ultrapassar a quota. Esta entrega não cria um Codespace nem altera limites de cobrança.
2. Aguardar a criação do devcontainer. O arranque é automático. No terminal aparece `https://NOME-8080.app.github.dev/app/casos`. No separador **Ports**, a porta **8080 deve estar Private**. Abrir essa ligação no Chrome Android, autenticado no GitHub com a conta dona do Codespace. Não escolher Public ou Organization. PostgreSQL e portas internas não devem aparecer em Ports.
3. No editor web do Codespace, abrir `.centerway-demo/app/e2e/private/mvp-users.json`. Copiar a password temporária de `admin`; entrar no CENTERWAY com `mvp-admin@example.invalid`. Os outros utilizadores sintéticos são `mvp-operator@example.invalid` e `mvp-viewer@example.invalid`. Nenhuma destas credenciais é do backend Lovable. Não partilhar o ficheiro.
4. Selecionar a empresa **Atlas SaaS · SINTÉTICO operacional** ou **FlowReports · MVP SINTÉTICO**, depois um cliente em **Casos**. Objetivos/avaliações C04, Core, investigação, plano, autorização, execução, observação e histórico usam PostgreSQL/RPCs reais. Clientes, Perfil e Dados dão acesso aos blocos C01–C04.

O GitHub protege a ligação privada; o CENTERWAY exige também a sua autenticação sintética. A sessão da aplicação fica no armazenamento do navegador e é revalidada pelo GoTrue. Recarregar a página não apaga o caso. Cookies de acesso ao port forwarding são geridos pelo GitHub, não pela aplicação.

## Se o arranque precisar de ser repetido

No terminal da raiz:

```sh
python3 scripts/demo/manage.py start --background
```

O comando confirma via GitHub que 8080 é privada e rejeita encaminhamentos das portas 5432, 9999, 54321, 54322 e 5173. Se o GitHub recusar gerir/listar as portas, o arranque fica bloqueado. Confirmar a conta dona do Codespace e a autorização da CLI `gh` para o Codespace atual; remover portas internas de Ports e voltar a executar. Não resolver tornando a porta pública ou desativando verificações. O editor Codespaces fornece a autenticação GitHub; não é necessária qualquer credencial Lovable.

Para parar serviços mantendo dados:

```sh
python3 scripts/demo/manage.py stop
```

Depois parar o próprio Codespace no menu GitHub para cessar consumo de quota. Serviços parados dentro de um Codespace ainda ativo não interrompem a cobrança/contagem do Codespace. Não é possível ao script conhecer ou garantir os limites gratuitos da conta.

Para eliminar **apenas esta demo sintética** e criar outra de HEAD:

```sh
python3 scripts/demo/manage.py reset
python3 scripts/demo/manage.py start --background
```

`reset` elimina o volume e os dados sintéticos da demo, incluindo alterações feitas durante a apresentação. Nunca é executado automaticamente. O comando rejeita containers/volumes de outra stack. Não corre migrações numa base existente durante `start`/resume. Atualizações de código/migrações requerem reset explícito da demo ou outro Codespace; o estado pronto regista o commit exportado em `.centerway-demo/ready.json`.

## Dados e limites funcionais

Reutilizam-se integralmente `mvp-seed.mjs`, `operational-seed.mjs` e os carregadores de histórico existentes. Atlas não exige sinal candidato de deterioração C02. O cliente `prospective` permite abrir um caso, investigar uma hipótese/impedimento, preparar plano, autorizar e registar execução humana agora. A janela é explicitamente escolhida no plano. Medições anteriores à execução não demonstram recuperação; nesse percurso o sistema pode manter o caso aberto.

Os clientes `historical_resolved` e `historical_unmet` têm **C05–C08 retrospectivos fictícios**, marcados nos eventos e na interface. Não são prova de autorização/execução histórica ou espera passada observada. C09 e C10 são operações reais: permitem demonstrar encerramento elegível ou continuidade por objetivo não atingido. FlowReports mantém exclusivamente `flowreports-demo-v1`, incluindo a sua janela de 14 dias e limitações.

Preservam-se um indicador e um ciclo por caso, condições textuais revistas por humano e ausência de reabertura automática/conectores/causalidade automática. Contrato: `docs/OPERATIONAL_JOURNEY.md`.

## Isolamento e persistência

A aplicação é exportada de HEAD para `.centerway-demo/app` **sem ficheiros `.env*`**. Variáveis herdadas PG/Supabase/VITE/Lovable e tokens GitHub são removidos dos processos da aplicação. A URL pública é derivada apenas do Codespace atual. Só o processo de gestão usa `gh` para confirmar a porta privada. O cliente Supabase e a configuração de produção continuam intactos.

A API usa `/auth/v1` e `/rest/v1` na mesma origem HTTPS; SSR usa apenas o gateway interno. Não há localhost no destino de pedidos do navegador remoto. Os serviços internos escutam exclusivamente no loopback. Só 8080 é declarada para encaminhamento; deteção automática das outras portas está desligada. Hosts permitidos são explícitos. O servidor recusa ficheiros privados, `.env`, migrações e caminhos arbitrários do workspace.

Cada demo cria o seu segredo JWT, passwords e utilizadores `example.invalid`. GoTrue mantém JWTs de utilizador de uma hora e refresh tokens reais; a chave pública anon da demo dura sete dias e é renovada em `start`, sem dar permissões de empresa a anónimos. Depois de carregar fixtures, novos registos de utilizadores ficam desativados. RLS, memberships e RPCs não são enfraquecidos.

O volume Docker `cw-codespaces-demo-data` é próprio e descartável, limitado ao Codespace. Persiste entre stop/start e preserva utilizadores, objetivos, casos e eventos; apagar/recriar o Codespace ou executar reset elimina os dados. A camada Docker-in-Docker também tem de ser preservada pelo Codespaces. Um rebuild que elimine essa camada exige demo nova; o arranque não adivinha nem importa dados de outra base. A perda de um estado parcial exige reset explícito, nunca destruição silenciosa.

## O que foi verificado e o que não foi

O workflow `Isolated Codespaces configuration and mobile HTTPS` constrói e executa o **devcontainer configurado**, instala as ferramentas e inicia a stack completa numa base própria. Executa revisão SQL com papéis reais, TLS local em `https://demo.centerway.test:8443`, Chrome com emulação Pixel 7, autenticação, reload, navegação, percurso operacional, isolamento, negação de ficheiros privados e preservação após stop/start. O certificado local é confiado apenas pelo teste (CA explícita para curl/Node e chave pública específica para Chromium); não há desativação global de TLS. Os testes anteriores continuam no workflow existente.

Esse hostname de teste resolve para loopback **dentro do devcontainer de teste**. Não é uma URL remota Codespaces. A emulação Chromium Android não equivale a um teste num telemóvel físico.

Nesta sessão o proxy de rede recusou a ligação CONNECT a `api.github.com` (HTTP 403), impedindo listar ou gerir Codespaces; não foi possível abrir ou verificar uma URL HTTPS real do Codespaces nem o login GitHub da conta do fundador no Android. Esta verificação remota permanece pendente e deve ser feita nos passos acima. Resultados efetivos do CI e commit validado constam do PR; a existência do workflow não é por si só prova de sucesso.
