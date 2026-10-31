# Missão 66 — decisão de infraestrutura

Data de consulta: 2026-10-31. Resultado B: publicação bloqueada; alternativa gratuita identificada, ainda não provisionada nem validada no fornecedor.

## Evidências e âmbito

- Base inspecionada: PR #64, commit `705db9cb009ca672aab407c86d82ea5c05614903`; PR #65, commit `8eabdd0b7279a8d16567818b489e407293330179`. Ambos abertos e não integrados.
- Esta alteração contém apenas a decisão de infraestrutura. Não altera produto, autenticação, frontend, configuração ativa ou main.
- Os resultados anteriormente confirmados de CI pertencem aos commits dos PRs #64/#65; não são testes de um deployment público. Não se repetiram as suites para esta alteração documental.
- Nenhum backend público, persistência remota ou integração hospedada foi comprovado. Nenhuma conta, recurso, cartão, contrato ou despesa foi criado nesta missão; nenhum crédito Lovable foi consumido.

## Requisitos reais da stack

| Código inspecionado | Requisito e consequência |
| --- | --- |
| `recovery-mvp/api/app.py` | Flask, psycopg, PostgreSQL com TLS verify-full; identidade por login PostgreSQL individual, rejeição de privilégios excessivos; sessões opacas persistidas em SQLite privado. O disco efémero elimina sessões após redeploy/reinício. |
| `recovery-mvp/infra/gunicorn.conf.py` e `gateway.caddy` | Gunicorn TLS em loopback e Caddy com verificação do upstream. Não pressupor compatibilidade com terminação TLS e cabeçalhos de um PaaS. |
| `recovery-mvp/cloud-demo/bootstrap.sh` e `runtime.py` | Host Linux com Docker, PostgreSQL em volumes persistentes, certificados e estado privados. O limite configurado de 768 MiB para PostgreSQL não é uma medição de consumo. |
| `recovery-mvp/sql/001_foundation.sql` | Criação de roles e isolamento por identidade/RLS. A compatibilidade com privilégios de um PostgreSQL gerido precisa de teste real. |
| `recovery-mvp/operations/recovery.py` | Backup físico cifrado e restauro isolado de volumes Docker. Este procedimento não funciona sem adaptação num PostgreSQL gerido. |

## Comparação das opções

Valores e planos mudam: confirmar novamente no painel antes de criar qualquer recurso. Gratuito não implica disponibilidade contínua ou adequação a produção.

| Opção | Gratuidade, cartão e limites | Persistência, HTTPS e compatibilidade | Decisão |
| --- | --- | --- | --- |
| Render Free + Neon Free | Render permite primeiro deployment gratuito sem pagamento. Neon anuncia US$0 sem prazo e sem cartão: 100 CU-h/mês/projeto, 1 GB/projeto, até 2 CU/8 GB. | Render tem HTTPS e domínio próprio, mas disco efémero; suspende após 15 min sem tráfego. Neon mantém dados PostgreSQL e suspende compute após 5 min; limites de tráfego e restauro curtos. Exige adaptação descrita abaixo. | Melhor candidata para demonstração sintética; não produção. |
| Render Free com PostgreSQL Free da própria Render | Serviço web gratuito recorrente; PostgreSQL gratuito expira em 30 dias. | HTTPS disponível; banco temporário sem backups gratuitos. | Rejeitado como base persistente sustentável. |
| Northflank Sandbox | Pricing anuncia sem cartão, 2 serviços, 2 jobs e 1 banco; documentação de faturação exige método de pagamento para todos. Contradição não resolvida. | Serviços e volumes persistentes documentados, mas inclusão exata no Sandbox precisa de confirmação. Incidente de segurança ainda identificado na consulta, com orientação oficial para assumir comprometimento das variáveis de ambiente. | Não publicar agora nem fornecer segredos. |
| Railway Free | Sem cartão, crédito inicial US$5/30 dias; depois apenas US$1/mês recorrente. Até 1 vCPU/512 MB por serviço e volume de 0,5 GB. | Suporta processos/container, domínio HTTPS e volume; uma configuração continuamente ligada pode exceder o crédito. Armazenamento gratuito não acomoda os dois volumes independentes atuais sem adaptação. | Crédito limitado, não uma VM gratuita ilimitada. Sustentabilidade desta stack não demonstrada. |
| Oracle Always Free | Existe oferta recorrente, distinta do trial; inscrição exige verificação de pagamento. | VM e disco aproximam-se da stack atual; capacidade e elegibilidade não confirmadas nesta conta. | Bloqueada pela restrição de cartão/verificação do titular. |
| Google Cloud Free Tier | Recursos gratuitos limitados exigem conta de faturação; componentes e excedentes podem cobrar. | VM/disco podem executar stack, mas dimensionamento, IP e tráfego exigem controlo. | Incompatível com a autorização atual de zero risco de despesa e sem cartão. |
| Fly.io | Trial limitado a 2 horas de VM ou 7 dias. | Suporta aplicação e volumes, mas a oferta consultada não é alojamento permanentemente gratuito. | Rejeitado para custo zero recorrente. |
| Aiven PostgreSQL Free | Sem cartão, sem prazo fixo; 1 CPU, 1 GB RAM, 1 GB disco, 20 conexões; pode desligar por inatividade com aviso. | Banco persistente com backups; não aloja o processo Python. Privilégios reais exigem prova. | Alternativa de banco ao Neon; não resolve alojamento sozinho. |

