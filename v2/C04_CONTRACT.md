# Missão 10 — propostas IA/C04 fundamentadas e inativas

Parte do PR #39 (`cdd1809`). Adapta uma investigação C03 fixada a um pedido de modelo,
valida a resposta por código independente e guarda o resultado. **A IA recomenda;
não autoriza nem executa.** Core, sandbox e motores M06–M09 ficam intactos. Sem
HTTP novo, C05, conector SaaS, interface Lovable ou publicação.

Sem configuração/credenciais autorizadas, a inferência fica **unavailable**. Não há
modelo/endpoint predefinido, leitura automática de chaves do ambiente ou fallback
para simulator-v1. Fixtures existem apenas nos testes e são identificadas por
inference_kind=test_fixture; são recusadas em production e não têm opção de CLI.

## Contexto e resposta do modelo

O backend constrói e fixa um contexto com:

- SaaS/cliente, C02 e C03, versões/hashes de configuração/critérios/investigação,
  as_of e through, classificação e modo do runtime;
- investigação completa: observações e proveniência, resultados C02, hipóteses não
  confirmadas, requisitos observados, contradições, lacunas e limitações;
- configuração SaaS: produto, modelo de cliente, objetivos de valor, métricas,
  definições de evidência e catálogo de capacidades com condições/permissões/verificação;
- role verificada pelo Core, estado inativo e cabeças atuais de dados/configuração;
- [JSON Schema da resposta](contracts/c04-response.schema.json).

Os objetivos são os declarados no contrato SaaS para esse cliente, não um perfil
individual inventado: goal_scope=saas_contract_for_selected_customer. Não são enviados
tabelas de contas/passwords/sessões, ficheiro de credenciais ou configurações secretas
do adaptador. Dados/textos de fornecedores continuam não confiáveis; não colocar
segredos em evidências/descrições. Exportação ao modelo exige autorização local
explícita para a SaaS e classificação, além da permissão operator do utilizador.

Contexto até 262144 bytes; excesso é 413 antes de reservar/enviar, **sem truncar ou
fabricar resumo**. O hash é calculado pelo servidor; o modelo apenas o devolve.

Formato da resposta, ilustrado com listas vazias:

```json
{
  "schema_version": 1,
  "context_hash": "<hash-exato-do-contexto>",
  "hypothesis_reviews": [],
  "impediment_refs": [],
  "contradiction_refs": [],
  "missing_information_refs": [],
  "analysis_limitation_refs": [],
  "recommendation": {
    "kind": "no_action",
    "capability_id": null,
    "reason_code": "no_safe_action",
    "evidence_refs": [],
    "criterion_refs": []
  }
}
```

O hash é um marcador explicativo. As listas têm de refletir o contexto real, não
ficam vazias por omissão. Uma hipótese exige uma entrada com hypothesis_id,
disposition=retain_unconfirmed|human_review e support_refs/contrary_refs. Referências
são `{evidence_id,field}`, existentes e temporalmente elegíveis, e só podem ser
subconjuntos do lado respetivo já declarado em C03. Nenhuma disposition confirma causas.

impediment_refs só admite IDs de supported_impediments. As listas de contradições,
lacunas e limitações devem conter **todos** os índices correspondentes do C03 fixado;
não se permite omitir uma disputa. Não há novos factos, causas, scores de confiança,
roles ou campos de execução na resposta. Texto livre de análise/justificação é
recusado: a análise é expressa por referências, disposições não causais e códigos
limitados, para não fingir validação semântica de prosa gerada.

recommendation.kind é action_proposal, no_action ou human_review. Ação exige ID
exato do catálogo, reason_code=catalogue_match, citações de evidências e pelo menos
um critério C02 demonstrado. As alternativas não admitem capability_id. Códigos:
catalogue_match, no_safe_action, insufficient_evidence, contradictory_evidence,
human_review_required e no_deterioration. Este último exige dimensões C02 estáveis;
não se aceita uma justificação que negue a deterioração demonstrada.

## Validação determinística independente

`centerway.c04_contract.validate` não chama o modelo. Verifica formato/limites,
hash, referências, versões vinculadas, hipóteses não confirmadas, incertezas,
capacidade declarada, role e condições. Campos extra, citações inventadas, causas
confirmadas, tool calls ou pedidos de execução resultam em recusa/revisão.

