# T01 — preparação adversarial, exclusivamente sintética (issue #69)

Base inspecionada: `recovery-mvp/m68-live-frontend`, `5086e33dc438fbc3e5d9f08014d2df21d3745a37`.
Nada aplicado ao Neon/Render público. Nenhuma alteração Lovable, publicação, merge,
crédito ou recurso novo. Este seed não é executado no build/start da API.

## O que foi inspecionado e o que existe

- F01 `CONTRACT.md`, SQL 001/002: versões imutáveis, um escalar por evidência,
  unidade/método/fonte iguais ao contrato, janelas fechadas, qualidade declarada.
- F02 SQL 003: compara **revisões explícitas de um mesmo contrato**. Sem agregador
  de tickets, não calcula mediana nem interpreta texto de documentos.
- F03/F03.1 SQL 004/005: inputs estruturados podem existir antes da deteção;
  `discover_company` só encaminha entradas com período elegível da deteção.
- F04 SQL 006: apenas `set_synthetic_flag`, catálogo não é autorização; políticas
  administrativas separadas. F05 SQL 007 exige execução/janelas legítimas.
- F06 SQL 008 e API `api/app.py`/`openapi.json`: append, detect, discovery, open,
  investigate, intervene, undo, plan/evaluate; nenhum endpoint de criar tenant/conta.
- Sessões `api/session_store.py`, `managed/sql/001_sessions.sql`, provisionamento
  `managed/provision.py`, seeds A/B e UI `lovable-ui/src/routes/app.*`.
- Principal real `session_user`, runtime sem privilégios administrativos. RLS de
  **tenant** no PostgreSQL; limite de cliente e de operações no HTTP, como L01.
  Não se afirma RLS de cliente nem role PostgreSQL só de leitura para `t01_reader`:
  o seu DSN fica exclusivamente no backend e a API restringe operações a `[]`.

Os motores, migrações, transporte e frontend não foram alterados. Não importar a
arquitetura antiga C01–C10/Supabase. Não utilizar Neon Auth nesta fixture.

## Identidade e representação

| Campo | Valor |
|---|---|
| namespace | `adversarial-t01` |
| empresa | AtlasOps Cloud (100% sintética) |
| tenant_id | `110577e9-2d2c-5288-93f2-2ba53f86f074` |
| cliente | Meridian Distribuição (100% sintético) |
| client_id | `073b083a-e6f1-590a-882b-063dfac5f1da` |
| contract_id | `6bc03825-1d3d-5570-9fd9-1e182e3c8379` |

IDs determinísticos UUIDv5; somente um T01 por instalação. Reutilizar o bundle
original para retomadas. Não criar outro bundle para contornar colisões.

`initial.json` é a especificação legível; `documents/` contém os documentos reais
**da fixture sintética**. Hash SHA-256 calculado dos bytes no carregamento, versão
v1 na referência; CSV tem digest próprio conferido no manifesto JSON. Não são
arquivos externos obtidos/verificados. Preservar estes ficheiros com a versão do
commit usada na instalação; não editar v1 depois da ativação.

| Evidência da issue | Representação inicial legítima |
|---|---|
| Contrato 01/09, prazo 31/10; baseline 40h, mínimo/alvo 24h | Fonte do contrato v1, contrato r1 com janela global `[01/09,01/11)` UTC; texto mantém o prazo e assinatura sintéticos |
| S1–S8: 39,35,29,30,33,37,36,34h | Mesmo contrato r2–r9, janelas semanais contíguas; oito evidências `outcome` r1 com fonte/método/unidade e hash exatos |
| S7 com 7/28 timestamps não confiáveis | 36h **declaradas**, qualidade `partial`; não recalculamos nem introduzimos zeros |
| Adoção 18/40 → 31/40 | Documento/fonte contextual, não `outcome`, nem `usage` com falsa unidade em horas |
| CSV fornecedor S6 22h, média e P1 | CSV/JSON e fonte contextual. F01 rejeita esse método para o contrato; não o inserimos como segunda mediana válida |
| Integração atrasada em 14/10 | Documento + input F03.1 **não executado**, associado a S7/r8; sem ticket linkage, sem review |
| Feriado/greve em S6 | Documento + input F03.1 **não executado**, S6/r7, externo; sem impacto individual demonstrado |
| Pedidos de reconfiguração/notificações | Documento explícito sem autorização externa. Uma flag reversível e catálogo sintético; **zero políticas de execução** |
| S9 23h com amostra/critério incompatíveis | Apenas `future/s9.json`, fora de `initial.json` e de todo carregamento |

