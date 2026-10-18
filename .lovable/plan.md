# Diagnóstico 0012 (somente leitura) — não autoriza instalação

## 1. Estado confirmado
- Base: `drizzle.__drizzle_migrations` tem 12 entradas (0000–0011); a última é o hash ad64c139…a1f1f (0011). Não há 0012 aplicada.
- 16 tabelas e 40 funções em `public`; nenhuma tabela `cw_*`, nenhuma função `*_demo_*`.
- Dados: 2 empresas, 2 memberships, 4 linhas de auditoria; 0 clientes, observações, análises C02 e pacotes C03.
- `c03_bundles` tem as chaves únicas `(tenant_id,id)` e `(tenant_id,run_id,algorithm_version)`. A nova `(tenant_id,subject_id,id)` não existe: não há conflito de nome.
- Repositório: o ficheiro 0012 existe e o journal já tem a entrada idx 12 (`0012_mvp_case_journey`, when 1792274400000), escrita à mão no PR. Não existe `0012_snapshot.json`.
- O SQL 0012 é aditivo: 1 chave UNIQUE, 4 tabelas `cw_*`, RLS só de leitura para membros (`is_tenant_member`), RPCs SECURITY DEFINER com REVOKE de PUBLIC/anon e EXECUTE só para authenticated, e `NOTIFY pgrst`. Não tem BEGIN/COMMIT nem INSERT de dados de exemplo. Os INSERT existem apenas dentro das funções.

## 2. Mecanismo suportado e conflito
- A sincronização com o GitHub não aplica migrations. O único caminho suportado é a ferramenta de migration do agente: cria um ficheiro e uma entrada no journal novos, escreve o SQL, corre `drizzle-kit check` e aplica numa transação. O Drizzle regista depois o hash e o `created_at`.
- **Bloqueio factual:** a entrada 0012 escrita à mão já está no journal. Por isso, a ferramenta geraria uma segunda entrada (idx 13).
- **Hipótese (não verificada):** o migrator aplicaria então a 0012 do repositório e a nova, ou seja, o mesmo SQL duas vezes. A segunda falharia por objetos duplicados e a transação seria revertida. No melhor caso, o SQL ficaria registado com o nome errado.
- Sequência recomendada (igual à usada para a 0011):
  1. Num commit no GitHub, retirar do repositório o ficheiro 0012 e a sua entrada no journal.
  2. Confirmar aqui que o journal termina na 0011.
  3. Aplicar o SQL 0012, byte a byte, pela ferramenta, com o nome `mvp_case_journey`.
  4. Integrar de volta o ficheiro e o journal gerados.
  Assim não se fabrica nenhum hash nem se reescrevem as migrations 0000–0011.

## 3. Pré-condições, impacto, backup e rollback
- Pré-condições: confirmar de novo as 12 entradas, a ausência de `cw_*` e que ninguém está a aplicar outra migration ao mesmo tempo.
- Impacto: sem alteração de dados nem de grants das 16 tabelas existentes, segundo o teste de CI. Isto não foi provado nesta base.
- Backup: não existe aqui backup gerido acessível ao agente. O rollback depende da transação atómica da ferramenta. Depois de aplicada, reverter exige uma migration compensatória (DROP), sujeita a aprovação.
- Verificações depois da aplicação, só com SELECT:
  - 13 entradas no histórico, com as 12 anteriores iguais;
  - 20 tabelas, todas com RLS;
  - ACL das funções novas: só authenticated;
  - grants e políticas das 16 tabelas antigas iguais a antes;
  - contagens de dados iguais.

## 4. Página /app/casos
- Hoje: a consulta a `cw_cases` falha porque a tabela não existe; a página mostra a limitação documentada.
- Depois da instalação: deve abrir e mostrar "Sem casos". Os dados reais estão vazios: 0 clientes, observações, análises e pacotes.
- Ainda faltará, para ver o percurso: clientes, um perfil aprovado, observações importadas, análise C02, pacote C03 e um objetivo. A política é apenas sintética (`flowreports-demo-v1`). O seed do PR é só para a stack descartável e não deve correr aqui.

## 5. Recomendação
Não aplicar a 0012 enquanto a entrada escrita à mão estiver no journal. Primeiro, um commit separado a retirar o ficheiro e a entrada; depois, autorização explícita para aplicar pela ferramenta. Aguardo essa autorização.
