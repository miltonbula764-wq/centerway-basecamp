import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import handoff

class HandoffTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
 def make(self,name):
  p=self.root/name;p.mkdir(mode=0o700)
  checks={}
  for name in ['database.age','manifest.age']:
   raw=b'age-encryption.org/v1\nsynthetic-test-only'
   (p/name).write_bytes(raw);(p/name).chmod(0o600);checks[name]=hashlib.sha256(raw).hexdigest()
  (p/'checksums.json').write_text(json.dumps(checks));(p/'checksums.json').chmod(0o600)
  return p
 def test_recipient_mismatch_and_private_material_rejected(self):
  p=self.root/'public';p.write_text('age1'+'a'*58+'\n')
  fp=handoff.recipient_fingerprint(p)
  self.assertEqual(handoff.check_recipient(p,fp)['status'],'public_recipient_matches')
  with self.assertRaises(ValueError):handoff.check_recipient(p,'0'*64)
  p.write_text('AGE-SECRET-KEY-SYNTHETIC')
  with self.assertRaises(ValueError):handoff.recipient_fingerprint(p)
 def test_return_is_matching_ciphertext_not_restore_proof(self):
  a=self.make('a');b=self.root/'b';shutil.copytree(a,b)
  r=handoff.verify_return(a,b)
  self.assertFalse(r['restore_verified']);self.assertFalse(r['provider_acl_verified'])
  with self.assertRaises(ValueError):handoff.verify_return(a,a)
 def test_corruption_extra_files_public_files_and_symlinks_rejected(self):
  for variant in ['corrupt','extra','public','link','plain']:
   with self.subTest(variant=variant):
    a=self.make(variant)
    if variant=='corrupt':(a/'database.age').write_bytes(b'changed')
    if variant=='extra':(a/'secret').touch()
    if variant=='public':(a/'database.age').chmod(0o644)
    if variant=='link':(a/'database.age').unlink();(a/'database.age').symlink_to(a/'manifest.age')
    if variant=='plain':
     (a/'database.age').write_bytes(b'PGDMP');c=json.loads((a/'checksums.json').read_text());c['database.age']=hashlib.sha256(b'PGDMP').hexdigest();(a/'checksums.json').write_text(json.dumps(c))
    with self.assertRaises(ValueError):handoff.bundle(a)
