import io,json,sys,tarfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import android_ops as ops
from android_stream import frame
class OpsTests(unittest.TestCase):
 def test_synthetic_channel_roundtrip_and_rejection(self):
  nonce='a'*64
  data=frame(b'{"probe":"synthetic-only"}',b'PGDMP'+bytes(range(256))*64,nonce)
  self.assertEqual(ops.probe_receive(io.BytesIO(data),nonce),{'status':'synthetic_ssh_verified','nonce':nonce,'database_access':False})
  with self.assertRaises(Exception):ops.probe_receive(io.BytesIO(data),'b'*64)
 def test_remote_uses_existing_gh_session_without_shell_or_secret(self):
  with patch.object(ops,'run',return_value=b'ok') as run:
   self.assertEqual(ops.remote('synthetic-space','true',b'synthetic'),b'ok')
  args=run.call_args.args[0]
  self.assertEqual(args,['gh','codespace','ssh','-c','synthetic-space','--','-T','true'])
  self.assertNotIn('-tt',args)
  with self.assertRaises(Exception):ops.remote('bad;command','true')
 def test_wrong_sha_stops_before_codespaces(self):
  with patch.object(ops,'run') as run:
   with self.assertRaises(Exception):ops.prepare('bad-sha')
   run.assert_not_called()
 def test_missing_access_stops_without_resource_creation(self):
  with patch.object(ops,'checked_package',return_value=b'public-code'),patch.object(ops,'run',side_effect=ValueError('denied')),patch.object(ops,'remote') as remote:
   with self.assertRaises(Exception):ops.prepare('a'*40)
   remote.assert_not_called()
 def test_ambiguous_or_stopped_codespace_not_started(self):
  for spaces in [[{'name':'a','state':'Shutdown'}],[{'name':'a','state':'Available'},{'name':'b','state':'Available'}]]:
   with patch.object(ops,'checked_package',return_value=b'public-code'),patch.object(ops,'run',return_value=json.dumps(spaces).encode()),patch.object(ops,'remote') as remote:
    with self.assertRaises(Exception):ops.prepare('a'*40)
    remote.assert_not_called()
 def test_failed_preparation_cleans_its_unique_directory(self):
  seen=[]
  def remote(name,command,data=None,timeout=240):
   seen.append(command)
   if 'prepare_codespace.sh' in command:raise ValueError('failed')
   return b''
  with patch.object(ops,'checked_package',return_value=b'public-code'),patch.object(ops,'run',return_value=b'[{"name":"synthetic","state":"Available"}]'),patch.object(ops,'remote',side_effect=remote):
   with self.assertRaises(Exception):ops.prepare('a'*40)
  self.assertTrue(seen[-1].startswith('rm -rf -- "$HOME/.local/state/centerway-gate1/'))

class BaselineGuards(unittest.TestCase):
 def test_primary_binding_rejected_before_connect(self):
  import tempfile
  import capture_baseline
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);config=root/'config';binding=root/'binding'
   config.write_text('{}');config.chmod(0o600)
   binding.write_text(json.dumps({'branch_id':'same','parent_id':'same','primary':True,'default':True}));binding.chmod(0o600)
   with patch.object(capture_baseline.psycopg,'connect') as connect:
    with self.assertRaises(Exception):capture_baseline.capture(config,binding,root/'out','synthetic')
    connect.assert_not_called()
