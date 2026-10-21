# Missão 20.3 — engenharia de valor integrada

Base: `main` `49354db39939d0f4bf828d7a2acaf5d26a656a1f`, com 20.1 e 20.2 integradas. Ensaio limpo de 2026-10-21, sem reutilizar as medições das missões anteriores. Somente testes, fixtures e documentação; nenhuma alteração à lógica C01–C10 ou migração.

## Critérios definidos antes dos envios

Autoridade: [C04 configurável](C04_CONFIGURABLE.md), contratos C01/C02/C03 e funções das migrações 0000–0027. [Plano executável](../e2e/integrated-value-plan.json) contém os dez resultados esperados, documentos sintéticos, regras e sete provas adicionais. O teste guarda os objetivos humanos antes de ingerir qualquer medição.

Empresa SaaS fictícia **ReportPilot**; dez clientes com objetivos de duração do relatório (`cycle_minutes`, min, menor é melhor). O cliente 10 tem também entrega (`delivery_pct`, %, maior é melhor), com avaliação independente. Pro oferece automação diária; Starter oferece somente CSV manual semanal. A promessa sintética descreve automação diária e objetivos individuais confirmados, sem garantia universal. Referências `fixture://` são documentos sintéticos declarados, não certificações externas. A incompatibilidade Starter/promessa é uma revisão humana explícita e referenciada.

C02 `c02-v2`: média, cadência diária, duas janelas correntes de dois dias, referência de dois dias, cobertura mínima 100%, denominador mínimo 2. Deterioração de duração exige **ambas** as janelas >150 min e referência sem deterioração; entrega exige ambas <95%. Baselines fixas: 100 min e 98%. `as_of` e prazo em UTC à meia-noite do dia do ensaio; intervalos `[início,fim)`. C04 `c04-numeric-v1` exige que **cada** janela selecionada satisfaça a meta, sem média entre janelas. `current_1` é a mais recente.

## Dez clientes: esperado versus obtido

Médias na ordem **anterior → mais recente**, em minutos. Todas as expectativas coincidiram com os resultados persistidos. `complete` em C03 significa evidência íntegra, sem implicar objetivo atingido.

| Cliente / cenário | Médias e meta individual | C02 esperado = obtido | C03 esperado = obtido | C04 esperado = obtido |
|---|---|---|---|---|
| 01 · Objetivo atingido | 55 →50; ≤60 | `no_deterioration` | `complete` | `achieved`, `compatible` |
| 02 · Melhoria sem meta | 80 →70; ≤65 | `no_deterioration` | `complete` | `not_achieved`; melhoria descritiva de 30% face à baseline |
| 03 · Deterioração | 160 →170; ≤90 | `deterioration_candidate` | `complete` | `not_achieved` |
| 04 · Oscilação | 160 →50; ≤60 | `no_deterioration` | `complete` | `not_achieved`: uma janela falha a meta |
| 05 · Dados insuficientes | 50 →40; ≤55; cobertura recente 50% | `insufficient_data` | `insufficient` | `inconclusive`, `needs_information` |
| 06 · Documentação incompleta | 50 →45; ≤50; confirmação do objetivo ausente | `no_deterioration` | `complete` | `inconclusive`, `missing_documentation` |
| 07 · Promessa versus plano | 50 →45; ≤60; Starter incompatível declarado | `no_deterioration` | `complete` | `achieved` numérico + `contradiction` + `configuration_review` |
| 08 · Medição atrasada | 55 →45; ≤55; cobertura 50% →100% após chegada | `insufficient_data` → `no_deterioration` | `insufficient` → `complete` | `inconclusive` → nova avaliação `achieved` |
| 09 · Correção | 55 →85; ≤60; correção 85→15 produz média recente 50 | `no_deterioration` nas duas versões | `complete` nas duas versões | `not_achieved` → nova avaliação `achieved` |
| 10 · Indicadores independentes | Duração 55→50, ≤60; entrega 90→92%, ≥95% | duração `no_deterioration`; entrega `deterioration_candidate` | ambos `complete` | duração `achieved`; entrega `not_achieved`, sem score global |

Nos clientes 08 e 09, os envios adicionais ocorreram **depois do cutoff** original. Novas análises/pacotes apontam `revision_of` para os anteriores; análises, referências e avaliações originais continuam idênticas. A observação corrigida continua armazenada e a referência superseded liga-a à correção. Não houve UPDATE de medições.

## Evidência técnica e segurança

Execução local: **662 asserções integradas** e **252 verificações SQL/RLS** (permissões 67, C01 35, C02 70, C03 40, C04 40), todas aprovadas. [Resumo persistido](INTEGRATED_VALUE_MISSION_20_3_RESULTS.json) contém esperado/obtido e IDs. Os números correspondem exclusivamente a esta execução.

