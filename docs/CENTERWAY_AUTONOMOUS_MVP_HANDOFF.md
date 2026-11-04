# CENTERWAY — Handoff completo para Claude Code
**Data:** 2026-11-04 · **Estado:** preparação de engenharia; NÃO é autorização para alterar produção · **Idioma de trabalho:** português

## 0. Resumo executivo
CENTERWAY é um serviço B2B que trabalha autonomamente para uma empresa SaaS, com o intuito de ajudar os seus próprios clientes a obter os resultados que esperam do produto. Não é CRM, não é dashboard de operações manuais, não é plataforma de envio de recomendações genéricas.

Promessa operacional **a validar, não ainda comprovada**:
1) SaaS conecta/autoriza o acesso às fontes uma única vez;
2) motor obtém eventos e indicadores por cliente SEM inserção individual pelo founder;
3) avalia realização de valor (não apenas uso) e deterioração;
4) investiga causas possíveis com evidências;
5) executa uma intervenção concreta, segura e previamente autorizada, apenas quando aplicável;
6) verifica o que mudou após a janela adequada;
7) envia resultados por API de leitura para um dashboard simples.

**Separação firme:** o motor opera fora da interface; o dashboard apenas lê e apresenta. A aplicação deve continuar a trabalhar com o founder desligado, sujeito às limitações reais de infraestrutura e agendamento.

## 1. Preferências inequívocas do founder
- Simplicidade radical, rapidez, baixo consumo de ferramentas/créditos; fazer o mínimo QUE FUNCIONA.
- Não pedir ao founder para preencher dados, lançar operações ou autorizar caso a caso quando já existem permissões suficientes. As aprovações sensíveis continuam obrigatórias.
- Backend ANTES de frontend. Evitar reconstruir o que está provado e útil, mas remover legado desnecessário **apenas após inventário e backup**.
- Uma única stack já disponível, se tecnicamente viável: Python no Render, PostgreSQL no Neon, Lovable para o futuro dashboard. Evitar microsserviços, Kafka, filas externas, Kubernetes, 6 agentes separados, complexidade prematura.
- Fundador no Android, sem exigir PC. Trabalho técnico por agentes/PRs.
- Não contratar serviços pagos, fazer upgrades, gastar créditos Lovable ou expor informações reais/segredos sem autorização.
- Mensagens ao founder CURTAS; especificações técnicas podem ser extensas em ficheiros e PRs.

## 2. Arquitetura-alvo do MVP
```text
SaaS (API/eventos autorizados)
         |
         v
C01 — CONEXÃO / RECOLHA AUTOMÁTICA
         |
         v
C02 — ANÁLISE DE VALOR / DETERIORAÇÃO
         |
         +-- Valor demonstrado -> monitorização contínua
         +-- Dados insuficientes -> aguardar/recolher, SEM ação
         v
C03 — INVESTIGAÇÃO COM EVIDÊNCIAS
         |
         +-- Inconclusivo -> aguardar dados, SEM ação
         v
C04 — INTERVENÇÃO SEGURA E AUTORIZADA
         |
         v
C05 — VERIFICAÇÃO NA JANELA CORRETA
         |
         v
C06 — API DE RESULTADOS (READ-ONLY)
         |
         v
Dashboard (apenas leitura)
```
C01 a C06 são módulos no **mesmo processo/projeto backend**, não seis servidores nem seis etapas que exigem clique.

### C01 — Conexão / recolha
**Recebe:** autorização e configuração inicial da SaaS; fonte de eventos de produto + ID estável de clientes; acesso autorizado de leitura.
**Faz:** leitura incremental/agendada, deduplicação, mapeamento tenant→cliente→evento, persistência com proveniência/tempo de observação.
**Entrega:** clientes e eventos validados para C02, estados de sincronização e erro sem fuga de dados.
**Condições de pronto:** onboarding uma vez por SaaS; mínimo 20 contas sintéticas importadas automaticamente; reimportar não duplica; falha de API não apaga dados; isolamento entre SaaS; credenciais nunca expostas; recuperação após pausa. Integração real ainda exige uma SaaS piloto e credenciais próprias — NÃO fingir acesso.

