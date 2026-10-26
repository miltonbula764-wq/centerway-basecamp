# CENTERWAY V2 — Missão 14

[Continuidade: encerramento autorizado, novos ciclos, API e atualização explícita](CONTINUITY_CONTRACT.md).
Um ciclo ativo por cliente, histórico preservado e incerteza mantida bloqueada.

[Contrato da orquestração, estados, lotes e consulta autenticada](ORCHESTRATION_CONTRACT.md).
Encaminhamento automático até ao próximo requisito; sem fabricar investigação, IA ou aprovação.

[Contrato C06, exemplos sintéticos e instruções](C06_CONTRACT.md).
Execução, recuperação operacional e valor avaliados separadamente; nenhum resultado real presumido.

[Contrato C05: aprovação explícita, execução de teste, auditoria e limites](C05_CONTRACT.md).
Intervenções externas e production bloqueados; sem adaptador instalado ou recuperação presumida.

[Contrato C04, configuração segura, testes e limitações](C04_CONTRACT.md).
A IA propõe; a validação é independente e não autoriza execução. Sem credenciais, inferência indisponível.

[C03 isolado: contrato, exemplos e instruções](INVESTIGATION_CONTRACT.md).
Factos, hipóteses, requisitos observados e lacunas separados; sem confirmação causal ou ativação.

[C02 isolado: contrato de critérios, exemplos e instruções](DETECTION_CONTRACT.md).
Operação e perda de valor avaliadas separadamente, sem ativar o fluxo de produção.

[Entrada autorizada de evidências, contrato HTTP e instruções](EVIDENCE_API.md).
Eventos, métricas e evidências por SaaS/cliente/configuração; sem ativar C01–C06 operacionais.

[Contrato interno de integração, três exemplos e instruções](INTEGRATION_CONTRACT.md).
Configurações versionadas por SaaS; nenhuma ligação nova a C01–C06 ou execução de negócio.

[Modos isolados, contas privadas e instruções da fundação permanente](PERMANENT_FOUNDATION.md).
Production mantém autenticação privada sem lease de 24 h; operações reais continuam bloqueadas.

[Infraestrutura proposta, custos e operação](infra/ARCHITECTURE.md).
Sem contratação, publicação ou migração de dados.

[Contrato HTTP e integração futura](API_CONTRACT.md) · [OpenAPI 3.1](contracts/openapi.json).
A lógica e a interface existentes da Missão 02 continuam preservadas.

[Pré-visualização privada: preparação, testes e impedimento de alojamento](PRIVATE_PREVIEW.md).
O laboratório abaixo continua apenas em loopback; não usar as suas contas na Internet.

Python 3.11+ (testado com 3.12), SQLite e navegador. Runtime sem pacotes externos.
Na demo, a decisão continua **simulator-v1, sem IA real**; todos os dados e efeitos são do sandbox. Production bloqueia operações de negócio.

## Abrir com 150 clientes sintéticos

A partir da branch `centerway-v2/missao-10-ai-proposals`, usar um caminho de base novo:

```sh
cd v2
python3 -m centerway.synthetic --db data/missao02-150.sqlite3
python3 -m centerway.server --db data/missao02-150.sqlite3
```

Abrir **http://127.0.0.1:8080**. Num servidor remoto, encaminhar a porta 8080 para o
computador local, por exemplo `ssh -L 8080:127.0.0.1:8080 utilizador@maquina`.
Não foi criado um URL público. O gerador recusa bases que já tenham clientes;
para repetir, escolher outro ficheiro, sem apagar o histórico anterior.

Todas as contas usam a palavra-passe pública de teste **centerway-local**:

| Conta | Permissão |
| --- | --- |
| `demo` | Operador de AtlasFlow e NimbusDesk |
| `atlas` | Operador só de AtlasFlow |
| `leitor` | Só leitura de NimbusDesk |

## Experimentar no navegador

- O registo central mostra apenas as SaaS autorizadas. Filtrar por SaaS e estado,
  pesquisar nome/ID e usar a paginação de 20 clientes. Abrir um cliente para operar.
- `client-007` está pronto para C05 em ambas as SaaS. Atlas entrega 12 trabalhos;
  C06 confirma operação e valor **no sandbox**. Nimbus ativa o percurso: C06 confirma
  operação, mas não valor. «Simular uso posterior» grava quatro relatórios; nova
  verificação pode então confirmar valor simulado.
- «Registar cliente no sandbox» cria um cliente sem inventar observações. O ID é
  único dentro de cada SaaS; o mesmo ID pode existir noutra SaaS.
- Introduzir linhas `AAAA-MM-DD,valor,fonte` no cliente. O botão de exemplo preenche
  14 dias de dados explicitamente simulados, mas só «Validar e gravar lote» os grava.
- Avançar pelos botões C01–C06. Dados insuficientes e causas sem ação ficam em exceções.
  Depois de um ciclo terminal, «Iniciar novo ciclo» preserva o anterior. O seletor de
  ciclos permite consultá-lo; não permite executar novas operações no ciclo histórico.
- Recarregar/reiniciar preserva clientes, observações, casos, efeitos e histórico.

## Estados e ensaio reproduzível

O gerador usa o mesmo Core validado dos endpoints HTTP, com 75 clientes por SaaS e
IDs `client-001` a `client-075`. Não escreve resultados de casos diretamente no SQL.

| Grupo do registo | Clientes no ensaio inicial |
| --- | ---: |
| Deterioração (C02) | 16 |
| Investigação (C03) | 14 |
| Intervenção (C04/C05 ou operação recuperada sem valor) | 35 |
| Recuperação de operação e valor no sandbox | 23 |
| Exceções (dados insuficientes ou causa sem ação) | 32 |
| A observar | 14 |
| Estáveis, sem deterioração | 16 |

