# Evidência da Missão 20.7B

Base: main `de8e4ca675e36f7c5fcb7cc014e409f8a968fe83`. Tudo nesta entrega é laboratório independente/teste controlado. Não houve acesso, criação de recursos, envio, deploy, migração ou alteração de Cron no CENTERWAY hospedado.

## Demonstração histórica de semente fixa

Comando: `PYTHONPATH=. python3 tests/demo.py` dentro de `living-lab/`.

| Verificação | Esperado antes do envio | Obtido no receptor controlado |
|---|---|---|
| Identidade | 24 clientes persistentes por empresa, duas fontes/credenciais | Atlas 24, Beacon 24; sem cruzamento |
| Tempo | 50 ciclos históricos por empresa; nenhuma alegação de tempo real | 100 ciclos históricos; instantes sintéticos de teste explícitos |
| Valores/identidades | Cada medição gerada deve ter uma única observação remota | Atlas 2046/2046, Beacon 2006/2006; total 4052 |
| Correções | Novas linhas após recibos autorizados do receptor | 18 + 18; originais preservados |
| Falhas de A | Perda após commit, 503 e 429, sem perder/duplicar observações | Três tentativas falhadas/ambíguas, recuperação com mesmos IDs |
| Isolamento de B | Continuar apesar das falhas de A | 2006 medições concluídas, nenhuma falha de transporte B |
| Quota local | Máximo 10 tentativas por 60s móveis, incluindo retries | Asserção de todas as janelas aprovada |
| Fim do ensaio | Nenhum lote oculto ou pendente | Zero lotes pendentes/bloqueados; 33 tentativas HTTP totais |
| Privacidade | Só campos allowlisted do C01 | Nenhuma causa, coorte ou resultado esperado no payload |

A resposta do receptor mantém o formato de contagens do C01 e não devolve IDs de observações. Os recibos da demonstração são uma leitura privada do receptor **de teste**, não uma API inventada para o CENTERWAY. O receptor não implementa todo o produto: estas contagens não provam C01/RLS hospedados nem avaliações C02–C10.

## Verificações executáveis

21 testes da biblioteca padrão verificam motor, cenários, instantes/cobertura, durabilidade, backup consistente/restauro, reinício, concorrência e leases, limite persistente de pedidos, integridade/privacidade dos corpos, recusa de redirects, erros permanentes/ambíguos, Retry-After, isolamento de ficheiros de credenciais, recibos, comparação imutável e painel privado. O teste HTTPS usa apenas `127.0.0.1`, rejeita certificado não confiável e aceita a CA sintética explicitamente confiada; não desativa TLS.

O teste de daemon usa subprocesso autónomo e relógio real, espera novas medições, mantém A ativa enquanto B recebe 401, termina e reinicia com a mesma base e comprova recuperação de B. Isso é uma prova local de autonomia/reinício; funcionamento hospedado 24/7, relógio do fornecedor, disco e TLS do painel ainda precisam de aceitação posterior.

Playwright abre desktop e viewport móvel: auth anónima recusada, ambas as empresas, pausa/retoma isoladas, reload persistente, paginação, secções abertas preservadas na atualização, comparação importada renderizada como texto inerte e nenhum erro JS. Viewport móvel não é prova num aparelho físico. A imagem Docker constrói apenas o laboratório e importa módulos como UID 10001, com rede desativada no smoke.

CI reproduz os testes em Python 3.12 e 3.13 e o painel em Chromium; o estado final e links estão no PR. Não há workflow de deploy nem secrets de produção configurados. Agregados e screenshots de fixtures sintéticas são os únicos artifacts publicados no CI.

## Problemas detetados durante desenvolvimento

- Backpressure podia impedir a etapa de entrega que drenaria a fila. As três etapas agora têm tratamento independente; regressão exige que entrega seja chamada mesmo com geração e formação de lotes falhadas.
- Comparação temporal por texto ISO podia excluir factos no mesmo segundo quando o corte tinha fração. A vista de comparação usa instantes numéricos; cobertura é testada como datetime, não por ordem lexical de strings.
- O caminho de importação histórica agora marca explicitamente todos os ciclos importados como `synthetic_history`; os ciclos reais do daemon permanecem separados.
- A importação de recibos aceita UUID/fuso/decimal equivalentes de exportações legítimas, mas recusa qualquer alteração de valor, instante ou identidade.
- A inicialização do painel valida o segredo antes de iniciar workers, impedindo envio de arranque sem painel válido.

São correções no **código novo do laboratório**; não se encontrou nem alterou defeito em C01–C10 nesta missão.

## Limites e próximo ponto de revisão

A implantação e a ligação ao CENTERWAY ficam pendentes. Recibos/avaliações dependem de exportação autorizada manual; proveniência não é certificada pelo laboratório. Sem HA, SSO/RBAC próprio, alertas externos ou retenção automática. O serviço único partilha host/disco; separar serviços/volumes se exigir isolamento físico. A fila não reescreve, divide ou descarta automaticamente lotes inválidos. A comparação é factual, para revisão humana, sem um segundo classificador ou resultados esperados enviados ao produto.

Seguir [DEPLOYMENT.md](DEPLOYMENT.md) para infraestrutura, segredos, aceitação, backup/reversão e posterior ligação manual, somente depois da revisão/autorização. Não fazer merge ou deploy automaticamente.