Semanas: S1 01–08/09, S2 08–15/09, S3 15–22/09, S4 22–29/09,
S5 29/09–06/10, S6 06–13/10, S7 13–20/10, S8 20–27/10.
Intervalos `[início,fim)` UTC, observação datada pelo fim da semana no documento;
`recorded_at`/ator são gerados pela base na instalação, nunca retrodatados.
A janela de baseline 01/08–01/09 é uma escolha explícita de modelação sintética:
a issue fornece o valor, mas não as datas da amostra de baseline.

Limitação: a cadência não é um campo formal F01. As semanas exigem revisões das
janelas; r1 preserva o contrato global, r2–r9 são recortes semanais explícitos,
não oito renovações comerciais. Para deteção semanal usar **[2,3,4,5,6,7,8,9]**,
excluindo r1. Não se calcula um resultado global fazendo média de medianas.
Instalar apenas após 27/10/2026 UTC: as guardas originais rejeitam medições futuras.

Não existe tabela independente de documentos/contexto antes de uma investigação.
As fontes têm localizadores/digests; os corpos ficam no repositório. A journey não
expõe os inputs F03.1 e a UI não tem leitor desses documentos. O CSV incompatível
é preparado para análise humana; o motor não deteta semanticamente a diferença de
método a partir de texto. Não alegamos que já reconciliou essa contradição.

## Ensaio reproduzível sem serviços públicos

Requisitos: Python 3.12, Docker local e acesso aos pacotes/imagem usados pelos testes.

```sh
bash recovery-mvp/adversarial-t01/test.sh
```

Cria PostgreSQL 17 descartável em loopback, TLS verificado, migrações F01–F06,
C02 e sessões; preserva seed A/B no ensaio e acrescenta T01 com logins próprios.
Testa a API real por WSGI HTTPS, não um navegador/TLS público. Remove contentor,
base, credenciais e diretório temporário no fim. O teste não deixa T01 ativo.
Não lê credenciais externas nem chama Render, Neon ou Lovable. Os testes de
regressão anteriores mantêm os seus próprios cenários; não operam T01.

Preparação autónoma requer uma instalação sintética existente com esses schemas.
Não executar `managed/provision.py` por cima da demonstração: ele exige base vazia.
Não reaplicar migrações numa instalação já provisionada.

## Preparação do bundle (offline)

Num computador/terminal privado, usar o Python com dependências L01 instaladas.
Os caminhos abaixo são exemplos locais, não credenciais. Diretório pai `0700`,
ficheiros `0600`, fora do checkout. Não colar JSON secreto no chat/issue/terminal
partilhado, argv ou frontend. Não colocar o DSN owner na configuração Render.

`owner.json`: objeto privado com `synthetic_only: true` e `dsn` administrativo
direto da **base pretendida**, `sslmode=verify-full`, CA confiável, sem pooler.
`current-runtime.json`: cópia privada atual de `CENTERWAY_MANAGED_CONFIG`,
`synthetic_only=true`, `demo=false`, sessões PostgreSQL. Ambos devem apontar à
mesma base, incluindo os DSNs individuais e de sessões.

```sh
python3 recovery-mvp/adversarial-t01/seed.py prepare \
  --owner-config /private/t01/owner.json \
  --runtime-config /private/t01/current-runtime.json \
  --output /private/t01/bundle
```

Não consulta a base. Produz três ficheiros privados sem sobrescrever existentes:
`bundle.json` (roles/escopos e fingerprint), `runtime-config.json` (configuração
atual **mais** três contas), `credentials.json` (passwords de login só de T01).
Passwords PostgreSQL e passwords HTTP são distintas e aleatórias; não são emitidas
em stdout. Manter o bundle em custódia privada, pois contém segredos de backend.

| Login | Principal | Permissões HTTP |
|---|---|---|
| `t01_operator` | `cw_t01_operator` | Operações existentes F01–F06; discovery apenas no tenant T01 |
| `t01_reviewer` | `cw_t01_reviewer` | append_investigation e investigate, sem intervenção |
| `t01_reader` | `cw_t01_reader` | Consultas, sem operações |

Todos acedem só ao cliente T01. O reviewer é uma identidade separada, **não** uma
verificação efetuada. Nenhum registo de review é criado. Os logins existentes,
passwords, escopos, CORS, TTL e DSN de sessões são copiados sem alterações.

## Ativação na demonstração — somente após nova autorização

**Não foi executada.** A autorização para este PR não autoriza o procedimento
remoto abaixo. Há duas mudanças separadas: adicionar dados/roles à base existente
e acrescentar contas ao segredo de runtime. É necessário operador com acesso
privado e autorização explícita para ambas e para reiniciar/publicar a release.

