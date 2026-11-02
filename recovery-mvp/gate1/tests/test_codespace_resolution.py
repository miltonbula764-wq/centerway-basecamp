import io,json,sys,unittest
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import android_ops as ops

SPACES=[{'name':'solid-train-synthetic123','displayName':'solid train','state':'Available'},
 {'name':'ideal-garbanzo-synthetic456','displayName':'ideal garbanzo','state':'Shutdown'}]
DETAIL={'name':SPACES[0]['name'],'state':'Available','repository':{'full_name':ops.REPO},'connection':{'token':'SYNTHETIC-MUST-NOT-LOG'}}
class ResolutionTests(unittest.TestCase):
 def test_unique_available_with_stopped_other_is_selected(self):
  self.assertEqual(ops.resolve_codespace(SPACES)['name'],SPACES[0]['name'])
 def test_short_label_resolves_to_exact_canonical_name(self):
  for label in ['solid train','solid-train',SPACES[0]['name']]:
   self.assertEqual(ops.resolve_codespace(SPACES,label)['name'],SPACES[0]['name'])
 def test_ambiguous_prefix_stopped_or_unknown_rejected(self):
  cases=[(SPACES,'ideal-garbanzo'),(SPACES,'missing'),(SPACES+[{'name':'solid-train-other','state':'Available'}],'solid-train')]
  for spaces,label in cases:
   with self.assertRaises(ops.AccessError):ops.resolve_codespace(spaces,label)
 def test_basic_get_uses_canonical_not_display_name(self):
  with patch.object(ops,'run',side_effect=[json.dumps(SPACES).encode(),json.dumps(DETAIL).encode()]) as run:
   result=ops.inspect_codespace('solid-train')
  self.assertEqual(run.call_args.args[0],['gh','api','--hostname','github.com','--method','GET','user/codespaces/solid-train-synthetic123'])
  self.assertTrue(result['selector_resolved']);self.assertNotIn('connection',result)
 def test_wrong_repository_or_changed_name_rejected(self):
  for bad in [{**DETAIL,'name':'other'},{**DETAIL,'repository':{'full_name':'other/repo'}}]:
   with patch.object(ops,'run',side_effect=[json.dumps(SPACES).encode(),json.dumps(bad).encode()]):
    with self.assertRaises(ops.AccessError):ops.inspect_codespace('solid-train')
 def test_get_404_stops_before_any_ssh_or_staging(self):
  with patch.object(ops,'checked_package',return_value=b'public'),patch.object(ops,'inspect_codespace',side_effect=ops.AccessError('codespace_read_404')),patch.object(ops,'remote') as remote:
   with self.assertRaises(ops.AccessError):ops.prepare('a'*40,'solid-train')
   remote.assert_not_called()
 def test_diagnostic_sanitizes_version_and_connection_payload(self):
  with patch.object(ops,'run',side_effect=[b'gh version 2.46.0 (synthetic)\n',json.dumps(SPACES).encode(),json.dumps(DETAIL).encode()]):
   report=ops.diagnose('solid-train')
  self.assertEqual(report['gh_version'],'2.46.0');self.assertFalse(report['ssh_verified'])
  self.assertNotIn('SYNTHETIC-MUST-NOT-LOG',json.dumps(report))
 def test_read_and_ssh_http_statuses_are_distinct_without_raw_error(self):
  for command,code in [(['gh','api','user/codespaces/name'],'codespace_read_404'),(['gh','codespace','ssh','-c','name'],'codespace_ssh_404')]:
   with patch.object(ops.sp,'run',return_value=Mock(returncode=1,stderr=b'gh: secret data not found (HTTP 404)',stdout=b'')):
    with self.assertRaises(ops.AccessError) as error:ops.run(command)
    self.assertEqual(error.exception.code,code);self.assertNotIn('secret',str(error.exception))
 def test_first_connection_404_not_masked_as_cleanup_failure(self):
  with patch.object(ops,'checked_package',return_value=b'public'),patch.object(ops,'inspect_codespace',return_value={'name':SPACES[0]['name']}),patch.object(ops,'remote',side_effect=ops.AccessError('codespace_ssh_404')) as remote:
   with self.assertRaises(ops.AccessError) as error:ops.prepare('a'*40,'solid-train')
   self.assertEqual(error.exception.code,'codespace_ssh_404');self.assertEqual(remote.call_count,1)
 def test_conflicting_host_override_fails_without_call(self):
  with patch.dict(ops.os.environ,{'GH_HOST':'different.invalid'}),patch.object(ops,'run') as run:
   with self.assertRaises(ops.AccessError):ops.inspect_codespace('solid-train')
   run.assert_not_called()
 def test_diagnostic_identifies_individual_get_404(self):
  with patch.object(ops,'run',side_effect=[b'gh version 2.46.0\n',json.dumps(SPACES).encode(),ops.AccessError('codespace_read_404')]):
   report=ops.diagnose('solid-train')
  self.assertEqual(report['phase'],'canonical_get')
  self.assertEqual(report['name'],SPACES[0]['name'])
  self.assertEqual(report['status'],'codespace_read_404')
 def test_ssh_404_after_staging_still_attempts_cleanup(self):
  calls=[]
  def remote(name,command,data=None,timeout=240):
   calls.append(command)
   if 'prepare_codespace.sh' in command:raise ops.AccessError('codespace_ssh_404')
   return b''
  with patch.object(ops,'checked_package',return_value=b'public'),patch.object(ops,'inspect_codespace',return_value={'name':SPACES[0]['name']}),patch.object(ops,'remote',side_effect=remote):
   with self.assertRaises(ops.AccessError):ops.prepare('a'*40,'solid-train')
  self.assertTrue(calls[-1].startswith('rm -rf --'))
