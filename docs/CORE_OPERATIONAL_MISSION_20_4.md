# Missão 20.4 — C04 → Core → C05–C10

Base: `main` `f5c277020a36d45aa918c304c85b05c2da58db60` (20.3 integrada). Execução limpa em 2026-10-21, sem dados das missões anteriores. Apenas testes/documentação/workflow; nenhum contrato, critério comercial, relógio, migração ou lógica do produto foi alterado.

## Autoridade e critérios antecipados

Contratos: [percurso operacional](OPERATIONAL_JOURNEY.md), [ciclos](OPERATIONAL_CYCLES.md), [Central](CORE_FOLLOWUP.md), [notificações internas](RESPONSIBILITIES_NOTIFICATIONS.md), [C04](C04_CONFIGURABLE.md) e funções efetivas das migrações 0000–0027. [Plano executável](../e2e/core-operational-plan.json) fixa os oito resultados antes de qualquer envio. Objetivos são guardados antes de C01.

Empresa SaaS **Sentinel**, oito clientes independentes, indicador `cycle_minutes`, minutos, média e cadência diária. Perfil aprovado: duas janelas de um dia, cobertura mínima 100%, denominador mínimo 1, baseline fixa 100, deterioração persistente >150; meta individual ≤60 em **cada** janela. Documentação e elegibilidade são declarações humanas sintéticas referenciadas por URN. O sistema valida sintaxe/identidade, sem certificar documentos externos ou inferir causalidade.

Datas relativas ao dia UTC do teste: entrada C04 em `as_of=-25 dias`, medições 100/95/90 nos dias -28/-27/-26; avaliação posterior em `as_of=-1 dia`, medições nos dias -4/-3/-2. Prazo C04=-30 dias e início admissível=-40. Todas as entradas elegíveis têm `not_achieved`, `compatible`, evidência suficiente e C02 `no_deterioration`: abrir não exige candidato C02. O cliente 07 não tem a medição -26, logo a **avaliação de entrada referenciada** é inconclusiva; avaliações posteriores são registos separados e não tornam essa avaliação antiga elegível. No cliente 08 a contradição documental é explicitamente declarada por revisão humana.

A elegibilidade e os critérios específicos são decisões humanas explícitas, fixadas em `opening_definition`; nenhum limiar foi alterado para produzir fecho. C10 exige meta histórica demonstrada, dados posteriores suficientes, ausência de novas pendências relevantes e revisão humana dos critérios textuais.

## Resultados esperados versus obtidos

Todas as expectativas coincidiram com os resultados persistidos. Os estados abaixo são projeções finais do caso; nenhuma consulta avançou estados automaticamente.

| Cliente | Prova e expectativa antecipada | Obtido |
|---|---|---|
| 01 · Prospectivo | Hipótese/insuficiência não permitem plano; confirmação humana com prova permite preparar e autorizar. Espera real de 3 s; pacote pré-execução não demonstra recuperação. C10 mantém aberto e admin inicia ciclo 2. | `hypothesis`/`needs_information` bloqueados para plano; C09 `inconclusive`, motivo `post_execution_observation_insufficient`; C10 `remain_open`; final `investigation`, ciclo 2, sem autorização herdada. |
| 02 · Prospectivo | Revisão de plano invalida aprovação; aprovação expira naturalmente; perda do papel admin pelo aprovador bloqueia execução; nova aprovação explícita permite recibo humano. | Todos os bloqueios confirmados; prazo de 2 s realmente expirado; perda do papel produz HTTP 403 `approver_no_longer_authorized`; execução liga plano revisto e nova aprovação. Final `waiting_observation`, sem C09/C10 automático. |
| 03 · Prospectivo | Corrigir a observação usada em C05 impede novo plano e execução, apesar de aprovação anterior. | HTTP 400 `investigation_evidence_changed`; observação superseded não pode ser reconfirmada. Projeção final `approved`, mas execução bloqueada e revisão necessária; nenhuma execução registada. |
| 04 · Retrospectivo sintético | Depois de janelas válidas com 50/45 min, contradição material ou critérios humanos pendentes mantêm aberto; revisão explícita completa permite fecho. | Dois `remain_open`, depois `closed_resolved`, motivos vazios. Novo ciclo rejeitado. Correção posterior 45→46 não apaga nem reabre o encerramento histórico. |
| 05 · Retrospectivo sintético | Janelas 85/80 min não cumprem meta; C10 mantém aberto; nova decisão humana pode iniciar ciclo, com conflito entre decisões concorrentes. | `remain_open`, motivo `objective_not_demonstrated`; concorrência produz HTTP 200/409 `PT409`; final `investigation`, ciclo 2. Aprovação do ciclo anterior não autoriza execução. |
| 06 · Retrospectivo sintético | Correção tardia após C09 atingido bloqueia fecho; novo pacote reflete 45→85 e não cumpre meta; contrato posterior não pode migrar silenciosamente o caso. | Primeiro `remain_open` com `new_relevant_evidence_requires_comparison`; nova análise/pacote/avaliação `not_achieved`; último `remain_open` por objetivo não demonstrado. Nova configuração documental bloqueia `start_cycle`; histórico original intacto. |
| 07 · Entrada inconclusiva | C04 de entrada `inconclusive`/insuficiente não abre caso. | HTTP 400 `evaluation_requires_information`; zero casos desse cliente. |
| 08 · Entrada contraditória | C04 de entrada `contradiction` não abre caso. | HTTP 400 `evaluation_requires_information`; zero casos desse cliente. |

