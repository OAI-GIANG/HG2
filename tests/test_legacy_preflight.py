import json, os, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from tools.legacy_state_preflight import audit

class LegacyPreflightTests(unittest.TestCase):
 def test_outside_library_path_never_opened(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)/'product'; lib=root/'core/runtime/data/library'; lib.mkdir(parents=True)
   (lib/'safe.txt').write_text('safe')
   outside=root/'outside.txt'; outside.write_text('do not read')
   state={'memory':[{'id':'m1','title':'title','content':'body','scope':'HG'}, {'id':'m2','title':'x','content':'y'}],
          'library':[{'id':'safe','name':'safe.txt','path':'core/runtime/data/library/safe.txt','size':4},
                     {'id':'bad','name':'outside.txt','path':'core/runtime/data/../../outside.txt','size':12}],
          'message':[{'text':'private'}], 'conversations':[{}]}
   src=root/'state.json'; src.write_text(json.dumps(state))
   result=audit(src,root)
   self.assertEqual(result['memory']['safe_candidate_count'],1)
   self.assertEqual(result['memory']['quarantine_count'],1)
   self.assertEqual(result['library']['safe_present_count'],1)
   self.assertEqual(result['library']['quarantine_or_missing_count'],1)
   self.assertNotIn('private',json.dumps(result))
 def test_malformed_state_fails_closed(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'state.json'; p.write_text('[]')
   with self.assertRaises(ValueError): audit(p,Path(t))
if __name__=='__main__': unittest.main()
