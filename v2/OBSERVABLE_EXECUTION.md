# Missão 17 — executar e observar os motores sem interface

Base PR #46. A CI desse commit (`2f21da0`) foi confirmada como aprovada.
Este comando executa os motores **existentes M06–M14**, num laboratório local
isolado, exclusivamente sintético. Não altera motores, piloto, produção ou APIs.
Não cria servidor HTTP, interface, conector externo, modelo de IA ou scheduler.

## Iniciar e inspecionar

Python 3.12+, stdlib, Linux (flock). A partir do checkout da branch desta missão:

```sh
cd v2
python -m centerway.journey --workspace /tmp/centerway17 prepare-suite --ack-test-fixtures
python -m centerway.journey --workspace /tmp/centerway17/complete inspect
```

`prepare-suite` exige diretório **novo**, fora do checkout. Cria oito ambientes
privados 0700, cada um com duas bases SQLite 0600, fontes/contratos sintéticos e
conta privada aleatória. Não utiliza contas públicas nem dados da demo antiga.
A base do motor e o serviço sintético são separados. Instalação é explícita;
comandos de retoma abrem bases existentes, sem seed/DDL/reparação.

As credenciais ficam em `credentials.json`, o token local em `session.json`.
Não os imprimir, copiar para Git ou incluir no relatório. São exclusivamente
contas deste laboratório, não credenciais reais da SaaS. A sessão dura 1h; para
renovar após expiração:

```sh
python -m centerway.journey --workspace /tmp/centerway17/complete login --credentials-file /tmp/centerway17/complete/credentials.json
```

Omitir `--credentials-file` pede a palavra-passe via getpass. O login verifica o
hash privado; cada escrita verifica sessão e permissões Core. `inspect` e `report`
também exigem sessão. Não disponibilizar estas bases por HTTP ou na Internet.
O comando recusa bases production, demo privada, piloto ou sem marcador próprio.

`prepare-suite` carrega explicitamente documentos de exemplo para os cenários de
verificação. Não investiga causas sozinho e **não aprova ou executa** nada. A
resposta C04 fornecida em quatro cenários é fixture identificada como
`test_fixture` / `explicit-fixture-not-ai`; a validação M10 é real, a inferência
não ocorreu. O cenário `ai_unavailable` não fornece essa fixture e fica bloqueado.

## Percurso manual de um único cliente

Para acompanhar cada fronteira, em vez da preparação em lote:

```sh
python -m centerway.journey --workspace /tmp/meu-ensaio init --scenario complete
python -m centerway.journey --workspace /tmp/meu-ensaio login --credentials-file /tmp/meu-ensaio/credentials.json
python -m centerway.journey --workspace /tmp/meu-ensaio ingest --file /tmp/meu-ensaio/inputs/initial-evidence.json
python -m centerway.journey --workspace /tmp/meu-ensaio advance
python -m centerway.journey --workspace /tmp/meu-ensaio inspect
```

M06 regista produto, goals/métricas, fontes e catálogo; M08 regista critérios
explícitos. M07 recebe o ficheiro e valida identidade, fonte, versão, momento,
tipos, períodos, idempotência e contradições. O orquestrador calcula C02 e para em
`awaiting_investigation` se demonstrar deterioração. Não fabrica C03.

```sh
python -m centerway.journey --workspace /tmp/meu-ensaio investigate --file /tmp/meu-ensaio/inputs/investigation.json
python -m centerway.journey --workspace /tmp/meu-ensaio advance
```

O documento C03 é uma declaração **fornecida** pelo operador; no exemplo, é uma
fixture documental declaradamente fictícia. O motor separa factos, hipóteses não
confirmadas, requisitos observados, contradições e lacunas, com referências de
origem/versão. O ficheiro exige o C02 run ID e IDs de evidência realmente presentes;
se mudar os dados, consultar `inspect`/relatório e fornecer documento compatível.
Sem IA configurada, `advance` para em `awaiting_ai`, sem pedido de inferência nem
fallback simulado. Não é uma investigação autónoma ou uma causa comprovada.

## IA real opcional versus entrada de teste

Para uma futura chamada autorizada, utilizar apenas o adaptador M10 existente:

```sh
python -m centerway.journey --workspace /tmp/meu-ensaio advance --ai-config /private/provider.json --consent-synthetic-ai
```

A configuração/segredo devem estar fora do checkout, com permissões privadas,
HTTPS verificado, allowlist da SaaS e classificação **synthetic** autorizada.
Não existe endpoint/modelo/key predefinidos ou leitura de chaves de ambiente.
O relatório regista protocolo de resultado, modelo reportado e validação, sem
expor segredo ou endpoint privado. Nenhuma chamada externa/paga foi configurada
ou executada na entrega. Configuração inválida/ausente é indisponibilidade, não
simulação. Inferência pendente/interrompida não é repetida automaticamente.