- PostgreSQL 17 novo em tmpfs; GoTrue com password grants confirmados; PostgREST real e C01 HTTPS com certificado verificado. Quatro utilizadores reais: admin, operator, viewer e admin externo. Dez clientes pertencem à empresa SaaS; a segunda empresa é apenas controlo de isolamento.
- **14 pedidos C01**, **78 apresentações de medições aceites**, **66 observações únicas persistidas**, **12 reapresentações idempotentes**, **0 rejeitadas**. Seis linhas são repetição do mesmo pedido e seis usam observation keys iguais num novo pedido. Provas negativas de configuração/autorização são distintas de medições rejeitadas. Não confundir com as 18 observações do ensaio antigo da 20.1.
- **13 análises C02**, **13 pacotes C03**, **83 referências C03**, **19 configurações C04**, **22 avaliações C04**. Cálculos/cobertura reconstruídos das observações; IDs exatos por janela; fonte, unidade, cliente, perfil, cutoff, payload hashes e correções preservados. [Verificador SQL independente](../e2e/c03-verify-content.sql) reconstrói os 13 hashes de conteúdo sem chamar a construtora.
- Quatro chamadas concorrentes iguais ao guardar configuração, construir evidência e avaliar objetivo produzem um único resultado. Repetição C01/C02/C03/C04 idempotente; operation ID com meta alterada e revisão obsoleta rejeitados. Regressões C03 incluem construção inválida e rollback sem pacote parcial.
- Sete provas adicionais: prazo futuro → `pending_deadline`; plano ausente → meta numérica `achieved` e `missing_documentation`; revisão humana `not_checkable`; três janelas quando só duas existem → `inconclusive`; fonte errada → `inconclusive`; unidade errada → `contradiction`/`inconclusive`; revisão humana explícita de uma janela no cliente 04 → `achieved`, preservando o resultado original de duas janelas. Critérios originais não foram mudados para converter o cenário em sucesso.
- Perfil aprovado v2 com limiar explícito: observações compatíveis reutilizadas pelo fingerprint, nova análise/pacote/configuração referem v2. Configuração v1 com pacote v2 é `inconclusive`/`contradiction` (`historical_measurement_configuration_mismatch`). Perfil v1 e resultados anteriores permanecem intactos.
- HTTP e SQL com `authenticated`/`anon`: viewer consulta mas não avalia; somente admin guarda; admin/operator avaliam; outsider não vê dados da empresa; pacote de outro cliente rejeitado; escrita direta bloqueada, inclusive mutação do histórico pelo owner. SQL sempre revertido. Auditoria identifica utilizadores JWT reais; medições C01 identificam a credencial de integração.
- Hashes de **22 tabelas não envolvidas**, incluindo C05–C10, permanecem iguais. C01 não inicia análises; C02/C03 não iniciam C04; nenhuma etapa abre casos ou intervém. Avaliações explicitam `causality=not_established`, `promise_fulfillment=not_determined`, `automatic_case_transition=false`.

Artefacto Actions `integrated-value-<run>-<attempt>`: `integrated-value-results.json` (todas as asserções), `integrated-value-evaluations.json` (observações sintéticas, referências/pacotes C03, configurações e avaliações C04, versões/run/cutoff/hashes), pedidos C01 e logs SQL. Exclui palavras-passe, tokens, certificados privados e `.env`. Retenção de três dias conforme o workflow existente; cenário e resumo local permanecem no repositório.

## Reprodução independente

GitHub Actions: job **C01 to C04 / ten SaaS customers** em [browser-e2e.yml](../.github/workflows/browser-e2e.yml). Runner/base novos; não depende de fixtures browser, 20.1 ou 20.2. O job browser existente conserva auditorias, regressões unitárias/browser, tipos e build. CI final e SHA ficam ligados no PR.

Local (Linux, Docker, Python 3.12+, psql, OpenSSL, Bun 1.3.0): checkout isolado sem `.env`, portas locais 5432/54321/54443 livres. Nunca usar credenciais ou endereços hospedados.

```bash
export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=postgres PGDATABASE=cw_e2e
export PGPASSFILE=/dev/null PG_CONTAINER=cw-mvp-db CW_LOCAL_MVP=1
docker run -d --name cw-mvp-db --label centerway.disposable=mvp \
  -p 127.0.0.1:5432:5432 -e POSTGRES_USER=postgres -e POSTGRES_DB=cw_e2e \
  -e POSTGRES_HOST_AUTH_METHOD=trust --tmpfs /var/lib/postgresql/data postgres:17
# Aguardar pg_isready antes do arranque.
python3 e2e/start_backend.py --local-mvp
python3 e2e/integrated-value.py
python3 scripts/mvp/stop-local.py
```

Executar a limpeza também após falhas (`if: always()` no CI). O teste recusa bases sem nome, labels, tmpfs e bindings locais esperados e exige zero clientes existentes. Login, tenants, membership, perfis, objetivos e medições usam operações autorizadas. SQL owner é usado para verificação e regressões revertidas, não para fabricar resultados de negócio.

## Defeitos e limites

**Nenhum defeito de produto encontrado.** Nenhuma mudança à lógica C01–C04 foi necessária; C05–C10 intactos. Sem Lovable, Supabase hospedado, publicação ou merge.

1. Melhoria relativa é cálculo descritivo; não existe enum C04 de “melhoria”. A melhoria de 30% não implica meta atingida.
2. Compatibilidade documental é declaração humana referenciada. C04 não interpreta texto, deteta semanticamente contradições nem certifica documentos externos. Comprova-se a distinção/preservação dos estados declarados, não deteção automática de contradições.
3. Não existe política de cumprimento global da promessa, pesos ou agregação entre indicadores. Pedidos com esses critérios ou agregação não suportada são rejeitados.
4. `c04-numeric-v1` avalia cada janela C02 selecionada; não aproxima períodos arbitrários ou média entre janelas. Insuficiência, documentação ausente e prazo pendente são resultados legítimos.
