# CENTERWAY

## Projeto atual (MVP CENTERWAY 3.0)

**Objetivo:** uma SaaS autoriza uma ligação; o CENTERWAY recolhe resultados,
deteta e investiga impedimentos, executa uma ação previamente autorizada e
mede o resultado posterior. O founder acompanha evidências no dashboard,
sem operar manualmente cada cliente.

**Fonte do MVP F01–F06:** `recovery-mvp/`, em desenvolvimento
na cadeia de PRs iniciada em #49 e validada sinteticamente em #83.
**M00:** [inventário/decisões](PROJECT_STATE.md) e PR #85.
A branch `main` continua a conter a aplicação legada C01–C10.

### Componentes existentes

- `recovery-mvp/sql/` — F01–F06: contrato, deteção, investigação, decisão
  de intervenção **sintética**, verificação e orquestração idempotente.
- `recovery-mvp/api/` — API autenticada.
- `recovery-mvp/managed/` — perfil de demonstração Render/Neon.
- `recovery-mvp/lovable-ui/` — interface atual; fluxo manual a substituir
  pelo founder dashboard de leitura, após existir motor autónomo.
- `recovery-mvp/tests/` — testes de regressão e isolamento.

### Limite do que foi demonstrado

Há percurso F01–F06 sintético com PostgreSQL/HTTPS/browser testado
(consultar PR #83). Ainda **não** está demonstrada a ingestão autónoma
de uma SaaS real, intervenção externa real ou execução agendada.
Uma medição declarada `verified` não equivale a prova independente
de valor empresarial; melhoria posterior não prova que a ação a causou.

### Ordem de execução

**M00** inventariar/limpar com segurança → **M01** integrar uma SaaS e obter
resultados verificáveis → **M02** avaliar valor e deterioração → **M03**
investigar → **M04** executar uma ação real autorizada → **M05** verificar →
**M06** dashboard apenas de leitura e piloto.

### Trabalho local

O projeto Lovable legado permanece na raiz (`npm install`, `npm run dev`).
As instruções de testes do MVP Python/PostgreSQL encontram-se em
[`recovery-mvp/README.md`](recovery-mvp/README.md) e
[`recovery-mvp/api/README.md`](recovery-mvp/api/README.md).
Não confundir a aplicação antiga com a fonte do novo MVP, nem aplicar
migrações dos testes descartáveis à base de dados pública.
