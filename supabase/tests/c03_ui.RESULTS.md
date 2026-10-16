# C03 UI — resultados

Escopo: painel "Pacote de evidência (C03)" no detalhe do cliente, sobre o servidor c03-v1 (migration 0010). Sem SQL novo, sem migrations, sem C04–C10, nada publicado.

## Histórico
- 2026-10-16, commit 8595a3f: primeira versão (7 testes controlados).
- 2026-10-16, revisão independente de 8595a3f: corrigidos 5 problemas (abaixo). Base desta correção: main 46b83e6.

## Correções após revisão
1. **Guard de resposta tardia.** Identidade tenant+subject+run e geração (`gen`) capturadas no clique e passadas como variáveis da mutação. A geração muda em cada troca de tenant/cliente/análise e na desmontagem (cleanup do efeito). `onSuccess` exige mesma identidade, mesma geração, componente vivo e tenant ainda ativo; `onError` exige mesma identidade/geração/vivo. Invalidações usam sempre o tenant/run capturados, nunca os da closure nova. Guard pré-pedido (`assertActiveTenant`) mantido. O botão só mostra "a montar" no contexto que o iniciou. No detalhe do cliente, a análise selecionada vive num componente com `key` tenant+cliente, e o painel C02 ignora uma seleção que não pertença à lista de análises do cliente atual.
2. **Pacote histórico.** Consulta direta `c03_bundles` por tenant+subject+run (query key inclui o run); já não depende dos 50 pacotes mais recentes do cliente.
3. **Contrato visível.** Cada referência abre um detalhe acessível por toque (mobile) com papel, id da observação, indicador, valor (texto como dado), fonte, janela UTC `[início, fim)`, observado/recebido UTC, corte do pacote, `corrects_observation_id`, `superseded_by` e hash completo. Resumo histórico por indicador só a partir do snapshot guardado (estado C02, classificação, baseline, gap, motivos C02); ausência aparece como "não registado", nunca 0. Contagens em falta no resumo aparecem como "?". `revision_of`, id do pacote e id da análise mostrados por extenso.
4. **Testes completados** (abaixo).
5. **Documentação** corrigida (roadmap, readiness, este ficheiro).

## Testes — red/green (testes controlados com pedidos simulados, não backend real)
Ficheiro: `src/test/evidence-panel.test.tsx` (18 testes). Corridas contra a versão antiga do painel (cópia de 8595a3f) e depois contra a corrigida.

Red (versão antiga): `bunx vitest run src/test/evidence-panel.test.tsx` → 12 falharam / 6 passaram.
- Falhas por comportamento de corrida (sentinela: callback correu e invalidou tentativas antes da asserção negativa): toast de sucesso após troca de tenant (rerender do Provider), após desmontagem e em A→B→A; nota de recusa e nota de erro (onError sem guard) mostradas no tenant novo.
- Falhas por funcionalidade em falta: snapshot histórico, contagem desconhecida ≠ 0, pacote de análise antiga fora dos 50 recentes, paginação com detalhe por referência, detalhe completo da referência, invalidação com chave do run capturado.
- Passou já na versão antiga (esperado): resposta tardia após troca só de análise (o guard antigo cobria esse caso), e os testes de estados/viewer/rejected/failed/reused/guard pré-pedido.

Green (versão corrigida): 18/18.

Cobertura: três estados e semântica; snapshot só guardado; contagens ausentes; pacote de análise antiga com filtros tenant/subject/run verificados no pedido; paginação com `order(ordinal asc)`, `range(50,99)` e filtros tenant+bundle+indicator verificados, esperando os dados da página 2 (página 1 não fica visível como página 2 durante o carregamento); detalhe da referência; budget excedido; viewer sem botão nem RPC; built (toast único, invalidações com tenant/run capturados); rejected e failed como JSON sem error (código seguro, tentativas refeitas, sem toast de sucesso); reused (info); guard pré-pedido (RPC não chamada); corridas com RPC diferida: troca de tenant (built, rejected, erro), troca de análise, desmontagem, A→B→A.

## Comandos e resultados finais
- `bunx vitest run` — 6 ficheiros, **55/55**.
- `bunx tsgo --noEmit` — 0 erros (6 erros de tipos introduzidos durante esta correção foram corrigidos antes do fim).
- Build da pré-visualização: OK.

## Browser real
Neste bloco não foi aberta nova sessão de browser. A verificação autenticada anterior (dev local ligado ao backend real) viu empresas sem clientes: com 0 clientes, o detalhe do cliente — onde está o painel C03 — não é alcançável, por isso **o painel C03 nunca foi renderizado no browser real**. Todos os cenários do painel são testes controlados.

## Limitações
- Sem dados reais de C02/C03; nada foi inventado no backend.
- Reset da análise selecionada ao mudar de cliente é feito por `key`; coberto por inspeção de código, sem teste de rota dedicado.
- A mutação do painel C02 ("Analisar agora") não recebeu o mesmo guard de geração; fora do escopo C03 UI.

## Fecho da revisão
- Ajustes apenas de texto após a validação 55/55: ausência de `revision_of` significa sem pacote anterior associado, não necessariamente o primeiro pacote do cliente; falha na montagem preserva a tentativa de auditoria; código `c02_input_hash_mismatch` traduzido.
- A lista apresenta as últimas 20 tentativas; o seletor C02 existente apresenta as 50 análises mais recentes. O histórico completo permanece na base de dados; a paginação completa desses dois históricos ainda não foi implementada.
- Créditos reportados pela API Lovable nesta continuação: 3,7 (verificação autenticada), 8,0 (primeira interface) e 13,7 (correções e validação), total 25,4. Estes valores não são o saldo do workspace.
