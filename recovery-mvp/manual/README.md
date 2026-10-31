# T02 — operação manual F01–F06 (issue #71)

Base: PR #70, `recovery-mvp/t01-adversarial-fixture`, `ec407d441df43b691c799f738ab579b9b3b35caa`.
Preparação de código e validação isolada; **não é publicação nem execução do T01**.
Não acede ao Neon/Render públicos, não cria contas públicas, não usa ferramentas ou
créditos Lovable, não altera main. Motores, migrações e fixture T01 preservados.

## Contratos efetivamente utilizados

Inspecionados API `app.py`/OpenAPI, F01 CONTRACT.md/SQL001–002, F02 SQL003,
F03/descoberta SQL004–005, F04 SQL006, F05 SQL007, F06 SQL008/ORCHESTRATION.md,
HttpTransport/SessionController/LiveRuntime e as rotas M68 reais. Nenhuma lógica de
avaliação/autoridade foi copiada para o browser. As dez operações F06 existentes
cobrem todas as escritas necessárias; a extensão é **somente uma consulta**.

| Ação do formulário | Operação real | Limite/condição |
|---|---|---|
| Registar fonte, contrato, observação/correção | append_value | fonte/contract/evidence; expected_revision explícita, validação F01 |
| Detetar deterioração | detect | contrato, revisões selecionadas, corte com fuso e política de 2–120 períodos |
| Abrir investigação | open_investigation | deteção persistida e período dessa deteção |
| Registar fator, evidência ou revisão | append_investigation | hipóteses/requisitos/proposições explícitas; revisões por outra identidade, quando sustentáveis |
| Descobrir fatores | discover_company | escopo de empresa; pode abranger vários clientes; não concede verificação |
| Avaliar investigação | investigate | registos persistidos, corte explícito; lacunas/contradições preservadas |
| Pedir intervenção | intervene | relatório exato, somente ação sintética existente; servidor revalida tudo |
| Reverter execução | undo | execução original, principal correto, regras F04 |
| Definir janelas de recuperação | plan_recovery | decisão existente, versões/janelas explícitas e compatíveis |
| Avaliar/reavaliar recuperação | evaluate_recovery | plano existente, corte explícito; sucesso de execução separado de recuperação |

F01 não ganha editor de assessment/conclusões declaradas: a avaliação automática
é pedida à F02. Não existe onboarding, concessão de políticas ou alteração de
regras/inputs F03.1 pela UI. Novos fatores/evidências podem ser registados diretamente
pela F03; as entradas T01 de descoberta já vêm preparadas pelo operador.

Consulta aditiva `GET /v1/tenants/{tenant}/clients/{client}/manual-context`, contrato
`t02-v1`, no mesmo backend. Autenticação, principal PostgreSQL individual, escopo HTTP
e RLS atuais. Snapshot read-only/repeatable-read de fatores/evidências/revisões F03,
catálogo da empresa, recursos do cliente, políticas/revogações do próprio principal
e auditoria do cliente (eventos de políticas alheias também filtrados). Máximo 100
linhas por coleção, truncation explícita. Sem query params, novos grants, migrações,
conclusões ou efeitos de leitura. api/openapi-t02.json e api/README.md documentam formato/erros; api/openapi.json
c02-v1 e os hashes da captura original de71 casos permanecem imutáveis.
Os guards CI aceitam apenas os hashes exatos revistos de app.py/OpenAPI desta extensão.

## Controlos e segurança

No detalhe de um cliente, botão **Operar jornada F01–F06**. Reutiliza diálogo,
cores, shell, navegação e componentes existentes. Formulários por ação, seleção de
IDs/versões disponíveis, cópia explícita de registo para nova revisão, campos sem
metas/resultados/verificações preenchidos automaticamente. O UUID novo é identidade
do registo/pedido; não é evidência. Instante atual só é preenchido por clique.

O produtor escolhe qualidade/type/afirmações. `verified` não é prova independente.
Campos numéricos em falta não viram zeros; false e null permanecem distintos. A
qualidade e ausência de evidência aparecem na seleção de períodos. Janelas futuras
no corte são recusadas no preview; qualidade parcial continua selecionável para que
o motor devolva inconclusivo, não seja ocultada pela UI. A validação do servidor
continua definitiva, incluindo compatibilidade semântica, versões e concorrência.

