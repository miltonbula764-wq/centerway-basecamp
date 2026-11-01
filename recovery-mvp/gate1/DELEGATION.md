# T03-G6 — delegação operacional

Base PR #80/900cc4c. Preparação, não backup/restauro reais. Preservar GATE1_FINAL.md.

Já existiam export PG17/TLS→age, snapshot, restauro Docker sem rede, validação de
identidade/permissões/sessões e stream Android sem chave remota. Foram reutilizados.

## Executado nesta missão

- Leitura integral dos contratos; Codespaces API recusou403 e gh reportou identidade
  CLI inválida. Não existe ferramenta de execução Codespaces no conector GitHub ou
  binding remoto neste ambiente. Não contornar essa recusa.
- Neon free_v3 confirmado, 1/10 branches, quotas efetivas500MB/1GB/100CU-h. Nenhum
  recurso/credencial criado; não repetido hardening cloud_admin descartado.
- Drive pasta só owner; upload sintético91bytes, readback/download materializado
  idêntico byte a byte, eliminação e404 confirmados. Nenhuma identidade aberta.
- Sete testes novos de orquestração/guardas e um integrado PG17/age do baseline
  passaram localmente. CI do PR executa regressões obrigatórias sem secrets reais.

## Uma entrada Android, duas fases do mesmo procedimento

No checkout privado do SHA revisto deste PR:

```sh
bash recovery-mvp/gate1/android_gate1.sh prepare --reviewed-sha SHA_COMPLETO_DESTE_PR --identity /privado/identity.age
```

O wrapper instala apenas dependências Termux ausentes: python/git/gh/openssh/age.
Se necessário abre login oficial GitHub no browser do titular; não enviar tokens.
Pacote gh oficial: https://github.com/termux/termux-packages/blob/master/packages/gh/build.sh

Seleciona um Codespace existente Available do repo; ambiguidade exige --codespace
NOME. Não cria/inicia/redimensiona recursos. Não altera checkout/main remoto:
envia git archive revisto a staging privado novo, sem symlinks/path traversal.
Cria venv, instala dependências pinadas, reutiliza instalador G2 para PG17/age se
faltarem (Ubuntu24; outro SO falha), confirma Docker LOCAL e hashes de scripts.
Testa SSH com nonce e dados sintéticos, sem acesso PostgreSQL. Só age-keygen -y NO
ANDROID lê a identidade: apenas o destinatário público é enviado ao staging.
Guarda recibo privado com SHA, fingerprint, staging e prova SSH para retoma.

O agente não executou SSH real:403/identidade são bloqueios reais; testes mock não
substituem essa prova. Falha tenta remover/conferir só o staging novo; se não
conseguir, comunica remote_cleanup_unconfirmed. No fim do restauro confirmado,
remove/confere staging. Nenhuma prova de limpeza remota é inventada.

Após export autorizado, Drive/novo download e fingerprint ORIGINAL do executor:

```sh
bash recovery-mvp/gate1/android_gate1.sh restore --receipt /privado/receipt-DO_PREPARE.json --archive /privado/retorno --identity /privado/identity.age --expected FINGERPRINT_ORIGINAL
```

Não calcular expected apenas do download. A mesma entrada confere bundle,
destinatário e código remoto, autentica age local e transmite em RAM ao restauro
G2. Nunca envia chave/passphrase. A presença do titular para login e decifragem é
inevitável com a chave exclusivamente Android; não há instalação/SSH/SQL manual.

## Baseline pré-grants automatizado

Antes da role/grants, só na filha identificada pelo conector:

```sh
python recovery-mvp/gate1/capture_baseline.py --config /privado/owner-read.json --binding /privado/child-binding.json --destination /privado/pre-export.age --recipient CHAVE_PUBLICA_CONFERIDA
```

Binding gerado de metadados API: branch_id,parent_id,primary,default,endpoint_id,
host. Não é flag de aprovação: validar IDs pelo plano de controlo. Helper confere
não-primary/default/parent=child, endpoint/DSN/TLS, lê em transação read-only e cifra
em RAM hashes/estrutura, atributos e memberships de roles SEM passwords. Só grava
ciphertext privado. cw_owner faz inventário, nunca export. Credenciais reais não
foram criadas nem solicitadas nesta missão.

## Capacidade e bloqueios reais

| Operação | Situação |
|---|---|
| Gestão Neon por conector | Disponível; escrita só após pré-requisitos/autorização aplicável |
| Upload/download/eliminação Drive | Comprovado com sintéticos deste workspace; pasta privada |
| Comandos Codespaces do titular |403/CLI inválida; OAuth GitHub não equivale a gh/SSH |
| Decifragem real | Exclusivamente Android, nunca pedir identidade/passphrase |
| BYPASSRLS limitado Neon | Ainda não testado após bloqueio anterior; sem fallback admin |
| ACLs iguais à origem | Baseline pré-grants e reconciliação do delta; não presumir pelo dump |

Para delegação total, disponibilizar ao ambiente acesso suportado de execução,
autenticação e egress ao Codespace, sem tokens no chat. Sem isso, a entrada Android
prepara o executor existente. Não atribuir acesso inexistente ao agente.
O conector Drive não liga automaticamente o disco Codespaces a este workspace:
precisa materialização autenticada do ciphertext ou upload pelo Android. Essa
fronteira ainda não foi validada; roundtrip deste teste não saiu do Codespace.
Quota Drive não exposta pelo conector: conferir espaço antes do export, sem compra.

## Sequência Gate1

1. Comprovar prepare/SSH sintético ou habilitar execução remota ao agente; conferir
   fingerprint público e quota/custódia. Não repetir suites gerais manualmente.
2. Confirmar autorização Gate1 com risco LO exclusivamente na filha (G5), sem
   ativar workflows bloqueados ou criar recursos antes das condições.
3. Filha Free0,25CU; binding/LSN/pre-export.age; role SQL efémera<=1h sem
   neon_superuser; provar BYPASSRLS e acessos/negações, ou interromper e limpar.
4. Export PG17/TLS→age; exits/checksums/baseline e permissões originais preservados.
5. Custódia Drive/novo download/hash original; restore pela mesma entrada Android.
6. Revogar/testar login recusado, eliminar filha/compute, conferir ausência e
   comparar origem antes/depois. Só então avaliar conclusão Gate1.

Nenhum backup real, credencial nova, recurso Neon, alteração Render/Lovable/main,
chave remota, workflow sensível ou serviço pago nesta preparação.
