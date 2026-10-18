# Core e percurso operacional configurável — individual-review-v1

Base: main `ee30c7d`, com 0012–0013 instaladas e metadados reconciliados. Nenhuma dessas migrações ou snapshots foi reescrita. A 0014 é aditiva; o journal recebe apenas a entrada seguinte e o snapshot novo encadeia o ID reconciliado da 0013. O schema declarativo Drizzle continua vazio, como na base existente. O manual PDF não está acessível nesta sessão; a referência são os contratos existentes e esta missão autorizada.

## Contrato funcional limitado e explícito

Um caso acompanha **um indicador e uma versão histórica C04**, com um ciclo de intervenção humana. Não há score de cliente, agregação de metas, conectores, execução remota, contacto automático ou inferência de causalidade. O FlowReports continua nas tabelas/RPCs anteriores, sem alterações. O novo percurso utiliza `cw_operational_cases` e `cw_operational_events`, evitando reinterpretar contratos históricos do piloto.

O Core recebe C04 através das avaliações persistidas e da lista de entradas em Casos, incluindo pendências. A abertura não consulta o sinal C02: uma meta pode não estar demonstrada apesar de `no_deterioration`. C04 ainda utiliza os pacotes C03 e os snapshots de medição existentes; esta entrega remove a dependência de um **sinal candidato**, não substitui a cadeia de evidências por uma fonte nova.

Para abrir, um administrador declara elegibilidade, fundamento, referência documental, critérios de abertura e de encerramento específicos. A avaliação deve ser conclusiva, documentalmente compatível, suficiente e da última configuração desse indicador. Podem ser selecionadas avaliações `achieved` ou `not_achieved`: o resultado isolado não decide a elegibilidade comercial. Informação inconclusiva, prazo pendente, contradição ou falta de documentação ficam visíveis em C04 e não originam intervenções. A declaração humana é obrigatória; não existe política universal de abertura embutida.

Ao abrir, aceita-se explicitamente a fronteira técnica de `individual-review-v1`: objetivo histórico demonstrado após execução, janela válida, suficiência, ausência de novas pendências relevantes e revisão humana dos critérios específicos. A configuração fica fixada; uma revisão C04 posterior bloqueia nova preparação/execução e o fecho, mantendo o caso aberto. Resolver/migrar o contrato de um caso existente exige um próximo bloco de produto: nesta versão usa-se uma nova avaliação e decisão humana para outro caso. Não há alteração automática dos estados históricos.

## Transições e provas

| Operação | Guarda e resultado |
|---|---|
| Abrir | Admin, avaliação elegível e decisão documentada → investigação. Um caso por avaliação. |
| C05 investigar | Admin/operator; regista `confirmed`, `hypothesis` ou `insufficient`. Hipótese/insuficiência não permitem plano. Confirmação humana exige observação C01 deste cliente/empresa, não corrigida, e referência documental. |
| C06 planear/rever | Impedimento confirmado; ação, justificação, condições de sucesso, limitações, reversão (ou razão documentada de ausência), referência e janela em segundos → aguarda autorização. Revisão invalida a autorização anterior. |
| C07 autorizar/renovar | Admin, plano atual e validade futura explícita com fuso. Não há prazo universal de 24h. |
| C07 executar | Admin/operator, autorização não expirada, mesmo plano, aprovador ainda admin, provas C05 não corrigidas → execução humana registada e início C08 no relógio do servidor. |
| C08 observar | Janela do plano validada no servidor, entre 1 e 31.536.000 segundos inteiros. São limites técnicos desta versão, não recomendações ou defaults comerciais. A janela deve ser escolhida de acordo com a cadência do indicador. |
| C09 comparar | Janela terminada, novo pacote deste cliente, mesma configuração C04 histórica. Todas as janelas devem começar após a execução e a última terminar depois do mínimo C08. C04 é avaliado no servidor; o C09 persiste comparação e insuficiência temporal separadas do resultado C04. |
| C10 decidir | Admin e C09 persistido; revisão documentada dos critérios e contradições. Fecho apenas com objetivo atingido, suficiência pós-execução, critérios declarados satisfeitos e ausência de contradição material, revisão C04 posterior ou dados relevantes ainda não cobertos. Caso contrário → `remain_open`; pode repetir C09/C10. |

As referências documentais exigem HTTPS ou URN. O servidor valida sintaxe e ligações internas; **não consulta nem certifica o conteúdo de um documento externo**. C05 guarda snapshots das observações (ID, fonte, unidade, data, hash e valor) e a interpretação humana. A existência de uma observação não estabelece automaticamente impedimento ou causalidade: a pessoa assume a conclusão e os seus limites. Correções posteriores invalidam preparação/execução antes de agir.

