# CENTERWAY V2 · Missão 11 — autorização C05 e execução controlada de teste

[Contrato C05: aprovação explícita, execução de teste, auditoria e limites](v2/C05_CONTRACT.md).
Intervenções externas e production bloqueados; sem adaptador instalado ou recuperação presumida.

[Contrato C04, configuração segura, testes e limitações](v2/C04_CONTRACT.md).
A IA propõe; a validação é independente e não autoriza execução. Sem credenciais, inferência indisponível.

[C03 isolado: contrato, exemplos e instruções](v2/INVESTIGATION_CONTRACT.md).
Factos, hipóteses, requisitos observados e lacunas separados; sem confirmação causal ou ativação.

[C02 isolado: contrato de critérios, exemplos e instruções](v2/DETECTION_CONTRACT.md).
Operação e perda de valor avaliadas separadamente, sem ativar o fluxo de produção.

[Entrada autorizada de evidências, contrato HTTP e instruções](v2/EVIDENCE_API.md).
Eventos, métricas e evidências por SaaS/cliente/configuração; sem ativar C01–C06 operacionais.

[Contrato interno de integração, três exemplos e instruções](v2/INTEGRATION_CONTRACT.md).
Configurações versionadas por SaaS; nenhuma ligação nova a C01–C06 ou execução de negócio.

[Modos isolados, contas privadas e instruções da fundação permanente](v2/PERMANENT_FOUNDATION.md).
Production mantém autenticação privada sem lease de 24 h; operações reais continuam bloqueadas.

[Arquitetura, custos, dependências e verificações](v2/infra/ARCHITECTURE.md).
Proposta: VM + Caddy + Python + SQLite persistente, sem contratar ou publicar.

[Contrato backend ↔ frontend](v2/API_CONTRACT.md) e
[OpenAPI 3.1](v2/contracts/openapi.json). C01–C06 e Core preservados.
Sem interface nova, Lovable, publicação ou integração externa real.

**Pré-visualização privada: preparada e testada localmente, ainda sem URL externo.**
O ambiente atual não dispõe de HTTPS/ingress para este runtime Python. Nada foi
publicado. Ver [estado, bloqueio e operação privada](v2/PRIVATE_PREVIEW.md).

Acompanhamento de múltiplos clientes por SaaS, com registo central, entrada validada
de observações e ciclos C01–C06 independentes. Python + SQLite, sem dependências de
runtime, IA real, Lovable, conectores externos ou serviços pagos.

Para experimentar com **150 clientes sintéticos (75 por SaaS)**, numa base nova:

```sh
git checkout centerway-v2/missao-10-ai-proposals
cd v2
python3 -m centerway.synthetic --db data/missao02-150.sqlite3
python3 -m centerway.server --db data/missao02-150.sqlite3
```

Abrir **http://127.0.0.1:8080**. Conta `demo`, palavra-passe pública de teste
`centerway-local`. Filtrar por SaaS/estado, pesquisar e abrir um cliente. Também é
possível registar clientes e gravar observações pelo navegador.

```sh
cd v2
python3 -m pip install -r tests/requirements.txt
python3 -m unittest discover -s tests -v
```

[Instruções, cenários e limites](v2/README.md). Toda a recuperação demonstrada é
**simulação no sandbox**, nunca recuperação real de SaaS ou retenção comprovada.

A Missão 11 parte do PR #40, commit `38acb5e`, na branch `centerway-v2/missao-11-controlled-execution`. A `main` não foi
alterada. A V2 não importa a aplicação histórica dos restantes diretórios; os
comandos npm da raiz pertencem à versão antiga. Não houve deploy.
