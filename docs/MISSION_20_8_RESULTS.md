# Missão 20.8 — resultados de validação

Base: main `d764f893ea47448836f8a64f1b8660fdd3b0a143`. PR [#29](https://github.com/miltonbula764-wq/centerway-basecamp/pull/29). Arquitetura, critérios, reprodução, gates externos e rollback em [CONNECTED_ONBOARDING.md](CONNECTED_ONBOARDING.md).

**PostHog é um fornecedor OAuth/HTTP controlado.** GoTrue, PostgreSQL/RLS, PostgREST e o handler HTTPS C01 são reais e descartáveis. Não há autorização hospedada nem validação de dados PostHog externos. Os workflows associados ao commit e o artefacto `connected-results.json` constituem a execução independente de CI; este quadro identifica também os ensaios locais, sem os somar como uma única execução.

| Prova | Esperado | Obtido no laboratório |
|---|---|---|
| Auth e empresas | Administrador atual e sessão real; nenhuma herança | Dois administradores, operador, duas empresas; sessões adicionais isoladas e logout comprovado |
| Contexto inicial | Até cinco perguntas; nenhuma chave pessoal | Wizard responsivo, consentimento, região e unidade imutável |
| OAuth | PKCE S256, state/nonce únicos, um projeto, apenas leitura | Replay/expiração/CSRF/issuer/paginação adulterada recusados; projetos 41 e 72 independentes; scopes/refresh verificados |
| Descoberta | Apenas grupos/eventos observados, join explícito | Duas referências estáveis por amostra; dados pessoais extras descartados; nenhuma pessoa convertida em cliente B2B |
| Aprovação | Sem recolha antes de clientes/perfil aprovados | Rascunho incompleto bloqueado; regras humanas explícitas usadas no teste; C01 não fez bootstrap |
| Execução limpa local HTTP/SQL | Resultados persistidos reproduzíveis | 186 asserções; 3 clientes; 10 observações (9 A, 1 B); 9 tentativas C01, 7 UUIDs únicos; 13 linhas transmitidas incluindo repetições/falha |
| Reenvio e correção | Mesmas identidades; histórico intacto | Duas falhas HTTP injetadas (503 antes do handler e resposta ambígua após persistência) recuperadas; correção com UUID real; valores anteriores preservados; nenhuma rejeição de linha C01 válida |
| Refresh/revogação | Sessão/projeto não mudam; falha identificável | Um refresh válido e um inválido; uma revogação remota concluída e uma pendente após 503, cifrada e bloqueada até ao retry real de cinco minutos |
| Worker | Diagnóstico persistido e backoff respeitado | Invocação manual com falha upstream guardada; 429 bloqueia nova leitura até Retry-After; não se instalou ou comprovou scheduler hospedado |
| Corte PostgreSQL | Erro controlado e operação seguinte revalidada | Regressão adicional termina apenas a ligação do runtime descartável, observa recusa e recupera nova lease; executada isoladamente e incorporada na suite CI |
| Browser móvel | Percurso e bloqueios reais no produto | Login → OAuth controlado → descoberta → nome/meta/direção → rascunho → aprovação bloqueada → desconexão; sem overflow horizontal |
| Troca A → B → A | Resposta tardia não restaura a empresa anterior | Browser com resposta atrasada controlada; nenhum estado ativo ou botão de sync indevido |
| Regressões locais | Segurança, tipos e build | 144 unitários em 16 ficheiros, duas regressões Python da sondagem C01, 15 testes de readiness offline, tipos e build aprovados |
| Core | Zero decisões automáticas | Zero C02 runs, C03 bundles, C04 evaluations, casos Core e casos operacionais nas duas empresas |

As contagens acima são da fase HTTP antes dos ensaios de browser; estes criam um rascunho noutra empresa sintética e não enviam medições. A regressão de corte de ligação integra a execução final de 186 asserções. A execução local de 184 asserções foi um ensaio anterior e não deve ser somada. A execução local anterior de 133 asserções/nove observações é um ensaio anterior da mesma missão, não deve ser somada. Também não se reutilizam as contagens das Missões 20.1–20.7B.

O percurso móvel foi medido entre cerca de 1,9 e 2,1 segundos em automação local, desde o preenchimento automático do contexto até à desconexão, incluindo OAuth controlado, descoberta, rascunho e bloqueio da aprovação. Não mede tempo de resposta humana, autorização PostHog real, latência hospedada ou um objetivo comercial. Cinco perguntas iniciais não eliminam as revisões de contrato que o produto exige posteriormente.

Foram corrigidos problemas encontrados durante a implementação: remontagem React StrictMode; recuperação de ligação de sessão anterior sem herdar consentimento; transação atómica da ligação/PKCE; tratamento de estado revogado; backoff/diagnóstico do worker; bloqueio de reativação de autorização falhada; calendário/timezone UTC explícito; ligação pelo campo nativo de grupo indicado no schema oficial, sem presumir conservação de JSON bruto; validação de seleção incompleta; libertação de lease mesmo quando o reset falha. O patch mínimo do driver PostgreSQL impede escrever ou devolver ao pool uma lease cujo socket fechou, com regressão de corte real de ligação. A versão continua bloqueada em 3.4.9 e a auditoria não foi desativada. Os avisos GHSA-qxg6-89mg-rqv8 e GHSA-xp26-3454-mjgp do @vitest/mocker motivaram a atualização bloqueada para Vitest 4.1.12.

A CI demonstrou ainda uma falha no teste antigo de recuperação C01: uma resposta HTML 502 no reinício do PostgREST causava JSONDecodeError. A sondagem mantém o prazo e só aceita HTTP 200; duas regressões verificam 502→200 e falha persistente. Nenhuma lógica C01–C10 foi alterada.

Limitações: OAuth hospedado e HogQL em projeto real não validados; requer CIMD HTTPS e gates de implantação; runtime Cloudflare por omissão não comprovado para PostgreSQL; apenas ligação DB direta/pooler de sessão suportada; scheduler preparado, não instalado; B2C não mapeado por este conector; descoberta limitada/amostrada; novos clientes/mapeamentos e atrasos além de dois dias exigem revisão; regras e justificação de resultado ainda passam pelo editor atual; chave C01 expira em 30 dias e consentimento depende da sessão; retry remoto de cinco minutos foi respeitado e mantido pendente, não apresentado como recuperação já concluída. A confirmação administrativa de metas não comprova documentos, confirmação do cliente ou objetivos individuais C04.

Nenhum acesso ao Supabase hospedado, Lovable ou dados PostHog externos; nenhum deploy, alteração de Cron hospedado ou merge. A aprovação do PR é separada da futura autorização para ligação externa.
