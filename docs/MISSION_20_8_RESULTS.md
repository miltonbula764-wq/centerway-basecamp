# Missão 20.8 — resultados de validação

Base: main `d764f893ea47448836f8a64f1b8660fdd3b0a143`. Implementação, critérios, reprodução, gates externos e rollback em [CONNECTED_ONBOARDING.md](CONNECTED_ONBOARDING.md).

O relatório final será atualizado neste PR após a conclusão dos workflows. Resultados abaixo são do laboratório e não representam validação hospedada PostHog.

| Prova | Resultado observado |
|---|---|
| GoTrue + PostgreSQL + C01 HTTPS | Autenticação por palavra-passe real; duas empresas, dois administradores e operador; runtime NOINHERIT dedicado |
| Primeira execução completa limpa | 133 asserções; 2 clientes criados; 9 observações persistidas; 8 tentativas HTTP C01, incluindo falha e resposta perdida |
| Imutabilidade e segurança | Correções append-only; perda de administrador revoga chave própria; zero execuções C02/C03/C04/Core |
| Browser móvel | Login real → OAuth controlado → descoberta → nomes/objetivos → rascunho → aprovação bloqueada → desconexão; sem overflow horizontal |
| Primeiro percurso móvel medido | 2.020 ms da submissão de contexto até rascunho, em automação local com OAuth simulado; não é previsão comercial nem tempo humano |
| Unitários existentes + segurança nova | 139 testes aprovados em 16 ficheiros na execução local inicial |
| Tipos e build | Execuções locais aprovadas; CI do commit final é a autoridade de reprodução |
| Privacidade/ACL | Schema privado indisponível ao PostgREST; public roles sem capacidade; FORCE RLS; envelopes cifrados vinculados ao tenant; nenhum segredo em respostas |

Foram corrigidos problemas encontrados durante a implementação: bloqueio de ações após remontagem React StrictMode; recuperação explícita de ligação pertencente a sessão anterior, sem herdar consentimento; transação atómica para criar ligação e estado PKCE; estado revogado não exige novamente a remoção de consentimento já retirado. As regressões de browser/HTTP cobrem estes percursos. Foi ainda corrigida uma falha no teste de recuperação C01: uma resposta HTML 502 durante o reinício real do PostgREST causava JSONDecodeError. A sondagem mantém o prazo e só considera HTTP 200 como recuperação; duas regressões verificam 502→200 e falha persistente. Nenhuma lógica C01–C10 foi alterada.

Limitações: OAuth hospedado e HogQL em projeto real não validados; requer CIMD HTTPS e gates de implantação; runtime Cloudflare por omissão não comprovado para TCP PostgreSQL; agendamento apenas preparado, não instalado; B2C não suportado pelo mapeamento de grupos; descoberta limitada/amostrada; atraso superior a dois dias exige revisão; regras/justificação de resultado ainda requerem o editor de perfil existente; credencial C01 expira em 30 dias e consentimento depende da sessão autorizada. Não há inferência de causas, avaliação automática, comprovação documental ou intervenção.

Nenhum acesso ao Supabase hospedado, Lovable ou dados PostHog externos; nenhum deploy, Cron ou merge.
