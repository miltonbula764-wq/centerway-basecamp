# CENTERWAY — auditoria Work Mode e candidato integrado

Auditoria iniciada em 30 de outubro de 2026 (Africa/Luanda). Apenas dados sintéticos.
Este documento descreve preparação técnica; não autoriza produção nem prova um piloto.

## Fontes e estado confirmado

Backend: base `b08ca056fae0ad037b029552eb348858598f4edc`, PR #62.
A branch `recovery-mvp/work-mode-integration` contém toda a cadeia por ancestralidade.
Não exige fazer merges para executar o conjunto. `main` permanece em
`d764f893ea47448836f8a64f1b8660fdd3b0a143`; nenhum merge foi realizado.

| PR | Missão | SHA de cabeça auditado | Estado na consulta |
|---|---|---|---|
| 49 | F01 | 2a06c4746a85a36cbc3899306591454f57640886 | aberto |
| 50 | F02 | 45f755514c6de1c839a2c4ca2c88d594d095194f | aberto |
| 51 | F03 | 9d0a28ea32319e04c53fe3a9cd11c3ae20bdb4e3 | aberto |
| 52 | F03.1 | 074630fc43b7000639df0c6670fda0a00da06bcf | aberto |
| 53 | F04 | 9f964c2ad7396f355adfb1f03bec685f2890d5b7 | aberto |
| 54 | F05 | 1523a18f382a48c119f96bc95c67bcd0b0c3cbe9 | aberto |
| 55 | F06 | c4d975642dbee08734cf76d5f85f6634a0d866aa | aberto |
| 56 | L01 | d32c6e862bcca1c281e96c6bf845d74afbe8602a | aberto |
| 57 | C01 | 3b9d3a2315aaa5562360ab3b2e248a4c9937df2d | aberto |
| 58 | C02 | 9d8c124dd6623d562d4867fa0a57085b0aa188bd | aberto |
| 59 | C03 | eeae52ef4d1fbf3bdc524299203098fe75f6badd | aberto |
| 60 | Issue de handoff | não é pull request | aberta |
| 61 | L03-PREP | 503eb0ea176f0e33ee1f06534a21488de3b60535 | aberto |
| 62 | C04-PREFLIGHT | b08ca056fae0ad037b029552eb348858598f4edc | aberto |

Frontend canónico: Lovable `d355ef56-6d8c-4f6a-9294-a32f2a9919df`,
Value Recovery Radar, workspace Suzana's Lovable, plano Pro. SHA L04 confirmado:
`55ae6182e54974f25157c5300946c4920069cde5`.
Correções desta auditoria: `c0b880f46e32a3ce197c380ec762ab60ab229230` e
`149ee23a60618b577e9535ce8c121d34813741a2` (snapshot usado pela nova suite).
A aplicação continua a importar a demonstração; não foi ativado o transporte live.
A integração não devolveu saldo de créditos. Os dois trabalhos de correção custaram
4,6 e 1,5 créditos, respetivamente: 6,1 no total. Nenhuma infraestrutura foi contratada.

## Defeitos reproduzidos e corrigidos

O L04 permitia que uma resposta de login tardia restaurasse `authenticated` depois
de logout. Login não verificava a geração depois dos awaits; logout só limpava dados
após a resposta. O transporte podia instalar token antigo ou apagar token novo após
401 antigo. Foram corrigidos controller e transporte, com limpeza imediata, revogação
usando token capturado, geração de credenciais e rejeição de respostas antigas.
O TTL do controller deixa de acrescentar o tempo de leitura de GET /v1/session.

Os 10 testes novos de lifecycle foram executados independentemente contra L04:
10 falhas. Após a primeira correção, 177/177 passaram. A auditoria encontrou então
uma regressão de classificação: o 401 de login atual era convertido em stale_response.
A segunda correção preserva HTTP 401/invalid_credentials e acrescenta outra regressão.
Resultado local final: 178/178 testes, TypeScript sem erros e build aprovado.
Instalação inicial por npm sem reescrever bun.lock. Repetição independente com Bun
1.4.4 e bun install --frozen-lockfile: 178/178, tipos e build aprovados; Vitest
4.1.11 resolvido pelo lockfile. Nenhuma alteração ao bun.lock foi necessária.

As 71 capturas frontend/backend são iguais como JSON. Validação offline de schema,
versão e hashes dos contratos passou. LOVABLE_HANDOFF.md e BROWSER_HANDOFF.md foram
lidos e comparados com HttpTransport/SessionController. O indicador demo=false continua
sem certificar dados reais. Nenhuma hipótese foi promovida a causa.

## Prova acrescentada no PR #64

