import argparse
import hashlib
import hmac
import json
import secrets
import ssl
import ipaddress
import re
import threading
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from .core import Core, Problem
from .store import Store

STATIC = Path(__file__).resolve().parent.parent / 'static'


def make_server(store, host='127.0.0.1', port=8080, *, preview=None, tls_context=None):
    if preview and not tls_context:
        raise ValueError('Pré-visualização privada exige TLS; não existe fallback HTTP.')
    if not preview:
        if host != 'localhost' and not ipaddress.ip_address(host).is_loopback:
            raise ValueError('O laboratório com contas públicas só pode escutar em loopback.')
        with store.transaction() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='preview_metadata'").fetchone():
                raise ValueError('Base privada exige o servidor HTTPS de pré-visualização.')
    core = Core(store)
    cookie_name = '__Host-cw_session' if preview else 'cw_session'
    cookie_flags = '; HttpOnly; SameSite=Strict; Path=/' + ('; Secure' if preview else '')
    session_seconds = 3600 if preview else 28800

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, value, cookie=None, content_type='application/json; charset=utf-8'):
            payload = json.dumps(value, ensure_ascii=False).encode() if content_type.startswith('application/json') else value
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            if status==429:
                self.send_header('Retry-After','60')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            if preview:
                self.send_header('Strict-Transport-Security','max-age=3600')
                self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            if cookie:
                self.send_header('Set-Cookie', cookie)
            self.end_headers()
            self.wfile.write(payload)

        def identity(self):
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get('Cookie', ''))
            except Exception:
                raise Problem(401, 'Sessão inválida.')
            token = cookies.get(cookie_name)
            with store.transaction() as db:
                row = db.execute('SELECT user_id FROM sessions WHERE token=? AND expires>?', (token.value if token else '', datetime.now(timezone.utc).isoformat())).fetchone()
            if not row:
                raise Problem(401, 'Inicie sessão no laboratório.')
            return row['user_id']

        def check_transport(self):
            if not preview:
                return
            if not isinstance(self.connection,ssl.SSLSocket):
                raise Problem(503,'HTTPS obrigatório.')
            if preview.expired():
                raise Problem(503,'Pré-visualização expirada; acesso encerrado.')
            if self.headers.get('Host') != preview.authority:
                raise Problem(421,'Host não autorizado.')

        def setup(self):
            self.request.settimeout(10)
            if preview:
                self.request.do_handshake()
            super().setup()

        def do_GET(self):
            try:
                self.check_transport()
                parsed = urlparse(self.path)
                assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
                if parsed.path in assets:
                    filename, mime = assets[parsed.path]
                    payload = (STATIC / filename).read_bytes()
                    if preview and filename=='index.html':
                        # Only the authentication fields change; the product UI is retained.
                        html = payload.decode()
                        private_login = '<section id="login"><h2>Entrar na pré-visualização privada</h2><form id="login-form"><label>Conta privada<input id="account" autocomplete="username" maxlength="64" required></label><label>Palavra-passe privada<input id="password" type="password" autocomplete="current-password" maxlength="256" required></label><button type="submit">Entrar →</button></form></section>'
                        html,count = re.subn(r'<section id="login">.*?</section>',private_login,html,flags=re.S)
                        if count!=1 or 'centerway-local' in html or '<select id="account">' in html:
                            raise Problem(503,'Formulário privado indisponível; acesso recusado.')
                        payload = html.replace('LABORATÓRIO LOCAL','PRÉ-VISUALIZAÇÃO PRIVADA').encode()
                    self.respond(200,payload,content_type=mime)
                elif parsed.path == '/api/view':
                    query = parse_qs(parsed.query)
                    self.respond(200, core.view(self.identity(), *(query.get(key, [None])[0] for key in ('tenant','customer','case_id'))))
                else:
                    raise Problem(404, 'Página não encontrada.')
            except Problem as error:
                self.respond(error.status, {'error': error.message})

        def do_POST(self):
            try:
                self.check_transport()
                # No CORS; reject cross-site form posts and foreign origins, including login.
                origin = self.headers.get('Origin')
                if preview and origin != preview.origin:
                    raise Problem(403,'Origem HTTPS exata necessária.')
                if origin and origin not in ('http://' + self.headers.get('Host', ''), 'https://' + self.headers.get('Host', '')):
                    raise Problem(403, 'Origem não autorizada.')
                if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                    raise Problem(403, 'Pedido cross-site bloqueado.')
                if self.headers.get_content_type() != 'application/json':
                    raise Problem(415, 'Use application/json.')
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 65536:
                    raise Problem(400, 'Corpo inválido ou demasiado grande.')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise Problem(400, 'Objeto JSON necessário.')
                if self.path == '/api/login':
                    user, password = body.get('user'), body.get('password')
                    if not isinstance(user,str) or not isinstance(password,str) or not 1 <= len(user) <= 64 or not 1 <= len(password) <= 256:
                        raise Problem(400, 'Utilizador e palavra-passe necessários.')
                    if preview and not preview.limiter.allow(self.client_address[0],user):
                        raise Problem(429,'Demasiadas tentativas; aguarde um minuto.')
                    with store.transaction() as db:
                        row = db.execute('SELECT password_hash FROM users WHERE id=?', (user,)).fetchone()
                        # Same cost for unknown accounts.
                        salt, expected = row['password_hash'].split(':') if row else ('unknown', 'invalid')
                        digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
                        if not row or not hmac.compare_digest(expected, digest):
                            raise Problem(401, 'Credenciais inválidas.')
                        token = secrets.token_urlsafe(32)
                        expiry = (datetime.now(timezone.utc) + timedelta(seconds=session_seconds)).isoformat()
                        db.execute('DELETE FROM sessions WHERE expires<=?', (datetime.now(timezone.utc).isoformat(),))
                        db.execute('INSERT INTO sessions VALUES (?,?,?)', (token, user, expiry))
                    self.respond(200, {'user': user}, f'{cookie_name}={token}{cookie_flags}; Max-Age={session_seconds}')
                    return
                user = self.identity()
                if self.path == '/api/logout':
                    cookies = SimpleCookie(self.headers.get('Cookie', ''))
                    with store.transaction() as db:
                        db.execute('DELETE FROM sessions WHERE token=?', (cookies[cookie_name].value,))
                    self.respond(200, {}, f'{cookie_name}={cookie_flags}; Max-Age=0')
                    return
                allowed = {'tenant','customer','case_id'}
                if self.path == '/api/customers':
                    allowed = {'tenant','customer','name','scenario'}
                elif self.path == '/api/observations':
                    allowed = {'tenant','customer','observations'}
                if set(body) - allowed:
                    raise Problem(400,'Campos não autorizados; decisão e permissões vêm do servidor.')
                tenant, customer, case_id = body.get('tenant'), body.get('customer'), body.get('case_id')
                if not isinstance(tenant,str) or not isinstance(customer,str) or not customer or (case_id is not None and not isinstance(case_id,str)):
                    raise Problem(400,'SaaS e cliente explícitos são obrigatórios.')
                if self.path == '/api/customers':
                    self.respond(201,core.create_customer(user,tenant,customer,body.get('name'),body.get('scenario','blocked')))
                    return
                if self.path == '/api/observations':
                    self.respond(200,core.ingest(user,tenant,customer,body.get('observations')))
                    return
                operations = {'/api/advance':core.advance, '/api/execute':core.execute, '/api/verify':core.verify, '/api/simulate-usage':core.simulate_usage}
                operation = operations.get(self.path)
                if not operation:
                    raise Problem(404,'Operação não encontrada.')
                if self.path != '/api/advance' and not case_id:
                    raise Problem(400,'Caso necessário.')
                self.respond(200,operation(user,tenant,customer,case_id))
            except Problem as error:
                self.respond(error.status, {'error': error.message})
            except (ValueError, TypeError, json.JSONDecodeError):
                self.respond(400, {'error': 'Pedido inválido.'})
            except Exception:
                # Do not disclose internal state or credentials in error responses.
                import traceback
                traceback.print_exc()
                self.respond(500, {'error': 'Falha interna; transação revertida.'})

    class PreviewHTTPServer(ThreadingHTTPServer):
        # Slow TLS handshakes run in bounded request threads, never in accept().
        slots = threading.BoundedSemaphore(32)

        def process_request(self,request,address):
            if not self.slots.acquire(blocking=False):
                self.shutdown_request(request)
                return
            try:
                super().process_request(request,address)
            except BaseException:
                self.slots.release()
                raise

        def process_request_thread(self,request,address):
            try:
                super().process_request_thread(request,address)
            finally:
                self.slots.release()

    server = (PreviewHTTPServer if preview else ThreadingHTTPServer)((host,port),Handler)
    if tls_context:
        server.socket = tls_context.wrap_socket(server.socket,server_side=True,do_handshake_on_connect=False)
    return server


def main():
    parser = argparse.ArgumentParser(description='CENTERWAY V2 — laboratório local, sem serviços externos')
    parser.add_argument('--db', default='data/centerway.sqlite3')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=8080, type=int)
    args = parser.parse_args()
    server = make_server(Store(args.db), args.host, args.port)
    print(f'CENTERWAY V2 · SANDBOX · simulador de decisão · http://{args.host}:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