Outras exclusões: a documentação atual do Hugging Face exige plano pago para criar Spaces de compute Docker/Gradio, limita portas de saída e não oferece o disco persistente necessário gratuitamente. Alwaysdata Free restringe utilização comercial. HelioHost e Serv00 documentam Python/PostgreSQL, mas não comprovámos os privilégios, TLS e processos necessários; não os tratamos como compatíveis por suposição.

## Recomendação e limite de autorização

Recomendar Render Free + Neon Free para uma demonstração pública exclusivamente sintética. Custo nominal autorizado: US$0, apenas planos Free, sem cartão, sem upgrade, sem serviços adicionais pagos. Na Render, a FAQ documenta suspensão ao exceder determinadas quotas sem método de pagamento; confirmar quotas e comportamento de cada fornecedor no painel. Não prometer serviço contínuo: existem cold starts, quotas, ausência de SLA e limites de recuperação.

A stack atual não é diretamente publicável nesta combinação. A decisão material necessária é transferir sessões duráveis de SQLite para PostgreSQL e substituir o backup físico por um procedimento compatível com banco gerido. Não substituir a autenticação por outro produto nem aceitar perda silenciosa de sessões para aparentar compatibilidade.

Se aprovada a opção, a adaptação deve preservar TTL, revogação/logout, isolamento, digest de tokens e invalidação por configuração; manter o modo atual disponível. Exige ainda empacotamento sem Docker aninhado e validação segura do HTTPS externo, sem confiar em cabeçalhos arbitrários. Provisionar roles de runtime limitadas via SQL: roles criadas pelo painel/API Neon podem receber privilégios incompatíveis com as verificações atuais. Nunca usar a credencial administrativa como identidade de runtime.

## Bloqueio de acesso e intervenção mínima

Não existe conta Render/Neon autorizada e ligada às ferramentas desta sessão. Foram encontrados conectores para ambos, ainda não instalados. Não se tentou contornar esta ausência por credenciais ou sessões de terceiros.

1. Confirmar a opção Render Free + Neon Free e a mudança de persistência/backup descrita.
2. Ligar as integrações Render e Neon a contas Free elegíveis, sem introduzir cartão. O titular aceita os termos diretamente. Não enviar passwords ou tokens na conversa.
3. A partir das ligações, verificar plano, quotas, região e permissões antes de qualquer criação; preparar a adaptação num PR isolado e testar antes de publicar.

Elegibilidade regional e contratual não foi comprovada por um registo real. Os termos Render exigem pelo menos 16 anos e capacidade contratual; não basta cumprir a idade mínima. Neon remete para termos contratuais Databricks. Northflank também exige não ser menor na jurisdição; Railway prevê consentimento do responsável nos casos indicados nos seus termos. Quando necessário, a conta deve ser gerida por titular adulto legalmente elegível. Não contornar estas exigências.

## Critérios antes de declarar publicação

- URL HTTPS externa acessível, certificado válido, readiness e login reais.
- Roles restritas e isolamento entre empresas verificados no banco remoto.
- Dados e sessões mantidos após reinício/redeploy; migrações sem privilégios administrativos no runtime.
- Backup cifrado, restauro isolado e verificação funcional no novo modelo.
- Quotas e falhas de suspensão/reconexão testadas, sem mecanismo artificial para contornar suspensão gratuita.
- Só então configurar frontend, CORS estrito e executar browser hospedado; preservar rótulos sintéticos.
- Dados de clientes e produção requerem avaliação e autorização próprias.

## Fontes oficiais

- Render: [Free e limitações](https://render.com/docs/free), [primeiro deployment sem pagamento](https://render.com/docs/your-first-deploy), [discos](https://render.com/docs/disks), [FAQ e excedentes](https://render.com/docs/faq), [termos](https://render.com/terms), [regiões](https://render.com/docs/regions).
- Neon: [preços](https://neon.com/pricing), [limites dos planos](https://neon.com/docs/introduction/plans), [roles](https://neon.com/docs/manage/roles), [termos atuais](https://neon.com/platform-terms).
- Northflank: [preços](https://northflank.com/pricing), [faturação](https://northflank.com/docs/v1/application/billing/pricing-on-northflank), [volumes](https://northflank.com/docs/v1/application/databases-and-persistence/add-a-volume), [incidente consultado](https://status.northflank.com/cmvv0rn5a092f14rutwccodpp), [termos](https://northflank.com/legal/terms).
- Railway: [preços](https://railway.com/pricing), [volumes](https://docs.railway.com/volumes/reference), [termos](https://railway.com/legal/terms).
- [Oracle Free](https://www.oracle.com/cloud/free/), [Google Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features), [Fly trial](https://docs.fly.io/about/free-trial).
- [Aiven Free](https://aiven.io/docs/products/postgresql/concepts/pg-free-tier), [Aiven termos](https://aiven.io/terms).
- [Hugging Face Spaces](https://huggingface.co/docs/hub/spaces-overview), [Alwaysdata Free termos](https://www.alwaysdata.com/en/contract/5/), [HelioHost](https://wiki.helionet.org/What_HelioHost_Offers), [Serv00 PostgreSQL](https://docs.serv00.com/PostgreSQL/).
