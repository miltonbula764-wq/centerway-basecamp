# C03 UI — resultados

Data: 2026-10-16. Escopo: painel de pacote de evidência no detalhe do cliente, sobre o servidor c03-v1 (migration 0010). Sem SQL novo, sem migrations, sem C04–C10.

## Ficheiros
- `src/lib/c03.ts` — traduções de estados, roles de refs e códigos de recusa/falha da migration 0010, com fallback legível.
- `src/components/app/evidence-panel.tsx` — painel C03 (bundle, indicadores, refs paginadas, tentativas, montagem).
- `src/components/app/deterioration-panel.tsx` — prop `onRunChange` para expor a análise selecionada.
- `src/routes/_authenticated/app.clientes.$subjectId.tsx` — ligação run selecionado → painel C03.
- `src/test/evidence-panel.test.tsx` — 7 testes controlados (mocks, sem backend real).

## Comportamento implementado
- Pacote selecionado pelo `run_id` da análise histórica escolhida (não só a última).
- Montagem explícita via `build_evidence_bundle(_tenant_id, _run_id)`, só admin/operator; viewer nem vê o botão.
- RPC pode devolver rejected/failed como JSON sem error: mostra código traduzido, refaz fetch de tentativas, sem toast de sucesso. built → sucesso; reused → info.
- Estados por indicador: complete = "Evidência íntegra" (nunca recuperação/valor/caso), insufficient com motivos, context_facts.
- Refs paginadas por ordinal (50/página), filtros tenant+bundle+indicator, contagem total visível; página parcial nunca apresentada como total.
- `ref_budget_exceeded`: explica que nenhuma ref foi guardada para não apresentar pacote parcial como completo.
- Guard de corrida: tenant+run capturados antes da RPC; resposta tardia após troca não mostra toast nem seleciona pacote no run errado. Reset de estado na mudança de cliente/run/tenant.
- Query keys com prefixo de tenant; texto importado tratado como dado.

## Testes executados
- `bunx vitest run` — 44/44 (37 preexistentes + 7 novos C03 UI).
- Build: OK (log de build sem erros).
- Cobertura nova: três estados com semântica honesta; paginação determinística (página 2 começa no ordinal 51, total 120 visível); budget exceeded explicado; viewer sem botão; rejected JSON sem error (código visível, tentativas refetchadas, sem toast de sucesso); reused → info; resposta tardia após troca de tenant sem toast.

## Limitações
- Dados reais vazios: cenários ricos são testes controlados com mocks, não backend populado.
- Browser real validou apenas o empty state (sem pacotes).
- Concorrência real não testada (prevista para PostgreSQL isolado via Codex).
- Nada publicado; sem custos de serviços.
