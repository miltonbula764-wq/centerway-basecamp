# Core/C04 — primeiro bloco: contexto histórico de valor

## Fontes disponíveis e fronteira

Foram lidos AGENTS.md, roadmap.md, .lovable/plan.md, DEVELOPMENT_READINESS.md,
c02_semantics.md, os contratos SQL 0001/0003/0004/0009/0010/0011 e as implementações
de C01–C03. PRODUCT.md, DECISIONS.md, ARCHITECTURE.md e os anexos de transferência
anteriores não estão disponíveis nesta sessão nem na árvore do repositório. Não se
presume que as definições de produto inexistam fora do repositório.

A missão Engenharia #6 autoriza agora o primeiro bloco Core/C04; a anotação antiga
“C04–C10 não autorizados” no roadmap era o limite da missão anterior, não uma
especificação funcional nem uma proibição que substitua esta autorização.

O fundador confirmou nesta missão que não há confirmação de um contrato completo aprovado
para classificação/agregação C04. Autorizou expressamente continuar a base independente,
sem conclusões de realização/gap, sem pesos/thresholds ou agregação arbitrária e sem
inferir causas/impedimentos/intervenções. Essa confirmação não substitui os contratos
existentes: o significado dos sinais C02 e da integridade C03 foi conferido no SQL.

Não existe implementação prévia de Core/C04: há C02 (candidatos e below_target) e
C03 (integridade e referências), sem modelo persistido de conclusão de valor.
O perfil corrente mostrado no detalhe do cliente não é necessariamente o histórico.

## Parte implementada, sem novas regras de negócio

O pacote selecionado passa a mostrar a promessa e o resultado esperado do perfil
efetivamente referenciado pelo seu run C02, no próprio painel de evidência existente.
O módulo de queries existente disponibiliza uma projeção de leitura reutilizável
historicalValueContextQuery: perfil histórico, run imutável e identidade do bundle.
Os indicadores/snapshots e as referências continuam nas tabelas e consultas C03
existentes, ligados por bundle/indicator_id, sem cópia paralela ou carregamento ilimitado
de referências no browser. O futuro motor deve produzir as suas conclusões no servidor;
esta projeção de interface não é uma autoridade de interpretação.

1. Ler o run por tenant, cliente e id exatos, através do cliente autenticado/RLS.
2. Verificar correspondência do hash de inputs, algoritmo C02 e corte com o pacote.
3. Ler tenant_value_profiles pelo tenant e profile_id desse run, nunca o perfil atual.
4. Confirmar id, tenant, versão, aprovação e status approved/superseded.
5. Mostrar a promessa histórica junto dos snapshots, observações e refs já existentes.

Sem correspondência, a promessa não é apresentada como validada. Sem resultado esperado,
mostra-se “Não registado neste perfil”; não se usa zero, perfil corrente ou texto inferido.
Erros de leitura têm mensagem e opção de repetição. Query keys incluem tenant, cliente,
run e bundle; respostas tardias ficam na chave original, sem reutilização de dados de
outra identidade. Não há montagem automática, nova RPC, escrita ou estado C04 persistido.

As permissões são as leituras existentes para membros admin/operator/viewer; RLS/grants,
FKs e triggers continuam a ser a autoridade. A validação defensiva na interface não é
uma nova garantia de segurança do servidor. Hashes são comparados com o vínculo guardado,
não recalculados pelo browser como se este pudesse certificar o pacote.

## Decisão de produto pendente — impede apenas o classificador C04

São necessárias as especificações aprovadas que definam:

- Que critério e período demonstram valor realizado em cada indicador outcome; alcançar
  um target isolado, satisfazer recuperação e ausência de deterioração não são equivalentes.
- Quando below_target representa gap em relação à promessa e qual a magnitude/unidade;
  uso não demonstra valor e um alvo de indicador não é automaticamente toda a promessa.
- Como combinar vários outcomes e evidência parcial, incluindo conflitos, prioridades,
  estados de informação insuficiente e estado indeterminado; se a conclusão é por
  indicador, cliente ou ambos, e qual a enumeração/precedência aprovada.
- O que constitui evidência suficiente para essa conclusão, além da integridade C03;
  validade temporal, tratamento de versões e quais inputs/versões devem ficar persistidos.

O sistema não atribui valor realizado, gap de valor agregado, perda, causa, impedimento,
caso acionável ou recuperação. A mensagem “Conclusão de valor não disponível” é uma
limitação de apresentação, não um novo estado de domínio C04. Os sinais e below_target
já existentes continuam visíveis nos snapshots, com o significado original.

## Validação e limites

Testes unitários novos exercitam perfil superseded, ausência de campos, versões/identidades
incompatíveis, falha de leitura e respostas tardias positivamente concluídas depois de
mudar tenant/cliente/run. Não comprovam RLS.

O workflow browser existente foi alargado à branch de revisão. Testes Chromium com GoTrue,
JWT, PostgREST e PostgreSQL descartáveis verificam promessa v1 depois da aprovação v2,
admin/operator/viewer, mudança de empresa e resultado esperado ausente. A suite anterior
continua a verificar indicadores insuficientes e ausência de dados, sem concluir valor.
Os cenários rejected/failed continuam a simular apenas o JSON da RPC: não passam a ser
prova SQL. Não há novos locks/escritas; não se repetem suites de concorrência SQL sem causa.
As migrações e os testes de privilégios existentes são executados no ambiente descartável.
Resultados e commits exatos devem ser consultados no PR e nas execuções CI, não inferidos
da existência deste documento. Nenhum teste autoriza aplicação ao backend real.

Próximo bloco: recuperar/aprovar o contrato acima e implementar então a conclusão C04
versionada no servidor, com histórico/auditoria e testes de autorização/idempotência,
sem converter candidato ou pacote íntegro automaticamente em caso acionável.
