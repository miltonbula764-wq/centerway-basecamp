"""Explicit synthetic retrospective fixtures, new local database only."""
import json
import os
from pathlib import Path
import subprocess
if os.environ.get('CW_LOCAL_MVP') == '1':
    info=json.loads(subprocess.check_output(['docker','inspect','cw-mvp-db']))[0]
    assert info['Config'].get('Labels',{}).get('centerway.disposable') == 'mvp'
    assert info['Config']['Image'] == 'postgres:17'
    assert all(m['Type'] == 'tmpfs' and m['Destination'] == '/var/lib/postgresql/data' for m in info.get('Mounts', []))
    assert info['HostConfig']['PortBindings']['5432/tcp'] == [{'HostIp':'127.0.0.1','HostPort':'5432'}]
else:
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
assert os.environ.get('PGHOST') == '127.0.0.1'
assert os.environ.get('PGDATABASE') == 'cw_e2e'
fixture=json.dumps(json.loads(Path('e2e/mvp-fixtures.json').read_text()))
# SQL literal escaping, not shell interpolation; fixture has no credentials.
statement="BEGIN; SELECT set_config('cw.mvp_fixture', '"+fixture.replace("'","''")+"', true);\n"+Path('e2e/mvp-history.sql').read_text()+"\nCOMMIT;"
result=subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1'],input=statement,text=True,capture_output=True)
if result.returncode:
    print(result.stderr)
    raise SystemExit(result.returncode)
print('Synthetic retrospective fixture persisted. Core C09/C10 produced resolved and remain_open from actual C01-C03 evidence; this does not prove a real elapsed observation window or historical approvals.')
