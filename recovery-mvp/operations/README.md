# Operação C03 — cópia cifrada, restauro e prontidão

Preparação para o perfil **sintético**, privado e de um host já existente. Não é
publicação, configuração de produção ou autorização para dados reais. Não modifica
F01–F06, a API, a PKI ou os scripts C03 anteriores. A conta cloud/VM continua pendente.

## O que o código faz

`recovery.py backup` exige PostgreSQL com paragem limpa e API/gateway parados.
Recusa fazer uma cópia a quente e **nunca para serviços por conta própria**. Copia
o volume PG inteiro (incluindo WAL, roles, permissões e auditoria), o volume de
certificados PG e o estado C03 necessário. As sessões são copiadas pela API de
backup SQLite, não por uma cópia parcial de um ficheiro em uso.

O pacote inclui manifesto, hashes, versão das migrações, imagem por digest,
arquitetura, configurações, PKI e marcadores/recibos do cenário. Configurações e
chaves só saem dentro de um ficheiro **cifrado com age**. O backup aceita apenas
destino novo e privado; nunca substitui uma cópia anterior. A publicação da cópia
é atómica no mesmo filesystem. Nenhum segredo é posto em argumentos ou logs.
A chave pública `--recipient` não é um segredo.

`restore` exige autenticação completa do ciphertext, inventário/hashes íntegros,
formato conhecido, mesma imagem/migrações e mesma arquitetura. Recusa diretórios
existentes, links, travessia de paths e cópias com certificados expirados ou com
menos de cinco minutos de validade. Só depois cria um estado e volumes **novos**.
Não apaga nem reconfigura a origem, não corre seed, não migra versões e não renova
autorizações F04. Os marcadores do cenário preservam a recusa de reexecução.

O restauro inicia exclusivamente PostgreSQL em loopback. API e gateway ficam
parados até o operador os iniciar pelo runtime C03 habitual. As novas portas e
paths são escritos nos DSNs/configuração privados; o conteúdo de negócio e os
recibos conservam identidade. A alteração de binding invalida as sessões antigas:
é obrigatório fazer novo login. Uma sessão revogada não é recuperada como válida.

## Preparação do operador

Requisitos: Linux, Docker local dedicado, Python 3.12 com os requirements L01,
OpenSSL, Caddy fixado da C01 e `age` da distribuição oficial. Em Ubuntu 24.04, a
nova suite instala `age` pelo APT oficial. Docker dá acesso administrativo: o
host deve ser dedicado e o operador deve ter essa autorização.

Gerar uma identidade de recuperação age **fora do Git e preferencialmente fora
do host da aplicação**, no dispositivo/gestor seguro do titular:

```bash
umask 077
age-keygen -o /private/recovery.agekey
age-keygen -y /private/recovery.agekey
```

Guardar a identidade privada num segundo local seguro. O servidor de backup só
precisa da chave pública age1… devolvida pelo segundo comando. Sem a identidade
privada, não há forma prevista de recuperar a cópia. Não a enviar por chat, email,
capturas, repositório ou artefactos de CI. Os testes usam identidades descartáveis.

Os caminhos `/private` são exemplos: o operador deve escolher diretórios locais
privados (0700), fora do checkout. Ficheiros privados são 0600 e pertencem ao
operador. Não criar estes caminhos num serviço público ou pasta partilhada.

## Procedimento de backup autorizado

1. Reservar uma janela de manutenção. Bloquear novas operações e parar a unit
   da API/gateway pelo gestor de serviços autorizado. Esperar pelas operações
   pendentes e guardar os request_id para resultados incertos.
2. Parar a base C03 pelo comando `stop-db` do runtime existente. Confirmar paragem
   limpa. Não executar `docker kill`, apagar volumes ou fazer prune.
3. Executar o backup no venv L01 existente. Substituir PUBLIC_RECIPIENT pelo valor
   público age1… do titular; nunca pela identidade privada.

```bash
/private/demo/venv/bin/python recovery-mvp/operations/recovery.py \
  --caddy /private/demo/bin/caddy backup \
  --state /private/demo --output /private/backups/centerway-001.age \
  --recipient PUBLIC_RECIPIENT
```

4. Confirmar JSON `backup_created` e saída zero. Reiniciar C03 pelo procedimento
   existente; uma cópia falhada não exige reinitializar nem alterar a origem.
5. Copiar **apenas o ciphertext** para armazenamento externo autorizado com
   retenção/custo revistos. A ferramenta não faz uploads, não cria contas e não
   configura retenção remota. Uma cópia que só existe no host não protege contra
   perda do próprio host.
6. Ensaiar restauro periodicamente num destino novo. Data do ficheiro e sucesso
   da cifragem não provam, sozinhos, que o conteúdo pode ser recuperado.