1. Confirmar base sintética correta, commit revisto, backup cifrado/restauro e
   exportação privada da configuração atual. Preservar A/B e recibos. Preparar o
   bundle **uma única vez** como acima; guardar cópia privada.
2. Ensaio local: `apply` aceita loopback sem a flag remota. Na demonstração, depois
   da autorização explícita, o operador executará deliberadamente:

   ```sh
   python3 recovery-mvp/adversarial-t01/seed.py apply \
     --owner-config /private/t01/owner.json \
     --bundle /private/t01/bundle/bundle.json \
     --allow-remote-demo \
     --confirm-tenant 110577e9-2d2c-5288-93f2-2ba53f86f074
   ```

   O destino é comparado com o bundle. Sem flag/confirmação, qualquer host não
   loopback é recusado **antes da ligação**. A flag técnica não substitui aprovação.
   Primeira transação: só novas roles/tenant/cliente/memberships/catálogo/flag.
   Segunda: dados iniciais e inputs via principal real `cw_t01_operator`, sem
   deteção/discovery/investigação/intervenção/verificação. Retomada usa o MESMO
   bundle, verifica conteúdo/ACLs e não regrava linhas. Falha entre fases pode deixar
   apenas o provisionamento; reexecutar o mesmo bundle é seguro após inspeção.
3. Reexportar a configuração privada atual para confirmar que ninguém a alterou:

   ```sh
   python3 recovery-mvp/adversarial-t01/seed.py check-activation \
     --runtime-config /private/t01/current-runtime-fresh.json \
     --bundle-dir /private/t01/bundle
   ```

   O comando é offline e recusa drift ou alterações além das contas T01. Se falhar,
   não sobrescrever utilizadores/configurações mais recentes; reconciliar com revisão
   do operador. Nunca repetir `prepare` para mudar passwords de roles existentes.
4. Só após essa verificação/autorização, atualizar **apenas** o segredo de runtime
   existente `CENTERWAY_MANAGED_CONFIG` com o ficheiro candidato, sem DSN owner.
   Preservar o override CORS existente `CENTERWAY_BROWSER_ORIGINS`; nenhuma mudança
   de DNS/origem/frontend é necessária. Reiniciar a release da base M68 com o novo
   segredo. Este PR não necessita de código web novo para servir os dados.
5. Entregar privadamente as passwords de `credentials.json` ao utilizador, testar
   login/diretório/journey T01, negação A/B↔T01 e logout; comparar snapshots A/B e
   recibos com o backup. Não abrir links com tokens/passwords em parâmetros.

Reversibilidade: a transação de dados falhada reverte atomicamente. Depois de
commit, histórico/tenants são append-only: **não há DELETE/reset do seed** e não se
deve desativar triggers. Pode retirar as três contas da configuração e reiniciar,
invalidando as suas sessões; para bloquear também conexões DB dessas contas, um
operador autorizado aplica NOLOGIN e termina apenas as suas sessões, preservando
histórico e A/B. Isto suspende acesso, não apaga T01. Para um ensaio descartável,
remover a base/contentor privado inteiro é a limpeza adequada. Restauro nunca por
cima da instalação pública sem um plano/aprovação separado.

## Checklist humano: links e ações efetivamente disponíveis

