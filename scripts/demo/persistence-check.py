"""Check our labelled demo only, after a complete stop/start; never prints credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'scripts/mvp'))
from disposable import require_local_database
os.environ.update(PGHOST='127.0.0.1',PGDATABASE='cw_e2e',CW_CODESPACES_DEMO='1')
require_local_database()
sql="""SELECT encode(sha256(convert_to(jsonb_build_object(
'users',(SELECT jsonb_agg(id ORDER BY id) FROM auth.users),
'goals',(SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM public.c04_configurations x),
'cases',(SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM public.cw_operational_cases x),
'events',(SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM public.cw_operational_events x)
)::text,'UTF8')),'hex')"""
value=subprocess.check_output(['docker','exec','cw-mvp-db','psql','-U','postgres','-d','cw_e2e','-Atc',sql],text=True).strip()
p=root/'.centerway-demo/persistence.sha256'
if sys.argv[1]=='snapshot':p.write_text(value)
else:
 assert value==p.read_text(),'Demo data changed during stop/start'
 print('Own users, C04 goals, cases and history preserved across complete demo stop/start.')
