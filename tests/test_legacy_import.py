import json, os, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from hg.history import StateStore
from hg.memory import MemoryStore
from tools.import_legacy_state import import_snapshot

class LegacyImportTests(unittest.TestCase):
 def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)/'product'; (self.root/'core/runtime/data/library').mkdir(parents=True)
 def fixture(self):
  lib=self.root/'core/runtime/data/library'; (lib/'safe.txt').write_text('hello asset')
  s={'memory':[{'id':'mem-1','title':'title','content':'body','scope':'HG','memory_type':'note','status':'active','version':3},
               {'id':'mem-2','title':'missing scope','content':'preserve me','memory_type':'auto'}],
     'library':[{'id':'asset-1','name':'safe.txt','path':'core/runtime/data/library/safe.txt','size':11},
                {'id':'escape','name':'probe','path':'core/runtime/data/../../escape','size':1}],
     'message':[{'id':'msg-1','text':'historic data'}], 'conversations':[{'id':'c1'}],
     'phone_devices':[{'device_id':'phone-1','device_token':'must-not-enter-event-log'}]}
  src=self.root/'state.json'; src.write_text(json.dumps(s)); return src
 def test_dry_run_does_not_create_target(self):
  src=self.fixture(); target=self.root/'target'; out=import_snapshot(src,self.root,target,False)
  self.assertEqual(out['status'],'DRY_RUN_ONLY'); self.assertFalse(target.exists())
 def test_apply_imports_safe_data_and_quarantines_unsafe(self):
  src=self.fixture(); target=self.root/'target'
  out=import_snapshot(src,self.root,target,True)
  self.assertTrue(out['integrity']['ok']); self.assertEqual(out['memory_active_count'],1)
  self.assertEqual(out['counts']['memory_quarantined'],1); self.assertEqual(out['counts']['library_imported'],1)
  self.assertEqual(out['counts']['library_quarantined'],1); self.assertEqual(out['counts']['messages_imported'],1)
  events=StateStore(str(target)).replay(); all_text=json.dumps(events)
  self.assertIn('historic data',all_text); self.assertIn('preserve me',all_text)
  self.assertNotIn('must-not-enter-event-log',all_text)
  self.assertTrue((target/'library').is_dir())
 def test_nonempty_destination_refused(self):
  src=self.fixture(); target=self.root/'target'; target.mkdir(); (target/'keep').write_text('x')
  with self.assertRaises(ValueError): import_snapshot(src,self.root,target,True)
if __name__=='__main__': unittest.main()