URL existente registada na aceitação M68; **não contactada nesta missão**:
[Iniciar sessão](https://value-recovery-radar.lovable.app/app).
Após ativação futura, entrar como `t01_operator` com password entregue privadamente.
A empresa é selecionada automaticamente por ser única no escopo; o seletor atual
mostra `Empresa · 110577e9`, não o nome completo da empresa. O diretório mostra o
nome real persistido da fixture, **Meridian Distribuição**.

- [Clientes](https://value-recovery-radar.lovable.app/app/clientes) e
  [Meridian](https://value-recovery-radar.lovable.app/app/clientes/073b083a-e6f1-590a-882b-063dfac5f1da):
  consultar jornada e próximas etapas/bloqueios F06; não cria cliente nem observação.
- [Contratos](https://value-recovery-radar.lovable.app/app/contratos): consultar
  contrato, versões, evidências projetadas e ausência de deteção. **Não há botão
  ativo para executar `detect`**, editar contrato ou importar tickets.
- [Investigações](https://value-recovery-radar.lovable.app/app/investigacoes):
  inicialmente vazio. Se uma investigação for aberta manualmente via API/operador,
  a UI permite **Reavaliar investigação**; se houver relatório, também **Pedir
  intervenção sintética autorizada**, com confirmação e revalidação do servidor.
  Não há formulário UI para abrir investigação, fatores, evidências ou reviews.
- [Intervenções](https://value-recovery-radar.lovable.app/app/intervencoes): consultar
  decisões/execuções. Reversão sintética só aparece quando existe execução. Não se
  espera nenhuma execução T01 com esta preparação; zero políticas foram concedidas.
- [Recuperação](https://value-recovery-radar.lovable.app/app/recuperacao): inicialmente
  vazio. Só permite **Reavaliar recuperação observada** de um plano já existente;
  não cria plano, janelas ou resultados posteriores.
- Atualizar dados, navegar, terminar sessão e alternar para contas reader/A/B são
  ações manuais disponíveis. Não há replay automático de POST; resposta incerta
  conserva request_id apenas no draft em memória. Refresh exige novo login.

**Não é possível percorrer F01–F06 integralmente só pelos botões atuais.** Isso é
uma capacidade ausente, não uma falha a disfarçar com seed pré-executado. O seed
para exatamente na próxima etapa `detect`. Para avançar, é necessário passo manual
via API L01/operador, explicitamente escolhido pelo utilizador. A API não tem console
arbitrária na UI. Não criámos uma nova UI nem automatizámos esses passos.

Exemplo de pedido manual futuro `POST /v1/tenants/110577e9-2d2c-5288-93f2-2ba53f86f074/clients/073b083a-e6f1-590a-882b-063dfac5f1da/operations`,
Bearer da sessão em canal privado, JSON abaixo **não executado**; substituir UUID e
instante por valores reais do pedido. Guardar ambos para retry idêntico:

```json
{
  "request_id": "<UUID novo do pedido>",
  "operation": "detect",
  "arguments": {
    "contract_id": "6bc03825-1d3d-5570-9fd9-1e182e3c8379",
    "revisions": [2,3,4,5,6,7,8,9],
    "as_of": "<instante UTC atual, posterior ao seed>",
    "required_periods": 2
  }
}
```

Só depois de ler o recibo/journey real, decidir entre `open_investigation` (ids reais,
contract_revision 7 para S6 ou 8 para S7, pergunta explícita) e `discover_company`
(com escopo administrativo HTTP T01 e corte atual). Discovery **executa F03** e não
faz parte do seed. S7 parcial pode impedir o encaminhamento automático do input
interno; não mover o log de 14/10 para S6 para obter um match. Nenhuma destas ações
foi executada em T01. Contratos completos: `../api/openapi.json`,
`../ORCHESTRATION.md`, `../INVESTIGATION.md`, `../DISCOVERY.md`.

Sem verificação suficiente, a investigação deve continuar inconclusiva. O cenário
não contém autorização externa nem reviews: não conceder autorização para obter
um resultado favorável. `future/s9.json` só pode ser revelado manualmente após o
ensaio inicial; não é um POST pronto. S9 termina em 03/11, ultrapassa o prazo global
original e pode anteceder a intervenção humana. Exige nova janela/revisão legítima
e tratamento explícito da incompatibilidade; não é evidência F05 causal ou um
resultado de recuperação já disponível. Nem UI nem seed fazem essa introdução.

Critérios a observar (não conclusões executadas): distinguir piora relativa S4–S6
de deterioração abaixo da baseline de 40h; manter S7 incerta; nunca traduzir adoção
em valor, coincidência em causa ou processamento de pedido em recuperação. Os
valores fornecidos são inferiores a 40h mas superiores a 24h: não mudar a baseline
para forçar `deterioracao_demonstrada` ou uma intervenção.

## Validação e limites da entrega

Suite nova: 11 testes PG17/TLS/API real, cobrindo seed sem antecipação, retomada entre
fases, rollback, repetição concorrente, privacidade da saída CLI, hashes/versões,
qualidade S7, rejeição CSV incompatível, ausência de zeros, sessões/logout,
permissões, RLS, negação de self-authorization, colisões/drift e snapshots completos
A/B incluindo recibos. Ensaios temporários, sem alteração do Neon público.

Suites anteriores: 97 backend + 11 managed; frontend 189 aprovados e um teste público
opt-in omitido. TypeScript sem erros. Consulte o PR/commit para CI verificável.
O teste público omitido não é falha nem prova hosted. A nova CI executa só recursos
locais e não tem segredos de deploy; não há upload de bundles ou credenciais.

Preparação/local testados. **Ativação pública, login humano T01, jornada operada e
aceitação manual ainda não realizados.** Não há garantia de produção, disponibilidade
contínua dos planos gratuitos ou prova causal. US$0 de infraestrutura nova e zero
créditos Lovable utilizados nesta missão.
