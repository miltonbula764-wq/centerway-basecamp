# Percurso mínimo CENTERWAY — contrato da demonstração

## Referência e autoridade

Manual completo de produto e engenharia v2.0, 17/10/2026, lido nesta missão
(22 páginas; edição «proposta de referência para revisão do fundador»).
Os blocos 05 e 09–15 descrevem propostas, não implementações nem políticas aprovadas.
A missão atual autoriza montar C01–C10 e isolar critérios específicos da demonstração.
Este contrato implementa SOMENTE esse recorte, não resolve as decisões A–H do manual.

Estado encontrado em main `8a9584c`: C01 importação append-only, C02 c02-v2,
C03 c03-v1, autenticação, empresas/membros, perfil único versionado e contexto
histórico estão implementados. Casos era um placeholder. Não havia classificador,
investigação, intervenção ou Core persistente. README e AGENTS identificam a
sincronização Lovable (projeto fb5e84e9-e3a9-40bf-a7ab-26c21ea1cf0a);
não foi consultado o serviço Lovable nem verificado o seu estado de sincronização.

## Contratos preservados e diferenças

- C02 continua a produzir candidatos, nunca casos ou conclusões de valor.
- C03 comprova integridade; suficiência C04/C09 é validada adicionalmente.
- O perfil único do tenant permanece. O objetivo sintético pertence a um subject
  e referencia uma versão aprovada; não substitui nem altera o perfil.
- Não há score global, interpretação automática de documentos, causalidade,
  conectores ou ações externas. A compatibilidade documental é uma confirmação
  humana explícita, com três referências distintas: capacidade, compromisso e objetivo.
- O contrato anterior CORE_C04_CONTRACT descreve corretamente a base histórica.
  A sua decisão pendente para um classificador universal mantém-se; este incremento
  acrescenta um avaliador limitado à política sintética abaixo.

## Política isolada `flowreports-demo-v1`

Dados sintéticos: FlowReports / Loja Aurora; outcome numérico `report_hours`,
unidade `h/semana`, menor é melhor, baseline 10, objetivo <=4, prazo explícito.
Perfil com agregação mean, cadência 7 dias, janela 7 dias, cobertura 100%,
denominador observation_count, duas janelas atuais. Nenhum destes números
é um default universal. Integração necessária: context/text `integration_status`,
unidade `estado`, valores `disabled` / `enabled`, importados pelo C01 com fonte e data.

C04 lê o snapshot C03 histórico. Exige outcome/configuração exata e duas janelas
completas, fonte única igual à fonte declarada e cobertura suficiente. Antes do prazo:
pending_deadline; sem suficiência: inconclusive; depois do prazo: achieved somente
se ambas as médias semanais <=4, caso contrário not_achieved. Resultado por objetivo,
sem agregação por cliente. Confirmação documental humana não certifica documentos.

## Core, autorização e transições

RPCs transacionais; tenant e papel verificados no banco. Admin cria objetivo sintético
confirmado; admin/operator avaliam e abrem caso só a partir de not_achieved suficiente.
Viewer apenas lê. Um caso por avaliação. Cada comando tem UUID de idempotência,
hash de payload e versão esperada; lock do caso serializa concorrência. Repetição
igual devolve o evento existente; mesma chave com outro conteúdo é rejeitada.

| Origem | Comando | Guarda | Destino |
|---|---|---|---|
| not_achieved | abrir | C04 suficiente, documentação confirmada | investigation |
| investigation / needs_information | investigar | observação disabled válida e temporalmente pertinente | impediment_found |
| investigation / needs_information | investigar | sem prova suficiente | needs_information |
| impediment_found | planear | plano manual explícito | awaiting_approval |
| awaiting_approval | aprovar | admin atual | approved |
| approved | registar execução | admin/operator, aprovação há menos de 24h, recibo humano | waiting_observation |
| waiting_observation / observed / remain_open | observar | relógio servidor >= execução +14 dias | observed |
| observed | decidir | C09 suficiente, ambas <=4, prova enabled pós-execução | closed_resolved |
| observed | decidir | qualquer critério ausente | remain_open |

O plano fixo reativa manualmente a integração e verifica estado; rollback é desativar
apenas com revisão humana caso a reativação origine erro. Não há botão que altere
uma integração externa. C07 regista uma execução humana declarada; não certifica a
ação remotamente. Gate começa na hora de registo no servidor; não aceita relógio
do browser nem encurta a janela para fazer a demonstração parecer concluída.

C09 usa novo bundle do mesmo cliente e perfil, duas janelas integralmente posteriores
à execução, mesma fonte/unidade/método e prova enabled posterior à execução e anterior
ao fim da medição. Se faltarem dados, persiste inconclusive; execução não é valor.
C10 fecha apenas o ramo resolved descrito. Continuidade permite nova observação.
Antes de fechar, C10 verifica se foram importadas novas medições relevantes ou
novos estados/correções da integração após o corte do C09. Havendo pendências,
mantém aberto e exige nova comparação. O C09 anterior continua imutável e resolve
correções da integração apenas até ao seu próprio corte, preservando a leitura histórica.
Outros fechos, cancelamento, reabertura, revisão de planos e aprovações delegadas são
limitações explícitas deste incremento, não funcionalidades escondidas.

Persistência: objetivos e avaliações imutáveis; casos como projeção do último evento;
eventos imutáveis guardam C05, C06, aprovação C07, gate C08, C09 e C10 com ator,
versão, referências e hora. RLS, FKs compostas e auditoria por triggers.
Não instalar esta migração no backend hospedado nesta missão.