**Totais:** seis casos abertos por RPC autenticada; **um encerrado e cinco abertos**; duas entradas bloqueadas; oito ciclos e 51 eventos. Dos cinco casos abertos, dois estão em nova investigação, um aguarda comparação, um tem execução bloqueada por prova corrigida e um permanece em `remain_open`.

## Prova prospectiva versus retrospectiva

**Prospectiva real:** clientes 01–03, abertura e comandos via GoTrue/PostgREST reais. Duas execuções humanas declaradas de um checklist sintético, sem ação externa. O servidor fixa `executed_at` e `wait_until`; espera de três segundos testada naturalmente. Um payload com `executed_at` fornecido pelo chamador é rejeitado mesmo com autorização válida. Prazo de autorização de dois segundos expira naturalmente. Nenhum relógio foi congelado, adiantado, substituído ou simulado.

A cadência diária exige janelas inteiramente posteriores à execução. Aguardar três segundos comprova o bloqueio temporal, **não comprova recuperação nem permite encerramento prospectivo legítimo**. O caso 01 tem C04 posterior numericamente atingido sobre dados anteriores à execução; C09 corretamente distingue isso de evidência pós-execução e mantém o caso aberto. No caso 02 a projeção `waiting_observation` persiste até uma operação autorizada de comparação, mesmo depois de passar o prazo.

**Retrospectiva sintética:** clientes 04–06. Aberturas reais por RPC e C01–C04 fundamentados permanecem intactos. [Loader exclusivo de teste](../e2e/core-retrospective-history.sql) acrescenta quatro eventos fictícios C05–C08 por caso e monta somente a projeção correspondente. Todos os 12 eventos contêm `fixture=synthetic_retrospective_history` e aviso explícito; a execução fictícia é em -10 dias e o fim de observação em -7 dias (3 dias). Os timestamps de execução nos detalhes são dados de fixture, não relógios alterados ou execução retroativa aceite pela API. Nenhum trigger é desativado. Os C09/C10 subsequentes são RPCs autenticadas reais, no relógio atual, contra medições C01 e pacotes C03 reais com janelas posteriores à data da fixture.

Essa prova demonstra as guardas de comparação/fecho sobre um histórico sintético conhecido. **Não demonstra autorização histórica, ação passada, espera histórica observada ou um ciclo prospectivo completo com recuperação.** A auditoria dos eventos HTTP é verificada separadamente dos eventos owner-loaded.

## Segurança, concorrência e integridade

