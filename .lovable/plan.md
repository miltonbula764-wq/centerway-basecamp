# CENTERWAY — Bloco C01–C05 e Value Profile (apenas planeamento)

Estatuto: documento de desenho. Não autoriza implementação. Legenda:
- **[Produto]** decisão fornecida pela equipa/Milton.
- **[Proposta]** proposta de engenharia nossa, sujeita a validação.

## 0. Princípios transversais

- [Produto] Contratos definidos por nós no desenho; o Core aplica-os, não os redefine.
- [Proposta] Encaminhamento do Core determinístico e auditável. Julgamento especializado só dentro dos componentes que o exigem (C02, C04, C05). Nenhum agente pode alterar o fluxo.
- [Produto] Responsabilidades separadas, contextos isolados, outputs estruturados.
- [Proposta] Todo registo carrega: `tenant_id` (SaaS cliente do CENTERWAY), `subject_id` (unidade acompanhada: conta B2B ou pessoa B2C), `source`, `observed_at` (quando o facto ocorreu), `ingested_at` (quando chegou), `contract_version`.
- [Proposta] Separação estrita: **observação** (facto vindo de fonte) vs **inferência** (conclusão de um componente, com referências às observações que a sustentam e nível de confiança). Inferências nunca são reescritas como observações.
- [Proposta] Dado ausente é explícito e tipado; nunca é tratado como zero.

## 1. Quadro C01–C05

| Comp. | Entradas | Saídas estruturadas | Invariantes (não faz) |
|---|---|---|---|
| **C01 Collector** | Fontes autorizadas por tenant; Value Profile (indicadores a recolher) | Observações normalizadas com identidade, fonte, `observed_at`/`ingested_at`; **relatório de cobertura** (indicador x janela: presente / ausente / atrasado / falha de ingestão) | [Produto] Não diagnostica. [Proposta] Não imputa valores em falta; não funde identidades ambíguas sem registar a ambiguidade |
| **C02 Deterioration Detector** | Observações + cobertura; baseline, janelas e critérios do Value Profile | Sinal por subject/indicador: `deteriorou` / `estável` / `melhorou` / `indeterminado`, tipo (súbita/progressiva), magnitude, janela, refs às observações | [Produto] Não conclui causalidade. [Proposta] Janela com cobertura insuficiente → `indeterminado`, não “queda” |
| **C03 Evidence Builder** | Sinais C02, observações, cobertura | Dossiê de evidências: itens citáveis (ref. à observação original), lacunas conhecidas, contradições | [Produto] Não fabrica provas. [Proposta] Cada item aponta para observação existente; sem resumos sem fonte |
| **C04 Value State** | Dossiê C03 + Value Profile | Estado de realização por resultado esperado: `realizado` / `parcial` / `em risco` / `não realizado` / `insuficiente`; gap estimado; confiança; refs | [Produto] Não escolhe intervenção. [Proposta] Distingue explicitamente indicadores de uso vs indicadores de resultado |
| **C05 Impediment** | Dossiê C03 + estado C04 | Hipóteses de impedimento com evidências a favor/contra e confiança, **ou** `informação insuficiente` com lista do que falta | [Produto] Só infere com evidências; pode declarar insuficiência; não executa |

## 2. Proposta mínima de Value Profile [Proposta]

Um por tenant (e opcionalmente por segmento/plano). Versionado.

- **Identidade**: `tenant_id`, segmento, tipo de unidade acompanhada (conta, workspace, pessoa).
- **Promessa**: o que a SaaS promete ao cliente, em linguagem de negócio.
- **Resultados esperados** (1..n): ex. “faturas emitidas e pagas a tempo”.
- **Indicadores observáveis** por resultado, cada um classificado como:
  - `resultado` (evidência direta de valor realizado),
  - `uso/atividade` (condição ou proxy; sozinho não prova valor),
  - `contexto` (ex. sazonalidade, mudança de plano, nº de lugares).
- **Baseline**: como se calcula (histórico próprio do subject, coorte, alvo contratado) e período mínimo.
- **Janelas**: observação, comparação, latência esperada de dados.
- **Critérios de deterioração**: por indicador, condições para súbita e progressiva; requisito de cobertura mínima.
- **Critérios de recuperação**: o que conta como regresso ao valor e em que janela (servirá a fase de observação pós-intervenção).
- **Regras de suficiência**: combinação mínima de indicadores para C04/C05 poderem concluir.

Regra-chave: perda de valor exige sinal em indicador de `resultado`, ou corroboração múltipla e explícita definida no perfil. Sinal só em `uso` gera, no máximo, “risco/atenção”.

## 3. Cenários

**A) Queda de logins, resultados estáveis**
1. C01 regista logins em queda e indicador de resultado estável, ambos com cobertura completa.
2. C02: `deteriorou` em logins (uso); `estável` no resultado.
3. C03: dossiê com ambos, marcando a divergência.
4. C04: resultado `realizado`; nota “padrão de uso alterado” (ex. automação, integração via API, menos utilizadores necessários). Não declara perda de valor.
5. C05: não aciona inferência de impedimento de valor; quando muito regista hipótese de baixa confiança para monitorização. Core encaminha para vigilância, não para intervenção.

**B) Dados ausentes por falha de ingestão**
1. C01 marca a janela como `falha de ingestão` (fonte, intervalo, erro), sem valores fictícios.
2. C02: `indeterminado` nos indicadores afetados; não emite queda.
3. C03: lacuna registada como lacuna, não como evidência.
4. C04: `insuficiente` para os resultados dependentes.
5. C05: `informação insuficiente`, listando dados em falta.
6. Core (determinístico): encaminha para nova recolha/alerta operacional; caso fica suspenso, não avança para intervenção.

Distinção importante: ausência real de atividade (fonte saudável, zero eventos) é observação válida; ausência por falha é lacuna. C01 tem de conseguir distingui-las (ex. sinal de saúde da fonte).

## 4. Ambiguidades em aberto (não resolvidas)

1. Quem define e aprova o Value Profile de cada tenant (equipa CENTERWAY, a própria SaaS, assistido)?
2. Unidade acompanhada em B2B: conta, workspace ou utilizador — e como agregar.
3. Resolução de identidade entre fontes: o que fazer quando IDs não coincidem.
4. Baseline para clientes novos sem histórico.
5. Se C02 lê critérios só do perfil ou pode propor critérios (julgamento) — proposta: só aplica os do perfil no MVP.
6. Limiares de confiança mínima para C05 propor hipótese vs declarar insuficiência.
7. Retenção e privacidade de dados pessoais em B2C.
8. Quem opera o sistema e quais as fontes de dados (ainda pendentes do bloco anterior).

Próximo bloco sugerido: C06–C10 (planeamento, autorização, execução, observação pós-janela).