Condições v1 usam observações **pontuais exatamente em as_of**, sem período, da
fonte/versão/cliente declarados. Não se presume que uma observação anterior persiste;
não se escolhe a última, não se inventa janela/validade e não se convertem séries
periódicas em estado atual. Campo ausente, disputa ou condição falsa dá revisão.
Todas as observações usadas na condição devem ser citadas na proposta.
A prova vale apenas no as_of fixado, não garante condições na hora da chamada ou
da futura execução. Sem validade temporal declarada, não se inventa TTL para estados;
a futura autorização do Core terá de voltar a verificar as condições reais.

A verificação declarada da capacidade é validada no contrato SaaS e anexada à proposta
como plano futuro. verification_status=not_performed: não se inventa estado após
intervenção nem recuperação de valor. Hipóteses sempre permanecem não confirmadas.

A inferência decorre **fora da transação SQLite**. Antes de finalizar, o Core volta a
verificar permissões e o backend reconstrói o contexto. Nova evidência, revisão C03,
configuração/critérios/C02 superados ou mudança de contexto impede validação atual.
Revogação de permissão/expiração durante a chamada é auditada como recusa e não
reabre acesso. Os controlos de production e a expiração de 24 h da demo mantêm-se.

| status | Significado |
| --- | --- |
| proposal_validated | Proposta limitada ao catálogo e fundamentada nos dados/condições fixados; **não é autorização** |
| no_action | O modelo não propõe ação, sem forçar escolha de capacidade |
| human_review | Incerteza, condição não demonstrada, contexto alterado, pedido de revisão ou falha do fornecedor |
| refused | Resposta inválida, suporte/ação inventados, permissão revogada ou fixture em production |
| unavailable | Sem configuração/credenciais, configuração inválida ou dados não autorizados para o fornecedor |

Todos os resultados têm operational_state=inactive, execution_authorized=false,
authorization=not_granted e human_review_required=true. Nem uma capacidade com
requires_human_approval=false elimina a aprovação futura do Core nesta missão.

## Adaptador real: configuração privada, sem o ativar nesta entrega

`AIAdapter` define descriptor()/generate(context), devolvendo Completion. O adaptador
incluído implementa o protocolo HTTPS Chat Completions compatível com vários
fornecedores, sem SDK nem modelo fixo. Outros protocolos exigem outro adaptador;
não se cria uma arquitetura de plugins nem vários fornecedores nesta missão.

[provider.json.example](examples/c04/provider.json.example) é apenas um modelo de
configuração, sem chave e com domínio reservado inválido. O responsável autorizado
prepara configuração e chave fora do Git, em diretório 0700 e ficheiros 0600:

```sh
umask 077
mkdir -p /private/centerway-ai
cp examples/c04/provider.json.example /private/centerway-ai/provider.json
chmod 700 /private/centerway-ai
chmod 600 /private/centerway-ai/provider.json
```

Editar endpoint/model/allowed_tenants/allowed_classifications com valores autorizados;
guardar a chave fornecida pelo responsável em api_key_file privado, sem passá-la em
argumentos, logs ou VITE_*. Não há contratação, aquisição de chave ou chamada real
nesta missão. allow_production_inference=false por defeito no exemplo; inferência
externa em production exige autorização explícita adicional na configuração.
Isso autoriza envio ao modelo, **nunca operação de negócio**.

Endpoint HTTPS exato, sem user/password/query/fragment; TLS verificado (sistema ou
CA privada explicitamente indicada), sem redirects ou fallback HTTP. Credencial
Bearer só em header. Timeout 1–30 s, max_output_tokens 1–4096, resposta até 65536
bytes. O fornecedor deve suportar system/user messages, response_format=json_object,
max_tokens e resposta Chat Completions completa. Modelo pedido e modelo reportado
são guardados separadamente; aliases podem diferir. O transporte não certifica a
implementação interna do fornecedor.

Falhas/redirecionamentos/truncações/tools/JSON inválido não geram sucesso simulado.
Chaves do ambiente são ignoradas. Não se envia contexto contendo a chave do próprio
adaptador e recusa-se eco da chave na resposta, incluindo escapes JSON. Erros têm
códigos limitados, sem corpo de erro, chave ou exceção do fornecedor nos registos.

