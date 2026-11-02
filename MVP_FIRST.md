# MVP FIRST — auditoria funcional e caminho mínimo

Prioridade atual: validar o produto num ambiente isolado sintético; infraestrutura
Gate1/SSH/backup/publicação suspensa para este ensaio. Produção/main intocadas.

## Estado confirmado nesta missão

| Componente | Evidência efetivamente executada | Limite |
|---|---|---|
| F01–F06 + API L01 + diretório C02 | Quatro testes C03 com PostgreSQL17, HTTPS, logins individuais e persistência reais | Entradas/reviews/negócio são sintéticos, não clientes reais |
| UI T02 integrada | Cinco testes na aplicação verdadeira, Chromium154.0.8037.57, API/PG/TLS reais | Local; mobile390×844 emulado, não dispositivo físico/publicação |
| Ciclo positivo pela UI | Novo prolongamento do teste existente: investigação, bloqueio, autorização administrativa limitada, execução, medições8→15 e recuperação completa | Janelas comprimidas em segundos; não piloto em calendário real |
| Falhas/segurança indispensáveis | Sem dados→inconclusivo; sem política→blocked; perda de resposta→mesmo recibo/efeito; isolamento, sessão/logout/expiry | Não é ensaio de escala/SLA |
| Persistência | Teste C03 reinicia PG/API/gateway, compara jornada e reenvia sem duplicar execução | Persistência local, não backup externo |

Critério sintético executado: baseline10, mínimo15, alvo20, deterioração9→8
(API) ou8 (UI), pós15. Recuperação completa significa atingir o mínimo contratado;
não significa alcançar todo o alvo20 nem comprovar causalidade. `verified` é qualidade
declarada, não validação independente. Revisões de evidência são registos de fixture
por outra identidade; nunca apresentadas como investigação humana real.

Código inspecionado: SQL001–008/CONTRACT/ORCHESTRATION, API FIELDS/rotas/OpenAPI,
Scenario/PersistentDemo, HttpTransport/LiveRuntime, ManualJourney e testes C03/T02.
LiveRuntime das páginas usa HTTP real, sem fallback mock. Os testes unitários
Vitest/adapters e exemplos offline são provas de contrato/renderização simuladas;
não são contados aqui como prova PostgreSQL/browser. Não foi necessário repeti-los.

## Integrações que não são requisitos do primeiro ensaio

Não há execução de intervenção em sistemas externos: F04 só altera flag sintética
reversível. Não existe inferência automática de causas/IA nem ingestão automática de
CSV/documentos; entram valores, referências, hashes e proposições estruturadas.
Políticas de autorização/catálogo/contas continuam administrativas, não são
concedidas pelo próprio utilizador na UI. Isso exige setup local, não nova função.
Publicação da versão frontend/backend não foi verificada nem alterada nesta missão.
Não confundir snapshot no Git com frontend publicado. Nenhuma ação no T01/AtlasOps.

## Caminho mínimo já disponível

1. Inicializar stack C03 descartável com dois tenants/logins reais e preparar,
   administrativamente, catálogo/flag/política de uma tentativa e risco limitado.
2. Fonte + promessa/objetivo + indicador/unidade/método + baseline/mínimo/janelas.
3. Registar medições e evidências sintéticas explícitas; pedir detecção F02.
4. Abrir F03, registar hipótese/requisito/evidências; sem suporte fica inconclusivo.
   Revisão só com outra identidade, identificada como fixture sintética no ensaio.
5. Ler impedimento/justificação, solicitar ação do catálogo. Sem política, bloquear;
   com autorização prévia explícita, executar só a flag sintética e auditar.
6. Registar janela posterior e nova medição; avaliar F05, consultar recibos/jornada
   F06 e reverter a flag para demonstrar reversibilidade. Não declarar causalidade.

Para teste de negócio seguinte, definir um único caso fictício concreto (por exemplo,
SaaS de processos, objetivo reduzir tempo de conclusão, unidade horas, critério e
fonte explícitos), com medições preparadas e contraditórias quando aplicável. Não
converter utilização/logins em valor. Datas e valores continuam claramente sintéticos;
unidades/janelas reais de observação exigirão execução longitudinal própria.

## Repetir imediatamente, sem cloud/Gate1

Da raiz, requisitos já usados nesta execução: Python3.12, Docker, OpenSSL, Node24,
Bun1.4.4, Chromium e dependências. Usar lockfile existente:

```sh
(cd recovery-mvp/lovable-ui && bun install --frozen-lockfile)
bash recovery-mvp/cloud-demo/test.sh --persistent-only
CENTERWAY_CHROMIUM_EXECUTABLE=/usr/bin/chromium bash recovery-mvp/manual/test.sh
```

Executar suites sequencialmente para evitar mudanças de rede Docker durante Chromium.
O segundo script faz todas as escritas de jornada pelos botões/formulários; a única
escrita SQL administrativa é a autorização/catalogação sintética já prevista. Cleanup
remove ambientes e volumes de teste; nenhum resultado é inserido no Neon público.

Bloqueios críticos funcionais para esse teste: **nenhum encontrado**. Há apenas
pré-requisitos locais e dados/autoridade explícitos. Próxima ação de produto: ensaio
humano do mesmo percurso e validação da clareza das conclusões com um caso fictício
concreto. Antes de publicação/dados reais, retomar requisitos operacionais adequados;
não expandir infraestrutura para demonstrar o ciclo local.

Mudança desta missão:23 linhas de teste estendem o caso Chromium existente até
recuperação positiva pela UI, preservando todos os casos anteriores. Nenhuma
funcionalidade, motor, schema, credencial existente ou serviço alterado.
Validação local:4 C03 +5 Chromium aprovados; resultados CI no PR para o SHA final.
