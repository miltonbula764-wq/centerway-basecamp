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
- [ ] Validação da montagem no commit final: consultar PR #8 e execução CI.
- [ ] Campanha completa de segurança e E2E C01–C10 após montagem, conforme nova prioridade.
- [ ] Classificação universal de valor, múltiplos objetivos, compatibilidade documental automática,
  reabertura e políticas gerais continuam pendentes das decisões A–H do manual.

Contrato: `docs/MVP_JOURNEY_CONTRACT.md`. Arranque e limites: `docs/MVP_RUNNING.md`.
