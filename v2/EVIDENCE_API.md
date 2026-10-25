# Missão 07 — motor de evidências inativas

Parte do PR #36 (`ab9b5b1`). Entrada de eventos, métricas e evidências estruturadas,
conforme o [contrato de integração v1](INTEGRATION_CONTRACT.md). HTTP 1.2.0 acrescenta
dois endpoints; os schemas/pedidos/respostas anteriores são preservados. Sem UI nova,
IA, deterioração, conclusões de valor ou execução. Core e C01–C06 operacionais existentes não consultam este
armazenamento. **Receber evidência não aprova nem ativa um fluxo operacional.**

## Preparação explícita

A base já deve ter autenticação privada e configuração versionada da SaaS. Executar
localmente, pelo responsável autorizado do host, fora de qualquer pedido HTTP:

```sh
cd v2
python3 -m centerway.integrations init --db /private/runtime.sqlite3
# Acrescentar a configuração da SaaS pelo procedimento da Missão 06, se necessário.
python3 -m centerway.evidence init --db /private/runtime.sqlite3
```

Não repetir o primeiro comando se as tabelas da Missão 06 já existem. Ambos recusam
estruturas existentes/parciais, sem limpar ou reparar. Fazer backup antes de preparar
uma base futura. Nesta missão só se prepararam bases temporárias de teste: nenhuma
base existente do utilizador foi alterada. O arranque HTTP não faz DDL, seed ou
migração. Sem preparação, a API de evidências devolve 503 após autenticação; o sandbox
continua disponível. A CLI nova prepara estrutura; a entrada de dados é pela API.

## POST `/api/evidence`

Sessão válida e membership **operator** da SaaS. Origin HTTPS exata e JSON UTF-8.
Reutiliza autenticação, cookies seguros, proteções de Host/Origin e CORS opt-in
existentes; não há API key pública nem role/autor fornecido no corpo.

Envelope obrigatório, sem campos extra:

```json
{"tenant":"configured-saas","customer":"account-a","config_version":1,"records":[{"external_id":"source-snapshot-001","kind":"evidence","definition_id":"operation-state","source_ref":"supplier:declared-state-source","occurred_at":"2026-01-02T00:00:00Z","period":null,"payload":{"paused":true}}]}
```

É um exemplo estrutural: definição, campos e origem têm de corresponder exatamente
à configuração daquela SaaS/versão. Não funciona contra uma configuração arbitrária.
Um [lote sintético completo](examples/evidence/collaboration-batch.json) corresponde
à fixture collaboration da Missão 06 e só deve ser usado num sandbox autorizado.
Não existe URL publicado; não enviar dados reais para o laboratório de contas públicas.

| Campo por registo | Validação |
| --- | --- |
| `external_id` | Identidade estável da origem, 1–128 caracteres, sem espaços nas extremidades |
| `kind` / `definition_id` | event → events; metric → metrics; evidence → evidence, sempre na versão explícita |
| `source_ref` | Igual à origem declarada nessa definição, sem buscar URLs |
| `occurred_at` | ISO UTC, sem momento futuro; normalizado para UTC com microssegundos |
| `period` | start/end UTC para metric e evidence de tipo metric; nos outros casos null |
| `payload` | Objeto não vazio; só campos/tipos declarados, sem omitir os obrigatórios |

Para metric, payload é exatamente `{"value": número}`, do tipo integer/number
configurado. O período tem start < end ≤ occurred_at, sem assumir agregação/cadência.
Eventos têm o campo identificador do cliente declarado em customer_id_field e este
deve coincidir com o envelope. Se uma evidência incluir o customers.id_field,
também tem de coincidir. Campo chamado occurred_at deve ser um timestamp UTC e corresponder ao
envelope. A origem e os momentos são declarações autenticadas do remetente, não
prova criptográfica do fornecedor. Evidência unavailable é recusada até existir
uma nova configuração apropriada, sem alterar versões anteriores.

Strings até 2000 caracteres; números finitos até ±(2^53−1); integer não aceita
booleanos/frações. Não há conversão de strings em números, defaults, preenchimento
de valores ou recolha de ficheiros/URLs. 3 e 3.0 são normalizados como o mesmo number;
representações equivalentes de timestamps UTC não criam falsas diferenças.

Resposta 200:

```json
{"tenant":"configured-saas","customer":"account-a","config_version":1,"config_hash":"<sha256-da-configuração>","operational_state":"inactive","classification":"declared","inserted":1,"duplicates":0,"record_ids":[1],"batch_id":1,"reused":false}
```

O hash acima é um marcador explicativo; o real tem 64 dígitos hexadecimais.
classification vem da configuração, nunca do pedido. Production recusa configurações
synthetic desde a Missão 06; declared continua a significar declaração não verificada,
sem afirmar que dados, resultado ou recuperação são reais.

## Histórico, duplicações e contradições

Lotes são atómicos: um registo inválido, colisão, limite ou falha SQL reverte o lote
inteiro. Cada item guarda SaaS/cliente, versão/hash da configuração, origem, identidade
externa, momento/período, payload/hash, autor da sessão e hora de receção do servidor.
Lotes têm recibo imutável e hash; reenvio exato normalizado reutiliza o mesmo batch_id,
com inserted=0, duplicates=N, reused=true, sem duplicar itens ou recibos.

A identidade do item é `(tenant, customer, kind, definition_id, source_ref, external_id)`.
Reutilizar essa identidade com outro conteúdo **ou versão** devolve 409, sem sobrescrever
ou reinterpretar. Outro lote pode reutilizar itens idênticos. Um snapshot metric/evidence
igual, no mesmo momento/período, com outro external_id é 409: reutilizar a identidade
original. Eventos com IDs distintos podem ser ocorrências distintas mesmo com payload
idêntico; o motor não os funde por suposição. A identidade estável cabe ao remetente.