O procedimento a frio implica indisponibilidade; RPO corresponde ao instante da
cópia concluída. RTO não foi medido num servidor público. Uma futura solução de
backup online/PITR exigirá trabalho próprio e autorização, não uma cópia a quente
dos volumes. Não há backup agendado ou paragem automática nesta entrega.

## Procedimento de restauro

Usar apenas backups de origem confiável. Cifragem age protege o conteúdo e deteta
corrupção, mas não certifica quem produziu o backup: alguém com a chave pública
também pode criar um ciphertext. A imagem e os arquivos PostgreSQL executam dados
administrativos do cluster. Não restaurar arquivos de terceiros não revistos.

```bash
/private/tools/venv/bin/python recovery-mvp/operations/recovery.py \
  --caddy /private/tools/bin/caddy restore \
  --archive /private/backups/centerway-001.age \
  --identity /private/recovery.agekey --destination /private/restored-demo
```

Esperado: `restored_private_database`, `login_required=true`; só PG privado iniciou.
Instalar o venv/bin necessários fora do estado ou fornecê-los explicitamente ao
runtime. Iniciar depois com o `runtime.py serve --state /private/restored-demo`
habitual, rever origens, fazer novo login e verificar diretório/jornadas, RLS,
recibos e reenvio **explícito da chave original** quando apropriado.

Numa falha depois de criar recursos, o estado permanece `initializing`, com os
nomes dos volumes/container no manifesto privado. Não há limpeza destrutiva,
retry de restauro, novo seed ou substituição automática. O operador deve inspecionar
e escolher outro destino após compreender a falha. Nunca apontar produção para
um restauro parcial. A origem continua separada.

## Monitorização de prontidão

```bash
/private/demo/venv/bin/python recovery-mvp/operations/recovery.py \
  --caddy /private/demo/bin/caddy probe --state /private/demo
```

Devolve JSON sanitizado e código 0 só quando todos os checks passam:
configuração compatível, container/volumes/bindings privados, PostgreSQL com as
identidades individuais não privilegiadas, integridade SQLite, HTTPS com CA e
hostname verificados, certificados com pelo menos 24 horas e 256 MiB de disco livre.
Esses limiares são mínimos da ferramenta de demonstração, não dimensionamento
de produção. O probe não faz login, não cria tokens, não executa operações de
negócio, não escreve auditoria e não emite alertas para terceiros.

`/health` da API continua a medir apenas liveness. Quando PG está parado, o HTTPS
pode responder e o novo probe continua a devolver `ready=false`. Não é um endpoint
público novo: deve correr no host, com acesso privado, nunca no frontend.

Os templates `systemd/` preparam uma execução por minuto com resultado no journal
local. **Não estão instalados nem ativados.** Rever caminhos, utilizador e
permissões no host autorizado. Não há envio automático de emails ou mensagens.
O operador ainda deve integrar alertas autorizados, verificar cópias externas,
planear renovação/rotação e medir disponibilidade externa. Um probe verde não
substitui testes funcionais, browser hospedado, restauro nem monitorização pública.

## Limites de segurança e compatibilidade

- Perfil C03 com `synthetic_only=true`; não é ferramenta validada para produção.
- Uma arquitetura/versão PG por cópia. Não converte amd64↔ARM64 nem muda SQL/imagens.
- Requer uma janela sem administração concorrente. Não é um lock distribuído.
- Até 2 GiB por arquivo analisado; destina-se ao MVP pequeno. Verificar capacidade
  para cópias temporárias, volume novo e ciphertext antes da janela.
- Temporários em claro existem só em diretório 0700 e são removidos ao terminar.
  Remoção não é garantia de apagamento físico em SSD/snapshots; proteger o disco
  do host e os acessos administrativos. Não sobe temporários para CI artefactos.
- Certificados/autorizações mantêm as datas originais. Backup não é renovação.
- Restauro público, reinício do sistema operativo, armazenamento fora do host,
  alarmes e operação a partir do telemóvel ainda precisam de prova no destino.

## Validação reproduzível

```bash
bash recovery-mvp/operations/test.sh
```

A suite cria PostgreSQL/Caddy/Gunicorn reais, executa o cenário F01–F06, cifra uma
cópia a frio e restaura em outros volumes. Verifica igualdade da jornada, RLS,
login/revogação, uma única execução/recibo, recusa de novo seed, corrupção/chave
errada, destino existente, cópia a quente, ficheiro público, arquivo inseguro,
drift e falhas de prontidão. Nenhum recurso ou ficheiro privado é publicado.
Os resultados de CI devem ser consultados no SHA do PR; esta descrição não os
substitui. A cadeia anterior mantém as suas suites independentes.

Referências primárias:
- https://www.postgresql.org/docs/17/backup-file.html — cópia física completa e paragem.
- https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup
- https://github.com/FiloSottile/age — cifragem e identidade de recuperação.