Para verificar tecnicamente C04–C06 **sem IA real**, selecionar uma entrada de
teste explícita, separada de `advance`:

```sh
python -m centerway.journey --workspace /tmp/meu-ensaio supply-test-proposal --ack-test-fixture
```

Este comando fornece o pacote sintético de resposta (capacidade/refs declaradas)
e liga-o ao hash/contexto efetivamente produzido por C02/C03. M10 valida-o de
forma independente; não é uma recomendação inferida por IA. O ficheiro exato fica
em `inputs/explicit-test-response.json` e a proveniência fica nos outputs. Não
substitui uma decisão de modelo já reservada/registada. O pacote é exclusivo deste
perfil de exemplo; não serve para outros contratos/clientes reais.

M13 prepara uma intenção M11 com observação **atual** do serviço sintético. O caso
fica `awaiting_approval`. `advance` nunca despacha automaticamente, mesmo se já
existir aprovação. `inspect` mostra o hash, a capacidade, condições, alvos e estado.

## Aprovação e execução

Rever a intenção concreta. A única ação deste adaptador é mudar `paused=true`
para `false` na base SQLite sintética daquele ambiente. Não executa comandos,
chamadas de rede ou intervenções em SaaS. Aprovação não é consequência de C04.

```sh
python -m centerway.journey --workspace /tmp/meu-ensaio inspect
python -m centerway.journey --workspace /tmp/meu-ensaio approve --intent-hash HASH_EXATO_MOSTRADO
```

O último comando pede ao humano que escreva `APROVO HASH_EXATO_MOSTRADO`. Para
um operador que já confirmou explicitamente esse hash, existe a alternativa
não interativa `--human-confirmation 'APROVO HASH_EXATO_MOSTRADO'`. Não preencher
este argumento automaticamente para contornar o requisito humano. O motor M11
verifica sessão, papel, hash, catálogo, versões, evidências e condições atuais;
regista aprovação imutável, responsabilidade e validade de até 300s. A IA não a
concede. Os testes unitários usam assertions de aprovação **de teste**, sem alegar
confirmação humana física; a demonstração operada exige a confirmação concreta.

```sh
python -m centerway.journey --workspace /tmp/meu-ensaio execute
python -m centerway.journey --workspace /tmp/meu-ensaio inspect
```

C05 reserva uma tentativa antes do I/O. O adaptador faz compare-and-set da revisão
e grava chave de idempotência + efeito na mesma transação do serviço sintético.
Há alteração persistida de `paused`/revision, não apenas uma mensagem de sucesso.
O cenário uncertain grava o efeito e depois provoca timeout de teste: C05 regista
incerteza e nunca repete ou resolve automaticamente. Ler a base de teste não
transforma, por si só, um recibo incerto numa execução confirmada pelo Core.

## Evidências posteriores e C06

```sh
python -m centerway.journey --workspace /tmp/meu-ensaio plan
python -m centerway.journey --workspace /tmp/meu-ensaio verify
python -m centerway.journey --workspace /tmp/meu-ensaio collect
python -m centerway.journey --workspace /tmp/meu-ensaio verify
```

`plan` regista janelas/metas explícitas M12, vinculadas à tentativa e à configuração.
A primeira avaliação, antes da recolha/maturidade, deve permanecer insuficiente.
As janelas posteriores começam **depois** da tentativa/recibo reais deste ensaio;
o relógio dos motores não é substituído ou avançado artificialmente.

`collect` aguarda dois ticks reais de 1s do serviço de teste (menos de 4s normalmente),
consulta estado persistido e regista amostras na base da origem antes de enviar ao
M07. O gerador de workload é explicitamente sintético e independente do resultado
C06: incrementa um contador de teste quando configurado, não imita valor de uma
empresa. Cada amostra preserva momento agendado, momento efetivamente observado,
chave e hash. Os ticks são a cronologia declarada da origem de teste, não medições
de uma SaaS real. Seeds anteriores são fixtures históricas relativas ao início;
nunca são apresentados como recolha real realizada no passado.

A cadência/janelas/limites dos exemplos são dados explícitos para acelerar o
ensaio; não são recomendações para um negócio. Uma janela perdida não é preenchida
com medições inventadas: a recolha recusa atraso superior a 2s. Depois de preservar
uma avaliação insuficiente com `verify`, `plan` pode registar nova revisão de
janelas futuras; repetir `collect; verify`. Nenhuma revisão antiga é apagada.

