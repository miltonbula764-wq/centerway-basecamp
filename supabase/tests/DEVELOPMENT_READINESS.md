# Estado para retomar desenvolvimento CENTERWAY — 16/10/2026 UTC

## Fundação e integração
- 0011 aplicada pelo executor gerido Lovable; 12 entradas, 11 anteriores preservadas. 812 checks de privilégios reais aprovados; 16 RLS, 40 funções, 29 policies e 44 triggers preservados.
- PR #1 integrado em main: 6770fd2. CI SQL/Drizzle success com 212 verificações históricas, sem enfraquecer expectativas.
- Nenhuma publicação nem serviço pago ativado.

## Sessões de base de dados concorrentes
scripts/ci/validate_concurrency.py usa duas conexões reais e observa pg_blocking_pids e wait_event_type=Lock antes de libertar a primeira transação.
Cenários:
1. Duas importações idênticas: 3 inserts na primeira, 0 inserts/3 duplicados na segunda; só 3 observações.
2. Duas análises C02 dos mesmos inputs: mesmo run_id, segunda reused; só um run.
3. Duas montagens C03: built/reused, mesmo bundle e apenas 3 refs.
4. Edição de indicador draft em paralelo com aprovação: aprovação aguarda, conserva edição e recusa escrita posterior com SQLSTATE42501.
5. Aprovação de nova versão em paralelo com importação de preview antigo: import aguarda, recusa SQLSTATE22023, nenhuma observação inserida com a chave de teste.
Primeira execução38980952054 falhou numa expectativa do próprio harness: psql -c não usou exit3 do modo script. A proteção42501 já funcionava. Corrigida a verificação para aceitar os exits de erro do cliente, mantendo SQLSTATE exato42501/22023. Nenhum SQL/produto nem teste histórico alterado.
Execução corrigida38981092103: etapa de testes passou; verificar a execução do head final desta branch antes de integrar.
Ambiente: GitHub-hosted Ubuntu24.04, PostgreSQL17 descartável, claims sintéticas, dados de teste no serviço descartável. Não liga ao Supabase real nem prova HTTP/JWT/GoTrue.

## Interface/autenticação
Lovable produziu src/test/tenant-session.test.tsx e supabase/tests/auth_tenant_ui.RESULTS.md em58a4a7ff.
- Suite completa36/36; depois quarto cenário acrescentado, execução focada4/4. Não alegar suite completa37/37.
- CacheA removida ao mudarB; respostaA tardia não aparece emB; formulárioA desmonta; preview capturadoA recusado após troca; escrita já enviada permanece dirigidaA; logout limpa/invalida antes de signOut.
- Navegador real rejeitou rota protegida sem sessão e password sign-in de conta inexistente contra o serviço real; reload não autenticado e zero erros de página.
- Não foi inventada sessão. auth.users=0 e tenants=0 antes; nenhuma fixture remota criada.
- 2026-10-16 (main 719ae43): verificação autenticada fechada — ver `auth_tenant_ui.RESULTS.md`. Conta real criada/confirmada pelo fundador (password login user-reported + registo DB `auth.users=1`, `last_sign_in` não nulo); sessão técnica via `lovable auth-session` na conta existente. Observado no navegador real: rota protegida, reload com sessão, troca A↔B sem cruzamento (tenants vazios — não prova isolamento por roles), logout e back sem conteúdo protegido, mobile autenticado, zero erros de consola/HTTP. Pendente: isolamento com dados reais e roles distintos, e password login observado diretamente.
- Não desativar email confirmation, não inserir backdoor, não apagar auditoria nem fingir teste positivo.
- Nenhuma falha de produto foi comprovada nos caminhos exercitados. Apenas testes/documentação foram acrescentados.

## Coordenação e recursos
- Lovable e Codex têm acesso operacional ao mesmo projeto/repositório; controlar um executor de escrita por área.
- main inclui as alterações geradas de preview/package anteriormente revistas; preservadas, não reescritas.
- Turno anterior de aplicação4,6créditos; turno auth/UI3,6créditos reportados.
- O Lovable reportou saldo workspace86 durante a verificação. Não é saldo reservado deste projeto nem valor de faturação pós-turno; a antiga estimativa por envelope100 não substitui a leitura do saldo.
- Bootstrap/testes SQL desta branch nunca devem ser executados no backend real.

## Próximo bloco de produto
C03 interface, sobre o servidor c03-v1 existente: detalhe de cliente/análise, montar pacote apenas admin/operator, viewer consulta, histórico e refs paginadas, estados complete/insufficient/context_facts com motivos claros. Usar snapshot e IDs; nunca fabricar evidências no browser, nem converter candidato/pacote em caso acionável.
Preservar tk(tenant), limpeza de cache, guard de tenant capturado, imutabilidade e 0011.
Começar por confirmar o entendimento desse escopo no Lovable antes da construção. Sem novos componentes C04–C10, IA paga, ações externas ou alterações de semântica do detector neste bloco.
A pendência de conta real é uma etapa de acesso/aceitação do fundador; não autoriza bloqueios artificiais nem declarar piloto operacional.
