# CLAUDE.md — CENTERWAY: regras para Claude Code
> Versão 2026-11-04. Documento de integração para colaboração ChatGPT + Claude Code + founder.

## Ler primeiro
Leia integralmente `docs/CENTERWAY_AUTONOMOUS_MVP_HANDOFF.md` ANTES de propor código. Este documento prevalece sobre documentos históricos do repositório quando trata de **objetivo e direção do produto**. Para factos técnicos (código executável, branches, endpoints, migrações, testes), inspecione o repositório atual e confirme; não assuma que notas antigas descrevem o deploy atual.

## Missão
O CENTERWAY é um **motor autónomo B2B** para empresas SaaS. Uma SaaS autoriza, numa configuração inicial curta, o acesso aos seus dados; o backend recolhe dados dos seus clientes, identifica falta/deterioração de valor, investiga com evidência, executa UMA intervenção permitida e verifica o resultado. O founder **não opera cliente por cliente**. O dashboard é **só leitura**: números, casos, trabalho em andamento, antes/depois e evidências.

## Arquitetura nova (um só backend, não microsserviços)
C01 recolha → C02 análise de valor → C03 investigação → C04 intervenção autorizada → C05 verificação → C06 API de resultados → dashboard.
Este C01–C06 é a **NOVA nomenclatura**, não os antigos C01–C10/PRs de infraestrutura. A implementação antiga F01–F06/manual é contexto, não o UX alvo.

## Critérios inegociáveis
- Simplicidade radical; evitar novas dependências, filas, agentes, serviços e infraestrutura salvo prova de necessidade.
- Backend primeiro, frontend depois. Uma SaaS de teste, 20 clientes sintéticos, uma métrica de valor, uma ação segura. Sintético valida engenharia, NÃO recuperação de clientes reais.
- Nunca fingir evidências, causalidade, dinheiro recuperado ou acesso a uma SaaS real.
- Automatizar sem founder a clicar; integrar SaaS uma vez; NÃO exigir introdução manual por cliente.
- Sem segredos/credenciais em código, prompts, commits ou logs; mínimo privilégio, isolamento multi-tenant e trilha auditável.
- C04: ação com consentimento prévio, chave de idempotência, modo ensaio por padrão, limite de frequência, registo de resultado e interruptor de paragem; negar ação com evidência insuficiente.
- C05: aguardar janela de observação; medir antes/depois; melhoria observada != causada pelo CENTERWAY.
- Não apagar código, alterar `main`, fazer merge, tocar Neon/Render/Lovable, gastar créditos ou criar recursos pagos sem autorização explícita. Trabalhar em branch isolada e PR.
- O utilizador prefere **respostas curtas, diretas e em português**. Reservar detalhes para ficheiros/PRs, não textões no chat.

## Processo em equipa
- Founder: visão de negócio e aprovação das decisões importantes.
- ChatGPT: especificações/contratos de aceitação, revisão e coordenação de serviços.
- Claude Code: inspeção técnica, implementação em branch, testes reproduzíveis, evidências, PR.
- **Não existe ligação direta automática entre chats Claude e ChatGPT**. O repositório/PR/issue do GitHub é a fonte comum.
- Em cada entrega: resumo curto do que mudou, ficheiros, comando de teste, resultados reais, lacunas, riscos e link do PR. Não declarar "100% pronto" sem critérios demonstrados.
- Primeira tarefa: auditar a base existente e propor especificação/implementação mínima para C01, **sem alterar código operacional, ambiente publicado ou dados** até revisão dos contratos.

## Onde começar a ler código legado
`recovery-mvp/`, `recovery-mvp/api/README.md`, `recovery-mvp/manual/README.md`, `recovery-mvp/managed/README.md`, `recovery-mvp/ORCHESTRATION.md`, `recovery-mvp/INTERVENTION.md`, `recovery-mvp/RECOVERY.md`, `PROJECT_STATE.md` (histórico; pode estar desatualizado).
