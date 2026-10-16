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