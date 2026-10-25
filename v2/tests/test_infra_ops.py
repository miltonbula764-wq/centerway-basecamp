import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch

from centerway.core import Core
from centerway.ops import check,backup,verify_backup
from centerway.preview import provision
from centerway.store import Store


class InfraOpsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'state.sqlite3'
        self.origin='https://app.example.invalid'
        provision(self.path,Path(self.temp.name)/'credentials.json',self.origin)

    def tearDown(self):
        self.temp.cleanup()

    def test_readiness_does_not_seed_migrate_or_modify_database(self):
        before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        with patch.object(Store,'__init__',side_effect=AssertionError('No initialization allowed')):
            result=check(self.path,self.origin)
            core=Core(Store.open_existing(self.path))
            self.assertEqual(150,len(core.view('founder')['registry']))
        self.assertEqual('ready',result['status'])
        self.assertEqual(before,hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_missing_incompatible_and_unprotected_databases_fail_without_repair(self):
        missing=Path(self.temp.name)/'missing.sqlite3'
        with self.assertRaises(FileNotFoundError): Store.open_existing(missing)
        self.assertFalse(missing.exists())
        with sqlite3.connect(self.path) as db: db.execute('PRAGMA user_version=1')
        before=self.path.read_bytes()
        with self.assertRaises(ValueError): Store.open_existing(self.path)
        self.assertEqual(before,self.path.read_bytes())
        with sqlite3.connect(self.path) as db:
            db.execute('PRAGMA user_version=2');db.execute('DROP TRIGGER immutable_history_DELETE')
        with self.assertRaises(ValueError): Store.open_existing(self.path)
        with sqlite3.connect(self.path) as db:
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='immutable_history_DELETE'").fetchone())

    def test_wrong_origin_expired_lease_and_loose_permissions_are_not_auto_fixed(self):
        with self.assertRaises(ValueError): check(self.path,'https://other.example.invalid')
        self.path.chmod(0o644)
        with self.assertRaises(ValueError): check(self.path,self.origin)
        self.path.chmod(0o600)
        expired=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        with sqlite3.connect(self.path) as db: db.execute('UPDATE preview_metadata SET expires=?',(expired,))
        with self.assertRaises(ValueError): check(self.path,self.origin)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(expired,db.execute('SELECT expires FROM preview_metadata').fetchone()[0])

    def test_consistent_snapshot_preserves_effects_history_and_source(self):
        core=Core(Store.open_existing(self.path))
        case=core.view('founder','atlas','client-007')['case']['id']
        core.execute('founder','atlas','client-007',case)
        core.verify('founder','atlas','client-007',case)
        before=core.view('founder','atlas','client-007')
        snapshot=Path(self.temp.name)/'backups'/'snapshot.sqlite3'
        report=backup(self.path,snapshot)
        self.assertEqual('verified',report['status'])
        self.assertEqual(0o600,stat.S_IMODE(snapshot.stat().st_mode))
        self.assertEqual(0o700,stat.S_IMODE(snapshot.parent.stat().st_mode))
        self.assertEqual(before,Core(Store.open_existing(snapshot)).view('founder','atlas','client-007'))
        with self.assertRaises(FileExistsError): backup(self.path,snapshot)
        self.assertEqual(report,verify_backup(snapshot))

    def test_backup_can_preserve_an_expired_preview_and_refuses_unsafe_targets(self):
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE preview_metadata SET expires=?',((datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),))
        self.assertEqual('verified',backup(self.path,Path(self.temp.name)/'expired.sqlite3')['status'])
        public=Path(self.temp.name)/'public';public.mkdir(mode=0o755);public.chmod(0o755)
        with self.assertRaises(ValueError): backup(self.path,public/'not-created.sqlite3')
        self.assertFalse((public/'not-created.sqlite3').exists())
        with self.assertRaises(ValueError): backup(self.path,self.path)

    def test_process_crash_does_not_commit_partial_write_and_file_loss_is_not_reseeded(self):
        store=Store.open_existing(self.path)
        before=Core(store).view('founder','atlas','client-001')
        script="import sqlite3,os,sys; db=sqlite3.connect(sys.argv[1]); db.execute('BEGIN IMMEDIATE'); db.execute(\"UPDATE environments SET revision=revision+99 WHERE tenant='atlas'\"); os._exit(17)"
        self.assertEqual(17,subprocess.run([sys.executable,'-c',script,str(self.path)]).returncode)
        self.assertEqual(before,Core(Store.open_existing(self.path)).view('founder','atlas','client-001'))
        self.path.unlink()
        with self.assertRaises(sqlite3.OperationalError): store.connect()
        self.assertFalse(self.path.exists())

    def test_cli_has_no_public_health_endpoint_and_does_not_create_a_missing_file(self):
        missing=Path(self.temp.name)/'absent.sqlite3'
        result=subprocess.run([sys.executable,'-m','centerway.ops','check','--db',str(missing),'--origin',self.origin],capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(1,result.returncode)
        self.assertEqual('operation_refused',json.loads(result.stderr)['code'])
        self.assertFalse(missing.exists())
        self.assertNotIn(str(missing),result.stderr)
