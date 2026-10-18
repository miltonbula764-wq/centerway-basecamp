# Roadmap CENTERWAY

## Autenticação e isolamento (concluído)
- [x] Testes controlados de troca de tenant, formulário e logout.
- [x] Verificação autenticada no browser (dev local ligado ao backend real, conta existente do fundador): rota protegida, reload, troca A↔B, logout e back, mobile. Ver supabase/tests/auth_tenant_ui.RESULTS.md.
- Limitação: password login é relatado pelo fundador + registo na base, não observado por nós; roles iguais em A/B não provam isolamento por roles.

## Concorrência real (concluído)
- [x] 5 cenários em PostgreSQL isolado no GitHub (PR #2 integrado em 719ae43, execução 38981197896). Ver DEVELOPMENT_READINESS.md.

## C03 UI (concluído, revisto)
- [x] Painel "Pacote de evidência (C03)" ligado à análise C02 selecionada; pacote consultado por tenant+cliente+análise.
- [x] Guard de resposta tardia por identidade+geração (sucesso e erro), reset ao mudar de cliente/análise/empresa.
- [x] Detalhe completo de cada referência e resumo do snapshot histórico.
- [x] 18 testes controlados (red/green registado), suite 55/55, tipos e build OK. Ver supabase/tests/c03_ui.RESULTS.md.

## MVP montado — missão de continuação, outubro 2026
- [x] Core/C04: contexto histórico preservado; avaliador sintético versionado, sem score global.
- [x] C05–C10: investigação com prova C01, plano manual, aprovação admin, recibo humano,
  gate de 14 dias, comparação com novo pacote C03 e decisão resolved/remain_open.
- [x] Página Casos integrada, dossier por etapa, histórico e estados/erros explícitos.
- [x] Mapa visual autónomo de leitura em `public/mvp-preview.html`.
- [x] Receita de base descartável e seis casos sintéticos; histórico retrospectivo explicitamente identificado.
- [x] Validação da montagem em `aa4698c`: 12 browser, 110 unitários, tipos e build;
  execuções CI 39079882488 e 39079882496, PR #8. Documentação posterior não altera o código testado.
- [ ] Campanha completa de segurança e E2E C01–C10 após montagem, conforme nova prioridade.
- [x] Revisão final em `7f6f08a`: 12 browser, 110 unitários, tipos/build,
  upgrade não vazio preservando 16 tabelas/grants e 76 verificações SQL com rollback.
  Arranque local real verificado; C10 bloqueia fecho com evidência nova pendente.
- [ ] Classificação universal de valor, múltiplos objetivos, compatibilidade documental automática,
  reabertura e políticas gerais continuam pendentes das decisões A–H do manual.

Contrato: `docs/MVP_JOURNEY_CONTRACT.md`. Arranque e limites: `docs/MVP_RUNNING.md`.

- [x] 0012 instalada no backend deste projeto (18/10/2026) pela ferramenta gerida; SQL idêntico (sha256 b1ace0b1…), histórico 13 entradas.

## Polimento visual de Casos
- [x] Orientação no estado vazio com ligações existentes, distinção do piloto e etapas legíveis em mobile.
- [x] Browser autenticado dev local ligado à base hospedada: ligações Clientes/Novo cliente (sem guardar), Perfil e Dados, 10 etapas expandíveis, retorno à seleção; mobile 390×844 sem overflow, zero erros de consola/HTTP e zero escritas REST.
- [x] Suite existente 110/110; build/typecheck gerido OK. Ajuste local das anotações de leitura de casos/eventos após tipos regenerados pela 0012, sem alteração de contrato ou dados.

## C04 configurável — missão atual
- [x] Configurações e avaliações persistentes e imutáveis por cliente/indicador; documentação separada de resultado medido.
- [x] Painel integrado em Casos; metas explícitas e revisões, pendências e entrada de coordenação do Core sem transições automáticas.
- [ ] Políticas gerais de casos, cumprimento agregado da promessa e migração de perfil na interface ficam pendentes.

Contrato e execução: `docs/C04_CONFIGURABLE.md`.

## Core e percurso operacional configurável
- [x] 0014 instalada em 18/10/2026 pela ferramenta gerida numa única chamada: SQL byte-idêntico ao PR #10 (SHA-256 3f8a9202e3e50c67dc0a8406ffdb3968264915fa2b2288560778812731d6c63a), 15 registos e 24 tabelas; journal idx14/timestamp 1792316571467 e snapshots encadeados, 0000–0013 intactos. RLS/ACL e lock tenant C04 confirmados por SELECT; dados preservados. Tipos regenerados automaticamente, build/typecheck OK e Vitest 110/110. Browser autenticado dev local ligado ao backend hospedado: /app/casos e reload, “Sem casos”, mobile sem overflow, zero erros/HTTP ≥400/escritas REST. Com 0 clientes, os painéis C04/Core por cliente não foram exercitados; sem seed ou publicação.
- [x] C04 persistido como entrada sem exigir candidato C02; pendências visíveis e abertura humana documentada.
- [x] C05–C10 por indicador, janela e critérios explícitos por caso, autorização, histórico e isolamento.
- [x] Percurso integrado em Casos, preservando o piloto e as migrações instaladas.
- [ ] Políticas universais, múltiplos ciclos, reabertura e migração de contrato do caso continuam pendentes.

Contrato e testes: `docs/OPERATIONAL_JOURNEY.md`.
