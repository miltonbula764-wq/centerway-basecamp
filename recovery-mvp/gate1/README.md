# T03-G2 — export cifrado e ensaio de restauro

Issue #76; base PR #75 (`435c2d4`). Preparação, sem acesso ao Neon remoto.
O sucesso TCP comunicado pelo utilizador não comprova TLS, export nem restauro.

## Auditoria e inventário

- `managed/backup.py`: dump dos schemas centerway/cw_sessions, envelope em memória,
  sessões excluídas, `--no-owner`; depende de roles previamente provisionadas.
  Não é um backup completo para Gate 1 T03.
- `operations/recovery.py`: cópia física fria do perfil C03, volumes/configuração/PKI,
  dependente do ambiente Docker original. Não serve como export do Neon gerido.
- Este módulo é aditivo. Não modifica esses programas, migrations, motores,
  API, T01 ou T02. Inspeção feita sobre SQL versionado e PostgreSQL17 sintético real;
  nenhum catálogo ou segredo da base remota foi consultado nesta missão.

Inventário exportado por pg_dump **sem filtro de schemas ou exclusão de tabelas**:
companies, clients, memberships, source_versions, contract_versions,
evidence_versions, assessment_versions, audit_log, detection_runs, investigations,
investigation_factor_versions, investigation_evidence_versions,
investigation_verification_versions, investigation_runs, discovery_rules,
discovery_inputs, discoveries, sandbox_flags, intervention_catalog,
intervention_policies, intervention_revocations, intervention_decisions,
intervention_executions, recovery_plans, recovery_runs, operation_receipts e
cw_sessions.sessions. Inclui constraints, índices, triggers, funções, policies,
RLS, ownership e ACLs. O inventário é descoberto dinamicamente, incluindo tabelas
adicionais; não fixa 25 recibos nem assume que o baseline remoto permaneceu igual.

Roles e memberships são inventariadas sem passwords. No sandbox todas as roles
recriadas são NOLOGIN/NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS.
ACLs e owners do dump são preservados. O administrador postgres é exclusivamente
local ao sandbox. Os grants de grupo são recriados sem ADMIN OPTION. Não se tenta
reproduzir roles administrativas do fornecedor, passwords ou configuração global.

Sessões **incluídas e comparadas**, mas em quarentena: sem API, rede ou contas de
login no restauro. A promoção futura a runtime deverá invalidar sessões e emitir
novos acessos depois de aprovar uma política própria. Não expor digests ou tokens.
Configuração Render, hashes de login HTTP, passwords PostgreSQL, CORS, DNS, chaves
TLS/age e configurações externas não estão no dump: exigem custódia privada
separada e reconfiguração autorizada. Não declarar recuperação integral do serviço
com apenas este bundle.

## Implementação e limites

`recovery.py export` exige ficheiro privado de configuração, destino novo fora do
checkout em diretório 0700, destinatário age nativo, pg_dump17, endpoint direto e
sslmode=verify-full. Credenciais passam por ficheiro de serviço temporário 0600;
nenhuma password/DSN em argv. O cliente não herda variáveis arbitrárias de secrets.

Baseline e pg_dump partilham snapshot REPEATABLE READ READ ONLY através de
pg_export_snapshot. O baseline calcula contagens e hashes ordenados por tabela;
DDL concorrente não suportado: pausar migrations durante export e ensaio. pg_dump
preserva o snapshot para DML concorrente. Não usar um login runtime para contornar
RLS: a conta de export tem de conseguir ler **todos** os dados necessários. pg_dump
falha se não conseguir desativar a filtragem RLS, em vez de aceitar cópia parcial.
A menor credencial efetivamente capaz de exportar ainda precisa de avaliação
privada; não são criadas roles ou grants na origem por este código.