C06 separa **execução**, **recuperação operacional** e **recuperação de valor**.
Os estados demonstrados referem-se somente ao ensaio: `assessment_scope` permanece
`synthetic_test_only`, os booleanos de recuperação real permanecem null/false,
a causalidade não é estabelecida e M14 não fecha o caso automaticamente.

## Interromper, retomar e auditar

Pode parar entre comandos, voltar a abrir o mesmo diretório e consultar. Não
repetir init nem apagar bases. Para continuar depois de uma aprovação válida:

```sh
python -m centerway.journey --workspace /tmp/meu-ensaio resume
```

`resume` não aprova: sem aprovação mantém bloqueio. Depois de uma tentativa,
nunca a repete. Reenvia amostras já persistidas através da idempotência M07 e
reutiliza a avaliação C06 final se as fontes/janelas não mudarem. Comando concorrente
é recusado por lock local; os motores mantêm também as próprias unicidades/fences.
Um processo interrompido entre reserva e recibo permanece incerto, não é reexecutado.
Sessão expirada exige novo login; aprovação expirada antes de despacho permanece
bloqueada pelas regras atuais do M11, sem renovação/bypass automático nesta missão.

```sh
python -m centerway.journey --workspace /tmp/meu-ensaio report --out-dir /tmp/relatorio17-v1
python examples/observable/export_suite.py --workspace /tmp/centerway17 --out-dir /tmp/relatorios17-v1
```

Cada exportação exige destino novo: preserva exports anteriores. Produz JSON
com outputs e hashes reais dos motores, cronologia Markdown completa e manifesto
SHA-256 dos artefactos. Não inclui credenciais, tokens de sessão, endpoint privado
ou contexto de pedido do modelo. A ordem usa o momento **de registo**; os momentos
e períodos declarados pelas fontes permanecem separados nos outputs. `inspect`
e `report` leem e validam histórico; não processam ou escrevem avaliações.

## Cenários da preparação

| Perfil | Percurso/entrada explicitamente preparada |
| --- | --- |
| complete | C02/C03 + proposta fixture validada; aguarda aprovação para testar execução e ambos os resultados C06. |
| insufficient | Só uma leitura fornecida; o motor deve conservar insuficiência. |
| contradictory | Leituras incompatíveis conservadas; nenhuma é escolhida arbitrariamente. |
| investigation_pending | Evidências completas, nenhuma declaração C03 fornecida. |
| ai_unavailable | C03 fornecido; sem configuração de IA e sem fixture C04. |
| approval_pending | Proposta fixture validada, nenhuma aprovação/execução. |
| uncertain | Adaptador com falha de resposta após commit do efeito; exige aprovação própria. |
| operation_only | Mesmo efeito operacional; gerador de valor sem incremento, exige aprovação própria. |

Os resultados da entrega devem ser lidos nos artefactos gerados, não nesta tabela
de entradas previstas. Estados/bloqueios/valores são calculados pelos motores.

## O que ainda não faz

- Não investiga causas sozinho; C03 estrutura declarações do operador e evidências.
- Não pesquisa fontes externas nem descobre automaticamente metas, regras ou SaaS.
- Não verifica um modelo de IA real através de uma fixture, nem usa fallback simulado.
- Não executa ações externas/reais; o adaptador desta missão é um serviço SQLite fictício.
- Não demonstra recuperação real de operação/valor nem atribui causalidade.
- Não resolve incertezas, repete intervenções ou renova aprovações automaticamente.
- Não encerra ciclos em consequência de C06 nem altera os bloqueios do piloto.
- Não substitui autenticação empresarial, auditoria assinada externamente, backup,
  cifragem em repouso ou agendamento de produção. Hashes locais não são assinaturas.

O que se pode comprovar aqui é a engenharia do percurso e das proteções, com os
motores reais e entradas/efeitos explicitamente sintéticos. Inferência real,
integração SaaS real e recuperação de clientes reais exigem validações futuras.

## Artefactos já produzidos nesta missão

[Resultados e cronologias antes de aprovação](demonstrations/mission17/pre-approval/RESULTS.md)
foram exportados das bases efetivamente executadas. Incluem inputs, resultados
M06–C05, bloqueios, hashes e manifestos. Os cenários complete/operation_only/uncertain
estão preparados com **zero efeitos**; exigem a confirmação dos seus hashes antes
de uma demonstração operada até C06. Não confundir o perfil denominado complete
com uma execução já concluída.

A regressão técnica executou C06 com aprovações **fixture do test driver**, verificando
distinção operacional/valor, incerteza e retoma. Isso valida a engenharia, mas não
é apresentado como aprovação humana da demonstração. Relatórios pós-intervenção
só serão acrescentados depois da confirmação humana correspondente.
