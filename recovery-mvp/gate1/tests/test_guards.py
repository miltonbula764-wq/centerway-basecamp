import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import recovery as g2
ROOT=Path(__file__).resolve().parents[3]
class Guards(unittest.TestCase):
 def test_manual_workflow_cannot_be_enabled_by_input(self):
  w=yaml.load((ROOT/'.github/workflows/recovery-mvp-gate1-backup.yml').read_text(),Loader=yaml.BaseLoader)
  self.assertEqual(set(w['on']),{'workflow_dispatch'})
  self.assertEqual(w['jobs']['export']['if'],'${{ false }}')
  self.assertIn('exit 1',w['jobs']['security-block']['steps'][0]['run'])
  self.assertEqual(w['jobs']['export']['environment'],'centerway-g2-sensitive-export')
  ci=(ROOT/'.github/workflows/recovery-mvp-gate1-backup-ci.yml').read_text()
  self.assertNotIn('secrets.',ci)
  self.assertNotIn('upload-artifact',ci)
 def test_command_limit_and_timeout(self):
  with self.assertRaises(Exception):g2.command([sys.executable,'-c','print("X"*10000)'],limit=100)
  with patch.object(g2,'TIMEOUT',.1):
   with self.assertRaises(Exception):g2.command([sys.executable,'-c','import time;time.sleep(10)'])
 def test_no_plaintext_spooling_or_credential_arguments(self):
  with g2.connection_environment('host=example.invalid dbname=test user=test password=synthetic-secret sslmode=verify-full') as env:
   self.assertNotIn('synthetic-secret',str(env))
   self.assertEqual(Path(env['PGSERVICEFILE']).stat().st_mode & 0o777,0o600)
   p=Path(env['PGSERVICEFILE'])
  self.assertFalse(p.exists())
 def test_cli_never_discloses_bad_configuration(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'config';p.write_text('{"dsn":"SECRET-DO-NOT-LOG"}');p.chmod(0o600)
   r=subprocess.run([sys.executable,str(ROOT/'recovery-mvp/gate1/recovery.py'),'export','--config',str(p),'--archive',d+'/bundle','--recipient','invalid'],capture_output=True)
   self.assertEqual(r.returncode,1)
   self.assertEqual(r.stderr,b'recovery_failed\n');self.assertEqual(r.stdout,b'')
