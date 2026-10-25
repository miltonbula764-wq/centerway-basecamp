# CENTERWAY V2 · Missão 04 — preparação de infraestrutura

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
git checkout centerway-v2/missao-04-infra
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

A Missão 04 parte do PR #33, commit `f632c92`, na branch `centerway-v2/missao-04-infra`. A `main` não foi
alterada. A V2 não importa a aplicação histórica dos restantes diretórios; os
comandos npm da raiz pertencem à versão antiga. Não houve deploy.
