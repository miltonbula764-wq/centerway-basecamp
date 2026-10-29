"""Offline activation gates. No DNS, database connections or resource creation."""
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlsplit


def real_hostname(value):
    forbidden=('invalid','test','localhost','local','example.com','example.org','example.net')
    return bool(re.fullmatch(r'(?=.{1,253}$)[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?',value)) and '.' in value and not any(value==s or value.endswith('.'+s) for s in forbidden)


def check_gateway():
    if not real_hostname(os.environ.get('API_HOST','')): raise ValueError('Real API hostname must be configured')
    email=os.environ.get('ACME_EMAIL','')
    if '@' not in email or not real_hostname(email.split('@')[-1]): raise ValueError('Real ACME email must be configured')
    if not re.fullmatch(r'127\.0\.0\.1:\d+',os.environ.get('UPSTREAM_ADDR','')): raise ValueError('Loopback HTTPS upstream required')
    if not Path(os.environ.get('UPSTREAM_CA','')).is_file(): raise ValueError('Upstream CA file required')


def check_api():
    config_path=Path(os.environ['CENTERWAY_API_CONFIG'])
    if stat.S_IMODE(config_path.stat().st_mode)&0o077: raise ValueError('Private API configuration required')
    config=json.loads(config_path.read_text())
    if config.get('demo') is not False: raise ValueError('Public activation requires non-demo transport protections')
    if not config.get('origins'): raise ValueError('Explicit origins required')
    for origin in config['origins']:
        u=urlsplit(origin)
        if u.scheme!='https' or origin!=f'https://{u.netloc}' or u.username or not real_hostname(u.hostname or ''):
            raise ValueError('Actual exact HTTPS interface origin required')
    # Use L01's parser; only the non-secret sslmode is inspected.
    from psycopg.conninfo import conninfo_to_dict
    for user in config['users'].values():
        if conninfo_to_dict(user['dsn']).get('sslmode')!='verify-full': raise ValueError('Verified PostgreSQL TLS required')
    for env in ('CENTERWAY_TLS_CERT','CENTERWAY_TLS_KEY'):
        if not Path(os.environ[env]).is_file(): raise ValueError('Upstream TLS certificate/key required')
    if stat.S_IMODE(Path(os.environ['CENTERWAY_TLS_KEY']).stat().st_mode)&0o077:
        raise ValueError('Private upstream TLS key required')


if __name__=='__main__':
    try:
        {'gateway':check_gateway,'api':check_api}[sys.argv[1]]()
    except Exception:
        print('Activation configuration rejected. Fill real host/origins and private TLS configuration.',file=sys.stderr)
        sys.exit(1)
    print('Offline configuration checks passed; no external connectivity or readiness established.')
