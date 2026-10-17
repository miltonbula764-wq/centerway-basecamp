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

## Pendente
- [ ] Core/C04: missão Engenharia #6 autoriza contexto histórico; ver docs/CORE_C04_CONTRACT.md.
- [ ] Classificação de estado de valor: pendente do contrato aprovado (realização, gap, suficiência, agregação).
- [ ] C05–C10: fora do escopo atual.
