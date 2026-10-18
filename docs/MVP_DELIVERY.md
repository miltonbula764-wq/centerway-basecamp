# CENTERWAY — PRIMEIRO MVP FUNCIONAL: montagem para revisão

Entrega da fase «primeiro montar e visualizar». O piloto está integrado na aplicação
existente. A campanha completa de aceitação e segurança C01–C10 permanece para a
fase seguinte; esta entrega não é uma publicação nem uma aprovação de produção.

1. **Estado encontrado.** Main `8a9584c`: autenticação, tenants/membros, perfil único
   versionado, C01 CSV, C02 c02-v2, C03 c03-v1 e contexto histórico implementados;
   Casos era um placeholder. Manual v2.0 lido e confrontado. A referência Lovable
   foi confirmada nos ficheiros, sem consultar ou consumir o serviço.
2. **Reaproveitado.** C01–C03 e respetivos contratos/migrações; RLS, memberships,
   auditoria, autenticação, queries por tenant, rotas e componentes visuais existentes.
3. **Construído.** Objetivos sintéticos confirmados e avaliações imutáveis; casos,
   eventos C05–C10 e interface/dossier em `/app/casos`; tipos do cliente, fixtures,
   arranque/limpeza da stack descartável e mapa visual autónomo de leitura.
4. **Core.** RPCs transacionais controlam elegibilidade, estado, versão, papel e
   referências. Lock por caso; chaves de operação com hash; replay igual reutiliza
   evento, conteúdo diferente é recusado. Aprovação admin; execução declarada por
   admin/operator; gate no relógio servidor; fecho dependente de evidência.
5. **Percurso visível.** Seis clientes fictícios permitem explorar investigação,
   aprovação, execução, espera, resultado resolvido e objetivo por atingir. Quatro
   fixtures passam por Auth/RPCs reais até ao estado atual. Duas carregam eventos
   C07/C08 retrospectivos identificados e calculam C09/C10 com evidência persistida;
   não demonstram aprovação/execução histórica ou espera real de 14 dias.
6. **Verificação.** No código `aa4698c`, 110 unitários, tipos e build aprovados no
   [frontend CI](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/39079882496).
   A stack PostgreSQL/GoTrue/PostgREST, migrações, fixtures C01–C10 e checks básicos
   de viewer, operator, replay/conflito e gate prematuro passaram na montagem do
   [browser CI](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/39079882488).
   **Resultado final: 12 testes de browser aprovados** (11 regressões existentes
   + 1 smoke de montagem), 110 unitários, tipos e build aprovados. Screenshots
   `mvp-result.png`, `mvp-open.png`, `mvp-plan.png` no
   [artifact de evidência](https://github.com/miltonbula764-wq/centerway-basecamp/actions/runs/39079882488/artifacts/12118796055),
   com retenção de 3 dias. Não equivalem à campanha completa C01–C10.
7. **PR e commits.** [PR #8](https://github.com/miltonbula764-wq/centerway-basecamp/pull/8),
   branch `review/mvp-core-journey`, rascunho, sem merge. Commits remotos:
   `127aef2` montagem; `29bf79b` stack e fixtures; `27e053b` proveniência e leitura
   histórica; `d1f39f3` guardas de configuração/condição; `aa4698c` correção do loader.
   O checkout local tem commits equivalentes com as mesmas árvores; o acesso Git
   pelo proxy estava indisponível e a entrega remota foi feita pelo conector GitHub.
   Nenhuma história publicada foi reescrita.
8. **Lovable.** Nenhuma dependência visual obrigatória para esta fase. Polimento de
   interface pode ser considerado depois. Não foi usado o agente ou os créditos.
9. **Limitações reais.** Política exclusivamente `flowreports-demo-v1`; sem score
   global, interpretação automática de documentos, conectores, scheduler, revisão
   de plano, renovação de aprovação, cancelamento, fecho administrativo ou reabertura.
   Idempotência é por caso; um caso por avaliação, sem coordenação global de ações
   entre casos de avaliações diferentes. Listas limitadas a 100 linhas e dossier a
   300 eventos. Na entrega inicial, o executor não permitia o arranque local; essa
   limitação foi resolvida na revisão final, que executou o launcher numa stack nova.
   Ver [MVP_FINAL_REVIEW.md](MVP_FINAL_REVIEW.md) para os checks e correções atuais.
10. **Como abrir.** `public/mvp-preview.html` abre já, sem instalação, como mapa
    ilustrativo de leitura. Para a aplicação operacional, seguir
    [MVP_RUNNING.md](MVP_RUNNING.md): `python3 scripts/mvp/start-local.py`, abrir
    `http://127.0.0.1:5173/app/casos` e usar as credenciais temporárias do ficheiro
    privado indicado pelo comando. Tudo usa dados sintéticos numa base nova.

Contrato e diferenças para o manual: [MVP_JOURNEY_CONTRACT.md](MVP_JOURNEY_CONTRACT.md).
Nenhuma alteração ao backend hospedado, produção ou serviços pagos.
