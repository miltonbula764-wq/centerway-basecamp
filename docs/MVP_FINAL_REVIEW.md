# CENTERWAY — revisão final do PR #8

Data: 18/10/2026. Repositório `miltonbula764-wq/centerway-basecamp`.
A revisão cobre o MVP sintético da branch `review/mvp-core-journey`.
Não houve merge, publicação, acesso ao projeto Lovable, envio de tarefas ao seu
agente, consumo de créditos ou alteração ao backend hospedado.

## Veredictos e âmbito

| Pergunta | Resultado |
|---|---|
| PR pronto para merge? | **SIM para o código deste piloto**, após os checks do HEAD verdes e decisão humana de merge. Não equivale a publicar ou migrar o backend hospedado. |
| Código operacional completo para este MVP? | **SIM**, no contrato limitado `flowreports-demo-v1`, com intervenção humana e dados sintéticos. Não é a implementação universal das propostas do manual. |
| Migração pronta para aplicação posterior? | **SIM tecnicamente**, sobre uma base compatível com 0000–0011. Foi testada numa base descartável não vazia. O esquema hospedado não foi inspecionado; confirmar migrações instaladas, privilégios, backup e ambiente de destino antes de uma aplicação posterior autorizada. |
| Compatibilidade com o projeto Lovable? | **PROVÁVEL**: o mesmo projeto, framework, dependências/versionamento e rota existente compilam. A ligação está documentada em AGENTS/README. Estado atual da sincronização na plataforma não é verificável sem lhe aceder, acesso expressamente excluído pelo fundador. |

A interação com o Lovable fica com o fundador, separadamente. O Codex prepara e
revê código no GitHub; não entrega nem importa o projeto no Lovable.

## Oito verificações efetuadas

1. **Página operacional completa na branch.** `/app/casos` usa a rota TanStack
   já registada, `CaseWorkspace`, tipos e RPCs/table reads autenticados. A branch
   inclui objetivos, avaliações, investigações, planos, aprovação, registo humano,
   gate, comparação, decisão, eventos, migração, fixtures e launcher isolado.
2. **Compatibilidade C01–C03.** C01 continua a escrever observações append-only;
   a versão do perfil vem de `ingestion_batches`, não de um campo inventado em
   `observations`. C04/C09 leem bundles/snapshots C03 e o perfil histórico do run.
   C05 liga a prova C01 a tenant, cliente, perfil, período e payload hash.
   C02 continua a produzir candidatos; C03 não passa a concluir valor.
3. **Migração 0012.** É aditiva: quatro tabelas novas, uma chave UNIQUE adicional
   em C03, funções, grants/revokes e triggers. Não remove/recria tabelas ou dados
   C01–C03 e não enfraquece políticas anteriores. No CI, a 0012 é aplicada em
   transação depois de criar fixtures C01–C03: hashes de todas as linhas e grants
   das **16 tabelas anteriores** são comparados antes/depois e têm de coincidir.
   A notificação `pgrst, 'reload schema'` é entregue depois do commit e permite
   que uma API já em execução reconheça as novas tabelas e RPCs.
4. **Segurança básica.** 76 verificações SQL com `authenticated`/`anon`, claims
   sintéticas e rollback: leitura dos membros, invisibilidade para outra empresa,
   proibição de INSERT/UPDATE/DELETE diretos, RPC privada, viewer sem escrita,
   operator sem aprovação/administração, referências cruzadas de tenant/cliente,
   FK composta, versão antiga e salto da aprovação. O seed HTTP real acrescenta
   execução por operator, replay idempotente, conflito de payload e gate prematuro.
   As fixtures privilegiadas são distinguidas dos testes de autorização.
5. **Histórico Git preservado.** `main` é ancestral do HEAD. As correções são commits
   adicionais na própria branch, com push normal. Não houve rebase, amend, squash,
   force-push ou merge. O snapshot local da entrega anterior foi preservado numa
   branch local separada antes de obter os commits remotos reais.
6. **Código separado da aplicação de migrações.** Os comandos dev/build e os módulos
   da aplicação não aplicam SQL. A execução de migrações está nos scripts de teste,
   que restringem a base ao loopback descartável/GitHub-hosted. Sincronizar código
   não exige credenciais administrativas do backend. Numa base sem 0012, Casos
   apresenta uma limitação explícita; não tenta criar tabelas ou executar SQL.
   Não se verificou nenhum automatismo externo do serviço Lovable.
7. **Demonstração isolada.** A política tem nome/versionamento fixos, funções
   `*_demo_*`, critérios explícitos e etiquetas sintéticas na interface. A migração
   não cria tenants, utilizadores, observações ou casos de exemplo. O seed só
   escreve na stack descartável. Eventos retrospectivos têm marcador e aviso;
   não representam uma aprovação/execução histórica ou espera real de 14 dias.
8. **Independência do mapa.** A aplicação operacional não importa nem solicita
   `mvp-preview.html`; existe apenas uma ligação opcional. O smoke bloqueia qualquer
   pedido ao mapa e exige zero pedidos enquanto navega nos dossiers persistidos.

## Defeitos corrigidos nesta revisão

