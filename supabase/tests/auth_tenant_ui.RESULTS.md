# Autenticação e isolamento na UI — 2026-10-16 UTC

Base de trabalho: `6770fd2`. Apenas testes e documentação adicionados; nenhuma correção de produto comprovadamente necessária nos caminhos exercitados. Nenhum ficheiro gerado editado.

## Navegador contra serviço real

- Chromium, viewport 1280×1800, página existente de autenticação.
- `/app/clientes` sem sessão redirecionou para `/auth`; conteúdo protegido não apareceu.
- Tentativa email/palavra-passe com endereço sintético `example.invalid` inexistente e senha aleatória efémera: pedido ao endpoint real de password sign-in, HTTP 400, mensagem genérica apresentada. Isto é teste de rejeição, **não login positivo**.
- Reload permaneceu sem sessão. Zero erros JavaScript de página observados. Screenshot inspecionado, sem credenciais.
- Consulta de contagens antes dos testes: `auth.users = 0`, `tenants = 0`.

## Testes reexecutáveis controlados

`src/test/tenant-session.test.tsx` usa o layout, TenantContext, SubjectDialog, QueryClient e guard reais. Apenas router, memberships, requests e apresentação do menu são controlados, sem tokens ou sessões fabricados.

1. Admin A → viewer B: cache A removida, formulário aberto desmontado e resposta A tardia não aparece na UI/cache B. Viewer não recebe controlo de criação.
2. Tenant capturado num preview A é recusado pelo guard após troca B, antes de qualquer request. Não exercita o componente completo de importação nem escreve imports.
3. Logout cancela queries, limpa cache/preferência e invalida guard antes do signOut; navegação usa `/auth` com `replace: true`. Resposta tardia não repovoa cache tenant.
4. Request de criação já enviado em A permanece dirigido a A quando B é selecionado; nunca é reenviado/retargeted a B. Uma escrita já enviada não tem garantia de cancelamento transacional.

Comandos/resultados: `bunx vitest run src/test/tenant-session.test.tsx` inicialmente 2/3; falha no seletor do teste porque o modal torna sidebar inacessível, não falha do produto. Teste corrigido para invocar a troca através do contexto real. `bunx vitest run` passou 36/36. Execução focada final após adicionar cenário 4: **4/4 passaram**, 2,77 s. Não se repetiu a suite completa após acrescentar apenas esse teste.

Último commit observado após implementação dos testes: `67c6901` (gerido automaticamente pela plataforma; o relatório final pode produzir commit posterior).

## Fixtures, capacidades e limites

- Nenhuma conta/tenant/subject/import/run inserido ou removido no backend; fixtures apenas em memória de teste. Auditoria, triggers, RLS e políticas Auth intocados. Sem suites SQL ou concorrência no backend.
- CLI e catálogo de ferramentas disponíveis não oferecem criação administrativa de utilizador Auth confirmado. `auth-session` apenas cunha sessão existente e não prova password login; não foi usado.
- **Bloqueado:** login positivo email/senha, reload autenticado, logout/back reais e isolamento A/B no navegador real. Requer conta Auth confirmada e caminho suportado para credenciais de teste. Não se alterou confirmação global, não se enviou email nem se criou backdoor.
- RLS de admin/operator/viewer não é reprovada por mocks; operator não exercitado neste turno. Modal aberto bloqueia interação normal com sidebar; mudança externa foi simulada explicitamente.
- Build automático do preview registou `build OK`; nenhum build/typecheck manual (harness). Sem publicação/serviços pagos, C03 UI ou funcionalidades novas.
- Saldo workspace consultado: 86,00 créditos; não representa orçamento reservado do projeto nem custo final deste turno.
---

# Verificação autenticada no navegador real — 2026-10-16 UTC (main 719ae43)

## Proveniência da sessão
- Conta criada e confirmada pelo fundador; password login **reportado pelo fundador** e corroborado por registo do serviço (`auth.users=1`, `confirmed=1`, `last_sign_in` não nulo) — **não observado por nós**.
- Sessão técnica cunhada via `lovable auth-session --json` (conta existente, única) e restaurada no Chromium via localStorage. Sessão técnica não prova password login.
- Nenhuma password/código/token recolhido no chat; nenhum utilizador criado, nenhuma política Auth ou dado de empresa alterado.

## Observado no navegador real (Chromium, 1280×1800 e 390×844)
1. Rota protegida `/app` com sessão: carrega layout real, tenant "Centerway" (Administrador), contagens e próximos passos. Zero erros de consola.
2. Reload em `/app`: sessão preservada, conteúdo protegido reaparece.
3. Troca de tenant A ("Centerway") → B ("Milton"): cabeçalho e conteúdo passam a B; preferência em localStorage atualizada; sem dados de A no conteúdo de B (ambos os tenants estão vazios — empty state real, não prova de isolamento com dados).
4. Troca B → A: conteúdo de A reapresentado corretamente.
5. Logout: redireciona para `/auth`; botão "voltar" do navegador não mostra conteúdo protegido (permanece em `/auth`).
6. Mobile 390×844 autenticado: `/app` carrega com barra móvel; `/auth` renderiza corretamente.
7. Zero erros de consola; zero respostas HTTP ≥400 na segunda execução. Na primeira execução, pedidos REST apareceram como "failed" por cancelamento de queries no logout/troca (abort normal do React Query), confirmado como não-erro na reexecução instrumentada por código de estado.

## Limitações
- Ambos os tenants pertencem à mesma conta com papel admin: troca A/B não prova isolamento por roles nem RLS entre utilizadores diferentes.
- Tenants sem clientes/observações: não foi exercitado cruzamento de cache com dados reais (coberto apenas pelos testes controlados `tenant-session.test.tsx`).
- Password login, signup e confirmação de email continuam apenas user-reported + registo DB, sem observação direta.
- Pedidos de escrita/imports/runs não foram exercitados nesta fase.
