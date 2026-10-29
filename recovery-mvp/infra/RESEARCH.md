# C01 — decisão técnica HTTPS (consulta em 2026-10-29)

Recomendação: **Caddy num host estável já disponível**, ou num servidor cujo custo
seja aprovado separadamente, com TLS público automático e TLS verificado até Gunicorn.
Não é uma recomendação para comprar um VPS agora. Não existe domínio, servidor ou
origem Lovable real fornecido nesta missão. Nada foi provisionado na Internet.

A escolha preserva o desenho L01: SQLite persistente, um processo/nó, logins PostgreSQL
individuais e a exigência de HTTPS observado no WSGI. Evita uma nova dependência de
identidade num fornecedor e permite testar exatamente o proxy utilizado. Caddy
[automatiza emissão e renovação de certificados e redirecionamento HTTP](https://caddyserver.com/docs/automatic-https).
Isso reduz tarefas de TLS; não elimina manutenção do SO, backups ou o ponto único de falha.

| Opção | Segurança e identidade | Manutenção/disponibilidade | Custos e limites | Administração por telemóvel |
|---|---|---|---|---|
| Caddy + host próprio | Terminação TLS sob controlo do operador; API TLS e PG privados; sem token de túnel | SO, certificados internos, backup SQLite/PG e monitorização próprios; precisa host sempre ligado e entrada 443/ACME | Software/certificados automáticos sem nova licença; host, domínio, tráfego e backup podem ter custo; sem SLA intrínseco | SSH com chave e sudo limitado; estado/restart por systemd; DNS em painel web |
| Cloudflare Tunnel nomeado | Ligações de saída; dispensa IP público/portas de entrada; TLS termina também na Cloudflare; token de túnel é segredo adicional | Painel ajuda nas rotas, mas cloudflared e o host continuam a precisar de manutenção; dependência da Cloudflare e da ligação de saída | Tunnel disponível em todos os planos, incluindo Free; domínio/host continuam necessários; rever limites/termos do plano antes de ativar | Painel web é conveniente; instalar/atualizar daemon e proteger token ainda exige acesso ao host |
| Render Free | HTTPS gerido; persistência e identidade devem ser adaptadas cuidadosamente | Serviço pode adormecer e reiniciar; filesystem efémero não é compatível com a garantia atual de sessões SQLite persistentes | Free tem quotas e serviços podem ser suspensos; disco persistente exige plano pago; inadequado sem redesenho L01, fora de C01 | Painel simples, mas falhas por quotas/arranques e persistência exigem intervenção |
| Tailscale Funnel | HTTPS público gerido; autenticação L01 continua necessária; acesso público não equivale a identidade tailnet | Requer daemon, host e política própria; tráfego de Funnel tem limites | Elegibilidade/custos dependem do plano e uso; não presumir que plano pessoal cobre SaaS comercial | Aplicação/painel ajudam; URL e limites do Funnel condicionam a operação |

Cloudflare documenta [túneis sem IP público](https://developers.cloudflare.com/tunnel/)
e [verificação TLS da origem](https://developers.cloudflare.com/tunnel/reference/origin-parameters/).
É a alternativa preferível se o host existente estiver sob CGNAT e não houver servidor
público aprovado. Nesse caso, usar túnel **nomeado**, hostname estável e origem HTTPS
verificada; nunca `noTLSVerify`, origem HTTP ou token no frontend. A migração para esse
transporte e a verificação externa requerem ativação futura explícita; não foram feitas.

[Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
não são a base recomendada: hostname muda, sem garantia de uptime, limite de 200 pedidos
em voo e sem SSE. Essas propriedades dificultam CORS estável e operação fiável. Não foi
aberto sequer um Quick Tunnel nesta missão.

[Render Free](https://render.com/docs/free) descreve suspensão após inatividade, limites
de horas e ausência de disco persistente gratuito. Evitar pings artificiais para
contornar condições do serviço. [Funnel](https://tailscale.com/docs/features/tailscale-funnel)
é útil em demonstrações autorizadas, mas as suas restrições de domínio/portas e banda
não substituem um plano de disponibilidade. Não foi criada conta em nenhum fornecedor.

## Custos e autorização

Não foi contratado nenhum recurso ou serviço. Não há preço universal de VPS/domínio:
depende de região, impostos, quotas, fornecedor e infraestrutura já existente.
Antes de qualquer compra, obter orçamento explícito de host, domínio, backup e eventual
monitorização. Se o host/domínio já existirem, Caddy não acrescenta uma licença de proxy;
isso não significa custo operacional zero. Termos e preços devem ser confirmados no
momento de contratar. Free não é tratado como sinónimo de segurança ou fiabilidade.

## Cabeçalhos e confiança

A [configuração reverse_proxy oficial](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
permite verificar o CA e o nome do upstream. Esta entrega fixa Caddy v2.11.7 por digest
de imagem em versions.env, remove cabeçalhos de forwarding e estabelece TLS até
Gunicorn. O [Gunicorn](https://gunicorn.org/reference/settings/) pode interpretar
cabeçalhos de esquema; aqui secure_scheme_headers é vazio e forwarded_allow_ips também.
Não se instala ProxyFix nem se confia em qualquer CIDR enviado pelo cliente.

O endereço visto pela L01 é o loopback do proxy: o rate limit de login existente é
agregado, conservador e partilhado pelos clientes desse proxy. Não é uma proteção
por IP externo. Resolver isso no futuro exige política/proxy-aware limiter próprio,
não simplesmente confiar em X-Forwarded-For.