Pré-visualizar faz GET/draft, **não POST**. O pedido e o âmbito são congelados em
memória; confirmação explícita separada é obrigatória. Um recibo completed não
significa execução/valor/recuperação. Blocked, failed, inconclusivo e recibos de erro
são apresentados sem substituição por sucesso. Novo pedido só por ação explícita.
Resposta incerta conserva draft/UUID/conteúdo para reenvio humano; zero retry
automático. Fechar/reabrir o diálogo conserva esse draft. Refresh/re-login perde
memória: consultar recibos existentes antes de criar qualquer pedido substituto.

Tokens/passwords/drafts não são persistidos em storage, URL, SSR, logs ou artefactos
CI. Scope/identidade, logout, expiry e respostas tardias passam pelo controlador
existente. A consulta manual não reintroduz cache após logout/troca de âmbito.
Apenas uma origem HTTPS local DEV pode ser selecionada pelo harness, nunca por
input/query/storage do browser ou em build de produção. A API pública M68 por
omissão permanece inalterada; a missão não a contacta.

Hash de ficheiro opcional: SHA-256 calculado localmente (máximo 1 MiB); **não envia o
ficheiro** nem cria armazenamento de anexos. Referência/localizador e digest não
provam conteúdo externo ou revisão humana. A API não lê CSV/documentos por URL.

## Ensaio local reproduzível

Python 3.12, Node24, Bun1.4.4, Docker/PostgreSQL17 e bibliotecas de Chromium. Da raiz:

```sh
(cd recovery-mvp/lovable-ui && bun install --frozen-lockfile)
bash recovery-mvp/manual/api-test.sh
bash recovery-mvp/manual/test.sh
```

Não executar suites que param/arrancam contentores Docker simultaneamente com o
Chromium local: mudanças veth de outras suites podem gerar ERR_NETWORK_CHANGED,
mesmo em loopback. CI usa máquinas/jobs separados. Não há retry automático de POST
para esconder essas falhas; uma resposta de escrita perdida é testada deliberadamente.

O teste API usa apenas PostgreSQL17 descartável com TLS/roles reais e o seed inicial
T01 para provar permissões de t01_reader/reviewer/operator, **sem operar a jornada**.
O teste browser usa outro ambiente descartável, cliente sintético A e dados T02
explícitos, nunca AtlasOps/Meridian. Todas as escritas desse percurso são clicks nos
formulários da aplicação verdadeira; não uma página de substituição, Scenario.run,
console ou transport.operate chamado por JS de teste.

A UI Vite é servida por uma borda HTTPS de teste que só encaminha bytes; API C01,
Gunicorn TLS e PostgreSQL TLS reais. CA/hostname verificados; Chromium confia apenas
no SPKI da folha gerada, sem bypass geral de TLS/CORS. Fontes cosméticas Google já
existentes são bloqueadas no teste; pedidos fora das origens locais falham o ensaio.
Sem chamadas ao Render/Neon/Lovable públicos, HAR, traces, screenshots de credenciais
ou storage-state. Dados/volumes temporários são removidos no fim.

Se Chromium estiver instalado pelo sistema, pode definir apenas para o ensaio:

```sh
CENTERWAY_CHROMIUM_EXECUTABLE=/usr/lib/chromium/chromium \
CENTERWAY_TEST_BUN=/caminho/local/bun bash recovery-mvp/manual/test.sh
```

Sem essa variável, CI instala Chromium do Playwright1.62.0. A política deste ambiente
bloqueia cdn.playwright.dev; a execução local usa Chromium Debian154 já instalado,
não um caminho alternativo ao destino bloqueado. CI valida também a distribuição
pinned do Playwright. Mobile: 390×844 com emulação mobile/touch; não aparelho físico
nem Safari. A saída identifica a versão efetivamente usada.

## Como operar T01 pela interface depois da ativação autorizada

**Pré-requisitos fora do teste humano:** aplicar a fixture e acrescentar as contas
com o bundle seguro T01, conforme `../adversarial-t01/README.md`; instalar a release
API T02 e publicar a UI T02 pelo canal real autorizado. Nenhuma dessas ações foi
realizada nesta missão. Não é necessário novo schema/role/conta além do T01 já previsto.

