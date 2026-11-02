# T03-G7 — diagnóstico SSH e seleção canónica

Base PR #81/e41ae24. Não há prova de SSH Android real nesta entrega.

## Evidência e limites

O titular reportou listagem válida, solid-train Available e GET individual404.
Ainda não forneceu o campo name completo, URL exato do404 e versão gh Android.
Portanto a causa desse404 específico NÃO ESTÁ COMPROVADA; não atribuir culpa ao
scope, conta, identificador ou versão sem esses dados. Neste executor a listagem
real continua403, sem identidade CLI Codespaces configurada ou ferramenta remota.
A autenticação concluída no Android não se transfere ao agente por OAuth do conector.

Código oficial gh2.46.0 (instalado neste executor) verificado:
- list --repo usa GET /repos/OWNER/REPO/codespaces.
- ssh -c VALOR passa VALOR diretamente a GET /user/codespaces/VALOR; não expande
  rótulos/prefixos. A consulta de conexão acrescenta internal=true&refresh=true.
- A versão oficial2.103.3 consultada mantém a consulta de conexão com esses flags.
  Não há prova de incompatibilidade da versão Android, que ainda é desconhecida.
- Listagem e GET básico documentam codespace scope para tokens classic/OAuth e
  Codespaces(read) para tokens fine-grained. Listar não comprova o handshake/tunnel
  SSH. Um404 não distingue sozinho ausência, política ou acesso ocultado.

Fontes primárias:
https://github.com/cli/cli/blob/v2.46.0/pkg/cmd/codespace/codespace_selector.go
https://github.com/cli/cli/blob/v2.46.0/internal/codespaces/api/api.go
https://github.com/cli/cli/blob/v2.103.3/internal/codespaces/api/api.go
https://docs.github.com/en/rest/codespaces/codespaces
https://cli.github.com/manual/gh_codespace_ssh

## Defeitos demonstrados e correção mínima

A automação anterior exigia uma única entrada na listagem, recusando dois Codespaces
mesmo quando só um estava Available. Também só aceitava name exato e escondia todas
as falhas sob operation_rejected. Esses defeitos foram demonstrados por testes;
não se afirma que produziram o404 manual do titular, porque o script parava antes.

Agora a resolução escolhe o único Available, ou resolve um seletor explícito por
name exato, displayName normalizado ou prefixo único. Ambiguidade, Shutdown, nome
inválido e mudança de estado/identidade continuam bloqueados. Nunca inicia Codespace
nem tenta ideal-garbanzo como fallback. O GET básico verifica name/repositório/estado
antes do primeiro SSH e só usa o nome canónico validado, host github.com explícito.

Diagnóstico só de leitura no Termux, com este commit revisto no checkout:

```sh
bash recovery-mvp/gate1/android_gate1.sh diagnose --codespace solid-train
```

Não exige identidade age. O wrapper neste modo não instala pacotes nem abre login.
Prepare também não muda credenciais implicitamente: auth indisponível para, sem
refresh/login automático. A saída tem status,phase,gh_version,name quando resolvido,
selector_resolved e ssh_verified=false. Não contém token/headers/connection payload;
credential_override_present é só booleano, não prova de erro na credencial.
Não usar GH_DEBUG, --verbose, env/printenv ou copiar stdout de GET bruto com conexão.

| Resultado | Decisão seguinte |
|---|---|
| phase=list | API/listagem falhou; sem seleção ou conexão remota. |
| selection ambiguous/missing | Mostrar name/displayName localmente e selecionar entrada única; não adivinhar. |
| phase=canonical_get +404 | Name veio da listagem atual e GET canónico falhou; o rótulo curto já foi eliminado como causa dessa tentativa. Rever acesso/conta/política/estado com GitHub, sem concluir automaticamente qual. |
| canonical_get_verified | GET básico provado; não é prova SSH. Executar prepare sintético seguinte. |
| codespace_ssh_404 | GET básico passou, mas a consulta/conexão do gh falhou; guardar versão/diagnóstico sanitizado. Não contornar usando outro host ou conta. |

Após GET básico confirmado:

```sh
bash recovery-mvp/gate1/android_gate1.sh prepare --reviewed-sha SHA_COMPLETO_DESTE_PR --codespace solid-train --identity /privado/identity.age
```

O rótulo é resolvido por metadados atuais; só o name completo é passado ao SSH.
O mesmo prepare já aprovado faz pacote privado, hashes e teste sintético com nonce.
Um404 na primeira consulta SSH é preservado como causa, sem inventar cleanup falhado.
Se staging já existia, a limpeza continua a ser tentada. Não há mudança no formato
age, restauro, baseline, motores ou workflow sensível; nada real vai ao Neon.

## Autonomia suportada

gh codespace ssh é o caminho oficial de execução. Para o agente usá-lo, a sessão
precisa egress API/tunnel aprovado e identidade CLI Codespaces configurada fora do
chat. Não existe ferramenta equivalente de execução no conector GitHub atual.
Não copiar tokens/identidade age via issues, Actions, Drive ou prompts; não criar
servidor SSH público, proxy alternativo ou workflow como ponte de credenciais.
Sem esse acesso, o diagnóstico/prepare único no Android é a intervenção indispensável.
Não pedir renovação de scopes antes de evidência; não atualizar gh cegamente para
tratar um404. O titular pode enviar só o JSON sanitizado, não tokens/log de debug.

## Validação

Testes específicos simulados cobrem nome canónico/rótulo/ambiguidade, um disponível
com outro desligado, GET404 antes de SSH, erro de conexão separado, regressão da
limpeza, repo/nome alterados, host override e não exposição de connection token.
A execução real do novo diagnóstico aqui retornou codespace_read_403, phase=list,
gh_version2.46.0 e ssh_verified=false. Nenhuma preparação remota, credencial, início
Codespace, operação Neon ou transferência real foi realizada. Gate1 pendente.
