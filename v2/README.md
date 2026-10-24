# CENTERWAY V2 — Missão 01

Laboratório independente, sem imports da aplicação antiga. Requer Python 3.11+
(testado com 3.12.14). Não instalar as dependências npm da raiz.

## Abrir e testar

```sh
git checkout centerway-v2/missao-01
cd v2
python3 -m centerway.server
```

Abrir **http://127.0.0.1:8080** no navegador da máquina onde o servidor corre.
Para ambiente remoto, encaminhar a porta 8080 para o computador local (por exemplo,
`ssh -L 8080:127.0.0.1:8080 utilizador@maquina`). O servidor escuta apenas loopback
por predefinição. Não foi disponibilizado um URL público.

Palavra-passe pública de teste para todas as contas: **centerway-local**.

| Conta | Acesso |
| --- | --- |
| `demo` | Operador de AtlasFlow e NimbusDesk |
| `atlas` | Operador apenas de AtlasFlow |
| `leitor` | Só leitura de NimbusDesk |

1. Entrar como operador e iniciar C01. Avançar por C02, C03 e C04, inspecionando os registos.
2. Em AtlasFlow, executar C05: retoma o conector pausado e entrega 12 trabalhos pendentes.
3. Executar C06: confirma operação e 12 novos resultados persistidos (meta: pelo menos 4).
4. Trocar para NimbusDesk e repetir C01–C05: a ação ativa o percurso de primeiro valor.
5. Verificar C06: operação recuperada, valor ainda não confirmado (zero novos resultados).
6. Usar «Simular uso posterior»: grava quatro relatórios concluídos, explicitamente simulados.
   Verificar novamente: agora confirma valor no sandbox. As duas verificações ficam no histórico.
7. Recarregar ou reiniciar o servidor: os casos e efeitos permanecem. Sair e experimentar as contas restritas.

Dados em `v2/data/centerway.sqlite3`, ignorados pelo Git. Para repetir do zero sem
apagar histórico de ensaios, parar o servidor e iniciar com outra base:
`python3 -m centerway.server --db data/novo-ensaio.sqlite3`.

## O que existe

- `centerway/c01.py` a `c06.py`: componentes separados; `core.py`: estados, permissões,
  isolamento, coordenação e histórico; `store.py`: SQLite e cenários; `server.py`: HTTP/sessões.
- C01 lê 14 dias persistidos da mesma fonte. C02 compara duas janelas de sete dias,
  exige baseline positivo e sinaliza queda de pelo menos 30%. Configuração e métrica explícitas.
- C03 preserva estado, revisão e IDs das observações com hash. Um sinal de C02 não autoriza execução.
- C04 escolhe entre ações do catálogo autorizado, com base na causa investigada e evidências.
  **Só existe `simulator-v1`: não há integração de IA real nem chamadas a provedores.**
  O ambiente desta missão não tem credenciais de IA configuradas. Mesmo que se adicione
  uma chave ao ambiente, esta versão continua explicitamente em modo simulador.
- C05 altera o ambiente persistido. Estado, execução única por caso e histórico são
  gravados na mesma transação `BEGIN IMMEDIATE`. Pedidos repetidos devolvem `reused`,
  sem repetir efeitos. Evidência desatualizada ou ação não autorizada bloqueia execução.
- C06 relê a base depois da intervenção, verifica disponibilidade/fila e mede novos
  resultados contra o estado anterior à intervenção. Não infere valor de disponibilidade.
- Sessões opacas de oito horas em cookie HttpOnly/SameSite, passwords com scrypt,
  memberships no servidor, sem aceitar evidências/ações/roles do navegador.
  Observações, execuções e histórico têm triggers que bloqueiam UPDATE e DELETE.

## Validação reproduzível

Sem dependências externas:

```sh
python3 -m unittest discover -s tests -v
```

16 testes: ciclos das duas SaaS, persistência com reabertura de SQLite, permissões
reais via HTTP/cookies, isolamento com o mesmo ID de cliente, dados insuficientes,
baseline zero, sinal saudável, ordem de estados, catálogo, evidência desatualizada,
rollback de falha parcial, histórico append-only e oito execuções concorrentes com
um único efeito.

QA opcional de navegador (Node 20+, dependência apenas de desenvolvimento):

```sh
npm ci --ignore-scripts
npx playwright install chromium
npm run test:browser
# Alternativa, com Chromium já instalado:
CHROMIUM_PATH=/usr/bin/chromium npm run test:browser
```

O script inicia e termina um servidor próprio numa porta livre e usa uma SQLite
temporária. Cobre os dois percursos através dos botões reais, persistência após
reload, larguras 360/390/1280, resposta atrasada ao trocar de SaaS, leitor e operador
isolado. A imagem de QA fica em `test-results/atlas-mobile.png` (ignorada pelo Git).
A CI da V2 executa estes testes sem credenciais nem deploy.

## Limites

- Sandbox com duas SaaS e um cliente por SaaS, um caso por cliente e regras fixas.
  Reabrir ciclos, ingestão externa, agendamento, novas contas e configurações de
  valor por SaaS não estão implementados. Para outro ensaio, usar outra base.
- As observações iniciais são fixtures de 14 dias até à data de criação da base;
  bases envelhecidas podem bloquear novos casos por cobertura insuficiente.
- As intervenções e a medição são reais **dentro da SQLite do teste**. Não existem
  conectores externos, envio de mensagens, recuperação financeira ou prova de retenção.
  A meta de quatro resultados demonstra valor no cenário, não uma tendência sustentada.
- As contas têm credenciais públicas. HTTP da biblioteca padrão, sem TLS, rate limiting
  ou administração de identidades. Destina-se ao uso local, não a produção.
- Isolamento é aplicado no backend, com testes de pedidos hostis. SQLite não tem RLS;
  acesso direto ao ficheiro pela máquina deve ser considerado acesso administrativo.
- A aplicação histórica não foi executada nem validada nesta missão.