`recovery-mvp/compatibility/` guarda quatro ficheiros TypeScript exatos da Lovable
como fixture de compatibilidade, com SHA de origem e hashes SHA-256. Não é um frontend
alternativo nem código importado pela API. O build de teste apaga apenas tipos via
Node 24 e adapta extensões de import; não reimplementa o transporte ou o mapper.

Chromium aplica CORS de verdade, com fetch nativo, HttpTransport/SessionController,
API Python, Caddy/Gunicorn TLS e PostgreSQL reais. Não existem rotas/fetch simulados.
Apenas os certificados efémeros da demonstração são confiados por pin SPKI explícito;
não há ignore_https_errors, bypass de CORS ou confiança pública presumida. Python
verifica também hostname e cadeia CA antes do teste. Esta é uma prova local em Actions,
sem backend público e sem interface Lovable hospedada a chamar a API.

Cobertura: login/logout e armazenamento vazio; diretório/jornada; isolamento e
permissões; operação e replay/conflito com auditoria única; origem não autorizada;
expiração; PG indisponível com 503 legível; gateway indisponível com erro opaco;
percurso F01–F06 sintético completo, verificação inconclusiva/completa sem causalidade;
replay da intervenção sem execução duplicada; credenciais inválidas com HTTP 401.

Reprodução em Linux descartável com Docker local, Python 3.12, Node 24 e OpenSSL:

```bash
./recovery-mvp/browser/test.sh
bash recovery-mvp/compatibility/test.sh
```

O primeiro comando repete os 97 testes backend existentes. O segundo instala
Playwright/Chromium e executa os oito testes duas vezes com stacks descartáveis
independentes (oito testes únicos, não dezasseis funcionalidades). Instalação pode precisar de permissões
para dependências de sistema e acesso aos registos oficiais. Os testes só criam
listeners loopback e removem os seus containers/volumes/segredos descartáveis.
Não usar estes scripts sobre dados de produção.

## Decisão de infraestrutura

Comparação consultada em documentação oficial em 30/10/2026. Capacidade e elegibilidade
precisam de confirmação no painel antes de qualquer contratação.

| Opção | Recursos/limites relevantes | Compatibilidade atual | Decisão |
|---|---|---|---|
| Oracle A1 Always Free | quota total 2 OCPU/12 GB; 200 GB volumes; proposta 1 OCPU/4 GB/50 GB; home region; falta de capacidade e recuperação de instâncias ociosas possíveis | preserva PostgreSQL, identidades individuais, SQLite e Caddy; ARM ainda exige prova no destino | melhor via US$0 se um titular elegível conseguir concluir a conta; ainda não existe VM confirmada |
| Render Free | 0,1 CPU/512 MB; 750 horas/workspace; dorme após 15 min; sem disco persistente; PG grátis expira em 30 dias; domínio/TLS geridos | SQLite perde persistência; precisaria alterar sessões, configuração e fronteira TLS | não adotar como substituição direta da stack atual |
| Koyeb Free | 0,1 vCPU/512 MB/2 GB efémeros; uma instância; dorme após 1 h; sem volumes; PG grátis só 5 horas ativas/1 GB | memória limitada e SQLite não persistente; TLS/proxy exigem adaptação | não adotar como substituição direta |
| VM existente autorizada | Linux, disco persistente, cerca de 4 GB RAM para margem inicial; CPU e armazenamento a medir | preserva arquitetura; operação/backup sob responsabilidade do titular | caminho mais curto se houver servidor disponível |
| DigitalOcean Basic | 1 vCPU/2 GiB/50 GiB SSD/2.000 GiB tráfego: US$12/mês de compute | x86 com Docker, PG local, SQLite e Caddy; margem inicial a medir | alternativa paga concreta, só com aprovação de orçamento total |
| Hetzner CX23 | tabela oficial US$6,49/mês, mais IPv4 US$0,60; 4 GB/40 GB; preço sem IVA | preserva stack em x86; capacidade não confirmada e página assinala indisponibilidade na categoria | alternativa de preço, não prometer disponibilidade nem custo final |

PostgreSQL é self-hosted nas VMs; não existe custo extra de DB gerida nesta proposta.
Caddy oferece HTTPS público automático, dependente de DNS/portas/configuração corretos.
Backups fora do host, impostos, domínio, excesso de tráfego e outros extras não estão
incluídos nos preços de compute. Não se tratam créditos temporários como gratuitidade.

