> Extensão posterior: o percurso configurável C05–C10 autorizado na missão seguinte está em [OPERATIONAL_JOURNEY.md](OPERATIONAL_JOURNEY.md). As fronteiras históricas abaixo descrevem a entrega C04 inicial.

# C04 configurável — primeiro bloco funcional

Base: main `54e4a43`, incluindo orientação de Casos, journal e snapshot da 0012 instalada. A migração 0012 e os snapshots 0000–0012 ficam intactos. O PDF v2 referido na conversa não está acessível no caminho anexado nesta sessão; esta entrega usa os contratos SQL/documentação existentes e os requisitos atuais do fundador. As restrições históricas do contrato CORE_C04_CONTRACT descrevem a missão anterior; a missão atual autoriza a avaliação configurável por indicador, sem autorizar uma conclusão global da promessa.

## Operações reais

Em `/app/casos`, selecionar um cliente abre **C04 · Value State configurável**. O administrador escolhe um indicador outcome de um perfil aprovado ou superseded, regista apenas os factos que possui e guarda uma versão. Campos desconhecidos podem ficar vazios; `pending_fields` identifica e persiste as pendências imediatamente, sem depender de um pacote C03. Promessa/ref, capacidade do plano/ref e objetivo do cliente/confirmação são campos separados; nenhum é preenchido pelo sistema a partir dos outros. A revisão humana da compatibilidade exige referência documental. Não há interpretação automática de texto nem contacto com clientes.

Cada cliente/indicador tem uma sequência de versões imutáveis. Uma revisão parte da última versão e preserva as anteriores, incluindo documentos, meta, regras e perfil histórico. Outro perfil pode ser ligado numa revisão pela RPC; a interface desta primeira versão mantém o perfil ao copiar uma revisão. Uma migração de perfil pela interface fica para um bloco posterior.

`save_c04_configuration` exige admin, operation UUID e versão anterior esperada; repetição idêntica devolve o mesmo ID, alteração do pedido com o mesmo UUID falha. A UI conserva o UUID em repetições do mesmo formulário durante a sessão. `evaluate_c04_configuration` exige admin/operator e reutiliza o resultado para configuração + pacote + algoritmo. Leitores apenas consultam. As duas tabelas têm RLS por membership, FKs compostas por empresa/cliente, proibição de escrita direta, triggers de imutabilidade e auditoria com auth.uid(). O bloqueio de revisão segue tenant → configuração; configurações de perfil aprovado/superseded referenciam definições estáveis.

## Semântica `c04-numeric-v1`

A configuração explicita unidade, fonte, agregação C02, comparador (`lt/lte/gt/gte/eq`), meta numérica, início admissível da observação, prazo e quantidade N de janelas. Não há valores por omissão. A regra desta versão é **cada uma das janelas current_1…current_N do C02 satisfazer a comparação**. Não é média entre janelas ou metas. `current_1` é a janela mais recente, conforme o C02 existente. A quantidade disponível e as regras de cobertura/cadência/denominador são as do perfil histórico aprovado; pedir mais janelas produz insuficiência. Outras formas de período/agregação de objetivos não são aproximadas.

A RPC usa o snapshot de um indicador C03, nunca recebe medições/resultados calculados pelo browser. Exige perfil exato, C02 v2/C03 v1, classificação outcome, unidade/agregação compatíveis, indicador C03 completo e cada janela suficiente, na fonte exata, iniciada depois ou no início admissível e terminada até o `as_of` e o momento da avaliação. A integridade C03, por si só, não comprova o objetivo. Uma fonte errada, período insuficiente ou documentação do objetivo ausente produz avaliação inconclusiva. Evidência suficiente antes do prazo produz `pending_deadline`; depois do prazo, `achieved` ou `not_achieved`. A data de referência é o `as_of` guardado, não a passagem posterior do relógio. Para reavaliar outro período cria-se outro pacote C03; avaliações antigas nunca são recalculadas.

Compatibilidade documental (`compatible/contradiction/missing_documentation/not_checkable`) é separada do resultado medido. Contradição documentada tem referência humana; incompatibilidade de perfil/unidade/agregação também é registada. Uma meta pode ser atingida com plano não documentado ou contradição documental: isto **não declara promessa cumprida**. `promise_fulfillment=not_determined` e `causality=not_established` são explícitos. As pendências e os motivos ficam no resultado persistido. Um indicador vazio/contraditório não bloqueia outro indicador independente, mesmo no mesmo pacote.

## Integração com o Core e fronteira de produto

Cada avaliação contém `core_disposition`: `configuration_review` para contradições; `needs_information` para documentação pendente/não verificável, insuficiência ou prazo pendente; `assessment_available` para revisão de uma avaliação suficiente e documentada. Trata-se de uma entrada persistida para coordenação humana no Core, visível em Casos. Não é um novo caso nem uma autorização de execução. Não há score global, combinação de metas, inferência de causalidade, abertura/fecho automático, promessa universal de valor ou reclassificação histórica. Essas políticas comerciais continuam pendentes de decisão. Resultados e configurações anteriores continuam consultáveis.

`flowreports-demo-v1`, tabelas cw_* e RPCs do piloto permanecem intactos e separados. C05–C10 ainda funcionam exclusivamente com o piloto. O novo C04 não cria um caminho geral de intervenção ainda não aprovado.

## Executar e verificar

- Aplicação existente: seguir `docs/MVP_RUNNING.md` para ambiente exclusivamente local/descartável. O arranque aplica o journal completo, incluindo 0013; não apontar ferramentas a uma base hospedada. Selecionar um cliente em Casos e seguir o painel configurável.
- Sem 0013 instalada, o painel mostra erro real de indisponibilidade; não simula persistência. A entrega não aplica nada ao backend hospedado. A instalação posterior da 0013 é uma operação separada.
- CI browser: C01–C03 reais → 0012 → casos/piloto/histórico sintético → 0013. As duas migrações são verificadas contra hashes de todas as linhas e grants das tabelas anteriores numa base não vazia. A instalação nova segue o journal normal.
- `python3 scripts/mvp/review-database.py --c04` verifica versões, metas diferentes do piloto, repetição/conflito, prazo, insuficiência/documentos, indicadores independentes, superseded profile, papéis reais, RLS, auditoria e casos intactos. Usa os mesmos guards de base descartável do teste anterior e termina com rollback. Exige fixtures `seed.mjs` e `mvp-seed.mjs`.
- `npx playwright test` em `e2e/`: novo teste C04 usa login real, guarda configuração e avaliação, recarrega a aplicação, cria revisão com outra meta e verifica os dois resultados históricos. Testes anteriores continuam ativos. `bun run test`, `bun run --bun tsc --noEmit`, `bun run build` verificam regressões.

Limites de interface: listagens até 100 entradas, sem paginação nesta primeira versão; os registos adicionais continuam persistidos e acessíveis por RLS. O bloco não extrai documentos, recolhe confirmação ou escolhe critérios comerciais pelo utilizador. Nenhum dado sintético é instalado pela migração.
