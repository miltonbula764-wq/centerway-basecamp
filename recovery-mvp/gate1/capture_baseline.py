"""Read-only pre-grant inventory, encrypted in RAM. Never a database dump."""
import argparse
import json
import os
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict
from recovery import private,require,inventory,structure,command,encode,digest,connection_environment,ROOT

def capture(config_file,binding_file,destination,recipient):
    config=json.loads(private(config_file).read_bytes())
    binding=json.loads(private(binding_file).read_bytes())
    require(binding['branch_id']!=binding['parent_id'] and binding['primary'] is False and binding['default'] is False)
    opts=conninfo_to_dict(config['dsn'])
    require(opts.get('host')==binding['host'] and opts.get('dbname')=='centerway')
    require(binding['host'].split('.')[0]==binding['endpoint_id'])
    dest=Path(destination).absolute();private(dest.parent,True)
    require(ROOT not in dest.parents and not dest.exists() and not dest.is_symlink())
    # Verifies direct TLS connection settings without relaxing the G2 contract.
    with connection_environment(config['dsn']):pass
    with psycopg.connect(config['dsn'],connect_timeout=10) as db:
        db.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        db.execute("SET LOCAL statement_timeout='30s'")
        require(db.info.server_version//10000==17)
        data={'format':'centerway-pre-export-v1','binding':binding,'tables':inventory(db),'structure':structure(db),
              'roles':db.execute("SELECT coalesce(jsonb_agg(x ORDER BY rolname),'[]'::jsonb) FROM (SELECT rolname,rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolcanlogin,rolreplication,rolbypassrls,rolconnlimit,rolvaliduntil,rolconfig FROM pg_roles WHERE rolname NOT LIKE 'pg_%') x").fetchone()[0],
              'memberships':db.execute("SELECT coalesce(jsonb_agg(x ORDER BY group_name,member_name),'[]'::jsonb) FROM (SELECT a.rolname AS group_name,b.rolname AS member_name,m.admin_option,m.inherit_option,m.set_option FROM pg_auth_members m JOIN pg_roles a ON a.oid=m.roleid JOIN pg_roles b ON b.oid=m.member) x").fetchone()[0],
              'extensions':db.execute('SELECT extname,extversion FROM pg_extension ORDER BY 1').fetchall(),
              'runtime_credentials':'not_included','purpose':'pre_grant_metadata_and_data_hashes_only'}
    cipher=command(['age','-r',recipient],encode(data))
    fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as out:out.write(cipher);out.flush();os.fsync(out.fileno())
    return {'status':'pre_export_baseline_encrypted','sha256':digest(cipher),'tables':len(data['tables'])}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['config','binding','destination','recipient']:p.add_argument('--'+name,required=True)
    a=p.parse_args();print(json.dumps(capture(a.config,a.binding,a.destination,a.recipient),sort_keys=True))
if __name__=='__main__':
    try:main()
    except Exception:
        print('baseline_capture_failed',file=__import__('sys').stderr);raise SystemExit(1)