### C02 — Análise de valor
**Recebe:** eventos C01 + contrato de valor configurado **uma vez por SaaS/segmento**.
**Faz:** mede UM resultado observável do cliente com limiar e período de avaliação definidos; distingue mudança real de ruído/ausência de dados; regras determinísticas, compreensíveis.
**Entrega:** por cliente `valor_observado`, `em_risco`, `abaixo_da_meta`, `dados_insuficientes`, mais medidas e referências a eventos. Estados finais e nomes podem ajustar-se no contrato técnico.
**Condições de pronto:** testes com valor alto, baixo, deterioração, dados em falta, sazonalidade, alto uso/baixo valor, fronteiras de janela; não inventa metas nem confunde login com resultado de negócio. O contrato de valor (evento, meta, janela) ainda requer decisão com SaaS piloto.

### C03 — Investigação
**Recebe:** casos sinalizados por C02 e evidências existentes.
**Faz:** procura impedimentos verificáveis, separa factos/hipóteses/contradições; opcionalmente usa IA para interpretar texto, **sem autoridade para inventar dados**.
**Entrega:** hipótese sustentada + evidências citadas + confiança/limitações, ou `inconclusivo`.
**Condições de pronto:** não atribui causa sem prova; quando inconclusivo não aciona C04; qualquer texto gerado é rastreável; IA não é obrigatória para concluir o primeiro fluxo sintético se regras bastarem.

### C04 — Intervenção
**Recebe:** caso elegível de C03 + ação permitida pela SaaS.
**Faz:** executa APENAS UMA intervenção do MVP, com permissão específica, verificação de escopo, dry-run ligado por padrão até ativação aprovada, chave idempotente, limite por cliente, kill switch global e recibo.
**Entrega:** registo da intenção, execução/erro e identificador/recibo verificado, sem confundir ação com sucesso.
**Condições de pronto:** testes de ação autorizada, proibida, duplicada, revogada, concorrente, falha de rede, timeout e reinício; sem efeitos laterais em dados reais no teste; nenhuma intervenção real até confirmação da API/consentimento da SaaS. Não presumir que pequenas SaaS expõem API de correção. Alternativa segura para piloto: envio de orientação aprovada, se de facto autorizada/possível.

### C05 — Verificação
**Recebe:** ação de C04, baseline, contrato de valor, prazo `avaliar_depois_de` e novas medições C01.
**Faz:** verifica no período correto, compara antes/depois e regista exceções/ausência de dados; sem avaliação instantânea artificial para casos reais.
**Entrega:** `melhoria_observada`, `sem_melhoria`, `inconclusivo` e evidências/versionamento.
**Condições de pronto:** janelas respeitadas, sem inventar medições, reavaliações idempotentes, não declarar causalidade só porque uma métrica subiu após ação.

### C06 — Resultados / API de leitura
**Recebe:** estados persistidos C01–C05.
**Faz:** projeta dados simples e consistentes por SaaS para dashboard, com autorização e isolamento de tenants.
**Entrega:** total de clientes acompanhados; a obter valor/em risco/abaixo da meta/sem dados; investigações, ações, melhoras observadas; antes/depois e evidências por caso; quando disponível, MRR das contas que voltaram ao limiar, explicitamente **não receita causada/comprovadamente recuperada**.
**Condições de pronto:** somas coerentes e reconciliáveis com casos, escopos de leitura corretos, ausência de números fictícios no dashboard real, nenhuma operação de escrita requerida pelo founder.

## 3. MVP mínimo e prova de funcionamento
- Uma fonte/simulador de SaaS, 20 contas sintéticas, uma métrica de valor e uma única ação sintética autorizada.
- Demonstrar o ciclo **sem cliques por cliente**. Testar também casos difíceis: dados em falta, conta sazonal, muito uso sem valor, erro no conector, retry, intervenção duplicada e falta de autorização.
- Um ciclo completo sintético comprova CANALIZAÇÃO TÉCNICA, **não** a tese comercial nem recuperação real.
- Paralelamente encontrar 1 SaaS piloto, definir com ela um indicador de valor genuíno e um canal de intervenção real, limitado. Critério para falar em utilidade real: evidência do que aconteceu em contas reais, incluindo limitações, sem causalidade automática.
- O dashboard só é construído depois de backend/contratos passarem no teste: interface minimalista (Visão Geral, Clientes, Ações, Resultados), só leitura.

