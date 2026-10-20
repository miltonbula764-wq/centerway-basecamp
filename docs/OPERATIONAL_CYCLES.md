# Continuidade operacional por ciclos — 0021

Um caso mantém a identidade, indicador, avaliação inicial, configuração C04 e critérios de encerramento originais. A migração 0021 permite continuar um `remain_open` com uma decisão humana explícita de administrador, o mesmo papel que já decide C10. Não reabre casos encerrados, altera objetivos ou inicia ciclos automaticamente.

## Contrato

`command_operational_case(..., 'start_cycle', {"reason":"Fundamento documentado", "reference":"urn:empresa:decisao"})` exige:

- Administrador atual da empresa; versão esperada e UUID de operação.
- Estado `remain_open` e última decisão C10 desse ciclo persistida com esse resultado.
- Fundamento não vazio e referência HTTPS/URN, validados como nas decisões anteriores. Referências externas não são consultadas nem certificadas.
- Configuração histórica ainda aplicável: uma versão C04 posterior bloqueia o novo ciclo, sem substituir o objetivo silenciosamente.

O início acrescenta um ciclo e um evento `start_cycle`, muda o estado do mesmo caso para `investigation` e incrementa a versão global. Não cria outro caso. O ciclo seguinte exige nova investigação, plano, aprovação, execução, janela e comparação. Os critérios textuais continuam sujeitos a revisão humana; não há política comercial de continuidade presumida.

Cada ciclo tem UUID, número sequencial, sequência inicial, fundamento, referência, autor, data e ligação à decisão anterior. O ciclo inicial usa o UUID do caso e os dados reais da sua abertura. A migração acrescenta estes metadados numa tabela nova; não reescreve eventos nem casos históricos e não inventa outra decisão.

Os ciclos e eventos são imutáveis. Os intervalos de sequência particionam o histórico; só o ciclo mais recente aceita novas operações. A identidade do caso nunca muda. O bloqueio tenant → caso serializa decisões; restrições únicas impedem colisões de número/sequência. A criação pelo cliente é proibida por grants e RLS.

Todas as consultas de investigação, plano, autorização, execução e comparação do motor existente passam a utilizar o intervalo do ciclo atual. Assim, uma aprovação antiga não pode autorizar outro ciclo. A validade, o plano e o papel atual do autorizador continuam a ser revalidados em C07. C09 compara com o objetivo C04 histórico e exige medições posteriores à execução e janela do ciclo correspondente. Um pacote histórico pode produzir uma comparação inconclusiva; não demonstra recuperação do ciclo seguinte.

O replay de uma operação antiga devolve o recibo original, sem executar novamente ou alterar o ciclo atual. Uma operação diferente com versão antiga é rejeitada. Para esse conflito, o SQLSTATE passa de `40001` para **`PT409` (HTTP 409)**: `40001` representa serialização PostgreSQL e fazia o PostgREST12 repetir indefinidamente um conflito lógico que nunca poderia desaparecer. A mensagem continua `case_version_conflict`; os guardas e o significado da versão mantêm-se. O contrato do piloto FlowReports permanece separado.

## Consulta e interface

`operational_cycle_history` é uma RPC de leitura sob RLS. Valida empresa/caso/ciclo, pagina ciclos por número e eventos por sequência (25 por página na interface, máximo 100). Devolve também os últimos eventos de cada etapa do ciclo selecionado, independentemente da página de histórico, evitando perder uma autorização/execução após muitas revisões.

Em `/app/casos`, o dossier mostra o ciclo atual, identidade e fundamento. Um administrador pode iniciar outro ciclo após C10 manter o caso aberto. É possível selecionar ciclos anteriores e paginar os seus eventos; estes são apresentados apenas para consulta, sem formulários de execução. Respostas tardias são canceladas/descartadas e todas as chaves de cache incluem empresa, caso, versão e ciclo. As operações continuam autorizadas no PostgreSQL.

A Central e o agendador continuam a usar a mesma projeção do Core. O contexto e a janela provêm exclusivamente do ciclo atual, com UUID/número no fundamento. Após iniciar outro ciclo, a orientação regressa à investigação, sem reutilizar a janela ou aprovação anterior. Fotografias de monitorização antigas continuam identificáveis como desatualizadas até serem processadas novamente.

## Migração e integração posterior

Na main inspecionada, a última migração é **0020**. A nova migração é **0021_operational_cycles**, exclusivamente aditiva, com journal acrescentado e snapshot encadeado. Nenhum marcador de reconciliação foi criado.

**Dependência antes do merge/instalação:** a 0020 ainda não está instalada no ambiente hospedado, conforme informado. Esta entrega depende dela; a integração deve aplicar **0020 e depois 0021**. Se a ferramenta gerida reservar outro número entretanto, é necessário reconciliar a numeração no PR antes do merge, preservando 0000–0020. Não aplicar esta migração isoladamente num backend que ainda termina em 0019. Nada foi instalado no backend hospedado por esta missão.

## Validação e execução isoladas

O workflow existente passa a aplicar 0021 sobre dados não vazios e verificar a preservação de linhas/grants anteriores. Mantém as regressões C01–C10, API, equipas, Central e monitorização.

`e2e/operational-cycles.py` usa PostgreSQL17, GoTrue e PostgREST descartáveis: cria um cliente sintético por C01, executa dois ciclos prospectivos completos com janelas explícitas de um segundo e inicia o terceiro por decisão humana. Verifica autorizações independentes, não reutilização de execução, pacotes históricos inconclusivos, replay, concorrência, versões, RLS e paginação. Os testes SQL adicionais são revertidos e distinguem-se dos logins reais. O browser completa o terceiro ciclo, inicia o quarto e verifica navegação histórica e troca de empresa com pedido pendente. Uma prova SQL adicional fecha corretamente um segundo ciclo com evidência suficiente, usando uma fixture retrospectiva explicitamente sintética e revertida; não comprova autorização ou execução histórica real. As fixtures retrospectivas anteriores continuam explicitamente sintéticas.

Para montar a aplicação a partir do commit do PR, usar os requisitos já documentados em `scripts/mvp/start-local.py --monitoring`, que aplica todas as migrações do journal numa base nova. O percurso manual começa em `/app/casos`; após C10 manter um caso aberto, preencher «Core · Iniciar novo ciclo». O Cron não é instalado por esse comando. O workflow é a referência para a campanha automática completa, incluindo os novos testes de ciclos.

Limites: um indicador/configuração histórica por caso, execução humana declarada, condições textuais revistas por humano, sem reabertura de encerrados, sem conectores e sem causalidade automática. A continuidade com um objetivo C04 revisto requer uma decisão de produto posterior; não é autorizada por esta extensão. Não foi feito deploy, acesso à Lovable ou validação no serviço hospedado.
