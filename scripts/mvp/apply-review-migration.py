"""Apply 0012 only in the disposable GitHub database, proving old rows/ACLs survive."""
import os
from pathlib import Path
import subprocess
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
CREATE FUNCTION pg_temp.table_fingerprint(t text) RETURNS text LANGUAGE plpgsql AS $$
DECLARE v text;
BEGIN
  EXECUTE format('SELECT encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(r) ORDER BY to_jsonb(r)::text),''[]''::jsonb)::text,''UTF8'')),''hex'') FROM public.%I r',t) INTO v;
  RETURN v;
END $$;
CREATE TEMP TABLE before_mvp_review AS SELECT c.relname, c.relacl::text AS acl,
  pg_temp.table_fingerprint(c.relname) AS data_hash FROM pg_class c
  JOIN pg_namespace ns ON ns.oid=c.relnamespace WHERE ns.nspname='public' AND c.relkind='r';
'''
postlude = r'''
DO $$ DECLARE r record; n int:=0; BEGIN
  FOR r IN SELECT * FROM before_mvp_review LOOP
    IF pg_temp.table_fingerprint(r.relname) IS DISTINCT FROM r.data_hash THEN
      RAISE EXCEPTION 'migration changed historical rows: %',r.relname; END IF;
    IF (SELECT relacl::text FROM pg_class WHERE oid=('public.'||r.relname)::regclass) IS DISTINCT FROM r.acl THEN
      RAISE EXCEPTION 'migration changed historical table grants: %',r.relname; END IF;
    n:=n+1;
  END LOOP;
  RAISE NOTICE 'Migration 0012 non-empty upgrade passed: historical rows and table grants unchanged in % tables.',n;
END $$;
COMMIT;
'''
env=os.environ.copy()
for k in ('PGPASSWORD','PGSERVICE','PGSERVICEFILE','PGHOSTADDR','PGOPTIONS'):
    env.pop(k,None)
env['PGPASSFILE']='/dev/null'
r=subprocess.run(['psql','-X','-h','127.0.0.1','-p','5432','-U','postgres','-d','cw_e2e','-v','ON_ERROR_STOP=1'],
    input=prelude+Path('drizzle/migrations/0012_mvp_case_journey.sql').read_text()+postlude,
    text=True,capture_output=True,env=env)
print(r.stderr.strip())
if r.returncode:
    raise SystemExit(r.returncode)
print('Migration 0012 applied atomically ONLY in the disposable database; pre-existing data preserved.')