## Preparar, propor e consultar

Requer M06–M09 e C03 já preparado. Setup é explícito e local; não há DDL/seed/migração
no arranque HTTP. Só bases temporárias foram usadas nesta missão.

```sh
cd v2
python3 -m centerway.ai_proposals init --db /private/runtime.sqlite3
# Sem --ai-config: regista unavailable; não chama modelos nem usa fixtures.
python3 -m centerway.ai_proposals propose --db /private/runtime.sqlite3 \
  --user authorized-operator --tenant configured-saas --customer account-a \
  --c02-run-id 1 --c03-version 1 --request-id explicit-request-001
# Para inferência real futura, acrescentar --ai-config /private/centerway-ai/provider.json
python3 -m centerway.ai_proposals get --db /private/runtime.sqlite3 \
  --user authorized-reader --tenant configured-saas --customer account-a \
  --request-id explicit-request-001
```

Contas/caminhos são ilustrativos; CLI é local confiável, user não constitui login
remoto. Só operadores podem pedir inferência; membros leem auditoria da própria
SaaS/cliente. Não expor a CLI/ficheiros como serviço público. Interface interna:
`ProposalRepository.propose(...)` e `get(...)`; nenhum destes métodos escreve em
Core.cases, decisões executáveis, C05 ou ambientes operacionais.

request_id reserva uma tentativa antes da chamada. Reenvio exato reutiliza o resultado;
contexto/modelo diferente com o mesmo ID dá 409. Pedido pendente/interrompido dá 409,
sem repetir inferência ou fingir que falhou remotamente. Pode já ter havido consumo
no fornecedor: inspeção humana antes de criar outro ID. Não há retries automáticos.

## Auditoria e limites reais

Pedidos/resultados append-only guardam contexto/hash e versões, autor/horas,
protocolo/modelo pedido/reportado, ID da resposta, modo de inferência, hash da resposta,
revalidação, razões, condições e plano de verificação. Propostas válidas conservam
JSON estruturado; respostas inválidas conservam só hash/códigos, sem reter prosa
não validada ou possíveis segredos. get valida integridade e fontes e reproduz a
validação dos resultados aceites; não volta a chamar o modelo nem renova autorização
histórica. Hashes locais não são assinaturas; o administrador do host continua confiável.

Os exemplos SaaS em [examples/c04](examples/c04) são sintéticos. As respostas de
FixtureAdapter existem **só nos testes**, identificadas como fixture-not-a-real-model;
não são inferência real. O transporte foi verificado com um endpoint TLS falso local,
que também não é um modelo. **Não foi executada nem verificada inferência com um
fornecedor/modelo real**, pois não foram fornecidas credenciais/configuração autorizadas.

V1 exige respostas muito restritas e condições pontuais em as_of; séries periódicas,
objetivos personalizados por cliente, prosa factual livre, confirmação causal,
retry/recuperação automática e ativação operacional não são implementados. Contextos
maiores são recusados; não há sumarização automática ou ensaio de escala de produção.
Sem conectores SaaS, Lovable, serviços contratados, publicação ou alteração da main.

## Verificação executada

154 testes Python passaram sem skips, incluindo 23 novos testes de propostas/adaptador.
Cobrem catálogo, versões, evidências, ausência de credenciais/sem fallback, recusas,
permissões, alteração do contexto durante inferência, concorrência/reenvios/crash,
integridade/backup, limites, demo expirada e bloqueios de production. O transporte
foi testado com TLS verificado, redirecionamento recusado, autorização de dados,
timeout, truncação, tamanho, tool calls e eco de segredo, incluindo escapes JSON.
Três ensaios Chromium e a regressão Caddy em loopback passaram. compileall, validação
systemd e git diff --check passaram. Estes resultados não validam inferência com IA real.

A primeira CI desta missão passou os testes Python, mas foi cancelada pelo limite de
10 minutos ao descarregar fontes/bibliotecas via APT. O workflow usa agora o Chrome
preinstalado do runner Ubuntu (versão impressa no log), através de CHROMIUM_PATH,
para executar os mesmos três ensaios sem reinstalar pacotes/navegadores. O runtime
e os scripts de teste do produto não foram alterados por este ajuste de QA.
