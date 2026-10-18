"""Explicit synthetic retrospective fixtures, new local database only."""
import json
import os
from pathlib import Path
import subprocess
import sys
if os.environ.get('CW_LOCAL_MVP') == '1':
    from disposable import require_local_database
    require_local_database()
else:
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
assert os.environ.get('PGHOST') == '127.0.0.1'
assert os.environ.get('PGDATABASE') == 'cw_e2e'
fixture=json.dumps(json.loads(Path('e2e/operational-fixtures.json' if '--operational' in sys.argv else 'e2e/mvp-fixtures.json').read_text()))
# SQL literal escaping, not shell interpolation; fixture has no credentials.
statement="BEGIN; SELECT set_config('cw.mvp_fixture', '"+fixture.replace("'","''")+"', true);\n"+Path('e2e/operational-history.sql' if '--operational' in sys.argv else 'e2e/mvp-history.sql').read_text()+"\nCOMMIT;"
env=os.environ.copy()
for key in ('PGPASSWORD','PGSERVICE','PGSERVICEFILE','PGHOSTADDR','PGOPTIONS'):
    env.pop(key,None)
env['PGPASSFILE']='/dev/null'
result=subprocess.run(['psql','-X','-h','127.0.0.1','-p','5432','-U','postgres','-d','cw_e2e','-v','ON_ERROR_STOP=1'],input=statement,text=True,capture_output=True,env=env)
if result.returncode:
    print(result.stderr)
    raise SystemExit(result.returncode)
print('Operational C05-C08 synthetic retrospective history loaded; real C09-C10 will run separately.' if '--operational' in sys.argv else 'Synthetic retrospective fixture persisted. Core C09/C10 produced resolved and remain_open from actual C01-C03 evidence; this does not prove a real elapsed observation window or historical approvals.')