Fontes primárias:
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://www.oracle.com/cloud/free/ (verificação de titular/cartão; sem virtual/prepaid)
- https://render.com/docs/free
- https://render.com/docs/compute-plans
- https://www.koyeb.com/docs/reference/instances
- https://www.koyeb.com/docs/faqs/pricing
- https://www.koyeb.com/docs/reference/volumes
- https://www.digitalocean.com/pricing/droplets
- https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/
- https://docs.hetzner.com/cloud/servers/primary-ips/overview/
- https://www.hetzner.com/cloud/cost-optimized/

A inscrição Oracle anterior não concluída não foi contornada. Não há credencial,
integração de infraestrutura ou servidor disponível confirmado para publicar a stack.
Um titular adulto elegível deve concluir qualquer conta/contrato que assim o exija.

## Próxima ativação, quando existir host autorizado

1. Fixar SHA do candidato, host/região, quotas e responsável. Instalar a stack existente
   com estado privado, sem abrir PostgreSQL/Gunicorn. Validar instalação nativa no destino.
2. Rever a origem publicada exata da interface. O preview devolvido pela integração
   apresentou login Lovable no browser desta auditoria; não foi atravessado. O domínio
   getcenterway.com apresentou erro de ligação neste browser: não prova indisponibilidade
   global nem identifica uma origem live funcional. Não adivinhar slug ou autorizar wildcard.
3. Preparar backup cifrado externo de PG/roles, SQLite consistente e configuração/PKI,
   com restauro num ambiente novo. Definir monitorização de processo, disponibilidade,
   disco, erros e expiração de certificados. Monitorizar /health isoladamente é insuficiente.
4. Configurar DNS/TLS público, origens exatas e firewall. Repetir gates de BROWSER_HANDOFF
   e validar CA pública desde rede externa. Não confiar em X-Forwarded-* para fingir TLS.
5. Só então ligar interface preservada a API em ambiente sintético autorizado; repetir
   Chromium e percurso completo no frontend hospedado, desktop/mobile, incluindo falhas.
6. Autorizar piloto separadamente, com reversão e procedimento de suporte. Publicação
   destinada a clientes reais continua dependente da autorização exigida pelo utilizador.

## Piloto controlado proposto

Começar com uma empresa SaaS e um pequeno conjunto de clientes que ela autorize.
Registar quem aprovou dados, métricas, fontes, objetivo, mínimo e janelas; recolher apenas
o necessário, com política de retenção e eliminação definida. Confirmar proveniência e
separar qualquer demonstração. Primeiro executar observação/deteção/investigação em
modo acompanhado. A F04 atual só tem executor sintético: não oferece intervenções reais
sobre sistemas SaaS. Antes de testar efeitos reais, implementar e autorizar o executor
específico, os limites e a reversão; não chamar um flag sintético de recuperação real.

Critérios do piloto: utilizadores conseguem explicar uma conclusão a partir da evidência;
dados e permissões mantêm isolamento; nenhuma escrita sem autorização; dados ausentes
não viram zero; comparação antes/depois usa janelas e definições compatíveis; recibos e
falhas permanecem auditáveis. Medir tempo de configuração, obstáculos de utilização e
correções necessárias; não inventar metas comerciais ou resultados antecipadamente.
Recuperação observada permanece distinta de causalidade e de retenção comercial.

| Nível | Estado desta auditoria |
|---|---|
| Demonstração técnica local | backend existente e frontend sintético com testes; integração Chromium em validação no PR |
| Demonstração pública integrada | não comprovada; host/TLS/origem pendentes |
| Piloto controlado | ainda não; requer infra, operação, permissões/dados e intervenção adequada |
| Validado com empresas reais | não |
| Produção | não |

### Falha do runner identificada pela instrumentação

No SHA 6177827, o percurso completo recebeu uma falha de transporte após o ensaio
de paragem/reinício. O teste falhou sem retry de comandos. Uma execução seguinte
passou, mas a repetição em a816764 voltou a falhar; os diagnósticos registaram
`net::ERR_NETWORK_CHANGED` no POST. O teste anterior tinha parado/reiniciado Docker,
que recria interfaces virtuais no runner. A explicação apoiada nesses sinais é uma
notificação de mudança da rede do host recebida pelo Chromium durante o percurso.
Não se identificou um erro de negócio, autorização ou contrato nesse pedido.

O ensaio que provoca falhas de infraestrutura passa a correr por último, preservando
a prova ininterrupta do percurso completo. O seu GET de recuperação é consultado até
10 segundos, pois a recuperação após paragem é eventual. Não existe retry de login,
POST, intervenção ou nova chave. A suite continua a exigir duas execuções em stacks
novos. Esta correção organiza o ambiente de teste; não prova disponibilidade contínua
ou rede pública. No destino real, respostas incertas continuam a exigir conservação
do request_id/corpo e revisão explícita antes de qualquer reenvio.