- PostgreSQL 17 novo em tmpfs, loopback; GoTrue real com cinco contas/password grants confirmados (admin, segundo admin/aprovador, operador, leitor e admin de outra empresa), PostgREST e C01 HTTPS com certificado verificado. Nenhum backend hospedado, Lovable, deploy ou merge.
- **13 pedidos C01**, **62 apresentações aceites**, **50 medições únicas**, **12 reapresentações idempotentes**, **zero medições rejeitadas**. Provas negativas de operações Core são contabilizadas separadamente: 55 rejeições HTTP esperadas.
- **17 análises C02**, **17 pacotes C03**, **9 configurações e 17 avaliações C04**, seis casos, oito ciclos, 51 eventos. Os 17 hashes C03 são reconstruídos por SQL independente. Caso, cliente, empresa, configuração histórica e ator JWT são verificados em cada comando.
- Quatro chamadas concorrentes iguais para abertura, investigação confirmada, execução, início de ciclo e decisão de fecho persistem um único resultado. Dois UUIDs diferentes para iniciar ciclo com a mesma versão produzem uma operação e um conflito lógico HTTP 409, sem repetição infinita de serialização.
- Repetição exata devolve recibo original, inclusive de ciclo anterior. Payload alterado com mesmo UUID, versão obsoleta, dupla execução e nova abertura da mesma avaliação são rejeitados atomicamente. Viewer não recebe permissão através de replay.
- Plano exige C05 confirmado, evidência não corrigida, referência e janela explícita válida. Revisão invalida autorização anterior. C07 verifica prazo e papel atual do aprovador no banco, mesmo com JWT ainda válido; somente admin aprova/decide/inicia ciclo. A renovação após restabelecimento do papel é uma decisão explícita neste teste.
- IDs de observação, pacote e ciclo de outro cliente são rejeitados. Leitor consulta mas não comanda; admin externo não lê dados da empresa; IDs de caso de outra empresa falham. Escrita direta nas três tabelas operacionais e alterações owner de identidade/eventos/ciclos são bloqueadas. SQL/RLS usa `authenticated`/`anon`, sem service role, sempre com rollback.
- Todas as linhas C01–C04 pré-existentes, os 12 eventos de fixture e identidades originais dos casos são comparadas integralmente após as operações. Correções preservam a observação anterior, e análises/pacotes novos referenciam `revision_of`. Paginação restitui integralmente eventos anteriores; Central e consultas de histórico não escrevem dados nem avançam estados.
- **19 tabelas não envolvidas**, incluindo piloto, objetivos, notificações entregues e revisões programadas, permanecem com hashes idênticos. Exceção contratual verificada: `notify_plan` cria **sete trabalhos pendentes**, exatamente um por plano real ou sintético; zero tentativas ou entregas. Trata-se da outbox interna existente, não intervenção ou ação externa. Nenhum processador de notificações foi acionado.
- Recibos guardam `execution_type=human_record` (ou identificador retrospectivo sintético) e `value_recovery=not_proven`. C05/C09/C10 explicitam `causality=not_established`. Não há promessa global cumprida, certificação externa ou recuperação deduzida de um recibo.

## Testes e reprodução

Execução local aprovada: **570 asserções integradas**, incluindo 55 rejeições HTTP esperadas, e **265 verificações SQL/RLS**: permissões 67, C01 35, C02 70, C03 40 e Core 53. [Resumo persistido](CORE_OPERATIONAL_MISSION_20_4_RESULTS.json) contém esperado/obtido, identidades, motivos e resultados. CI final/commit são ligados no PR.

Job independente **Core and C05-C10 / eight independent scenarios**, em [browser-e2e.yml](../.github/workflows/browser-e2e.yml), recria a base vazia e o mesmo cenário. Os jobs existentes conservam missões 20.1–20.3, regressões browser/unitárias, auditorias de dependências, tipos e build. Não depende de seeds operacionais ou execuções anteriores.

Artefacto `core-operational-<run>-<attempt>`: `core-operational-results.json` (todas as asserções), `core-operational-evidence.json` (medições, análises, referências/pacotes, avaliações, casos/eventos/ciclos e outbox), pedidos C01 e logs SQL. Credenciais ficam exclusivamente em `e2e/private`, fora dos artefactos; `.env` não é exportado. Retenção de três dias; plano, cenário e resumo permanecem versionados.

Reprodução local: Linux, Docker, Python 3.12+, psql, OpenSSL e Bun 1.3.0; checkout isolado sem `.env`, portas 5432/54321/54443 livres. Seguir a receita descartável da [20.3](INTEGRATED_VALUE_MISSION_20_3.md#reprodução-independente), substituindo o comando do cenário por:

```sh
python3 e2e/core-operational.py
```

O teste recusa bases sem nome/label/tmpfs/binding local esperados ou com clientes existentes. Executar `python3 scripts/mvp/stop-local.py` também após falhas, como o workflow faz com `if: always()`.

## Defeitos e limitações

**Nenhum defeito de produto encontrado; nenhuma correção ou migração de produção necessária.** As verificações seguiram os contratos existentes. No desenvolvimento do teste foram tratados os códigos HTTP normais de operação void (204) e acesso anónimo (401), e a outbox prevista por `notify_plan` passou a ter invariantes próprios. Nenhuma guarda do produto foi enfraquecida.

Limites preservados: recuperação prospectiva com cadência diária exige tempo real suficiente; encerramentos nesta missão são provas retrospectivas sintéticas. Elegibilidade, confirmação C05, condições textuais e critérios específicos dependem de revisão humana. Não existe comando independente de revogação de autorização: comprova-se a invalidação por revisão do plano e perda do papel atual do aprovador, não uma revogação individual permanente. Não há reabertura de casos encerrados, migração silenciosa de contrato histórico, interpretação/certificação externa, execução remota, causalidade automática ou política comercial universal. Os cinco casos abertos e as duas entradas bloqueadas são resultados corretos dentro desses limites.
