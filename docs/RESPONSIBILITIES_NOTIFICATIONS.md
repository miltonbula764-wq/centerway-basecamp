# Responsabilidades e notificações internas — Missão 17

A atribuição pertence ao caso operacional configurável, atravessando os seus ciclos sem reutilizar autorizações. Apenas administradores atuais podem atribuir, substituir ou remover um responsável, com fundamento e referência verificável. O destinatário deve ser membro atual da mesma empresa e ter papel administrador ou operador. A atribuição não concede permissões C05–C10. O piloto FlowReports mantém o seu contrato separado.

Cada alteração gera uma revisão imutável com autor, data, operação idempotente e hash de pedido. A revisão esperada impede substituições concorrentes silenciosas. A validade é calculada contra o UUID da adesão original: remoção ou despromoção para leitor invalida a responsabilidade operacional, sem apagar histórico. Readmitir a mesma pessoa não reativa a adesão anterior; um administrador precisa de confirmar nova atribuição. A interface apresenta explicitamente essa pendência.

## Notificações e destinatários

A caixa é privada por empresa, utilizador, adesão e papel atual. Assumir responsabilidade não dá acesso à caixa de outra pessoa. O destinatário recebe «Caso atribuído»; o anterior recebe a alteração/remoção se ainda pertencer à empresa. As notificações exibem UUIDs de membros, não emails privados.

A preparação de revisões existente da Missão 15 alimenta a mesma outbox de notificações. Não há outro classificador: usam-se a projeção do Core e os factos/eventos imutáveis da monitorização. As orientações gerais são:

- Autorização necessária e falha de processamento: administradores atuais.
- Revisão disponível, janela terminada ou novas medições por analisar: responsável operacional válido; na sua ausência, administradores atuais.
- O plano e a revisão programada do mesmo plano partilham a identidade do acontecimento e não geram avisos duplicados. Um plano de outro ciclo tem identidade própria.
- Revisões já substituídas ou de uma versão de caso ultrapassada são ignoradas ao processar. Não se produzem notificações retroativas para eventos anteriores à instalação.

Estes destinatários são regras de encaminhamento desta versão, não urgências ou permissões adicionais. Não há emails nem preferências individuais de canais. Uma notificação é um acontecimento histórico: ao abrir o registo, o servidor volta a validar o estado e permissões atuais. O término da janela não demonstra suficiência das medições nem valor recuperado.

## Processamento e segurança

A outbox grava acontecimentos na mesma transação da origem. Atribuições notificam atomicamente; os restantes eventos são processados em lotes máximos de 25 ao preparar revisões (manual ou agendador existente) ou pela ação explícita «Processar notificações pendentes». A mera consulta não processa nem modifica casos.

Bloqueio `SKIP LOCKED`, unicidade por destinatário/adesão/acontecimento/tipo, tentativas imutáveis e subtransações por trabalho permitem concorrência, repetição e recuperação. Uma falha técnica preserva o trabalho, regista apenas SQLSTATE e permite nova tentativa após um minuto. Não é um prazo de negócio nem garantia de execução. Administradores podem consultar os trabalhos pendentes/com falha e últimas tentativas por RLS. A caixa mostra os cinco primeiros trabalhos pendentes/com falha para administração. Não há automatização de intervenções, avaliações ou decisões Core.

Tabelas de mensagens, leituras, atribuições e tentativas são append-only. Escritas autenticadas diretas são negadas; RPCs impõem autorização no PostgreSQL. A interface usa cache por empresa/conta, cancela consultas e valida a empresa ativa antes/depois de escritas. A mesma projeção Core serve a Central e «As minhas pendências», sem pontuações adicionais.

## Interface e execução

No dossier `/app/casos`, consultar «Responsável do caso», atribuir com fundamento/referência e expandir o histórico. Em `/app/acompanhamento`, usar «As minhas pendências» e «Notificações internas». A navegação mostra o total não lido; a caixa permite filtrar, paginar, marcar como lida e abrir o cliente/caso validado. A lista pessoal inclui casos encerrados enquanto a atribuição permanecer, identificados pelo estado real do Core.

Para montar uma base nova exclusivamente sintética: `python3 scripts/mvp/start-local.py --monitoring` (Docker, PostgreSQL client, Node e Bun 1.3.0). O script aplica o journal inteiro na base descartável e não instala Cron. Para atribuir, utilizar os membros sintéticos existentes na página Configurações. Credenciais temporárias ficam apenas no ficheiro privado indicado pelo script. Limpar apenas essa stack com `python3 scripts/mvp/stop-local.py`.

A campanha reproduzível integral está em `.github/workflows/browser-e2e.yml`: migrações sobre dados existentes, regressões SQL e HTTP, `e2e/responsibilities.py`, probes SQL revertidas e Playwright. A prova de permissões com roles/claims PostgreSQL distingue-se dos logins reais GoTrue; janelas de teste usam um segundo explícito e relógio real. Os testes controlados de respostas no frontend não substituem autenticação real.

## Instalação posterior e limites

**Ordem obrigatória: 0020 → 0021 → 0022_responsibilities_notifications.** As duas primeiras ainda aguardam instalação hospedada conforme contexto recebido. A numeração 0022 é provisória para revisão antes do merge: se a integração reservar esse número entretanto, reconciliar a nova migração/journal/snapshot sem alterar 0000–0021. Não foi criado marcador. Snapshots anteriores e o seu encadeamento permanecem intactos.

Nada nesta entrega instala migrações, Cron ou código no serviço hospedado. Sem acesso à Lovable ou verificação hospedada. Sem reabertura de casos, políticas comerciais de urgência ou emails. A periodicidade exige o agendador separado já documentado pela Missão 15; a consulta e o processamento manual não dependem dele. Não há backfill nem envio de notificações a membros admitidos depois do processamento de um evento histórico.
