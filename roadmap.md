# Roadmap CENTERWAY

## Autenticação e isolamento (concluído)
- [x] Testes controlados de troca de tenant, formulário e logout.
- [x] Verificação autenticada no browser real (dev local, backend real): rota protegida, reload, troca A↔B, logout e back, mobile. Relatado em supabase/tests/auth_tenant_ui.RESULTS.md.
- Limitação: password login é user-reported + registo DB, não observado por nós; roles iguais em A/B não provam isolamento por roles.

## C03 UI (concluído)
- [x] Painel "Pacote de evidência (C03)" no detalhe do cliente, ligado à análise C02 selecionada.
- [x] Montagem explícita só admin/operator; viewer só lê; rejected/failed JSON sem error tratado sem toast de sucesso.
- [x] Refs paginadas por ordinal; estados complete/insufficient/context_facts com semântica honesta.
- [x] Testes controlados (7 novos) + suite 44/44 + build OK. Relatório: supabase/tests/c03_ui.RESULTS.md.

## Pendente
- [ ] Concorrência real em PostgreSQL isolado (a cargo do Codex no GitHub).
- [ ] C04–C10: não autorizados.
