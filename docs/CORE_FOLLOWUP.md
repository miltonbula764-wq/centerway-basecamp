# Central de acompanhamento — missão 12

A rota `/app/acompanhamento` lê `core_followup_queue` (0015). Base: main `57ec341`, incluindo os ajustes da Lovable. Não depende do PR #11 nem de Codespaces. Não existem alterações no backend hospedado por esta entrega.

A RPC é **SECURITY INVOKER**, confirma membership e mantém RLS em todas as fontes. Só concede EXECUTE a authenticated. Não cria tabelas de estados paralelos, eventos, avaliações, casos, notificações ou intervenções. O relógio é capturado uma vez no servidor por consulta; abrir/atualizar a página não escreve dados.

## Fontes e classificação

- Uma entrada por cliente/indicador configurável: última configuração e última avaliação persistida dessa configuração. Indicadores outcome do perfil aprovado sem configuração também aparecem como informação pendente. Sem perfil/indicador não se inventam eixos: a interface orienta para a preparação existente.
- Cada caso operacional aparece com a identidade, estado, versão do caso e configuração histórica fixada. Uma avaliação de entrada já representada por um caso não é duplicada; uma avaliação posterior independente pode aparecer separadamente. Avaliações antigas continuam nos dossiers, sem inundar a fila atual.
- Contradições/documentação/resultados são lidos do C04. Suficiência não dá elegibilidade automática: a orientação exige decisão documentada de admin.
- Investigação/planeamento, aprovação e execução derivam dos estados e últimos eventos do Core. Antes da execução, configuração revista ou referências C05 corrigidas orientam para revisão. Autorização verifica plano, validade no servidor e papel atual do aprovador.
- C08 em curso mostra `wait_until`. Depois dessa data a fila permite revisão, sem alegar suficiência das medições. C09 insuficiente e C10 remain_open continuam pendentes. Só `closed_resolved` produz encerrado.
- O piloto continua separado, identificado por `flowreports-demo-v1`, com orientação apenas para consultar o seu dossier e contrato específico.

A orientação é leitura: `can_prepare` indica o papel para preparar a revisão, não é um token de autorização nem garantia de execução. A central tem apenas filtros, atualização e ligações. As RPCs operacionais existentes continuam a validar payload, evidências, versão e papel no momento da escrita. Contratos/políticas comerciais não foram alterados.

## Datas, atualização e escala

Prazo C04 e fim de C08 são mostrados apenas quando persistidos. `review_due` usa o relógio do servidor; não é urgência ou SLA. Uma data atingida não recomputa C04 nem muda o Core. Nova configuração, correção de prova C05 ou novas observações relevantes não cobertas pelo snapshot são sinalizadas como desatualização; indicadores independentes não se bloqueiam entre si. Encerramentos históricos permanecem encerrados mesmo que surjam novos dados.

Filtros por nome/referência do cliente, chave do indicador e categoria. Paginação por cursor exclusivo `entry_key`, ordenação lexical C estável por tipo/identidade, limite 1–100 (UI 25), sem score comercial. A consulta devolve mais um registo para identificar próxima página; índices suportam configuração/avaliação e últimos eventos por comando. É uma projeção atual, não snapshot entre páginas: operações concorrentes podem mudar filtros/entradas; atualizar/reiniciar a paginação relê o estado corrente. Não foi feito benchmark de produção com milhões de clientes.

Query keys começam por `["t", tenantId]`; cancelamento por AbortSignal, identidade da resposta validada, desmontagem e remoção de cache ao mudar empresa. Atualização manual, ao voltar ao ecrã/foco e a cada minuto; invalidação após C04/Core. Nada usa o relógio do navegador para permitir transições. Datas exibidas no fuso do navegador.

Ligações para Casos incluem tenant, subject, case/kind ou configuração/avaliação quando existentes. O destino revalida RLS e identidade completa; consulta diretamente registos referenciados fora das antigas listas de 100. Uma ligação de outra empresa não muda silenciosamente a empresa ativa. Não há abertura automática de formulários de execução.

## Executar e verificar numa base descartável

Com Docker, PostgreSQL client, Python 3.12+, Node 22 e Bun 1.3, após commit:

```sh
python3 scripts/mvp/start-local.py --followup
```

A receita existente exporta HEAD sem .env, cria base nova em loopback e aplica o journal, incluindo 0015. O argumento opcional acrescenta **Central SaaS · SINTÉTICO**, 102 clientes e três indicadores independentes (contradição, suficiente e insuficiente); Atlas/FlowReports mantêm-se. Abrir `http://127.0.0.1:5173/app/acompanhamento` e usar as credenciais sintéticas do ficheiro privado indicado no arranque. Nunca usar credenciais hospedadas.

No diretório isolado criado pela receita, com `CW_LOCAL_MVP=1 PGHOST=127.0.0.1 PGDATABASE=cw_e2e`:

```sh
python3 scripts/mvp/review-database.py --followup
```

A revisão SQL usa admin/operator/viewer/anon reais e sempre rollback; cobre 306 entradas, filtros/paginação, isolamento, indicadores independentes, novas evidências, estados C05–C10, validade/revogação de autorização, espera real configurada de 3 segundos, revisão histórica e ausência de escritas em cada leitura. Históricos Atlas retrospectivos são fixtures preexistentes explicitamente fictícias; nunca são criados pela central.

O workflow existente testa upgrade 0015 sobre dados 0000–0014, preservando hashes/grants, e executa a revisão SQL, browser autenticado, regressão, tipos e build. Os testes de UI controlados cobrem respostas tardias e identidade incorreta, separadamente dos testes reais de Auth/PostgreSQL. Resultados e commit efetivamente validados ficam no PR.

A [migração 0021](OPERATIONAL_CYCLES.md) acrescenta continuidade por ciclos independentes no mesmo caso. Limites preservados: um indicador/configuração histórica por caso, condições textuais revistas por humano, sem reabertura, contactos automáticos ou causalidade inferida. Referências externas são documentais; não são consultadas/certificadas pela central. Polimento visual e aplicação posterior da 0015 ao ambiente hospedado pertencem à integração separada.
