# 0011 restore_client_privileges — aplicação (backend Pro Suzana)

- Aplicado em 2026-10-16 ~23:02 UTC pela ferramenta de migration suportada (Drizzle, transacional).
- Ficheiro gerado: `drizzle/migrations/0011_restore_client_privileges.sql` (+ journal/snapshot gerados).
- `__drizzle_migrations`: 11 → 12 linhas; nova hash `ad64c139583a55ff02ed2d79a9e1becc1f3546effeee8974dfd1df10969a1f1f`, created_at 1792191706522. 0000–0010 não reaplicados.
- SQL: corpo revisto pelo Codex, sem alterações.

## Pré-checks (só leitura)
11 entradas, nenhuma 0011 local nem remota. Vitest 33/33 passou e o build passou.

## Pós-checks (catálogo, só leitura)
- Tabelas (16 × 2 roles × 7 privilégios = 224): anon 0; authenticated apenas SELECT em 11 tabelas, S/I/U em subjects, S/U/D em tenant_value_profiles, S/I/U/D em profile_indicators; value_profiles/indicators 0.
- Sequências (2 × 2 × 3 = 12): 0 concedidos.
- Funções públicas (40 × 2 = 80): anon 0; authenticated 16 (`_cw_is_privileged` + 15 RPCs).
- Total: 316 verificações por role-privilégio. Não é a matriz de 812 do Codex (inclui PUBLIC/column/ACL rows); essa matriz não foi executada aqui.
- RLS 16/16, 44 triggers ativos, 29 policies; soma de linhas das tabelas principais = 0 antes e depois.

## Limites
Sem testes de comportamento como authenticated nesta base; sem suites SQL históricas; corpos de funções não comparados com o CI.

## Verificação independente posterior — Codex
- SELECT de matriz efetiva: checks=812,passed=812,failed=0;inclui grant options,privilégio MAINTAIN e colunas, além de tabelas/sequências/funções.
- RLS16/16;40definition_hash de funções,29policies e44triggers comparados byte a byte após normalização e preservados.
-11primeiras entradas SQL(id,hash,created_at) exatamente iguais ao baseline CI e à fotografia remota anterior;12entradas no total.
-14contagens consultadas antes/depois:tenants,memberships,subjects,tenant_value_profiles,profile_indicators,ingestion_batches,observations,audit_log,c02_runs,c02_results,c03_bundles,c03_indicators,c03_refs,c03_attempts; todas0.
- A árvore final07471d7 mantém package.json/bun.lock/previewAuthStorage atualizados, apesar da descrição ambígua do agente sobre “não apareciam”. Build/Vitest reportados referem esse estado de trabalho.
- O hash diferente da cópia CI inicial resulta apenas da newline final removida; comandos SQL iguais.
- Sem teste de sessão HTTP/JWT real; sem testes mutáveis nem bootstrap no backend.
