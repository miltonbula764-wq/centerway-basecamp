"""Fresh labelled tmpfs PostgreSQL17 with real pg_cron; never a remote database.

Install the extension before PostgreSQL starts: container restart would discard
its tmpfs database. Uses signed Debian packages and the existing Cron integration.
"""
from pathlib import Path
import subprocess
import time
assert subprocess.run(['docker','inspect','cw-mvp-db'],capture_output=True).returncode!=0,'Refuse to replace an existing database'
logs=Path('e2e/logs');logs.mkdir(exist_ok=True)
command='''
if [ -f /etc/apt/sources.list.d/pgdg.list ]; then
 mv /etc/apt/sources.list.d/pgdg.list /etc/apt/sources.list.d/pgdg.list.disabled
fi
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends postgresql-17-cron
exec docker-entrypoint.sh postgres -c shared_preload_libraries=pg_cron -c cron.database_name=cw_e2e -c cron.use_background_workers=on
'''
subprocess.run(['docker','run','-d','--name','cw-mvp-db','--label','centerway.disposable=mvp','-p','127.0.0.1:5432:5432','-e','POSTGRES_USER=postgres','-e','POSTGRES_DB=cw_e2e','-e','POSTGRES_HOST_AUTH_METHOD=trust','--tmpfs','/var/lib/postgresql/data','postgres:17','sh','-ec',command],check=True,stdout=subprocess.DEVNULL)
for _ in range(240):
    if subprocess.run(['docker','exec','cw-mvp-db','pg_isready','-h','127.0.0.1','-U','postgres','-d','cw_e2e'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
    time.sleep(.5)
else:
    subprocess.run(['docker','logs','--tail','30','cw-mvp-db']);raise AssertionError('Disposable Cron PostgreSQL did not start')
with (logs/'monitoring-cron-install.log').open('w') as out:subprocess.run(['docker','logs','cw-mvp-db'],stdout=out,stderr=subprocess.STDOUT,check=True)
subprocess.run(['docker','exec','-i','cw-mvp-db','psql','-h','127.0.0.1','-U','postgres','-d','cw_e2e','-v','ON_ERROR_STOP=1'],input='CREATE EXTENSION pg_cron;\n',text=True,check=True,stdout=subprocess.DEVNULL)
print('Real pg_cron loaded in fresh disposable PostgreSQL17; no job scheduled yet.')
