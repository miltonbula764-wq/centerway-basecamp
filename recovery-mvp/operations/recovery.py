"""Cold, encrypted recovery for the existing C03 SYNTHETIC single-host profile.

Never stops a service, seeds data, migrates a database or overwrites a destination.
Docker access is administrative. No production or cross-architecture restore claim.
"""
import argparse
from contextlib import contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import socket
import sqlite3
import ssl
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cloud-demo'))
from runtime import PersistentDemo, POSTGRES_IMAGE, migration_hashes, private_json, free_port
from app import Database
from psycopg.conninfo import conninfo_to_dict, make_conninfo

FORMAT = 'centerway-c03-cold-v1'
LIMIT = 2 * 1024**3
REQUIRED = {'config.json', 'credentials.json', 'postgres.env', 'manifest.json', 'sessions.sqlite'}
OPTIONAL = {'scenario-started.json', 'scenario-result.json'}
PKI = {'ca.crt', 'ca.key', 'ca.srl', 'leaf.ext'} | {
    f'{name}.{ext}' for name in ('edge', 'api', 'db') for ext in ('crt', 'key', 'csr')}


class RecoveryError(Exception):
    """Only fixed, non-secret codes cross the CLI boundary."""


def fail(code):
    raise RecoveryError(code)


def private(path, directory=False):
    path = Path(path)
    s = path.lstat()
    kind = stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode)
    if not kind or s.st_uid != os.geteuid() or s.st_mode & 0o077:
        fail('private_owned_path_required')
    return path


def new_path(path):
    path = Path(path).absolute()
    private(path.parent, directory=True)
    if path.exists() or path.is_symlink():
        fail('destination_exists')
    if ROOT.parent == path or ROOT.parent in path.parents or any(c.isspace() for c in str(path)):
        fail('destination_outside_checkout_required')
    return path