Total: **150 clientes e 44 intervenções persistidas**. O grupo é calculado pelo
servidor a partir do ciclo mais recente. Estável não significa recuperação. Uma
verificação só operacional continua em intervenção, à espera de evidência de valor.

## Contratos e proteções

- Todas as operações de ciclo exigem `tenant` e `customer` explícitos. Um `case_id`
  tem de corresponder aos dois. Não existe escolha implícita de `customer-01`.
- C01 lê 14 dias completos da mesma fonte; C02 compara sete dias anteriores com sete
  recentes, exige baseline positivo e queda ≥ 30%; C03 preserva evidências/revisão;
  C04 só escolhe do catálogo autorizado; C05 aplica efeitos atómicos e únicos por caso;
  C06 distingue operação de valor (mínimo quatro novos resultados persistidos).
- Observações: 1–366 linhas, até 64 KiB por pedido; datas ISO canónicas até hoje e
  no máximo 365 dias atrás; valor inteiro 0–1000000; fonte simples de 1–64 caracteres;
  sem campos extra, dias duplicados no lote ou sobrescrita de dias existentes.
  O lote inteiro confirma ou reverte. Reenvios idênticos, mesmo reordenados, não
  duplicam dados. Conflitos de valor/fonte devolvem 409.
- Novos dados invalidam ciclos ainda entre C01 e C04 (`stale_evidence`); exige-se
  outro ciclo. Observações e snapshots anteriores não são alterados.
- Um índice único permite apenas um ciclo não terminal por cliente. Ciclos e
  intervenções de outros clientes permanecem independentes. Novos ciclos não
  reinicializam o ambiente nem as observações do cliente.
- Sessões HttpOnly/SameSite, memberships no servidor, catálogo, bloqueio de revisão
  desatualizada, rollback e histórico append-only da Missão 01 são mantidos.
  Lotes e registos de criação/entrada são também auditados e append-only.
- As bases da Missão 01 são migradas automaticamente ao abrir: substitui-se o índice
  de caso único pelo de ciclo ativo; preservam-se IDs, observações, efeitos e histórico.
  O formato HTTP mudou: agora `customer` é obrigatório nas mutações.

## Testes

```sh
python3 -m pip install -r tests/requirements.txt
python3 -m unittest discover -s tests -v
npm ci --ignore-scripts
npx playwright install chromium
npm run test:browser
# Com Chromium do sistema:
CHROMIUM_PATH=/usr/bin/chromium npm run test:browser
```

A suíte inclui os 16 testes da Missão 01 e cobre entrada atómica/idempotente,
permissões HTTP, isolamento entre clientes/tenants, ciclos concorrentes, invalidação
de snapshots, consulta de ciclos históricos, migração e o cenário de 150 clientes.
O navegador usa base descartável e cobre registo, filtros, paginação, criação,
observações inválidas/válidas/repetidas, os dois percursos, persistência após reload,
resposta atrasada entre clientes e larguras 360/390/1280. Não usa credenciais externas.

## Limites do laboratório sandbox

- Duas SaaS com catálogo e ambientes de teste fixos; a administração privada de contas
  production é apenas por CLI; não há novos conectores, agendamento nem IA real.
- Não existe correção de observações já gravadas nem suporte a múltiplas fontes no
  mesmo dia. Datas/fonte incompatíveis bloqueiam a análise em vez de serem aproximadas.
- Novos ciclos reutilizam o estado atual. Não existe simulação de uma nova avaria
  no mesmo ambiente; sem causa autorizada, o caso exige revisão humana.
- A meta de valor e o uso posterior são sintéticos. Não demonstram retenção,
  recuperação financeira ou recuperação real em produção.
- Validado com 150 clientes, não como teste de carga de produção. A lista é paginada
  no navegador; a API devolve o resumo autorizado completo e o histórico do cliente
  é lido integralmente. SQLite serializa escritas. Sem processamento em background.
- HTTP local, contas públicas, sem TLS/rate limiting; não preparado para produção.
  Isolamento é aplicado no backend, não por RLS. Quem acede diretamente ao ficheiro
  SQLite tem acesso administrativo. A aplicação histórica não foi executada.

### Missão 15 — entrada SaaS assinada

Entrada HTTPS server-to-server opt-in, HMAC sobre o corpo original, anti-replay,
rotação privada e mapeamento declarativo para o M07 existente. Só persiste
**declarações inativas da origem**. Sem contas de máquina com permissões humanas,
conectores de fornecedor, execução ou publicação.
[Contrato, configuração e exemplo executável](WEBHOOK_CONTRACT.md).

### Missão 16 — preparação do piloto privado

API 1.6.0 para configurar contexto/clientes/critérios e acompanhar evidências,
C02, C03 e C04 históricos. Piloto por SaaS, autorização administrativa local,
sessão privada e CSRF; processamento apenas de análise e revisão humana.
C05/intervenções e alegações de recuperação real bloqueados. Sem IA configurada
**e** consentida, não há inferência nem simulação.
[Contrato de integração, percurso reproduzível e prontidão](PILOT_INTEGRATION.md).

### Missão 17 — execução integral observável, sem interface

Comando `python -m centerway.journey`: laboratório local privado e sintético que
reutiliza M06–M14, mostra fronteiras humanas/automáticas, aprova hash C05 concreto,
persiste efeito num serviço SQLite de teste e recolhe amostras posteriores para C06.
Sem IA configurada há bloqueio; fixture C04 é entrada de teste explícita, nunca
inferência. Não altera o piloto/production. [Instruções exatas e limites](OBSERVABLE_EXECUTION.md).