1. Na UI publicada futuramente, iniciar sessão com `t01_operator`, password privada.
   URL M68 registada: https://value-recovery-radar.lovable.app/app. A versão atual
   **ainda não contém estes controlos**. Selecionar empresa `110577e9...`, Clientes →
   Meridian Distribuição → **Operar jornada F01–F06**.
2. Consultar **Contrato, revisões, fontes e evidências F01 (API)**: r1 global,
   r2–r9 semanas, S7 partial. O log 14/10 pertence a S7/r8, nunca deslocá-lo para S6.
   Usar F01 para acrescentar observação/correção apenas com dados explícitos legítimos;
   selecionar contrato/versão para copiar método/fonte/janela. Motivo e revisão
   esperada são obrigatórios. Não alterar baseline 40h/mínimo24h para obter deterioração.
3. Selecionar **F02 — Detetar deterioração**, contrato T01, revisões **2–9** (não r1),
   política explícita (por exemplo 2 períodos), usar corte UTC atual. Rever preview,
   confirmar e ler o recibo real. A interface mostra falta/qualidade, não prediz nem
   força a conclusão. Para avançar, **Novo pedido após consultar recibo** faz GET.
4. **F03 — Abrir investigação**: selecionar a deteção recebida, r7/S6 ou r8/S7 conforme
   a pergunta e o período efetivamente investigado. Introduzir pergunta. Depois,
   **Registar fator, evidência ou revisão**: selecionar investigação, tipo factor,
   hipótese/requisito/condição/protocolo/âmbito/controlo explícitos e instante dentro
   da janela; registar evidências com fonte/versão, proposição, afirmação, referência
   e hash. Não declarar impacto ticket-a-ticket que não existe.
5. Alternativamente pedir **F03.1 — Descobrir fatores da empresa**, se a sessão tiver
   esse escopo, ciente de que é uma operação da empresa. Só usa inputs/regras já
   persistidos. Pode não encaminhar o input interno de S7 parcial; não remover essa
   incerteza. Depois consultar as investigações efetivamente criadas.
6. Pedir **F03 — Avaliar investigação** com corte atual; consultar separadamente
   registos do operador e factos/hipóteses/contradições/lacunas calculados pela F03.
   Se houver revisão humana legítima, terminar sessão e entrar como `t01_reviewer`;
   selecionar investigação/tipo verification e evidência/versão. Se não for verificável,
   usar unverifiable e checked_assertion null, explicando a lacuna. Não confirmar por
   conveniência. A base recusa self-verification; outro login não comprova independência.
7. Voltar ao operador e avaliar a investigação de novo. **F04 — Pedir intervenção
   sintética** seleciona investigação e relatório persistido. Consultar políticas do
   principal, confirmar o pedido e ler o bloqueio/execução real. T01 tem **zero
   políticas**: não se espera execução autorizada. O formulário não permite criar
   autorizações nem enviar notificações/reconfigurar integrações externas.
8. **F05 — Definir janelas de recuperação**: selecionar decisão real, versões anterior
   e posterior comparáveis. Se faltarem, F01 contract → **Copiar registo para nova
   revisão**, conservar definição de medição e mudar explicitamente janelas/motivo.
   As janelas devem ter igual duração e ficar antes/depois do instante guardado da
   decisão/execução. A decisão aparece com esse timestamp no seletor; o servidor
   verifica as versões. Não é uma renovação comercial nem uma alteração das metas.
9. Escolher plano e **F05 — Avaliar recuperação observada**. Mesmo uma decisão bloqueada
   pode ter plano segundo o contrato F05 existente; a conclusão será qualificada pelo
   motor como execução ausente/inconclusiva, não recuperação. Uma intervenção executada
   também não basta sem resultados suficientes. Reavaliar somente após novos dados.
10. Consultar **Estados, próximas etapas e recibos F06**, auditoria e páginas existentes.
    Fechar o diálogo atualiza a projeção por GET; não há fallback mock. Terminar sessão,
    experimentar `t01_reader` (consultas apenas) e confirmar que A/B não veem T01.