C06 preserva condições específicas em texto e referência, revistas por administrador em C10. Só a meta numérica histórica, suficiência e regras temporais são verificadas automaticamente; não se finge avaliar condições textuais. O recibo C07 nunca prova recuperação de valor. C09/C10 guardam `causality=not_established`.

C10 verifica novos dados do indicador, denominador associado e chaves usadas como prova C05. Dados importados após o corte C09 ou observados após o período efetivamente avaliado impedem fecho. Recriar um pacote com corte mais recente mas período antigo não esconde uma nova medição fora desse período. Indicadores independentes não bloqueiam este caso nem recebem um resultado global.

## Segurança e histórico

Tabelas com RLS de leitura por membership, sem escrita direta para authenticated/anon; FKs compostas por empresa/cliente, eventos imutáveis, identidade/contrato do caso imutáveis e auditoria por triggers com `auth.uid()`. Apenas estado/versão são projeções mutáveis. RPCs SECURITY DEFINER verificam papéis e todos os IDs. Helpers privados sem EXECUTE para clientes.

A 0014 mantém a semântica `c04-numeric-v1` e acrescenta apenas o bloqueio inicial de tenant à RPC de avaliação C04, evitando inversão com Core/FKs; avaliações guardadas não são alteradas. Bloqueios seguem tenant → caso → configuração C04; C01 e alterações de perfil também bloqueiam tenant. Cada comando exige versão esperada, UUID e hash calculado no servidor. Repetição exata devolve o evento original mesmo após avançar estado; UUID com outro pedido falha. Não se repete execução com outro UUID, nem se reutiliza autorização de um plano substituído. Replays não dispensam a autorização do papel atual. Abertura também é idempotente; outro UUID para a mesma avaliação informa que o caso já existe.

A interface usa o cliente autenticado, query keys por tenant, guards de tenant capturado e desmontagem ao mudar empresa/cliente/caso. Entradas e casos são separados do piloto na mesma página existente.

## Abrir e testar

Na branch desta entrega, com Docker, Python 3.12+, psql, Node 22 e Bun 1.3:

```sh
python3 scripts/mvp/start-local.py
```

A receita exporta HEAD sem `.env`, cria exclusivamente uma base nova descartável em loopback e aplica o journal completo. Abre-se `http://127.0.0.1:5173/app/casos`; as credenciais temporárias ficam apenas no ficheiro privado indicado pelo comando. Escolher a empresa **Atlas SaaS · SINTÉTICO operacional** e um cliente. Configuração e interface C04 continuam disponíveis acima do Core. Para terminar a stack usar `python3 scripts/mvp/stop-local.py`.

Fixtures Atlas usam perfil, indicadores, C01, C02, C03, C04 e login reais, sem `flowreports-demo-v1`. C02 confirma `no_deterioration` no ponto de entrada. O ramo prospective permite C05–C10 com autorização atual e uma janela de 1 segundo explicitamente exclusiva do teste; as medições já existentes são anteriores à execução e C09 fica inconclusivo. O servidor mantém o caso aberto: não se apresenta isso como valor recuperado.

Dois clientes têm **histórico C05–C08 retrospectivo sintético carregado pelo proprietário**, identificado em cada evento e na interface. Não comprova execução/autorização passadas ou espera histórica observada. Permite testar agora, com o relógio real e C09/C10 reais autenticados, o objetivo atingido e o não atingido após uma janela explícita de 3 dias. Não existe RPC de produção que aceite execução retroativa ou encurte a janela.

CI instala 0012 sobre dados C01–C03; 0013 sobre casos do piloto; cria entradas C04 Atlas; instala 0014 sobre essas entradas. Compara hashes das linhas e grants de todas as tabelas anteriores a cada upgrade. Depois carrega apenas o histórico retrospectivo sintético e executa:

```sh
python3 scripts/mvp/review-database.py --operational
cd e2e && npx playwright test
```

A revisão SQL usa JWT claims e papéis reais authenticated/anon e termina com rollback. Cobre entrada sem candidato C02, pendências, estados C05, provas de outro cliente, autorização/revisão/revogação, idempotência, relógio real, insuficiência temporal, objetivos não atingidos, contradição, critérios pendentes, novas medições fora do snapshot, fecho elegível, RLS e auditoria. Os testes de browser usam GoTrue/PostgreSQL/PostgREST reais e exercitam o percurso atual e os dois resultados retrospectivos. Suites anteriores continuam ativas.

## Limites que permanecem

Um ciclo de intervenção por caso; sem reabertura, cancelamento, transferência de contrato, política universal de elegibilidade, catálogo de impedimentos ou avaliador de condições textuais. Aprovador e executor podem ser a mesma pessoa: não se inventa uma regra de segregação ainda não aprovada. Listas limitadas a 100 registos e histórico UI até 500 eventos; persistência mantém todos. O fecho atesta apenas os critérios deste indicador/caso, não cumprimento global da promessa. Nenhuma migração é aplicada ao backend hospedado por esta entrega.