def run(args, *, output=None, input=None, timeout=120):
    # Never return stderr or exception strings: they may include keys or DSNs.
    try:
        result = subprocess.run(args, input=input, stdout=output or subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        fail('dependency_command_failed')
    if result.returncode:
        fail('dependency_command_failed')
    return result.stdout


def write_bytes(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


@contextmanager
def stage(parent):
    with tempfile.TemporaryDirectory(prefix='.cw-recovery-', dir=parent) as name:
        os.chmod(name, 0o700)
        yield Path(name)


def inspect_demo(demo, *, cold=False):
    m = demo.read_manifest()
    item = json.loads(run(['docker', 'inspect', m['container']]))[0]
    if item['Config']['Image'] != POSTGRES_IMAGE or item['Config']['Labels'].get('centerway.synthetic') != 'true':
        fail('database_identity_mismatch')
    mounts = {x['Destination']: x.get('Name') for x in item['Mounts']}
    if mounts != {'/var/lib/postgresql/data': m['volume'], '/run/centerway-tls': m['volume'] + '-tls'}:
        fail('volume_binding_mismatch')
    expected = {'5432/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(m['db_port'])}]}
    if item['HostConfig']['PortBindings'] != expected:
        fail('database_not_private')
    if cold:
        if item['State']['Running'] or item['State'].get('ExitCode') != 0:
            fail('clean_database_shutdown_required')
        for key in ('port', 'api_port', 'http_port'):
            with socket.socket() as sock:
                sock.settimeout(.2)
                if sock.connect_ex(('127.0.0.1', m[key])) == 0:
                    fail('stop_servers_before_backup')
    return m


def validate_tar(path, *, outer=False):
    """No extraction before complete age authentication, size and path checks."""
    names = set()
    total = 0
    with tarfile.open(path, 'r:') as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or '\\' in member.name or not (member.isfile() or member.isdir()):
                fail('unsafe_archive_member')
            key = str(name)
            if key in names:
                fail('duplicate_archive_member')
            names.add(key)
            total += member.size
            if total > LIMIT or len(names) > 20000:
                fail('archive_limit_exceeded')
            if outer and not (key in {'metadata.json', 'postgres.tar', 'tls.tar', 'state'} or
                    key.startswith('state/') and key.removeprefix('state/') in
                    REQUIRED | OPTIONAL | {'pki'} | {'pki/' + n for n in PKI}):
                fail('unexpected_archive_member')
    return names


def snapshot_volume(volume, target, temporary):
    with open(target, 'xb') as output:
        os.chmod(target, 0o600)
        run(['docker', 'run', '--rm', '--network', 'none', '--mount',
             f'type=volume,src={volume},dst=/data,readonly', '--entrypoint', 'tar',
             POSTGRES_IMAGE, '-C', '/data', '-cf', '-', '.'], output=output)
    validate_tar(target)


def backup(state, output, recipient, caddy):
    output = new_path(output)
    if not re.fullmatch(r'age1[0-9a-z]{58}', recipient):
        fail('native_age_public_recipient_required')
    demo = PersistentDemo(state, caddy)
    private(demo.state, directory=True)
    m = inspect_demo(demo, cold=True)
    with stage(output.parent) as work:
        copy = work / 'state'
        copy.mkdir(mode=0o700)
        files = REQUIRED - {'sessions.sqlite'} | {n for n in OPTIONAL if (demo.state / n).exists()}
        for name in files:
            source = private(demo.state / name)
            write_bytes(copy / name, source.read_bytes())
        if demo.config['session_db'] != str(demo.state / 'sessions.sqlite'):
            fail('session_binding_mismatch')
        private(demo.state / 'sessions.sqlite')
        with sqlite3.connect((demo.state / 'sessions.sqlite').as_uri() + '?mode=ro', uri=True) as src:
            with sqlite3.connect(copy / 'sessions.sqlite') as dst:
                src.backup(dst)
                if dst.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    fail('session_integrity_failed')
        os.chmod(copy / 'sessions.sqlite', 0o600)
        private(demo.state / 'pki', directory=True)
        (copy / 'pki').mkdir(mode=0o700)
        for source in (demo.state / 'pki').iterdir():
            if source.name not in PKI:
                fail('unexpected_pki_file')
            private(source)
            write_bytes(copy / 'pki' / source.name, source.read_bytes())
        snapshot_volume(m['volume'], work / 'postgres.tar', work)
        snapshot_volume(m['volume'] + '-tls', work / 'tls.tar', work)
        # Recheck cold state after copying; concurrent administration is unsupported.
        inspect_demo(demo, cold=True)
        files = sorted(p for p in work.rglob('*') if p.is_file())
        metadata = dict(format=FORMAT, synthetic_only=True, source_state=str(demo.state),
            created_at=time.time(), architecture=run(['docker', 'image', 'inspect', POSTGRES_IMAGE,
                '--format', '{{.Architecture}}']).decode().strip(),
            migrations=migration_hashes(), postgres_image=POSTGRES_IMAGE,
            files={str(p.relative_to(work)): dict(sha256=sha(p), size=p.stat().st_size) for p in files})
        private_json(work / 'metadata.json', metadata)
        with tarfile.open(work / 'payload.tar', 'w') as archive:
            for name in ('metadata.json', 'state', 'postgres.tar', 'tls.tar'):
                archive.add(work / name, arcname=name)
        validate_tar(work / 'payload.tar', outer=True)
        # Only ciphertext is published, using an atomic hard link that cannot overwrite.
        with open(work / 'encrypted.age', 'xb') as encrypted:
            os.chmod(work / 'encrypted.age', 0o600)
            run(['age', '--encrypt', '-r', recipient, str(work / 'payload.tar')], output=encrypted)
            encrypted.flush()
            os.fsync(encrypted.fileno())
        os.link(work / 'encrypted.age', output)
    return dict(status='backup_created', synthetic_only=True, encrypted=True)


def unpack(archive, work):
    validate_tar(archive, outer=True)
    with tarfile.open(archive, 'r:') as source:
        source.extractall(work, filter='data')
    # Numeric ownership/mode from tar is never trusted for private host state.
    for path in work.rglob('*'):
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
    meta = json.loads((work / 'metadata.json').read_text())
    if meta.get('format') != FORMAT or meta.get('synthetic_only') is not True or meta.get('postgres_image') != POSTGRES_IMAGE:
        fail('unsupported_backup')
    if meta.get('migrations') != migration_hashes():
        fail('migration_drift')
    actual = {str(p.relative_to(work)) for p in work.rglob('*') if p.is_file()} - {'metadata.json', 'decrypted.tar'}
    if actual != set(meta['files']):
        fail('backup_inventory_mismatch')
    for name, info in meta['files'].items():
        p = work / name
        if p.stat().st_size != info['size'] or sha(p) != info['sha256']:
            fail('backup_hash_mismatch')
    for name in ('postgres.tar', 'tls.tar'):
        validate_tar(work / name)
    if not REQUIRED <= {p.name for p in (work / 'state').iterdir() if p.is_file()}:
        fail('incomplete_state')
    for name in ('ca', 'edge', 'api', 'db'):
        run(['openssl', 'x509', '-in', str(work / 'state/pki' / (name + '.crt')),
             '-noout', '-checkend', '300'])
    return meta


def restore(archive, identity, destination, caddy):
    destination = new_path(destination)
    private(archive)
    private(identity)
    if Path(archive).stat().st_size > LIMIT:
        fail('archive_limit_exceeded')
    with stage(destination.parent) as work:
        with open(work / 'decrypted.tar', 'xb') as plain:
            os.chmod(work / 'decrypted.tar', 0o600)
            run(['age', '--decrypt', '-i', str(identity), str(archive)], output=plain)
        meta = unpack(work / 'decrypted.tar', work)
        architecture = run(['docker', 'image', 'inspect', POSTGRES_IMAGE,
            '--format', '{{.Architecture}}']).decode().strip()
        if architecture != meta['architecture']:
            fail('cross_architecture_restore_not_supported')
        # All checks above precede creating any state, volume or database container.
        destination.mkdir(mode=0o700)
        for source in (work / 'state').rglob('*'):
            target = destination / source.relative_to(work / 'state')
            if source.is_dir():
                target.mkdir(mode=0o700)
            else:
                write_bytes(target, source.read_bytes())
        m = json.loads((destination / 'manifest.json').read_text())
        ident = 'centerway-c03-restore-' + secrets.token_hex(6)
        ports = set()
        def port():
            while (value := free_port()) in ports:
                pass
            ports.add(value)
            return value
        m.update(status='initializing', container=ident, volume=ident,
            db_port=port(), api_port=port(), port=port(), http_port=port())
        (destination / 'manifest.json').write_text(json.dumps(m))
        config = json.loads((destination / 'config.json').read_text())
        config['session_db'] = str(destination / 'sessions.sqlite')
        for user in config['users'].values():
            dsn = conninfo_to_dict(user['dsn'])
            if dsn.get('host') != '127.0.0.1' or dsn.get('sslmode') != 'verify-full':
                fail('unsupported_database_binding')
            dsn.update(port=str(m['db_port']), sslrootcert=str(destination / 'pki/ca.crt'))
            user['dsn'] = make_conninfo(**dsn)
        (destination / 'config.json').write_text(json.dumps(config))
        for suffix, archive_name in (('', 'postgres.tar'), ('-tls', 'tls.tar')):
            volume = ident + suffix
            run(['docker', 'volume', 'create', '--label', 'centerway.synthetic=true', volume])
            run(['docker', 'run', '--rm', '--network', 'none', '--mount',
                f'type=volume,src={volume},dst=/restore', '--mount',
                f'type=bind,src={work},dst=/snapshot,readonly', '--entrypoint', 'tar',
                POSTGRES_IMAGE, '-xpf', '/snapshot/' + archive_name, '-C', '/restore'])
        demo = PersistentDemo(destination, caddy)
        demo.container = ident
        demo.create_database(m)
        demo.ready_database()
        m['status'] = 'ready'
        (destination / 'manifest.json').write_text(json.dumps(m))
        demo.read_manifest()
    # Restored PG is private; API and gateway have not been started.
    # Rebound DSNs change session versions, requiring a fresh login after restore.
    return dict(status='restored_private_database', synthetic_only=True, login_required=True)


def probe(state, caddy, *, minimum_free=256 * 1024**2, certificate_seconds=86400):
    checks = dict(configuration=False, private_database=False, database_identity=False,
        sessions=False, verified_https=False, certificates=False, disk=False)
    try:
        demo = PersistentDemo(state, caddy)
        m = inspect_demo(demo)
        checks['configuration'] = True
        checks['private_database'] = json.loads(run(['docker', 'inspect', m['container']]))[0]['State']['Running']
        try:
            checks['database_identity'] = bool(demo.config['users']) and all(
                Database(False).call(user, 'identity') == user['principal'] for user in demo.config['users'].values())
        except Exception:
            pass
        path = private(demo.config['session_db'])
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            checks['sessions'] = db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        try:
            for name in ('ca', 'edge', 'api', 'db'):
                run(['openssl', 'x509', '-in', str(demo.state / 'pki' / (name + '.crt')),
                    '-noout', '-checkend', str(certificate_seconds)])
            checks['certificates'] = True
        except RecoveryError:
            pass
        try:
            ctx = ssl.create_default_context(cafile=str(demo.state / 'pki/ca.crt'))
            conn = http.client.HTTPSConnection('localhost', m['port'], context=ctx, timeout=5)
            try:
                conn.request('GET', '/health')
                response = conn.getresponse()
                body = response.read(4096)
                checks['verified_https'] = response.status == 200 and json.loads(body).get('status') == 'alive'
            finally:
                conn.close()
        except Exception:
            pass
        checks['disk'] = shutil.disk_usage(demo.state).free >= minimum_free
    except Exception:
        pass
    return dict(format='centerway-c03-probe-v1', synthetic_only=True, ready=all(checks.values()), checks=checks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--caddy', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    b = commands.add_parser('backup')
    b.add_argument('--state', required=True)
    b.add_argument('--output', required=True)
    b.add_argument('--recipient', required=True)
    r = commands.add_parser('restore')
    r.add_argument('--archive', required=True)
    r.add_argument('--identity', required=True)
    r.add_argument('--destination', required=True)
    p = commands.add_parser('probe')
    p.add_argument('--state', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'backup':
            result = backup(args.state, args.output, args.recipient, args.caddy)
        elif args.command == 'restore':
            result = restore(args.archive, args.identity, args.destination, args.caddy)
        else:
            result = probe(args.state, args.caddy)
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get('ready', True) else 1
    except Exception as error:
        code = str(error) if isinstance(error, RecoveryError) else 'operation_failed'
        print(json.dumps(dict(status='error', code=code)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
