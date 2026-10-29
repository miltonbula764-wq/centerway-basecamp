# C03 — infraestrutura gratuita (fontes consultadas em 2026-10-29)

Recomendação **condicionada à elegibilidade e capacidade**: Oracle Cloud Always Free,
uma VM A1 Flex ARM64, **1 OCPU, 4 GB RAM, boot de 50 GB**, Ubuntu 24.04 LTS ARM64,
PostgreSQL 17 em Docker, Python 3.12 e Caddy. É um dimensionamento inicial para poucos
utilizadores e dados sintéticos, não um benchmark de carga. Não foi criada conta nem
reservada capacidade. Se não houver A1 gratuita, parar; não trocar automaticamente
para uma shape paga ou contratar outro fornecedor.

A [documentação Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
indica atualmente 1.500 OCPU-h e 9.000 GB-h/mês (2 OCPUs/12 GB no total), na home region,
200 GB de volumes combinados e cinco backups de volume. A1 pode estar sem capacidade.
Instâncias pouco utilizadas podem ser recuperadas pelo fornecedor após sete dias.
Não gerar carga artificial para evitar essa regra. Os recursos gratuitos não são uma
garantia de disponibilidade; quotas existentes da conta também contam. O plano proposto
consome até 744 OCPU-h e 2.976 GB-h num mês de 31 dias, além dos 50 GB de boot.

**Não usar o limite antigo de 4 OCPUs/24 GB.** Há divergência com a
[tabela de preços](https://www.oracle.com/cloud/price-list/), que ainda mostra limites
anteriores: antes de qualquer criação futura, confirmar Console → Limits, Quotas and
Usage, estimativa de custo e etiqueta elegível. A documentação de
[fim do trial](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm)
também especifica 2 OCPUs/12 GB; crédito temporário não é Always Free. PostgreSQL será
self-hosted; Autonomous Database/MySQL gratuitos não substituem PostgreSQL nem os motores.

A [FAQ Oracle](https://www.oracle.com/cloud/free/faq/) exige informação válida, limita
as contas gratuitas por pessoa e descreve validação do cartão (possível bloqueio
bancário temporário). Inscrição/identidade, país, home region e capacidade precisam de
confirmação pelo titular. Conta abandonada pode ser suspensa. O titular deve proteger
a conta com MFA, sem partilhar credenciais. Não foi testado o painel num telemóvel real.

## Alternativas

| Opção | Compatibilidade e persistência | Limitações e custo zero | Administração móvel |
|---|---|---|---|
| Oracle A1 Always Free | VM Linux ARM64 permite PG17, logins individuais, SQLite persistente e Caddy existentes | Recomendação condicional; falta de capacidade, recuperação por inatividade e manutenção própria; sem promessa de SLA | Console no navegador + SSH com chave; SSH é necessário para instalar/operar |
| Oracle E2.1.Micro gratuita | x86, apenas 1 GB/VM e CPU fracionada; mesma stack em princípio | Muito pouca margem para instalação, PG e testes simultâneos; não dimensionada nem validada nesta entrega | Mesmo modelo de administração; duas VMs aumentariam a manutenção |
| Google Cloud Free Tier e2-micro | VM/persistência permitem a arquitetura; pouca RAM | Regiões específicas e quotas pequenas; IPv4 público não cabe de forma contínua no US$0 da rota direta; não adotada | Console/SSH pelo navegador ou cliente móvel |
| Render Free | Python e HTTPS geridos; filesystem gratuito não persiste SQLite | Base gratuita expira em 30 dias; disco persistente exige plano pago; incompatível com persistência L01 sem redesenho | Painel simples, mas limitações continuam |
| Host já existente + Caddy ou túnel nomeado | Preserva toda a stack e disco; evita nova conta cloud | Nenhum custo incremental de VM se já existir; energia, Internet e domínio não são automaticamente gratuitos; disponibilidade do host é necessária | SSH; túnel pode ajudar sob CGNAT, mas exigiria ativação futura separada |

Fontes: [Google Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features)
(e2-micro em três regiões dos EUA, disco standard 30 GB, tráfego limitado),
[preço de IPv4 Google](https://cloud.google.com/vpc/network-pricing)
(US$0,005/h em VM standard, apenas uma hora gratuita/mês),
[Render Free](https://render.com/docs/free), e comparação de túneis em
[RESEARCH C01](../infra/RESEARCH.md). Uma opção com créditos que expiram não é apresentada
como solução gratuita permanente.

## Arquitetura ARM e versões

O [índice oficial PostgreSQL](https://github.com/docker-library/official-images/blob/master/library/postgres)
e os manifests das imagens fixadas anunciam linux/amd64 e linux/arm64. Consultámos os
manifests reais via `docker buildx imagetools inspect --raw`: ambos os índices PostgreSQL
em versions.json e Caddy em ../infra/versions.env contêm ARM64. A extração C01 seleciona
a arquitetura do host. Isso confirma publicação dos artefactos, **não execução ARM**.
Python/venv e wheels psycopg precisam de instalação nativa nesse host; falha de pacote
não autoriza mudar versões sem revisão. Execução desta missão: Linux x86_64 local/CI.

## Proteção do orçamento

Alvo **US$0 incremental**, sujeito à conta elegível e aos limites. Nenhum custo foi
contratado. Não fazer upgrade da conta para obter capacidade, não usar créditos como
prova de gratuitidade, não criar DB gerida, balanceador, NAT gerido, imagem licenciada,
backup fora de quota ou serviços auxiliares. Alerts de orçamento avisam; não são um
limite rígido de despesa. Se no futuro houver conta paga, excesso pode ser cobrado.
Quotas e permissões administrativas devem impedir expansões não autorizadas.

O domínio getcenterway.com é um requisito fornecido, não foi verificada titularidade,
DNS ou renovação. Custos já existentes de domínio, Internet, backups externos e trabalho
operacional não são garantidos em US$0. Usar DNS já autorizado futuramente, sem contratar
uma zona paga nesta missão. Revalidar preços e elegibilidade imediatamente antes de uma
nova missão de ativação.
