import json, os, sqlite3, tempfile, unittest
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
 def test_backend_database_is_reconciled_without_promoting_unscoped_rows(self):
  src=self.fixture(); target=self.root/'target'; db=self.root/'backend.sqlite3'
  con=sqlite3.connect(db)
  con.executescript("""
   CREATE TABLE memory(memory_id TEXT PRIMARY KEY,version INTEGER,claim TEXT,provenance TEXT,evidence_refs TEXT,source TEXT,confidence REAL,authority TEXT,checksum TEXT,created_at TEXT,updated_at TEXT);
   CREATE TABLE operations(op_key TEXT PRIMARY KEY,op_id TEXT,kind TEXT,result_json TEXT,created_at TEXT);
  """)
  con.execute("INSERT INTO memory VALUES(?,?,?,?,?,?,?,?,?,?,?)",
    ("mem-1",3,"body","p","[]","AI",0.8,"phone","legacy-checksum","t1","t2"))
  con.execute("INSERT INTO memory VALUES(?,?,?,?,?,?,?,?,?,?,?)",
    ("backend-only",1,"secret DB claim","p","[]","AI",0.7,"phone","legacy-checksum-2","t1","t2"))
  con.execute("INSERT INTO operations VALUES(?,?,?,?,?)",
    ("secret idempotency key","operation-id","memory.persist",'{"ok":true,"stored":true,"memory_id":"mem-1"}',"t3"))
  con.commit(); con.close(); before=db.read_bytes()
  out=import_snapshot(src,self.root,target,True,backend_db=db)
  self.assertTrue(out['integrity']['ok']); self.assertEqual(out['memory_active_count'],1)
  self.assertEqual(out['counts']['backend_memory_deduplicated'],1)
  self.assertEqual(out['counts']['backend_memory_quarantined'],1)
  self.assertEqual(out['counts']['backend_operations_reconciled'],1)
  self.assertTrue(out['backend_reconciliation']['database_stable_during_audit'])
  events=StateStore(str(target)).replay()
  dedup=[x for x in events if x['event_type']=='legacy.backend.memory.deduplicated']
  quarantined=[x for x in events if x['event_type']=='legacy.backend.memory.quarantined']
  ops=[x for x in events if x['event_type']=='legacy.backend.operation.reconciled']
  self.assertEqual(len(dedup),1); self.assertNotIn('body',json.dumps(dedup))
  self.assertEqual(len(quarantined),1); self.assertNotIn('secret DB claim',json.dumps(quarantined))
  self.assertIn('claim_sha256',json.dumps(quarantined)); self.assertNotIn('scope_id',json.dumps(quarantined))
  self.assertEqual(len(ops),1); self.assertNotIn('secret idempotency key',json.dumps(ops))
  self.assertEqual(ops[0]['payload']['result_category'],'SUCCESS')
  self.assertEqual(db.read_bytes(),before)
 def test_backend_version_or_content_conflict_aborts_before_target_creation(self):
  src=self.fixture(); target=self.root/'target'; db=self.root/'conflict.sqlite3'
  con=sqlite3.connect(db)
  con.execute("CREATE TABLE memory(memory_id TEXT PRIMARY KEY,version INTEGER,claim TEXT,checksum TEXT)")
  con.execute("INSERT INTO memory VALUES(?,?,?,?)",("mem-1",4,"conflicting body","checksum"))
  con.commit(); con.close()
  with self.assertRaisesRegex(ValueError,"conflicts require quarantine review"):
   import_snapshot(src,self.root,target,True,backend_db=db)
  self.assertFalse(target.exists())
 def test_nonempty_destination_refused(self):
  src=self.fixture(); target=self.root/'target'; target.mkdir(); (target/'keep').write_text('x')
  with self.assertRaises(ValueError): import_snapshot(src,self.root,target,True)
if __name__=='__main__': unittest.main()