pg_dump stdout → age stdin; stdout cifrado em ficheiro privado. Verificam-se os
dois códigos de saída, prazo de 180s, tamanho e fsync. Manifesto (baseline/roles/
estrutura/hash do ciphertext) também cifrado. checksums.json contém apenas hashes
dos dois ficheiros cifrados, sem nomes de tabelas, contas ou dados. Falhas removem
staging; nome existente é recusado, sem overwrite. Falhas abruptas do host podem
deixar staging cifrado ou bundle incompleto: os checksums/conjunto de ficheiros
recusam esse bundle, nunca presumir sucesso após interrupção.

Limites conservadores: base até 256 MiB, ciphertext e buffers até 64 MiB por
ficheiro, declaração SQL até 30s, conexão até 10s. Baseline ordenado é apropriado
para esta demonstração pequena, não para bases grandes. Extensões além de plpgsql
e large objects são recusados nesta versão; precisam de suporte/testes explícitos.

`restore` não aceita DSN de destino. Valida paths/permissions/checksums, decifra e
autentica integralmente o dump em memória antes de executar SQL. Cria contentor
PostgreSQL17 no daemon local, `--network none`, sem portas ou bind mounts, limites
512MiB/1CPU/128 processos e PGDATA em tmpfs. Sem credenciais/rota da origem.
pg_restore executa uma única transação; comparação inclui tabelas, constraints,
triggers, índices, schemas, ACLs, RLS, funções e owners. A reconstrução de roles é
verificada, assim como `session_user`/allowed para cada principal e empresa.
O contentor/volumes são removidos no finally; após kill do host confirmar ausência
de contentores `cw-g2-restore-*` antes de repetir. Não é sandbox para dump hostil:
usar apenas export confiável, chave sob custódia e hashes conferidos externamente.

Hash externo deteta perda/corrupção; age autentica ciphertext. Quem conhece a chave
pública pode criar outro arquivo válido: custódia do checksum/identidade do export
é necessária. Não há assinatura de produtor nem proteção contra rollback remoto.

## Execução local reproduzível

Requisitos gratuitos: Python3.12, PostgreSQL17 cliente, age, Docker local e OpenSSL.

```sh
python3 -m venv /tmp/cw-g2-venv
/tmp/cw-g2-venv/bin/pip install -r recovery-mvp/api/requirements.txt PyYAML==6.0.3
PATH=/usr/lib/postgresql/17/bin:$PATH /tmp/cw-g2-venv/bin/python -B -m unittest discover -s recovery-mvp/gate1/tests -v
```

Os testes criam exclusivamente passwords/chaves descartáveis sintéticas, executam
F01–F06 sobre A/B locais, guardam uma sessão sintética e verificam export/restauro,
repetição, dados tardios, falhas e confidencialidade. Não usam o cenário AtlasOps.
A CI nunca recebe secrets reais nem publica bundles/keys. Nenhum ensaio cria
branch/compute Neon. Cliente/servidor17 são verificados; imagem postgres:17-alpine
segue atualizações de manutenção (fixar digest aprovado antes de operação real).

Interface preparada, **não executar na origem remota nesta missão**:

```sh
python recovery-mvp/gate1/recovery.py export --config /caminho/privado/source.json --archive /caminho/privado/export-001 --recipient age1CHAVE_PUBLICA_DO_TITULAR
python recovery-mvp/gate1/recovery.py restore --archive /caminho/privado/export-001 --identity /caminho/privado/identity.age
```

source.json tem campo `dsn`, gerado/guardado somente no executor privado; não copiar
para chat, commits ou argumentos. A CLI só publica códigos fixos ou resultado agregado.

## Workflow sensível: bloqueado por construção

`recovery-mvp-gate1-backup.yml` é apenas workflow_dispatch. O job de segurança falha;
o job de export tem **if literal false**, sem input ou variável que o possa ativar.
A exceção TCP anterior não o desbloqueia. Não existe revisor independente e não há
prova de controlos compensatórios suficientes. Nenhum secret/environment é criado.

