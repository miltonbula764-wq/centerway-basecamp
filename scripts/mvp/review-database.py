"""Review only a disposable backend, with an unconditional rollback on disconnect/error."""
import json
import os
from pathlib import Path
import subprocess

if os.environ.get('CW_LOCAL_MVP') == '1':
    info = json.loads(subprocess.check_output(['docker', 'inspect', 'cw-mvp-db']))[0]
    assert info['Config']['Image'] == 'postgres:17'
    assert info['Config'].get('Labels', {}).get('centerway.disposable') == 'mvp'
    assert all(m['Type'] == 'tmpfs' and m['Destination'] == '/var/lib/postgresql/data' for m in info.get('Mounts', []))
    assert info['HostConfig']['PortBindings']['5432/tcp'] == [{'HostIp': '127.0.0.1', 'HostPort': '5432'}]
else:
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
assert os.environ.get('PGHOST') == '127.0.0.1'
assert os.environ.get('PGDATABASE') == 'cw_e2e'
f = json.loads(Path('e2e/mvp-fixtures.json').read_text())
users = json.loads(Path('e2e/private/mvp-users.json').read_text())
f.update(operator=users['operator']['id'], viewer=users['viewer']['id'])
literal = json.dumps(f).replace("'", "''")
statement = "BEGIN; SELECT set_config('cw.review_fixture','" + literal + "',true);\n" + Path('e2e/mvp-review.sql').read_text() + '\nROLLBACK;'
env = os.environ.copy()
for key in ('PGPASSWORD', 'PGSERVICE', 'PGSERVICEFILE', 'PGHOSTADDR', 'PGOPTIONS'):
    env.pop(key, None)
env['PGPASSFILE'] = '/dev/null'
r = subprocess.run(['psql', '-X', '-h', '127.0.0.1', '-p', '5432', '-U', 'postgres', '-d', 'cw_e2e', '-v', 'ON_ERROR_STOP=1'], input=statement, text=True, capture_output=True, env=env)
# Suppress SQL output: the context contains only synthetic identifiers, but is not useful.
if r.returncode:
    print(r.stderr)
    raise SystemExit(r.returncode)
print(r.stderr.strip())
print('Disposable database review passed; all probe mutations rolled back.')
