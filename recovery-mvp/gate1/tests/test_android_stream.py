import io,json,struct,sys,unittest
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import android_stream as a
class StreamTests(unittest.TestCase):
 def test_frame_integrity_and_identity_binding(self):
  raw=a.frame(b'{"format":"synthetic"}',b'PGDMPsynthetic','a'*64)
  m,d=a.read_frame(io.BytesIO(raw),'a'*64)
  self.assertEqual(m['format'],'synthetic');self.assertTrue(d.startswith(b'PGDMP'))
  for bad in [raw[:-1],raw[:-1]+b'X',raw+b'extra',struct.pack('!I',9999)]:
   with self.assertRaises(Exception):a.read_frame(io.BytesIO(bad),'a'*64)
  with self.assertRaises(Exception):a.read_frame(io.BytesIO(raw),'b'*64)
 def test_failed_authentication_emits_no_plaintext(self):
  output=io.BytesIO()
  with patch.object(a,'bundle',return_value={'synthetic':'hash'}),patch.object(a.subprocess,'run',side_effect=[Mock(returncode=0,stdout=b'{}'),Mock(returncode=1,stdout=b'PGDMPunauthenticated')]):
   with self.assertRaises(Exception):a.send('/synthetic','/synthetic-key',output)
  self.assertEqual(output.getvalue(),b'')
