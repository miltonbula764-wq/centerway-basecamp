# CENTERWAY V2 · Missão 01

Reconstrução independente em [`v2/`](v2/README.md): C01 Observação → C02 Deteção →
C03 Investigação → C04 Decisão → C05 Execução → C06 Verificação, coordenados pelo Core.
Python + SQLite, sem dependências de runtime, Lovable ou serviços pagos.

```sh
cd v2
python3 -m centerway.server
```

Abrir **http://127.0.0.1:8080**. Escolher «Operador · duas SaaS» e usar a palavra-passe
pública de teste `centerway-local`. Seguir os botões C01 → C06 e trocar de SaaS.

```sh
cd v2
python3 -m unittest discover -s tests -v
```

[Instruções, cenários, testes e limites da V2](v2/README.md).
A decisão é um **simulador identificado, sem IA real**. Os efeitos alteram apenas o
sandbox persistido. Não houve publicação nem alteração de `main`.

Os restantes diretórios conservam a implementação histórica e não são importados
pela V2. Os comandos npm da raiz pertencem à versão antiga. O histórico anterior
permanece no Git, incluindo o ponto de partida `d764f893ea47448836f8a64f1b8660fdd3b0a143`.