Snapshots de metric/evidence da mesma definição/origem, cliente, versão, momento e
período, com valores diferentes nos mesmos campos, são preservados e assinalados
como contraditórios. Campos complementares ou períodos diferentes não são conflitos.
Não se escolhe o último, não se corrige o anterior e não se conclui deterioração.
O diagnóstico é calculado na consulta GET após a entrada, não no recibo de ingestão.
Não existe deteção de contradições semânticas entre definições diferentes nem entre
origens/momentos diferentes: o contrato ainda não fornece regras para isso.

## GET `/api/evidence/view`

Sessão e membership de leitura da SaaS. Query obrigatória: tenant, customer e
config_version. Opcionais: limit (1–100; default 100), after (default 0), through.
Campos desconhecidos/repetidos, inteiros inválidos e escopo incompleto são 400.

```http
GET /api/evidence/view?tenant=configured-saas&customer=account-a&config_version=1&limit=20
```

Resposta contém identidade/versão/hash/classificação, operational_state=inactive,
records com proveniência, quality, through e next_after. Para a página seguinte,
reutilizar through e enviar after=next_after. through fixa o limite de IDs recebidos;
não avançar esse limite durante a paginação. next_after=null termina a consulta.
Não há consulta global sem SaaS/cliente nem mistura automática de versões.

Quality é uma avaliação **estrutural**, com conclusion sempre not_evaluated:

- insufficient: faltam definições declaradas, ou não há definições na configuração.
- incompatible: só existem dados de outras versões, excluídos desta consulta.
- contradictory: há afirmações incompatíveis sobre o mesmo snapshot; conflicts
  identifica os registos envolvidos. A lista missing continua a indicar ausências.
- compatible: existem registos das definições declaradas e nenhum conflito estrutural.
  Não significa verdade, completude temporal, amostra suficiente para análise ou
  prontidão para C01–C06. Não há limiares de cobertura inventados pelo motor.

excluded_other_versions conta registos excluídos, sem os converter. As ausências,
conflitos e contagens usam o snapshot inteiro dessa versão até through, não só a página.
Uma consulta vazia não fabrica evidências, métricas ou conclusões.

Interface interna para futuros C01–C04, ainda sem ligação aos componentes:

```python
from centerway.evidence import EvidenceRepository
repository = EvidenceRepository(existing_store)
snapshot = repository.query(authenticated_user, tenant, customer, config_version=1)
# Usar apenas como dados inativos; nenhuma aprovação operacional é concedida.
```

## Segurança, limites e erros

400 para formato incompatível, origem/campos/tipos/tempos inválidos; 401 sem sessão;
403 sem membership/operator ou Origin autorizada; 404 configuração inexistente;
409 identidade/snapshot duplicado divergente; 413 limites; 415 formato/compressão
não suportados; 503 estrutura ausente, expiração da demo ou integridade não confirmada.
Erros mantêm `{error,code}` e não expõem payloads, segredos ou exceções internas.

Limites desta versão: 65536 bytes/lote, 100 itens/lote, 8192 bytes/item, 1000 itens
por SaaS/cliente e 5000 recibos por SaaS/cliente. Reenvios exatos continuam possíveis
no limite. Não são limiares de negócio; são proteções de recursos do protótipo.
Não há remoção/arquivo automático para contornar os limites.

Triggers impedem UPDATE/DELETE nos três conjuntos de metadados/itens/lotes. Consultas
validam estrutura, proteções e hashes dos itens/proveniência da configuração; recibos
são validados ao reutilizar um lote. Não se reparam dados. O proprietário do SQLite/SO
continua confiável; hashes locais não são assinaturas nem defesa contra um administrador
que reescreva toda a história. Ler/validar o histórico do cliente tem custo linear,
limitado pelos tetos acima; não foi validado tráfego de produção.

Produção conserva os bloqueios das seis tabelas antigas e de todos os endpoints de
negócio. Novas evidências são guardadas em tabelas separadas, **sempre inativas**;
não criam clientes operacionais, observações sandbox, casos, decisões ou intervenções.
Não há endpoint de ativação, execução, correção ou administração de configurações.
Sem IA, conectores externos, Lovable, publicação, serviços pagos ou alterações na main.

## Verificação executada

89 testes Python passaram sem skips, incluindo 16 novos testes de evidências:
API HTTPS autenticada nas três SaaS, formatos, escopos, sessões/permissões, conflitos,
reenvios concorrentes, rollback SQL, integridade, limites, expiração da demo e
inatividade de production. O teste Caddy passou também com entrada, consulta,
reinício real de Python e reenvio sem duplicação. Três ensaios Chromium passaram
(regressão responsiva de 150 clientes, HTTPS privado com Pixel 7 emulado e CORS).
Não é ensaio de integração externa, tráfego de produção ou Android físico.

```sh
cd v2
python3 -m pip install -r tests/requirements.txt
python3 -m unittest discover -s tests -p test_evidence.py -v
CADDY_BIN=/caminho/para/caddy python3 -m unittest discover -s tests -v
```

O Caddy de QA pode ser obtido pelo helper existente `infra/fetch-test-caddy.sh`;
sem CADDY_BIN/caddy, os testes de proxy são skipped. A CI fornece o binário verificado.

A [Missão 08](DETECTION_CONTRACT.md) acrescenta um C02 isolado que lê snapshots
deste armazenamento sob critérios explícitos, sem ativar o fluxo operacional.
