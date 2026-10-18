# Abrir o MVP montado

## Sem instalação: mapa visual

Abra `public/mvp-preview.html` diretamente no browser. Inclui navegação C01–C10,
objetivo, plano, intervenção e dois exemplos de resultado. É uma referência
ilustrativa de leitura: não consulta base, não autentica e não executa operações.
Também é servido em `/mvp-preview.html` quando a aplicação está a correr.

## Aplicação operacional em base descartável

Pré-requisitos: Python >=3.12, Docker local funcional, cliente `psql`, Node 22+
e Bun 1.3.0. Portas locais livres: 5432, 9999, 54322, 54321 e 5173.
Os quatro containers são gratuitos e descartáveis. Não usar uma base existente.
As dependências são obtidas do npm público, com versões e hashes congelados;
o arranque isolado não exige acesso à cache ou ao projeto Lovable.

Na branch da entrega que pretende testar, com os ficheiros commitados (o script usa HEAD):

```sh
python3 scripts/mvp/start-local.py
```

O comando exporta HEAD para uma pasta temporária **sem `.env`**, instala o lockfile
existente, cria um PostgreSQL 17 novo sem volumes persistentes, GoTrue, PostgREST
e gateway no loopback, aplica migrações e carrega seis clientes fictícios.
Não aceita URLs de bases remotas nem credenciais de produção. Não altera `.env`
ou o backend hospedado. O trust PostgreSQL e a confirmação de email automática
existem só nesta stack de teste local, tal como no harness CI anterior.

Abra **http://127.0.0.1:5173/app/casos**. O comando indica o caminho privado local
`e2e/private/mvp-users.json`, que contém contas e passwords temporárias:
`mvp-admin@example.invalid`, `mvp-operator@example.invalid`, `mvp-viewer@example.invalid`.
Os segredos não são publicados em artifacts ou commits. Use a password do ficheiro.

Para terminar a aplicação, Ctrl+C. Depois, no repositório:

```sh
python3 scripts/mvp/stop-local.py
```

O script recusa remover containers/redes sem a etiqueta descartável esperada.
As pastas temporárias com credenciais ficam locais; elimine a pasta indicada após
terminar. Um novo arranque cria uma stack e credenciais novas; não reutiliza dados.

## O que explorar

- **Percurso operacional configurável:** selecionar a empresa Atlas SaaS sintética e um cliente para decisões C04 → Core → C10. Critérios, dados retrospectivos e limites em `docs/OPERATIONAL_JOURNEY.md`; o piloto abaixo permanece separado.

- **C04 configurável:** selecionar um cliente e abrir o painel Value State. Registar factos conhecidos, consultar pendências, completar uma revisão e avaliar um pacote C03. Este bloco requer a 0013 e mantém o piloto abaixo separado; ver `docs/C04_CONFIGURABLE.md`.

- **Investigar:** selecionar o caso, consultar o cliente C01–C03, escolher a prova
  `integration_status=disabled` e investigar. Sem prova fica à espera de informação.
- **Aprovar:** consultar o plano e aprovar como admin. Operator não recebe esse botão.
- **Executar:** escrever um recibo e registar a execução humana; o Core inicia o gate.
  Isto não liga uma integração externa. Não existem conectores nesta entrega.
- **Em observação:** consultar wait_until; comparação prematura é recusada pelo servidor.
- **Resultado atingido:** dossier C09 com comparação, refs e decisão C10 resolvida.
- **Objetivo por atingir:** execução técnica separada de resultado; caso permanece aberto.

As quatro primeiras fixtures usam Auth e RPCs reais desde C01 até ao seu estado
atual. As duas últimas carregam eventos C07/C08 **retrospectivos e fictícios** por
uma ligação privilegiada exclusivamente descartável; C01–C04 e C09/C10 são calculados
de verdade. O campo `fixture=synthetic_retrospective_history` e o aviso ficam no
histórico. Isto permite ver resultados agora, sem alterar o relógio ou encurtar a
janela do produto. Não prova uma execução/aprovação histórica nem espera real.

## Verificações e fronteira

`git diff --check`, `node --check e2e/mvp-seed.mjs` e parsing Python são verificações
básicas locais. O workflow browser existente monta a base descartável, preserva
as regressões C02–C03 e acrescenta um smoke de montagem do MVP, além de tipos,
unitários e build. Consultar a execução do commit final, não presumir sucesso.
Screenshots sintéticos e mapa HTML são artifacts; credenciais ficam excluídas.

A montagem do código `aa4698c` foi aprovada: 12 testes de browser (11 regressões +
1 smoke MVP), 110 unitários, tipos e build. Evidência em `docs/MVP_DELIVERY.md`.
Na revisão final foram disponibilizados Bun/psql temporários e Docker local;
o arranque isolado é verificado sem usar o `.env` original. Consulte
`docs/MVP_FINAL_REVIEW.md` e os checks do HEAD para o resultado final.

A campanha completa C01–C10 (roles por comando, concorrência, RLS de todas as
novas entidades, replay/conflitos, respostas tardias, correções após cutoff,
expiração/revogação e todos os critérios de fecho) fica para a fase seguinte.
Não considerar o piloto pronto para produção por o smoke passar.

A revisão final acrescenta 76 verificações SQL com roles `authenticated`/`anon`
e rollback, incluindo leitura entre empresas, escrita direta, RPCs, ligações
tenant/cliente, versões/aprovação e encerramento com evidência nova pendente.
O CI aplica a 0012 sobre fixtures C01–C03 não vazias e compara hashes de todas
as tabelas anteriores e respetivos grants antes/depois. Isto não substitui uma
auditoria do esquema hospedado, que não foi consultado.

Limites: política apenas FlowReports, confirmação documental manual, um objetivo
por avaliação, até 100 linhas nas listas / 300 eventos no dossier, sem conectores,
scheduler, renegociação documental, revisão de planos, renovação de aprovação,
cancelamento, fecho administrativo ou reabertura. A idempotência protege o mesmo
caso; ainda não há coordenação global de ações entre casos de avaliações diferentes.
Aprovação expirada bloqueia o
caso neste piloto; pode criar novo caso de demonstração numa nova stack.
Sem trabalho visual obrigatório no Lovable: os componentes existentes bastam;
polimento visual e usabilidade podem ser avaliados depois pelo fundador.