Tudo que é operação de jornada F01–F06 acima tem controlo UI; não requer console ou
cliente HTTP externo. Continuam administrativos os pré-requisitos: tenant/contas,
políticas de autorização e configuração de descoberta. Estes não são permissões que
um utilizador deva conceder a si próprio.

**S9 não é pré-carregada nem existe botão automático de “sucesso”.** O ficheiro futuro
T01 só deve ser revelado na fase humana prevista. Registar fonte/observação pela F01
requer compatibilidade real de critérios/método/fonte/janela. S9 usa amostra/critério
contraditórios e pode anteceder a decisão: não copiar23h para um outcome compatível
falso. A API rejeita incompatibilidades estruturais; não interpreta semanticamente
texto de CSV. Se faltar suporte, conservar investigação/recuperação inconclusivas.

## Bloqueios, handoff e publicação posterior

- Não há anexos/document-reader, importador CSV, cálculo de medianas, dedução de causas,
  concessão de políticas, criação de utilizadores/tenants ou editor administrativo
  F03.1. Contexto tem limite100 por coleção, com aviso; não é histórico completo.
- T01 sem políticas/reviews/dados posteriores suficientes não deverá “recuperar” só
  porque existe este formulário. Bloqueios são resultados válidos do ensaio.
- Históricos são append-only. Corrigir significa nova revisão/UUID/pedido explícito,
  conforme o contrato; não existe apagar/reset do caso na UI.
- Testes aprovados locais/CI não são aceitação hosted ou prontidão para produção.
  Publicação, operação humana T01 e conectividade da UI T02 pública estão pendentes.

Após autorização separada: (1) aprovar/rever este PR empilhado; (2) atualizar somente
código API no Render existente, preservando segredos/origens e verificando novo GET,
sem reaplicar migrações; (3) aplicar/ativar T01 por operador autorizado sem alterar A/B;
(4) transferir o snapshot UI revisto para o projeto frontend correto e publicar pelo
canal efetivamente suportado; (5) testar login/CORS/isolamento/mobile externamente.

O commit Lovable M68 registado é e4248eefe24fc9a76d9738bc3d1625df613ed45d; o snapshot
está em recovery-mvp/lovable-ui, **não na raiz frontend antiga**. O PR neste repositório
não prova sincronização com a branch/repositório do projeto Lovable. A ligação GitHub
real e a ação de publicação têm de ser confirmadas pelo operador antes de promover o
snapshot; não foi utilizado Lovable para alterar/verificar essa ligação nesta missão.
Não presumir que merge neste repo ou build Vite publica a UI. Se a promoção exigir
créditos/ações Lovable, pedir autorização específica; não consumir automaticamente.

## Evidência local desta entrega

- Regressões originais: 60 motores +11 HTTP +8 HTTPS +4 persistência +7 captura de71
  casos +7 preflight =97 aprovadas. O contrato c02-v1 e a captura não foram regenerados.
- Managed11 e T01 inicial11 aprovados, sem alterações nos respetivos testes/fixtures.
- T02 API:6 testes reais PG17/TLS, incluindo principals T01, limites, políticas e
  revogações/auditoria filtradas, negação de escrita e ausência de operação no T01.
- Frontend:210 aprovados (189 anteriores +21 novos),1 público opt-in omitido; TypeScript
  e build aprovados. O teste público não foi ativado nem substituído por mock.
- Chromium154 local:5 testes na aplicação real; fluxo F01–F06 com bloqueio e recuperação
  inconclusiva; depois política administrativa sintética restrita **só no caso T02
  descartável** para provar pedido autorizado e reversão por botões. Perda deliberada
  de resposta após commit produz um único recibo/efeito após reenvio idêntico. Inclui
  hash local de documento, mobile/touch390×844, leitura, escrita, refresh/re-login,
  reader/reviewer, expiração e ausência de storage/cookies de credenciais.

Resultados GitHub Actions e SHA final ficam no PR de entrega. Nenhum resultado local
ou CI comprova o cenário T01 publicado ou operação humana realizada.

Recibos de erro da auditoria T02 são sanitizados como na journey: mensagens SQL
ficam apenas no histórico imutável da base. Testado com rejeição F06 real, sem
executar motores no T01.
