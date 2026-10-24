# Pré-visualização privada — estado: não publicada

**Não existe URL externo funcional nesta entrega.** A V2 foi preparada para uma
pré-visualização HTTPS privada e testada localmente. Não se publicou uma versão
insegura, nem uma página estática a fingir o sistema. `main` não foi alterada.

## Impedimento encontrado

O ambiente gerido não disponibiliza ingress/encaminhamento HTTPS para processos
Python, domínio/certificado ou credenciais de alojamento. Não há VPN configurada.
O alojamento Sites disponível executa Cloudflare Workers, enquanto a V2 atual usa
Python, HTTP e um ficheiro SQLite. Converter o backend para esse alojamento seria
uma adaptação da lógica/runtime fora do pedido. Não se criou um túnel nem se
contornaram as restrições de rede.

Falta um alojamento gratuito compatível com Python e armazenamento persistente,
um endereço HTTPS com certificado reconhecido pelo Chrome e encaminhamento
controlado até este servidor. Esses recursos não estão configurados neste ambiente.
Sem eles, o fundador ainda não consegue experimentar a V2 só pelo Android.

## Preparação entregue

- Mesmos ficheiros de interface da Missão 02, mesmos endpoints, Core e componentes
  C01–C06. Só se substituem os campos de login na resposta HTML do modo privado.
- Base dedicada com os mesmos 150 clientes fictícios; todas as intervenções são
  sandbox. Não se copia nenhuma base existente. A proveniência privada é marcada.
- Contas `founder` (operador das duas SaaS), `atlas-private` (operador só Atlas) e
  `reader-private` (leitor só Nimbus), cada uma com segredo aleatório de 32 bytes.
  As três contas públicas do laboratório são removidas antes de gerar os cenários.
- Segredos e SQLite ficam fora do checkout, com modo 0600. Os segredos não são
  impressos, enviados para GitHub ou incluídos no HTML. O operador responsável deve
  entregar apenas a credencial necessária ao fundador por um canal privado.
- HTTPS obrigatório, TLS mínimo 1.2, Host fixo e Origin HTTPS exata nas mutações.
  Headers de proxy não autenticam ninguém nem dispensam TLS. Cookies
  `__Host-cw_session`, Secure, HttpOnly, SameSite=Strict, sem Domain, duração de 1 h.
- Pré-visualização expira em até 24 h: depois disso até a página é recusada (503).
  Logout revoga a sessão; sessões expiradas não acedem à API. Login limitado a dez
  tentativas/minuto por endereço real e por conta. Não se confia em X-Forwarded-For.
- CSP, anti-frame, no-store, no-referrer e HSTS. Pedidos têm limites de corpo/tempo;
  o servidor privado limita a 32 threads, incluindo o handshake TLS.
- O modo privado recusa base normal, contas/senhas públicas e certificado ausente.
  O modo HTTP recusa bases privadas e bind fora de loopback. Não há fallback HTTP.

## Operação futura — para quem disponibilizar a infraestrutura

Os comandos seguintes **não criam alojamento nem um URL**. O domínio `.invalid`
é apenas um marcador a substituir por infraestrutura previamente disponibilizada.
Não são passos para o fundador executar no telemóvel.

```sh
cd v2
python3 -m centerway.preview init \
  --db /caminho-privado/centerway-preview.sqlite3 \
  --credentials-file /caminho-privado/centerway-credentials.json \
  --origin https://preview.example.invalid --hours 24

python3 -m centerway.preview serve \
  --db /caminho-privado/centerway-preview.sqlite3 \
  --certfile /caminho-privado/fullchain.pem \
  --keyfile /caminho-privado/privkey.pem \
  --host 0.0.0.0 --port 8443
```

O certificado deve corresponder ao domínio real e ser confiável para o Chrome.
O servidor recebe TLS diretamente; se houver proxy, deve manter TLS até ao backend
e preservar o Host público. Não basta enviar `X-Forwarded-Proto: https`.
Antes de entregar acesso, é necessário verificar externamente certificado, acesso
anónimo recusado pela API, credencial privada, isolamento e o percurso no Android
real. Não instruir o utilizador a ignorar alertas de certificado.

Depois de existir um URL validado, o acesso do fundador resume-se a abrir o link
no Chrome Android, introduzir a conta privada e a palavra-passe recebidas, e abrir
um cliente. O login de laboratório não é válido nessa instalação.

## Testes realizados e repetição

```sh
python3 -m unittest discover -s tests -v
npm ci --ignore-scripts
npx playwright install chromium
npm run test:browser
npm run test:private-browser
# Com Chromium já instalado:
CHROMIUM_PATH=/usr/bin/chromium npm run test:private-browser
```

- Testes HTTPS com certificado temporário de teste e validação TLS ligada, confiando
  explicitamente nesse certificado no cliente Python: autenticação, cookie seguro,
  recusa das contas públicas, logout, expiração, limites de login, CSRF/Host,
  isolamento entre SaaS/clientes, permissões, execução C05/C06 e paths de ficheiros.
- Arranque sem TLS/certificado e com base/credenciais inadequadas é recusado. Se a
  substituição do formulário não for segura, a página é recusada, sem expor a senha
  pública. Ficheiros de credenciais/base com permissões restritas são verificados.
- Chromium com emulação Pixel 7: login privado, recusa de login público, filtros de
  150 clientes, C01–C06, resultados de sandbox, cookies Secure, logout e leitor
  isolado. A interface e a lógica da Missão 02 permanecem sob os testes anteriores.
- A emulação usa uma exceção de certificado **apenas no contexto descartável de
  teste local**. Isso não prova confiança num certificado público. O teste Python
  valida a cadeia confiando explicitamente na CA de teste, sem desativar verificação.

## Limitações

Sem alojamento, URL público, certificado público, entrega de credenciais ao
fundador ou teste num Android físico. Não foi feito pentest nem teste de carga.
O servidor da biblioteca padrão continua destinado a um ensaio privado e curto;
não é uma instalação de produção. Limites de login vivem na memória do processo e
reiniciam com ele. A expiração impede novos acessos, mas não apaga os ficheiros;
a sua remoção segura fica a cargo do responsável pelo alojamento.

Os limites funcionais da Missão 02 mantêm-se, incluindo catálogo fixo, ausência de
conectores/IA real e recuperação exclusivamente simulada.
