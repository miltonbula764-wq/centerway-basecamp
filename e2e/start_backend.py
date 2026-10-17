"""Disposable GitHub-hosted backend. Never accepts a remote database URL or production secrets."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.request

assert os.environ.get('GITHUB_ACTIONS') == 'true'
assert os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
root = Path.cwd()
logs = root / 'e2e/logs'
logs.mkdir(exist_ok=True)
env = os.environ.copy()
for key in ('PGPASSWORD', 'PGSERVICE', 'PGSERVICEFILE', 'PGHOSTADDR', 'PGOPTIONS'):
    env.pop(key, None)
env.update(PGHOST='127.0.0.1', PGPORT='5432', PGUSER='postgres', PGDATABASE='cw_e2e', PGPASSFILE='/dev/null')

def run(name, args):
    with (logs / (name + '.log')).open('w') as output:
        subprocess.run(args, cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)


def wait(url):
    for _ in range(60):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(1)
    raise RuntimeError('Service not ready: ' + url)

secret = secrets.token_hex(32)
def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')
header = b64(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())
payload = b64(json.dumps({'role': 'anon', 'iss': 'supabase', 'iat': int(time.time()), 'exp': int(time.time()) + 7200}).encode())
unsigned = header + '.' + payload
anon = unsigned + '.' + b64(hmac.new(secret.encode(), unsigned.encode(), hashlib.sha256).digest())
# Only ephemeral keys; private files are outside the artifact allowlist and never printed.
private = root / 'e2e/private'
private.mkdir(mode=0o700)
def envfile(name, values):
    p = private / name
    p.write_text(''.join(k + '=' + v + '\n' for k, v in values.items()))
    p.chmod(0o600)
    return str(p)

run('bootstrap', ['psql', '-X', '-v', 'ON_ERROR_STOP=1', '-f', 'e2e/bootstrap.sql'])
run('network', ['docker', 'network', 'create', 'cw-e2e'])
run('attach-database', ['docker', 'network', 'connect', '--alias', 'db', 'cw-e2e', os.environ['PG_CONTAINER']])
auth_env = envfile('auth.env', {
    'GOTRUE_API_HOST': '0.0.0.0', 'GOTRUE_API_PORT': '9999',
    'API_EXTERNAL_URL': 'http://127.0.0.1:54321/auth/v1',
    'GOTRUE_SITE_URL': 'http://127.0.0.1:5173',
    'GOTRUE_URI_ALLOW_LIST': 'http://127.0.0.1:5173/**',
    'GOTRUE_DB_DRIVER': 'postgres', 'GOTRUE_DB_DATABASE_URL': 'postgres://postgres@db:5432/cw_e2e',
    'GOTRUE_DB_NAMESPACE': 'auth', 'GOTRUE_JWT_SECRET': secret,
    'GOTRUE_JWT_EXP': '3600', 'GOTRUE_JWT_AUD': 'authenticated',
    'GOTRUE_JWT_DEFAULT_GROUP_NAME': 'authenticated', 'GOTRUE_JWT_ADMIN_ROLES': 'service_role',
    'GOTRUE_EXTERNAL_EMAIL_ENABLED': 'true', 'GOTRUE_DISABLE_SIGNUP': 'false',
    # Disposable test instance ONLY. Password grants and signed JWT validation remain real.
    'GOTRUE_MAILER_AUTOCONFIRM': 'true', 'GOTRUE_RATE_LIMIT_EMAIL_SENT': '1000',
})
run('start-auth', ['docker', 'run', '-d', '--name', 'cw-auth', '--network', 'cw-e2e',
                   '-p', '127.0.0.1:9999:9999', '--env-file', auth_env, 'supabase/gotrue:v2.177.0'])
wait('http://127.0.0.1:9999/health')
# Apply actual repository migrations, unchanged, after GoTrue has created its own auth schema.
journal = json.loads((root / 'drizzle/migrations/meta/_journal.json').read_text())
for entry in journal['entries']:
    run(entry['tag'], ['psql', '-X', '-v', 'ON_ERROR_STOP=1', '--single-transaction', '-f',
                      'drizzle/migrations/' + entry['tag'] + '.sql'])
run('effective-acl', ['psql', '-X', '-v', 'ON_ERROR_STOP=1', '-f', 'supabase/tests/client_privileges_test.sql'])
rest_env = envfile('rest.env', {
    'PGRST_DB_URI': 'postgres://authenticator@db:5432/cw_e2e', 'PGRST_DB_SCHEMAS': 'public',
    'PGRST_DB_ANON_ROLE': 'anon', 'PGRST_JWT_SECRET': secret, 'PGRST_SERVER_PORT': '3000',
})
run('start-rest', ['docker', 'run', '-d', '--name', 'cw-rest', '--network', 'cw-e2e',
                   '-p', '127.0.0.1:54322:3000', '--env-file', rest_env, 'postgrest/postgrest:v12.2.3'])
wait('http://127.0.0.1:54322/')
nginx = private / 'nginx.conf'
nginx.write_text('''events {}\nhttp { access_log off; server { listen 80;
location /auth/v1/ { proxy_pass http://cw-auth:9999/; proxy_set_header Host $host; }
location /rest/v1/ { proxy_pass http://cw-rest:3000/; }
} }''')
run('start-gateway', ['docker', 'run', '-d', '--name', 'cw-gateway', '--network', 'cw-e2e',
                     '-p', '127.0.0.1:54321:80', '-v', str(nginx) + ':/etc/nginx/nginx.conf:ro', 'nginx:1.27-alpine'])
wait('http://127.0.0.1:54321/auth/v1/health')
(root / '.env.local').write_text('VITE_SUPABASE_URL=http://127.0.0.1:54321\nVITE_SUPABASE_PUBLISHABLE_KEY=' + anon + '\n')
(private / 'public.json').write_text(json.dumps({'url': 'http://127.0.0.1:54321', 'anon': anon}))
(logs / 'backend.json').write_text(json.dumps({'postgres': 17, 'auth': 'GoTrue v2.177.0', 'rest': 'PostgREST v12.2.3',
    'auth_method': 'real password grants; test-only auto-confirm', 'data': 'synthetic only', 'production': False}, indent=2))
print('Disposable GoTrue, PostgreSQL and PostgREST ready; migrations and effective ACL assertions passed.')
