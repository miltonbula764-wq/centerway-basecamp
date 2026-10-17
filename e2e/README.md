# Browser C02→C03 — ambiente descartável

O workflow `.github/workflows/browser-e2e.yml` executa a aplicação real em Vite/TanStack,
Chromium via Playwright e uma stack efémera PostgreSQL 17 + GoTrue 2.177.0 + PostgREST 12.2.3.
Não usa o agente Lovable, o backend alojado, contas reais ou serviços pagos. Só publica
portas no loopback do runner Ubuntu padrão e destrói os containers no fim.

## Reproduzir e consultar resultados

Enviar a branch de revisão ou abrir/atualizar o PR dispara o workflow. Não é necessário
merge em main. O job é a receita executável: instala a aplicação com Bun 1.3.0 e
`bun install --frozen-lockfile`; instala apenas a ferramenta de browser separada com
`npm ci` em e2e (Playwright 1.56.1 e package-lock próprio); prepara os serviços, executa
`node e2e/seed.mjs`, `npm test` em e2e, os testes Vitest, `tsc --noEmit` e o build.
Não atualiza o bun.lock nem as dependências da aplicação.

O bootstrap recusa execução fora de GitHub-hosted Actions e não aceita URL de base remota.
O PostgreSQL é um service novo, exclusivo do job. O diretório de execução é uma cópia sem
.env; `.env.local` é gerado com o URL local e a chave anónima efémera. As chaves de assinatura,
palavras-passe aleatórias, sessões e ficheiros privados não entram no repositório nem na
lista de upload. Traces/vídeos de autenticação estão desativados. Apenas logs técnicos,
relatório HTML e screenshots de dados sintéticos são retidos como artifacts durante 3 dias.
Os logs nativos do Actions seguem a política de retenção do repositório.

## Níveis de evidência

| Cenário | Browser | Serviços e respostas |
|---|---|---|
| Login por palavra-passe, rota protegida, reload, logout/back | Chromium real | GoTrue real, sem sessão injetada nem auth simulada |
| Seleção C02, built/reused, indicadores e refs, perfil histórico | Chromium real | PostgREST/RPC/SQL reais; JWT real emitido por GoTrue |
| A→B→A, cliente, tenant, desmontagem/remontagem | Chromium real | A entrega/despacho de respostas é controlada pelo Playwright; o body é preservado e a RPC real é chamada através de route.fetch |
| rejected e failed | Chromium real | Só o JSON da RPC C03 é simulado; login e leituras são reais. Não prova a persistência de uma tentativa falhada no SQL |
| admin/operator/viewer na UI, desktop/mobile | Chromium real | Utilizadores e memberships reais na base efémera; controlos da interface observados |
| RLS e permissões HTTP complementares no seed | HTTP real | JWT viewer: leitura de outro tenant devolve []; viewer e operator de outro tenant recebem 403/42501 ao montar; assinatura JWT inválida recebe 403/bad_jwt no Auth e 401/PGRST301 no REST |

O `auth.uid()` do bootstrap lê o sub das claims PostgREST, e os papéis são instalados
localmente; as tabelas e migrações Auth são criadas pelo GoTrue real. Não se desativa RLS.
PostgREST usa authenticator NOINHERIT e muda para anon/authenticated por pedido: as
verificações HTTP de tenant não correm como proprietário da base.

A confirmação automática de email está configurada SOMENTE no GoTrue descartável. Não há
SMTP nem alteração de política no serviço real. Isto exercita password grant/JWT/getUser,
não o envio/receção de emails. A stack é mínima: não equivale à configuração completa de
Supabase alojado (gateway gerido, Realtime, Storage, pooling ou políticas de produção).

## Fixtures e observação

Quatro utilizadores sintéticos são registados e autenticados pela API GoTrue. RPCs reais
criam dois tenants, memberships, dois clientes de A e um de B, perfis e observações. O
C02 é calculado com dados numéricos suficientes, um indicador sem medições e outro de
contexto. São criadas análises em datas diferentes e pacotes de leitura próprios; viewer
/mobile não dependem de um teste anterior montar um pacote. Uma versão v2 é aprovada com
baseline diferente, permitindo verificar que o C03 v1 preserva o snapshot/baseline 80.

A chave anónima é assinada só para esta instância; não representa sessão de utilizador.
Cada login do browser preenche o formulário real e obtém a sessão do GoTrue; não se usa
storageState, auth-session, localStorage injetado ou bypass da rota protegida.

`e2e/vite.config.ts` envolve a configuração normal e acrescenta SOMENTE um observador de
leitura do QueryClient. Não substitui componentes, guards, queries, RPCs ou autenticação.
Expõe apenas query keys e eventos de mutação (id/status/tenant/cliente/análise), nunca dados
Auth/tokens. O teste confirma o pedido e aguarda o evento terminal, emitido DEPOIS dos
callbacks, mais dois frames de apresentação, antes das asserções negativas. A configuração
de produção não importa este observador e o build final usa o vite.config.ts original.

As fontes Google são substituídas por CSS vazio para evitar tráfego externo/fontes instáveis;
os outros pedidos de browser externos a localhost são recusados. O teste A→B→A verifica
concorrência de pedidos/feedback da UI, não bloqueios simultâneos de transações PostgreSQL:
a suite SQL de concorrência existente permanece separada e intocada.

## Histórico de preparação

- Primeiro arranque: o search_path da ligação GoTrue não apontava para auth. As migrações
  Auth falharam numa referência ao enum auth.factor_type. Corrigida apenas a configuração
  do container para search_path=auth,public; nenhuma migração do produto foi alterada.
- Seed inicial: PostgREST recusou um lote com indicadores de campos diferentes (PGRST102).
  Inserções separadas mantêm os defaults e o contrato reais, sem enfraquecer validações.
- Check adicional de JWT: o harness inicialmente esperava 401 nos dois serviços; GoTrue
  2.177.0 devolve 403/bad_jwt, enquanto PostgREST devolve 401/PGRST301. Passou-se a exigir
  cada status e código exatos, mantendo a rejeição obrigatória.
- Primeira validação completa: execução 39015283962, commit
  5b712a589fcbe0b82f73e5d0f2409aa2c1333c6e — 9 E2E, 89 unitários, tipos e build aprovados.
  A suite atual acrescenta independência das fixtures de leitura e checks explícitos de
  assinatura JWT, rota protegida/reload/logout/back. Consultar o PR e a execução do HEAD
  para os resultados finais; não inferir sucesso apenas da existência deste documento.

Nenhum defeito de produto foi demonstrado durante a preparação. As alterações acrescentam
infraestrutura e cobertura reexecutável. Capturas e relatórios não constituem prova de
isolamento completo ou aceitação do piloto alojado com utilizadores reais.
