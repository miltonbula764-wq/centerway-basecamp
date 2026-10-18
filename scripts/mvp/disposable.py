"""Guards for our own local disposable containers; never accepts a database URL."""
import json
import os
import subprocess

DEMO_VOLUME = 'cw-codespaces-demo-data'

def require_local_database():
    assert os.environ.get('PGHOST') == '127.0.0.1'
    assert os.environ.get('PGDATABASE') == 'cw_e2e'
    info = json.loads(subprocess.check_output(['docker', 'inspect', 'cw-mvp-db']))[0]
    assert info['Config']['Image'] == 'postgres:17'
    assert info['HostConfig']['PortBindings']['5432/tcp'] == [{'HostIp': '127.0.0.1', 'HostPort': '5432'}]
    kind = info['Config'].get('Labels', {}).get('centerway.disposable')
    if kind == 'mvp':
        assert info['HostConfig'].get('Tmpfs', {}).get('/var/lib/postgresql/data') is not None
        assert not any(m['Type'] in ('bind', 'volume') for m in info.get('Mounts', []))
    else:
        assert kind == 'codespaces' and os.environ.get('CW_CODESPACES_DEMO') == '1'
        mounts = info.get('Mounts', [])
        assert len(mounts) == 1 and mounts[0]['Type'] == 'volume'
        assert mounts[0]['Name'] == DEMO_VOLUME and mounts[0]['Destination'] == '/var/lib/postgresql/data'
        volume = json.loads(subprocess.check_output(['docker', 'volume', 'inspect', DEMO_VOLUME]))[0]
        assert volume.get('Labels', {}).get('centerway.disposable') == 'codespaces'
    return info
