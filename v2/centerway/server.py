import argparse
import hashlib
import hmac
import json
import secrets
import ssl
import sqlite3
import ipaddress
import re
import threading
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .core import Core, Problem
from .store import Store
from .http_contract import API_METHODS, API_VERSION, ERROR_CODES, strict_json, view_query

STATIC = Path(__file__).resolve().parent.parent / 'static'


def make_server(store, host='127.0.0.1', port=8080, *, preview=None, tls_context=None, frontend_origins=()):
    production=getattr(preview,'mode',None)=='production'
    with store.transaction() as db:
        marked_production=bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='production_metadata'").fetchone())
    if marked_production!=production:
        raise ValueError('Modo explícito incompatível com a base; nenhum fallback permitido.')
    if production:
        preview.validate_runtime(store)
    if frontend_origins and not preview:
        raise ValueError('CORS externo só pode ser configurado no modo privado HTTPS.')
    from .preview import canonical_origin
    frontend_origins = frozenset(canonical_origin(origin) for origin in frontend_origins)
    if preview and not tls_context:
        raise ValueError('Pré-visualização privada exige TLS; não existe fallback HTTP.')
    if not preview:
        if host != 'localhost' and not ipaddress.ip_address(host).is_loopback:
            raise ValueError('O laboratório com contas públicas só pode escutar em loopback.')
        with store.transaction() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name IN ('preview_metadata','production_metadata')").fetchone():
                raise ValueError('Base privada exige o servidor HTTPS de pré-visualização.')
    core = Core(store)
    cookie_name = '__Host-cw_production_session' if production else '__Host-cw_session' if preview else 'cw_session'
    cookie_flags = '; HttpOnly; SameSite=Strict; Path=/' + ('; Secure' if preview else '')
    session_seconds = 3600 if preview else 28800

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, value, cookie=None, content_type='application/json; charset=utf-8', extra_headers=None):
            if status>=400 and isinstance(value,dict) and 'error' in value:
                value = {**value,'code':ERROR_CODES.get(status,'internal_error')}
            payload = b'' if status==204 else json.dumps(value,ensure_ascii=False).encode() if content_type.startswith('application/json') else value
            self.send_response(status)
            if status!=204:
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length',str(len(payload)))
            self.send_header('X-Centerway-API-Version',API_VERSION)
            if urlparse(self.path).path.startswith('/api/'):
                self.send_header('Vary','Origin')
                origin=self.headers.get('Origin')
                if preview and origin in ({preview.origin} | frontend_origins):
                    self.send_header('Access-Control-Allow-Origin',origin)
                    self.send_header('Access-Control-Allow-Credentials','true')
                    self.send_header('Access-Control-Expose-Headers','Retry-After, X-Centerway-API-Version')
            for key,value in (extra_headers or {}).items():
                self.send_header(key,value)
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
            if self.command!='HEAD':
                self.wfile.write(payload)

        def log_request(self, code='-', size='-'):
            # Queries may contain an accidental secret; never log request lines/headers/body.
            path=getattr(self,'path','').split('?',1)[0]
            safe_path=path if path in API_METHODS or path in ('/','/app.js','/style.css') else '<unknown>'
            self.log_message('%s %s %s',getattr(self,'command',None) or '<invalid>',safe_path,str(code))

        def log_error(self, _format, *_args):
            self.log_message('HTTP error (details omitted)')

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
                raise Problem(401, 'Inicie sessão.')
            return row['user_id']

        def check_transport(self):
            if not preview:
                return
            if not isinstance(self.connection,ssl.SSLSocket):
                raise Problem(503,'HTTPS obrigatório.')
            if production:
                try: preview.validate_runtime(store)
                except (ValueError,OSError,sqlite3.Error):
                    raise Problem(503,'Fundação production indisponível; verificação de modo/proteções falhou.')
            if preview.expired():
                raise Problem(503,'Pré-visualização expirada; acesso encerrado.')
            if self.headers.get('Host') != preview.authority:
                raise Problem(421,'Host não autorizado.')

        def check_origin(self, mutation=False):
            origin=self.headers.get('Origin')
            if preview:
                if (mutation or origin is not None) and origin not in ({preview.origin} | frontend_origins):
                    raise Problem(403,'Origem HTTPS não autorizada.')
            elif mutation and origin and origin not in ('http://'+self.headers.get('Host',''),'https://'+self.headers.get('Host','')):
                raise Problem(403,'Origem não autorizada.')
            if self.headers.get('Sec-Fetch-Site')=='cross-site':
                raise Problem(403,'Pedidos cross-site não são suportados por esta autenticação.')

        def route(self, method):
            parsed=urlparse(self.path)
            expected=API_METHODS.get(parsed.path)
            if expected and expected!=method:
                self.respond(405,{'error':'Método não permitido.'},extra_headers={'Allow':expected+', OPTIONS'})
                return None
            if expected and parsed.path!='/api/view' and parsed.query:
                raise Problem(400,'Este endpoint não aceita parâmetros na query.')
            return parsed

        def do_OPTIONS(self):
            try:
                self.check_transport()
                parsed=urlparse(self.path)
                expected=API_METHODS.get(parsed.path)
                if not expected:
                    raise Problem(404,'Endpoint não encontrado.')
                if not self.headers.get('Origin'):
                    raise Problem(403,'Origem necessária para preflight.')
                self.check_origin(mutation=True)
                if self.headers.get('Access-Control-Request-Method')!=expected:
                    self.respond(405,{'error':'Método de preflight não permitido.'},extra_headers={'Allow':expected+', OPTIONS'})
                    return
                headers={h.strip().lower() for h in self.headers.get('Access-Control-Request-Headers','').split(',') if h.strip()}
                if headers-{'content-type'}:
                    raise Problem(400,'Headers de preflight não autorizados.')
                self.respond(204,None,extra_headers={'Access-Control-Allow-Methods':expected,
                    'Access-Control-Allow-Headers':'Content-Type','Access-Control-Max-Age':'300'})
            except Problem as error:
                self.respond(error.status,{'error':error.message})

        def do_PUT(self):
            self.unsupported_method()

        do_DELETE=do_PUT
        do_PATCH=do_PUT
        do_HEAD=do_PUT
        do_TRACE=do_PUT
        do_CONNECT=do_PUT

        def unsupported_method(self):
            try:
                self.check_transport()
                if urlparse(self.path).path not in API_METHODS:
                    raise Problem(404,'Endpoint não encontrado.')
                self.route(self.command)
            except Problem as error:
                self.respond(error.status,{'error':error.message})

        def setup(self):
            self.request.settimeout(10)
            if preview:
                self.request.do_handshake()
            super().setup()

        def do_GET(self):
            try:
                self.check_transport()
                parsed = self.route('GET')
                if parsed is None:
                    return
                if parsed.path.startswith('/api/'):
                    self.check_origin()
                assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
                if parsed.path in assets:
                    filename, mime = assets[parsed.path]
                    if production:
                        raise Problem(404,'Este backend production fornece apenas a API; nenhuma interface demo é servida.')
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
                    self.respond(200,preview.view(store,self.identity(),*view_query(parsed.query)) if production else core.view(self.identity(),*view_query(parsed.query)))
                else:
                    raise Problem(404, 'Página não encontrada.')
            except Problem as error:
                self.respond(error.status, {'error': error.message})

            except ValueError:
                self.respond(400,{'error':'Parâmetros inválidos.'})
            except Exception:
                self.log_error('Internal request failure')
                self.respond(500,{'error':'Falha interna; pedido não concluído.'})

        def do_POST(self):
            try:
                self.check_transport()
                parsed=self.route('POST')
                if parsed is None:
                    return
                if parsed.path not in API_METHODS:
                    raise Problem(404,'Endpoint não encontrado.')
                self.check_origin(mutation=True)
                if self.headers.get_content_type() != 'application/json':
                    raise Problem(415, 'Use application/json.')
                length = int(self.headers.get('Content-Length', 0))
                if length>65536:
                    raise Problem(413,'Corpo demasiado grande; máximo 65536 bytes.')
                if length<=0:
                    raise Problem(400, 'Corpo inválido ou demasiado grande.')
                body = strict_json(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise Problem(400, 'Objeto JSON necessário.')
                if parsed.path=='/api/login':
                    if set(body)!={'user','password'}:
                        raise Problem(400,'Login exige apenas user e password.')
                    user, password = body.get('user'), body.get('password')
                    if not isinstance(user,str) or not isinstance(password,str) or not 1 <= len(user) <= 64 or not 1 <= len(password) <= 256:
                        raise Problem(400, 'Utilizador e palavra-passe necessários.')
                    if preview and not preview.limiter.allow(self.client_address[0],user):
                        raise Problem(429,'Demasiadas tentativas; aguarde um minuto.')
                    if production:
                        from .production import RESERVED_USERS
                        if user in RESERVED_USERS or password=='centerway-local':
                            raise Problem(401,'Credenciais inválidas.')
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
                if parsed.path=='/api/logout':
                    if body:
                        raise Problem(400,'Logout exige um objeto vazio.')
                    cookies = SimpleCookie(self.headers.get('Cookie', ''))
                    with store.transaction() as db:
                        db.execute('DELETE FROM sessions WHERE token=?', (cookies[cookie_name].value,))
                    self.respond(200, {}, f'{cookie_name}={cookie_flags}; Max-Age=0')
                    return
                allowed = {'tenant','customer','case_id'}
                if parsed.path == '/api/customers':
                    allowed = {'tenant','customer','name','scenario'}
                elif parsed.path == '/api/observations':
                    allowed = {'tenant','customer','observations'}
                if set(body) - allowed:
                    raise Problem(400,'Campos não autorizados; decisão e permissões vêm do servidor.')
                tenant, customer, case_id = body.get('tenant'), body.get('customer'), body.get('case_id')
                if not isinstance(tenant,str) or not 1 <= len(tenant) <= 128 or not isinstance(customer,str) or not 1 <= len(customer) <= 128 or (case_id is not None and (not isinstance(case_id,str) or not 1 <= len(case_id) <= 128)):
                    raise Problem(400,'SaaS e cliente explícitos são obrigatórios.')
                if production:
                    preview.block_operation(store,user,tenant)
                if parsed.path == '/api/customers':
                    self.respond(201,core.create_customer(user,tenant,customer,body.get('name'),body.get('scenario','blocked')))
                    return
                if parsed.path == '/api/observations':
                    self.respond(200,core.ingest(user,tenant,customer,body.get('observations')))
                    return
                operations = {'/api/advance':core.advance, '/api/execute':core.execute, '/api/verify':core.verify, '/api/simulate-usage':core.simulate_usage}
                operation = operations.get(parsed.path)
                if not operation:
                    raise Problem(404,'Operação não encontrada.')
                if parsed.path != '/api/advance' and not case_id:
                    raise Problem(400,'Caso necessário.')
                self.respond(200,operation(user,tenant,customer,case_id))
            except Problem as error:
                self.respond(error.status, {'error': error.message})
            except (ValueError, TypeError, json.JSONDecodeError):
                self.respond(400, {'error': 'Pedido inválido.'})
            except Exception:
                # Do not disclose internal state or credentials in error responses.
                self.log_error('Internal request failure')
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
