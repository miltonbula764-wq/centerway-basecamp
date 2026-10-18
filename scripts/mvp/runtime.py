"""Shared provisioning for the existing local MVP and the isolated Codespaces demo."""
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
from disposable import DEMO_VOLUME

CONTAINERS = ['cw-mvp-db', 'cw-auth', 'cw-rest', 'cw-gateway']

def clean_env():
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('PG', 'SUPABASE', 'VITE_', 'DATABASE_', 'LOVABLE_')) or key in ('GITHUB_TOKEN', 'GH_TOKEN'):
            env.pop(key, None)
    env.update(PGHOST='127.0.0.1', PGPORT='5432', PGUSER='postgres', PGDATABASE='cw_e2e',
               PGPASSFILE='/dev/null', PG_CONTAINER='cw-mvp-db', CW_LOCAL_MVP='1')
    return env

def stage_source(root, stage):
    stage.mkdir(parents=True, exist_ok=False)
    # Stream the archive: excluded .env files never become a temporary archive on disk.
    with subprocess.Popen(['git','archive','--format=tar','HEAD'],cwd=root,stdout=subprocess.PIPE) as process:
        with tarfile.open(fileobj=process.stdout,mode='r|') as tar:
            for member in tar:
                if not Path(member.name).name.startswith('.env'):
                    tar.extract(member,stage,filter='data')
        if process.wait(): raise RuntimeError('Could not export committed application source.')

def provision(stage, *, persistent=False, origin=None):
    for tool in ['docker', 'psql', 'bun', 'node']:
        if not shutil.which(tool):
            raise RuntimeError('Missing required local tool: ' + tool)
    for name in CONTAINERS:
        if subprocess.run(['docker', 'inspect', name], capture_output=True).returncode == 0:
            raise RuntimeError('Existing container ' + name + '; refuse to reuse/remove it during provisioning.')
    if subprocess.run(['docker', 'network', 'inspect', 'cw-e2e'], capture_output=True).returncode == 0:
        raise RuntimeError('Existing cw-e2e network; refuse to reuse it.')
    env = clean_env()
    if persistent:
        if subprocess.run(['docker', 'volume', 'inspect', DEMO_VOLUME], capture_output=True).returncode == 0:
            raise RuntimeError('Existing demo volume without ready manifest; explicit reset required.')
        subprocess.run(['docker', 'volume', 'create', '--label', 'centerway.disposable=codespaces', DEMO_VOLUME], check=True)
        env.update(CW_CODESPACES_DEMO='1', CW_DEMO_ORIGIN=origin)
    subprocess.run(['bun', 'install', '--frozen-lockfile', '--registry', 'https://registry.npmjs.org'], cwd=stage, env=env, check=True)
    storage = ['-v', DEMO_VOLUME + ':/var/lib/postgresql/data'] if persistent else ['--tmpfs', '/var/lib/postgresql/data']
    subprocess.run(['docker', 'run', '-d', '--name', 'cw-mvp-db', '--label', 'centerway.disposable=' + ('codespaces' if persistent else 'mvp'),
                    '-p', '127.0.0.1:5432:5432', '-e', 'POSTGRES_USER=postgres', '-e', 'POSTGRES_DB=cw_e2e',
                    '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', *storage, 'postgres:17'], check=True)
    for _ in range(60):
        if subprocess.run(['docker', 'exec', 'cw-mvp-db', 'pg_isready', '-U', 'postgres', '-d', 'cw_e2e'], capture_output=True).returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Disposable database did not start.')
    for command in [
        ['python3', 'e2e/start_backend.py', '--local-mvp'],
        ['node', 'e2e/mvp-seed.mjs'], ['python3', 'scripts/mvp/load-history.py'],
        ['node', 'e2e/operational-seed.mjs'], ['python3', 'scripts/mvp/load-history.py', '--operational'],
    ]:
        subprocess.run(command, cwd=stage, env=env, check=True)
    return env
