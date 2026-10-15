# C03 Evidence Builder: servidor apenas (`c03-v1`)

Neste passo não há interface, C04/C05, IA nem casos.

## 1. Transações: duas chamadas separadas
- Mantém-se `run_deterioration_analysis`: corre na sua própria transação e o C02 fica gravado de forma independente.
- Nova função `build_evidence_bundle(_tenant_id, _run_id)` (SECURITY DEFINER, apenas admin/operator, revalida o tenant e a análise). Não recalcula o C02 e não altera `c02_runs`.
- Por dentro, a montagem corre num bloco `BEGIN … EXCEPTION` (subtransação):
  - **Sucesso:** grava o pacote e os itens.
  - **Erro de integridade** (ref inexistente, de outro tenant ou cliente, hash ou valor divergente, importada depois do corte): a subtransação desfaz só o pacote. Fora dela grava-se uma tentativa falhada, e a função devolve `{status:'rejected', code}`. Não levanta um erro que apagaria o registo da tentativa e não declara o pacote completo.
  - **Erros inesperados:** são também registados como tentativa falhada e voltam a ser lançados.
- Nova tabela `c03_attempts`, só de acréscimo: análise, ator, resultado, código e hora. O C02 nunca é atualizado.
- **Idempotência:** fica `UNIQUE(run_id, algorithm)`. Repetir a montagem devolve o pacote existente. Depois de uma tentativa falhada pode-se tentar de novo, e cada tentativa fica registada.
- O estado mostrado ao utilizador vem de "existe pacote" ou "última tentativa", nunca de um campo do C02.

## 2. Contratos
- **`c03_bundles`:** tenant, cliente, análise, `algorithm_version` do C02, `as_of`, `data_cutoff`, `profile_id` e versão do perfil, `input_hash`, `content_hash`, resumo e ator.
  - O resumo é derivado por uma regra explícita: contagens por estado. Nunca rebaixa um indicador por causa de outro.
- **`c03_indicators`:** um por indicador, com a classificação e uma cópia dos parâmetros, impressão digital e cópia dos detalhes do C02 com o respetivo hash. Assim o histórico pode ser verificado sem consultar o perfil atual.
  - **Estado:**
    - `complete`;
    - `insufficient` com motivos guardados (insuficiência herdada do C02, `budget_exceeded`, `c02_v1_known_gaps` para análises v1 com indicadores avaliados);
    - `context_facts` para indicadores de contexto ou texto: só factos, sem avaliação temporal.
    - Não haverá estado `not_applicable` a esconder insuficiências reais.
- **`c03_refs`:** linhas pagináveis.
  - Cada linha tem a etiqueta da janela e o papel: numerador, denominador ou substituída por correção.
  - Guarda também `observation_id`, `payload_hash`, valor citado, unidade, fonte, `observed_at` e `ingested_at`.
  - Cada linha vem só dos ids guardados na análise C02. Nada importado depois do `data_cutoff` entra no pacote.
- **Limite:** 5000 refs por indicador. Acima disso o indicador fica `insufficient` com as contagens e não se grava uma prova parcial.
- **Segurança:** RLS de leitura para membros do tenant; ninguém tem permissão de escrita; gatilhos de imutabilidade e de auditoria.

## 3. Testes SQL a correr (fixtures próprias, sempre revertidas)
- **Pacote correto:** refs, hashes e valores coincidem com o C02; repetir reutiliza o mesmo pacote.
- **Refs forjadas:** ref forjada ou de outro tenant (injetada por um teste com privilégios) → rejeitada, sem pacote gravado e com a tentativa registada.
- **Corte respeitado:**
  - correção ou dado tardio depois do corte → fica fora do pacote antigo;
  - a nova análise C02 gera um pacote novo e o antigo fica igual byte a byte.
- **Estados por indicador:**
  - fontes incompatíveis → `insufficient` com o motivo herdado;
  - análise v1 → `c02_v1_known_gaps`;
  - contexto ou texto → `context_facts`;
  - limite ultrapassado → `insufficient: budget_exceeded`;
  - um indicador insuficiente não afeta os outros.
- **Permissões:** anónimo e leitor não montam pacotes; tenant B não lê nada; a escrita direta é recusada.

## Pontos em aberto
- Para testar o limite de 5000 sem importar 5000 linhas, o teste baixa o limite com um parâmetro interno visível apenas a quem tem privilégios.
