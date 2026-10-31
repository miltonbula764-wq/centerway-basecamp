"""Actual encrypted cold backup, new Docker volumes and authenticated TLS restore."""
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recovery import (backup, restore, probe, RecoveryError, PersistentDemo, stage,
    run, private_json, validate_tar, sha)
from scenario import Scenario
from demo.provision import T, B, C


def remove_demo(demo):
    demo.close()
    manifest = demo.state / 'manifest.json'
    if manifest.exists():
        m = json.loads(manifest.read_text())
        subprocess.run(['docker', 'rm', '-f', m['container']], capture_output=True)
        for name in (m['volume'], m['volume'] + '-tls'):
            subprocess.run(['docker', 'volume', 'rm', name], capture_output=True)


class OperationalRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='centerway-operations-')
        cls.root = Path(cls.temp.name)
        cls.caddy = os.environ['CENTERWAY_TEST_CADDY']
        cls.source = PersistentDemo(cls.root / 'source', cls.caddy)
        cls.restored = None
        cls.identity = cls.root / 'identity.agekey'
        cls.other_identity = cls.root / 'other.agekey'
        cls.archive = cls.root / 'snapshot.age'
        try:
            for identity in (cls.identity, cls.other_identity):
                run(['age-keygen', '-o', str(identity)])
                os.chmod(identity, 0o600)
            cls.recipient = run(['age-keygen', '-y', str(cls.identity)]).decode().strip()
            cls.source.initialize()
            cls.source.__enter__()
            cls.client = Scenario(cls.source)
            cls.result = cls.client.run()
            cls.client.login('reader')
            cls.revoked = cls.client.tokens['reader']
            cls.client.request('DELETE', '/v1/session', user='reader')
            cls.old_token = cls.client.tokens['alice']
            cls.before = cls.client.request('GET', f'/v1/tenants/{T}/clients/{C}/journey')[1]['data']
            cls.source.close()
            cls.source.run('docker', 'stop', cls.source.container)
            cls.source_manifest = sha(cls.source.state / 'manifest.json')
            backup(cls.source.state, cls.archive, cls.recipient, cls.caddy)
            restore(cls.archive, cls.identity, cls.root / 'restored', cls.caddy)
            cls.restored = PersistentDemo(cls.root / 'restored', cls.caddy)
            cls.restored.__enter__()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if cls.restored:
            remove_demo(cls.restored)
        remove_demo(cls.source)
        cls.temp.cleanup()

    def test_01_cold_restore_keeps_journey_roles_rls_and_single_execution(self):
        c = Scenario(self.restored)
        # Binding a recovered database to new ports/paths invalidates old sessions.
        c.tokens['alice'] = self.old_token
        self.assertEqual(c.request('GET', '/v1/session')[0], 401)
        c.tokens['reader'] = self.revoked
        self.assertEqual(c.request('GET', '/v1/session', user='reader')[0], 401)
        c.login('alice')
        c.login('bob')
        route = f'/v1/tenants/{T}/clients/{C}/journey'
        self.assertEqual(c.request('GET', route)[1]['data'], self.before)
        self.assertEqual(c.request('GET', route, user='bob')[0], 403)
        req = self.result['intervention_request']
        status, body = c.request('POST', f'/v1/tenants/{T}/clients/{C}/operations', req)
        self.assertEqual(status, 200)
        self.assertEqual(body['data']['result']['id'], self.result['decision_id'])
        import psycopg
        with psycopg.connect(self.restored.config['users']['alice']['dsn']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM centerway.intervention_executions').fetchone()[0], 1)
            count = db.execute("SELECT count(*) FROM centerway.audit_log WHERE entity='operation_receipts' AND snapshot->>'request_id'=%s", (req['request_id'],)).fetchone()[0]
            self.assertEqual(count, 1)
        with psycopg.connect(self.restored.config['users']['bob']['dsn']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM centerway.recovery_runs WHERE tenant_id=%s', (T,)).fetchone()[0], 0)
        self.assertEqual(sha(self.source.state / 'manifest.json'), self.source_manifest)
        state = json.loads(run(['docker', 'inspect', self.source.container]))[0]['State']
        self.assertFalse(state['Running'])
        with self.assertRaises(ValueError):
            Scenario(self.restored).run()

    def test_02_ciphertext_wrong_key_corruption_and_no_overwrite(self):
        raw = self.archive.read_bytes()
        self.assertTrue(raw.startswith(b'age-encryption.org/v1'))
        for secret in self.source.credentials.values():
            self.assertFalse(secret.encode() in raw, 'Ciphertext exposed a credential')
        self.assertEqual(self.archive.stat().st_mode & 0o777, 0o600)
        for identity, data in ((self.other_identity, raw), (self.identity, raw[:-100])):
            with stage(self.root) as work:
                bad = work / 'bad.age'
                bad.write_bytes(data)
                bad.chmod(0o600)
                target = work / 'never-created'
                with self.assertRaises(RecoveryError):
                    restore(bad, identity, target, self.caddy)
                self.assertFalse(target.exists())
        with self.assertRaisesRegex(RecoveryError, 'destination_exists'):
            restore(self.archive, self.identity, self.restored.state, self.caddy)
        with self.assertRaisesRegex(RecoveryError, 'destination_exists'):
            backup(self.source.state, self.archive, self.recipient, self.caddy)

    def test_03_hot_backup_and_public_files_are_refused(self):
        with stage(self.root) as work:
            with self.assertRaises(RecoveryError):
                backup(self.restored.state, work / 'hot.age', self.recipient, self.caddy)
            self.assertFalse((work / 'hot.age').exists())
            bad_identity = work / 'identity'
            shutil.copyfile(self.identity, bad_identity)
            bad_identity.chmod(0o644)
            with self.assertRaisesRegex(RecoveryError, 'private_owned_path_required'):
                restore(self.archive, bad_identity, work / 'target', self.caddy)
            self.assertFalse((work / 'target').exists())

    def test_04_archive_traversal_symlink_and_migration_drift_fail_closed(self):
        for name, link in (('../escape', False), ('state/link', True), ('/absolute', False)):
            with stage(self.root) as work:
                path = work / 'unsafe.tar'
                with tarfile.open(path, 'w') as t:
                    item = tarfile.TarInfo(name)
                    if link:
                        item.type = tarfile.SYMTYPE
                        item.linkname = '/tmp/escape'
                        t.addfile(item)
                    else:
                        item.size = 1
                        t.addfile(item, io.BytesIO(b'x'))
                with self.assertRaises(RecoveryError):
                    validate_tar(path, outer=True)
        with stage(self.root) as work:
            plain = run(['age', '-d', '-i', str(self.identity), str(self.archive)])
            with tarfile.open(fileobj=io.BytesIO(plain)) as t:
                t.extractall(work, filter='data')
            meta_path = work / 'metadata.json'
            meta = json.loads(meta_path.read_text())
            meta['migrations']['sql/001_foundation.sql'] = 'drift'
            meta_path.write_text(json.dumps(meta))
            with tarfile.open(work / 'drift.tar', 'w') as t:
                for n in ('metadata.json', 'state', 'postgres.tar', 'tls.tar'):
                    t.add(work / n, arcname=n)
            with open(work / 'drift.age', 'wb') as out:
                run(['age', '-r', self.recipient, str(work / 'drift.tar')], output=out)
            (work / 'drift.age').chmod(0o600)
            with self.assertRaisesRegex(RecoveryError, 'migration_drift'):
                restore(work / 'drift.age', self.identity, work / 'target', self.caddy)
            self.assertFalse((work / 'target').exists())

    def test_05_readiness_checks_real_dependencies_without_writes_or_secrets(self):
        import psycopg
        with psycopg.connect(self.restored.config['users']['alice']['dsn']) as db:
            before = db.execute('SELECT count(*) FROM centerway.audit_log').fetchone()[0]
        document = probe(self.restored.state, self.caddy)
        self.assertTrue(document['ready'], document)
        self.assertTrue(all(document['checks'].values()))
        with psycopg.connect(self.restored.config['users']['alice']['dsn']) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM centerway.audit_log').fetchone()[0], before)
        text = json.dumps(document)
        for secret in list(self.restored.credentials.values()) + list(self.client.tokens.values()):
            self.assertFalse(secret in text, 'Probe exposed a secret')
        self.assertNotIn('dsn', text)
        self.assertNotIn('password', text)
        strict = probe(self.restored.state, self.caddy, certificate_seconds=100 * 86400, minimum_free=2**100)
        self.assertFalse(strict['ready'])
        self.assertFalse(strict['checks']['certificates'])
        self.assertFalse(strict['checks']['disk'])

    def test_06_liveness_does_not_hide_database_or_gateway_failure(self):
        self.restored.run('docker', 'stop', self.restored.container)
        try:
            result = probe(self.restored.state, self.caddy)
            self.assertTrue(result['checks']['verified_https'])
            self.assertFalse(result['checks']['database_identity'])
            self.assertFalse(result['ready'])
        finally:
            self.restored.run('docker', 'start', self.restored.container)
            self.restored.ready_database()
        self.restored.stop(self.restored.proxy)
        try:
            result = probe(self.restored.state, self.caddy)
            self.assertTrue(result['checks']['database_identity'])
            self.assertFalse(result['checks']['verified_https'])
            self.assertFalse(result['ready'])
        finally:
            self.restored.start_proxy()
        self.assertTrue(probe(self.restored.state, self.caddy)['ready'])


if __name__ == '__main__':
    unittest.main()