Uma futura alteração revista/autorizada precisa comprovar: SHA aprovado e branch
restrita; proteção de environment sem bypass; revisão independente OU substituição
explicitamente autorizada apoiada em evidências (auditoria da conta, MFA, mudanças
protegidas, credencial temporária limitada, logs debug desativados, verificação do
código executado e do destinatário). Autorrevisão e uma variável “approved” não são
provas. Se não for possível, usar terminal privado do titular já autorizado; não
passar secrets a Actions. O bloqueio literal só sai com nova revisão de código.

O job preparado exporta com config secret, destinatário público e artifact cifrado
por um dia; isso é **transferência temporária**, não custódia durável. Sem seleção
externa/cópia confirmada/decifragem, Gate1 permanece fechado. A chave privada nunca
entra no workflow. O restauro real ocorre no executor privado do titular com Docker
isolado; não requer enviar a chave privada ao GitHub. O registo de dispatch na
branch predefinida continua dependência autorizável, sem alterar main aqui.

## Destino privado durável e Android — pesquisa em 2026-11-01

Preferência prática: Google Drive **já existente**, se houver quota suficiente,
com pasta privada sem links partilhados, MFA e export sempre age. Alternativa:
Proton Drive Free, com cifragem de fornecedor adicional. Ambos têm Android/download;
não selecionar trial/pedido de cartão nem plano pago. Nenhuma conta foi criada.

| Opção | Gratuito e limites | Administração/custódia |
|---|---|---|
| Google Drive existente | Até 15GB, partilhados com Gmail/Photos; confirmar quota real | Android familiar; guardar apenas ciphertext; MFA; atividade regular; não presumir 15GB livres |
| Proton Drive Free | 2GB iniciais; até 5GB mediante ações de boas-vindas | Android; end-to-end adicional; manter conta ativa; recuperar ficheiro e testar decifragem |
| Actions artifacts | Expiram; acesso sujeito a GitHub/repo público | Apenas transferência temporária, nunca destino de backup |

Fontes oficiais:
[Google quota](https://support.google.com/drive/answer/6374270?hl=en),
[Google inatividade](https://blog.google/innovation-and-ai/technology/safety-security/updating-our-inactive-account-policies/),
[Proton quota](https://proton.me/support/more-storage-proton-drive),
[Proton Android](https://proton.me/support/set-up-proton-drive),
[Proton inatividade](https://proton.me/support/inactive-accounts).
Os planos gratuitos não oferecem custódia imutável/SLA de backup; quotas e condições
podem mudar. Revisão mensal de quota, acesso e download; manter segunda cópia offline
cifrada em armazenamento existente. Retenção proposta: últimas 7 exportações e 3
mensais, dentro da quota, sem eliminar a última cópia restaurável antes de validar
sucessora. Sem contratação automática se o espaço acabar.

Menor sequência humana posterior:

1. Escolher pasta privada num serviço existente e confirmar quota/MFA. Sem links
   públicos. Guardar checksum e referência da execução em registo privado.
2. No dispositivo privado, gerar `age-keygen -o identity.age` e extrair somente
   `age-keygen -y identity.age`. Chave privada com cópia offline separada; nunca no
   runner/ChatGPT/GitHub. No Android pode usar terminal confiável com age instalado;
   instalação/operação Android ainda não testada nesta missão. Não fotografar chave.
3. Aprovar executor/controlo de credenciais após revisão. Depois da autorização de
   export real, descarregar ciphertext, copiar para pasta privada e confirmar hash;
   verificar download e restauro isolado no executor privado. Só declarar custódia
   após essa prova. Nada disso é realizado por esta entrega de engenharia.

Destino, chave pública e controlos sensíveis continuam pendentes. Gate1 T03 não
concluído; nenhuma publicação/ativação T01/T02, zero Lovable/serviços pagos.

Validação local confirmada: 14 testes aprovados com Python3.12, pg_dump17.11,
age1.2.1 e PostgreSQL17 em Docker; actionlint1.7.7 e git diff --check aprovados.
Inclui restauros reais sintéticos, falha durante publicação do bundle, baseline
adulterado, snapshot com escrita concorrente e limpeza do sandbox. Resultados CI
são registados no PR no commit exato; não equivalem a export/restauro do Neon.
