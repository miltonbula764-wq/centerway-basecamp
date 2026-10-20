"""Apply 0012, or subsequent additive C04 migrations with --c04, only in the disposable GitHub database, proving old rows/ACLs survive."""
import os
import json
import sys
from pathlib import Path
import subprocess
if os.environ.get('CW_LOCAL_MVP') == '1':
    info = json.loads(subprocess.check_output(['docker', 'inspect', 'cw-mvp-db']))[0]
    assert info['Config']['Image'] == 'postgres:17'
    assert info['Config'].get('Labels', {}).get('centerway.disposable') == 'mvp'
    assert '/var/lib/postgresql/data' in info['HostConfig'].get('Tmpfs', {})
    assert all(m['Type']=='tmpfs' for m in info.get('Mounts', []))
    assert info['HostConfig']['PortBindings']['5432/tcp'] == [{'HostIp': '127.0.0.1', 'HostPort': '5432'}]
else:
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
assert os.environ.get('PGHOST') == '127.0.0.1'
assert os.environ.get('PGDATABASE') == 'cw_e2e'
prelude = r'''
BEGIN;
DO $$ BEGIN
  IF NOT EXISTS(SELECT FROM public.observations) OR NOT EXISTS(SELECT FROM public.c03_bundles) THEN
    RAISE EXCEPTION 'non-empty C01-C03 fixtures required before migration review'; END IF;
END $$;
CREATE FUNCTION pg_temp.table_fingerprint(t text, cols text[]) RETURNS text LANGUAGE plpgsql AS $$
DECLARE v text;
BEGIN
  EXECUTE format('SELECT encode(sha256(convert_to(coalesce(jsonb_agg(x.j ORDER BY x.j::text),''[]''::jsonb)::text,''UTF8'')),''hex'') FROM public.%I r CROSS JOIN LATERAL (SELECT jsonb_object_agg(k,v) j FROM jsonb_each(to_jsonb(r)) e(k,v) WHERE k=ANY($1)) x',t) INTO v USING cols;
  RETURN v;
END $$;
CREATE TEMP TABLE before_mvp_review AS SELECT c.relname, c.relacl::text AS acl,
  a.cols, pg_temp.table_fingerprint(c.relname,a.cols) AS data_hash FROM pg_class c
  JOIN pg_namespace ns ON ns.oid=c.relnamespace CROSS JOIN LATERAL (SELECT array_agg(attname::text ORDER BY attnum) cols FROM pg_attribute WHERE attrelid=c.oid AND attnum>0 AND NOT attisdropped) a WHERE ns.nspname='public' AND c.relkind='r';
'''
postlude = r'''
DO $$ DECLARE r record; n int:=0; BEGIN
  FOR r IN SELECT * FROM before_mvp_review LOOP
    IF pg_temp.table_fingerprint(r.relname,r.cols) IS DISTINCT FROM r.data_hash THEN
      RAISE EXCEPTION 'migration changed historical rows: %',r.relname; END IF;
    IF (SELECT relacl::text FROM pg_class WHERE oid=('public.'||r.relname)::regclass) IS DISTINCT FROM r.acl THEN
      RAISE EXCEPTION 'migration changed historical table grants: %',r.relname; END IF;
    n:=n+1;
  END LOOP;
  RAISE NOTICE 'Non-empty upgrade passed: historical rows and table grants unchanged in % tables.',n;
END $$;
COMMIT;
'''
env=os.environ.copy()
for k in ('PGPASSWORD','PGSERVICE','PGSERVICEFILE','PGHOSTADDR','PGOPTIONS'):
    env.pop(k,None)
env['PGPASSFILE']='/dev/null'
r=subprocess.run(['psql','-X','-h','127.0.0.1','-p','5432','-U','postgres','-d','cw_e2e','-v','ON_ERROR_STOP=1'],
    input=prelude+''.join(Path('drizzle/migrations/'+e['tag']+'.sql').read_text()+'\n' for e in json.loads(Path('drizzle/migrations/meta/_journal.json').read_text())['entries'] if (e['idx'] in (23,24,25) if '--onboarding' in sys.argv else e['idx']==22 if '--responsibilities' in sys.argv else e['idx']==21 if '--cycles' in sys.argv else e['idx'] in (19,20) if '--monitoring' in sys.argv else e['idx'] in (17,18) if '--api' in sys.argv else e['idx']==16 if '--team' in sys.argv else e['idx']==15 if '--followup' in sys.argv else e['idx']==14 if '--operational' in sys.argv else e['idx']==13 if '--c04' in sys.argv else e['idx']==12))+postlude,
    text=True,capture_output=True,env=env)
print(r.stderr.strip())
if r.returncode:
    raise SystemExit(r.returncode)
print('Selected migration(s) applied atomically ONLY in the disposable database; pre-existing data preserved.')
