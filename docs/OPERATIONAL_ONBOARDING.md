# Onboarding operacional — Missão 18

A visão geral `/app` acompanha uma empresa desde a criação/seleção até à primeira avaliação C04. Usa os formulários já existentes de perfil, cliente, CSV, API, C02, C03 e C04. A entrada com conta sem empresas continua a encaminhar para `/onboarding`; convites e autenticação mantêm os seus contratos.

## Estado e autorizações

A RPC `operational_onboarding` é `STABLE SECURITY INVOKER`, apenas de leitura, sob RLS. Não existem tabelas/flags de progresso. Cada consulta verifica a adesão atual, a pertença do cliente e o papel. Mostra perfil aprovado, rascunho e problemas retornados por `value_profile_approval_issues`, cliente selecionado e indicadores de resultado do perfil aprovado, com configurações, observações e resultados persistidos C02/C03/C04.

A próxima orientação encaminha para uma operação existente; não a executa. Administrador aprova perfil/configura objetivo e gere credenciais; operador prepara perfil/importa/executa as análises já autorizadas; leitor consulta. Os links não são autorização. As RPCs originais validam novamente cada operação e as suas pré-condições.

Medições disponíveis permitem solicitar análise, mas não são apresentadas como suficientes antes da decisão do motor C02. Integridade C03 não comprova a promessa; C04 só aparece como avaliação válida para revisão quando a configuração é compatível, a evidência é suficiente e a projeção não deteta desatualização. Um resultado `not_achieved` pode ser uma avaliação válida: atingir a meta não é condição de conclusão da configuração. Contradições e insuficiência continuam visíveis por indicador. Nada abre casos ou aprova decisões automaticamente.

A última configuração de cada indicador é apresentada, identificando se pertence a outro perfil. Última análise refere-se ao perfil aprovado; o pacote C03 refere-se a essa análise, e a avaliação refere-se à configuração atual. Nova observação do mesmo indicador posterior ao cut-off, outro pacote ou mudança de perfil exige revisão. Esta sinalização conservadora não substitui os contratos temporais, a Central ou a monitorização. Os registos históricos permanecem acessíveis em Casos.

## Utilização

1. Entrar com conta autorizada; criar/selecionar a empresa.
2. Na visão geral, seguir «Da conta à primeira avaliação» para completar e aprovar o perfil.
3. Registar cliente; selecionar o cliente no acompanhamento inicial.
4. Abrir o objetivo C04 do indicador e documentar apenas informação conhecida.
5. Escolher CSV ou API para encaminhamento. A fonte exata permanece documentada em C01/C04; escolher uma via não cria credenciais nem observações.
6. Importar medições, consultar pendências e abrir o cliente para executar C02/C03 com as permissões existentes.
7. Abrir a configuração C04, selecionar o pacote persistido, avaliar no servidor e consultar o resultado/Central.

Os links preservam empresa/cliente e, quando existem, configuração/avaliação. O cliente e a via escolhida podem constar no URL `/app?tenant=…&subject=…&collection=csv` (ou `api`). Esses parâmetros são apenas contexto de navegação, não estado de progresso nem autorização. Reload e reentrada recalculam os registos persistidos; sem parâmetros seleciona-se o primeiro cliente por UUID. Consultas têm cancelamento, cache por empresa/papel/cliente e atualização periódica de 30 segundos; há atualização manual. A mudança de empresa elimina o contexto e cache anteriores.

Paginação por UUID de cliente e chave de indicador, 25 itens por página; o cliente explicitamente selecionado é validado separadamente e não depende da primeira página. A lista acompanha apenas indicadores de resultado atualmente aprovados. Perfis e configurações históricas continuam em suas páginas originais.

## Migração e validação

A nova migração **0025_operational_onboarding** depende de **0000–0024**, incluindo os marcadores existentes 0023/0024. Apenas acrescenta uma função de leitura e o seu grant específico, entrada de journal e snapshot encadeado; não altera migrações/snapshots antigos nem acrescenta marcadores. Instalar somente após revisão pela integração separada. Nada foi aplicado no backend hospedado nesta missão.

O workflow `.github/workflows/browser-e2e.yml` é a referência reproduzível: PostgreSQL17 descartável, GoTrue com auto-confirmação exclusivamente de testes, PostgREST, migração sobre dados existentes, testes HTTP e SQL anteriores, `e2e/operational-onboarding.py` e Playwright. O novo teste de navegador começa com uma conta sintética sem empresas e utiliza os formulários reais até à primeira avaliação, incluindo logout/reload. Os testes HTTP verificam insuficiência, contradição independente, perfis incompletos, papéis, RLS, paginação e ausência de escritas durante consultas. Testes unitários controlados não substituem autenticação real.

Montagem local: `python3 scripts/mvp/start-local.py --monitoring`, com Docker, cliente PostgreSQL, Node e Bun 1.3.0; credenciais sintéticas ficam no ficheiro privado indicado pelo script. Abrir `/app`. Limpar apenas a stack descartável com `python3 scripts/mvp/stop-local.py`.

## Limites

Sem contactos automáticos, dados inventados, emails, avaliações agendadas pelo onboarding ou execução automática do Core. A avaliação continua limitada aos indicadores numéricos suportados pelo contrato C04 atual. A API depende do endpoint já instalado/configurado separadamente; o percurso só encaminha para a gestão/instruções existentes, sem verificar nem modificar o serviço hospedado. Objetivos/medições/documentos precisam de ser fornecidos por pessoas ou integrações autorizadas. A consulta não tenta provar antecipadamente suficiência de janelas; os motores existentes decidem isso e registam o fundamento.
