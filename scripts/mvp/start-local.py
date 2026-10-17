"""Stage the existing application without .env and mount a new disposable MVP stack."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import tarfile

root = Path(__file__).resolve().parents[2]
for tool in ['docker', 'psql', 'bun', 'node']:
    if not shutil.which(tool):
        raise SystemExit('Missing required local tool: ' + tool)
for name in ['cw-mvp-db', 'cw-auth', 'cw-rest', 'cw-gateway']:
    if subprocess.run(['docker', 'inspect', name], capture_output=True).returncode == 0:
        raise SystemExit('Existing container ' + name + '; refuse to reuse or remove it. Stop the previous disposable stack explicitly.')
if subprocess.run(['docker', 'network', 'inspect', 'cw-e2e'], capture_output=True).returncode == 0:
    raise SystemExit('Existing cw-e2e network; refuse to reuse it.')
stage = Path(tempfile.mkdtemp(prefix='centerway-mvp-'))
archive = stage / 'source.tar'
subprocess.run(['git', 'archive', '--format=tar', '-o', str(archive), 'HEAD'], cwd=root, check=True)
with tarfile.open(archive) as tar:
    members = [m for m in tar.getmembers() if not Path(m.name).name.startswith('.env')]
    tar.extractall(stage, members=members, filter='data')
archive.unlink()
env = os.environ.copy()
for k in list(env):
    if k.startswith(('PG', 'SUPABASE', 'VITE_SUPABASE', 'DATABASE_URL')):
        env.pop(k, None)
env.update(PGHOST='127.0.0.1', PGPORT='5432', PGUSER='postgres', PGDATABASE='cw_e2e',
           PGPASSFILE='/dev/null', PG_CONTAINER='cw-mvp-db', CW_LOCAL_MVP='1')
print('Isolated working copy:', stage, flush=True)
subprocess.run(['bun', 'install', '--frozen-lockfile'], cwd=stage, env=env, check=True)
subprocess.run(['docker', 'run', '-d', '--name', 'cw-mvp-db', '--label', 'centerway.disposable=mvp',
                '-p', '127.0.0.1:5432:5432', '-e', 'POSTGRES_USER=postgres', '-e', 'POSTGRES_DB=cw_e2e',
                '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', '--tmpfs', '/var/lib/postgresql/data', 'postgres:17'], check=True)
for _ in range(60):
    if subprocess.run(['docker', 'exec', 'cw-mvp-db', 'pg_isready', '-U', 'postgres', '-d', 'cw_e2e'], capture_output=True).returncode == 0:
        break
    time.sleep(1)
else:
    raise SystemExit('Disposable database did not start; inspect docker logs cw-mvp-db.')
subprocess.run(['python3', 'e2e/start_backend.py', '--local-mvp'], cwd=stage, env=env, check=True)
subprocess.run(['node', 'e2e/mvp-seed.mjs'], cwd=stage, env=env, check=True)
subprocess.run(['python3', 'scripts/mvp/load-history.py'], cwd=stage, env=env, check=True)
print('\nOpen http://127.0.0.1:5173/app/casos\nOnly synthetic data in a new local database.', flush=True)
print('Demo accounts and temporary passwords are in the PRIVATE local file:', stage / 'e2e/private/mvp-users.json', flush=True)
print('Stop the app with Ctrl+C; remove ONLY this stack with python3 scripts/mvp/stop-local.py', flush=True)
subprocess.run(['bun', 'run', 'dev', '--host', '127.0.0.1', '--port', '5173'], cwd=stage, env=env, check=True)