- **Encerramento com informação desatualizada:** o código anterior podia fechar
  após uma nova observação de integração desativada. Reproduzido na base descartável
  antes da correção. C10 agora mantém aberto quando há nova evidência relevante
  posterior ao corte C09, exigindo nova comparação. O snapshot anterior fica igual.
- **Correções após cutoff:** C09 resolve os factos da integração até ao corte do
  bundle; correções posteriores não reescrevem a avaliação histórica. C10 trata a
  informação posterior como pendência antes de fechar.
- **Portabilidade de dependências:** 97 URLs de arquivos no `bun.lock` apontavam
  para uma cache Lovable inacessível neste executor. Foram normalizados para npm
  público, sem alterar versões, dependências ou hashes de integridade. Instalação
  congelada, tipos e build foram novamente verificados.
- **Cobertura CI:** alterações apenas a migrações/scripts de arranque também
  acionam a revisão. Acrescentados teste de upgrade não vazio e revisão SQL.
- **Cache da API após upgrade:** incluída a notificação de reload e uma sondagem
  de prontidão apenas de leitura; não se repetem mutações para descobrir prontidão.
- **Artefactos privados:** credenciais temporárias, fixtures geradas e relatórios
  de browser foram acrescentados ao `.gitignore`.

## Commits e evidência efetiva

Baseline revisto: `8641c2a04304bb232dfe43588ef865048b1e2e37`, confirmado no GitHub,
com Actions [39080132581](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/39080132581)
e [39080132567](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/39080132567)
aprovados: 12 browser, 110 unitários, tipos e build. Não se inferiu sucesso apenas do relatório inicial.

Correções: `e10b7ceab511127644cfb31166e06ec11932d2da` e
`7f6f08a2aa4a84f43c2c523ab13fdb23fd502b84`.
No primeiro, o upgrade preservou as 16 tabelas, mas o teste detetou a cache da API
por atualizar; não é registado como sucesso completo. A segunda correção resolve
esse bloqueio. Checks do código revisto:
[browser/SQL/upgrade](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/39104890492)
e [frontend](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/39104890498).
**Ambos aprovados:** 12 testes de browser, 110 unitários, tipos e build; upgrade
preservando as 16 tabelas anteriores e 76 verificações SQL com rollback.
Consultar também os checks do HEAD final no [PR #8](https://github.com/miltonbula764-wq/centerway-basecamp/pull/8);
commits documentais posteriores não alteram o código e a migração testados.

Execução local efetiva: launcher `start-local.py`, sem `.env` original, nova stack
PostgreSQL/GoTrue/PostgREST e seis casos sintéticos; Vite iniciou e respondeu em
`/app/casos`. As 76 verificações SQL passaram também nesta stack e foram revertidas.
Tipos, 110 unitários e build foram executados localmente na cópia isolada.
O endpoint HTTP por si só não prova login; login/roles/dossiers são cobertos pelo CI.

## Bloqueios reais e limitações

Não há bloqueio técnico identificado para integrar **o código deste piloto** após
os checks verdes. Para ver funcionalidades C04–C10 num backend que ainda não tem
0012, é necessária a instalação posterior e autorizada dessa migração: receber o
código por Git não cria as tabelas. Até lá, usar a aplicação operacional isolada.
A sincronização externa no Lovable e o estado da base hospedada permanecem não
verificados por decisão de âmbito; o fundador gere esse serviço separadamente.

Limites preservados: política apenas sintética, compatibilidade documental humana,
sem conectores, scheduler, revisão/renovação de planos, cancelamento, fecho
administrativo ou reabertura; idempotência por caso, sem coordenação global entre
casos de avaliações diferentes. Novas versões de perfil exigem novo enquadramento
explícito; não há migração automática do objetivo histórico. A campanha completa
C01–C10 de concorrência, segurança e aceitação permanece uma fase posterior.

## Passos exatos para ver a aplicação verdadeira

1. Obter a branch `review/mvp-core-journey` do PR #8, sem merge. Pré-requisitos:
   Python 3.12+, Docker, psql, Node 22+ e Bun 1.3.0; portas 5432, 9999, 54322,
   54321 e 5173 livres.
2. Executar `python3 scripts/mvp/start-local.py`. O comando exporta o HEAD sem
   `.env`, instala dependências do npm público e cria apenas serviços descartáveis.
3. Abrir `http://127.0.0.1:5173/app/casos`; usar uma conta de demonstração e a password
   temporária no ficheiro privado indicado pelo launcher (`e2e/private/mvp-users.json`).
4. Explorar os seis casos, os dossiers e os papéis admin/operator/viewer. Para o
   percurso humano novo, aprovar como admin e registar como operator. A janela de
   14 dias real não é encurtada; os dois exemplos finais usam histórico fictício
   explicitamente identificado e C09/C10 calculados com medições persistidas.
5. Terminar com Ctrl+C e `python3 scripts/mvp/stop-local.py` para remover somente os
   serviços etiquetados desta demonstração. Nunca usar a base hospedada para o seed.
6. Separadamente e só quando autorizado: decidir o merge preservando o histórico.
   O fundador verifica o projeto Lovable na sua própria sessão. A eventual aplicação
   hospedada da 0012 tem revisão de esquema, backup e autorização próprios; não foi
   executada nem é requisito para receber apenas o código.