## 4. Engenheira e infraestrutura — base já existente
- Repositório: `miltonbula764-wq/centerway-basecamp`, padrão GitHub. **A branch `main` pode não conter o MVP mais recente**. Base integrada de referência: `recovery-mvp/m68-live-frontend`, com commit histórico integrado `cab526826a3fafd4e71efac8e08c5a46c2598fb9` (verificar HEAD atual).
- Código legado a inspecionar: `recovery-mvp/` com F01 contrato/proveniência, F02 deteção, F03 investigação, F04 ações sintéticas autorizadas, F05 verificação, F06 orquestração/idempotência, `api/`, `managed/`, `manual/`, `lovable-ui/`. Procurar reuso comprovado, NÃO adotar por defeito toda a complexidade anterior.
- Implantação sintética anterior reportada: API `https://centerway-synthetic-m67.onrender.com`; frontend antigo `https://value-recovery-radar.lovable.app/app`. Estes serviços demonstraram a interface **manual** e backend sintético, não a autonomia alvo. NÃO alterar nem utilizar para testes de escrita sem instruções explícitas. Todos os IDs, passwords, API keys, DSNs e tokens são privados.
- Stack prevista: Python 3.12, PostgreSQL 17, GitHub Actions/testes; Render Free, Neon Free, Lovable. Disponibilidade/agendamento exatos da oferta gratuita DEVEM ser verificados antes de escolher mecanismo periódico. Render Free pode hibernar; não prometer execução contínua se não suportada.
- Nota importante: `PROJECT_STATE.md` e alguns README do legado refletem o estado no momento em que foram escritos e podem ter frases como 'não publicado' já superadas. Verificar GitHub e serviços antes de concluir estado vivo.
- Não existe prova atual de integração com SaaS cliente nem de intervenção externa com resultado de negócio. Nenhum cliente pagante comprovado.
- Versões antigas C01–C10 e F01–F06 têm significados diferentes dos NOVOS C01–C06. Não confundir.

## 5. Modelo de dados e segurança mínima
Começar por **seis entidades lógicas** se bastarem: `clients`, `events`, `value_contracts`, `cases`, `actions`, `results`. Credenciais de conexão/tenants/auditoria podem requerer estrutura adicional justificada, sem sacrificar isolamento ou segredo.
Imprescindíveis: isolamento por SaaS, RBAC/mínimo privilégio, origem dos eventos, idempotência de ingestão e ações, histórico, tentativas controladas, limitação de dados coletados, revogação de acesso e cancelamento de ações futuras. Nunca armazenar credenciais expostas no browser ou em GitHub.

## 6. Quem faz o quê — operação em equipa
- **Founder** decide direção de negócio, ação permitida do piloto, exposição de risco e alterações que necessitem de aprovação.
- **ChatGPT** mantém visão global, especificação dos contratos, critérios de aceitação e auditoria técnica, pode consultar GitHub/Render/Neon/Lovable conectados.
- **Claude Code** lê este documento e o código, investiga reuso, propõe implementação mínima, programa em branch própria, executa testes, explica resultados reais e abre PR para revisão.
- Coordenação indireta pelo GitHub (issues, PR, comentários, commits). NÃO dizer que existe conversa ou sincronização direta de duas IAs.
- Evitar tarefas paralelas que mexam no mesmo módulo; uma missão por vez no início. Para cada PR: contrato cumprido, riscos, testes comandáveis, logs sanitizados, limitações e lista de ficheiros.
- **Não autorizar merge automático/deploy, nem apagar histórico ou infra**. Antes de qualquer limpeza, inventário de dependências, plano de backup e lista exata do que vai ser removido.

## 7. Política de decisões e definição de pronto
Um componente fica **100% preparado para programar** quando tiver: entradas, saídas, regras, falhas, limites de permissão, teste de aceitação e dependências definidas. Isso não é o mesmo que **100% implementado** nem que estar pronto para clientes reais.
Faltas ainda abertas a decidir com piloto: evento de valor real, meta, janela, SaaS inicial, API de entrada, intervenção real permitida, agendamento confiável gratuito.
Não inventar respostas para essas faltas. Propor alternativas mínimas e justificar uma.

## 8. Primeira missão para Claude Code (sem código operacional)
1) Confirmar HEAD/base do repositório e mapear o que realmente já existe em `recovery-mvp/`. Distinguir reutilizável vs legado a aposentar, por C01–C06.
2) Para C01, propor **contrato técnico mínimo de ingestão automática** e um teste de aceitação com 20 clientes sintéticos, isolamento e deduplicação.
3) Identificar bloqueios indispensáveis, e escolher a opção mais simples de agendamento viável, distinguindo suposição de fato verificado.
4) Produzir diagnóstico/resumo curto em português e, se útil, um documento/PR **somente de planeamento** em branch nova. NÃO implementar antes de revermos o contrato C01.
5) Não gastar créditos Lovable, tocar Render/Neon, modificar `main`, efetuar deploy nem executar operações reais.
