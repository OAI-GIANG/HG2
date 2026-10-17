#!/usr/bin/env python3
"""Deterministic rehearsal importer for a frozen legacy HG JSON snapshot.

Default is dry-run. --apply requires a new/empty destination and writes only
there. Library paths are resolved and constrained to the canonical library root.
No model/provider/network calls are made. Device tokens are never imported into
the event log; their source snapshot remains protected in the rollback backup.
"""
from __future__ import annotations
import argparse, hashlib, json, shutil, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from hg.history import StateStore
from hg.memory import MemoryStore
try:
    from .legacy_state_preflight import audit
except ImportError:  # direct script execution
    from legacy_state_preflight import audit

TYPE_MAP={'profile':'fact','preference':'preference','working_rule':'rule','project_rule':'rule',
          'note':'other','goal':'project','fact':'fact','rule':'rule','project':'project','event':'event','other':'other'}

def sha_bytes(raw): return hashlib.sha256(raw).hexdigest()

def import_snapshot(state_path: Path, product_root: Path, target: Path, apply=False):
    raw=state_path.read_bytes(); source_sha=sha_bytes(raw); state=json.loads(raw)
    plan=audit(state_path,product_root)
    if not apply:
        return {'status':'DRY_RUN_ONLY','source_sha256':source_sha,'counts':plan['counts'],
                'memory_safe':plan['memory']['safe_candidate_count'],'memory_quarantined':plan['memory']['quarantine_count'],
                'library_safe':plan['library']['safe_present_count'],'library_quarantined':plan['library']['quarantine_or_missing_count'],
                'message_count':plan['message_count'],'conversation_count':plan['conversation_count']}
    if target.exists() and any(target.iterdir()): raise ValueError('destination must be absent or empty')
    target.mkdir(parents=True,exist_ok=True)
    store=StateStore(str(target)); memory=MemoryStore(store)
    store.emit('legacy.import.started',{'source_sha256':source_sha,'source_bytes':len(raw),'schema':'HG_LEGACY_MIGRATION_PREFLIGHT_V1'},
               event_id='legacy-import-start:'+source_sha)
    counts={'memory_imported':0,'memory_quarantined':0,'messages_imported':0,'conversations_imported':0,
            'library_imported':0,'library_quarantined':0,'devices_redacted':0}
    # Preserve every legacy memory. Only well-scoped active records enter the live memory projection.
    for i,rec in enumerate(state.get('memory',[]) if isinstance(state.get('memory',[]),list) else []):
        safe=next((x for x in plan['memory']['quarantine'] if x['index']==i),None)
        if safe:
            store.emit('legacy.memory.quarantined',{'source_sha256':source_sha,'index':i,'record':rec,'reason':safe['reason']},
                       event_id=f'legacy-memory-quarantine:{source_sha}:{i}')
            counts['memory_quarantined']+=1; continue
        kind=TYPE_MAP.get(str(rec.get('memory_type',rec.get('kind','other'))),'other')
        provenance=str(rec.get('provenance','legacy-snapshot'))[:800]
        provenance += f"; legacy_source_sha256={source_sha}; legacy_version={rec.get('version','unknown')}"
        mapped={'id':str(rec['id']),'type':kind,'title':str(rec['title']),'content':str(rec['content']),
                'scope_id':str(rec['scope']),'source':str(rec.get('source','legacy'))[:256],'provenance':provenance}
        memory.remember(mapped,principal_id='phone-owner',grants={'global','HG'},
                        idempotency_key=f'legacy-memory:{source_sha}:{rec["id"]}')
        counts['memory_imported']+=1
    # Keep conversations and messages as inert, provenance-labelled data events.
    for i,rec in enumerate(state.get('conversations',[]) if isinstance(state.get('conversations',[]),list) else []):
        store.emit('legacy.conversation.imported',{'source_sha256':source_sha,'index':i,'record':rec},
                   event_id=f'legacy-conversation:{source_sha}:{i}')
        counts['conversations_imported']+=1
    for i,rec in enumerate(state.get('message',[]) if isinstance(state.get('message',[]),list) else []):
        store.emit('legacy.message.imported',{'source_sha256':source_sha,'index':i,'record':rec},
                   event_id=f'legacy-message:{source_sha}:{i}')
        counts['messages_imported']+=1
    # Only copy assets proven to exist inside the canonical Library root.
    libroot=(product_root/'core/runtime/data/library').resolve()
    target_lib=target/'library'; target_lib.mkdir(exist_ok=True)
    for i,item in enumerate(state.get('library',[]) if isinstance(state.get('library',[]),list) else []):
        item_plan=plan['library']['items'][i]
        if item_plan['status']!='SAFE_PRESENT':
            store.emit('legacy.library.quarantined',{'source_sha256':source_sha,'index':i,'record':item,
                       'reason':item_plan['status']},event_id=f'legacy-library-quarantine:{source_sha}:{i}')
            counts['library_quarantined']+=1; continue
        src=(product_root/str(item['path'])).resolve()
        if not src.is_relative_to(libroot) or not src.is_file() or sha_bytes(src.read_bytes())!=item_plan['sha256']:
            raise ValueError(f'asset changed or escaped root at index {i}; abort import')
        digest=item_plan['sha256']; dest=target_lib/digest
        if not dest.exists(): shutil.copy2(src,dest)
        if sha_bytes(dest.read_bytes())!=digest: raise ValueError(f'asset copy hash mismatch at index {i}')
        store.emit('legacy.library.asset.imported',{'source_sha256':source_sha,'index':i,'legacy_id':item.get('id'),
                   'name':item.get('name'),'sha256':digest,'size':dest.stat().st_size,'relative_blob':f'library/{digest}'},
                   event_id=f'legacy-library-asset:{source_sha}:{i}')
        counts['library_imported']+=1
    # Device credentials are intentionally excluded from events; keep only a one-way fingerprint.
    for i,rec in enumerate(state.get('phone_devices',[]) if isinstance(state.get('phone_devices',[]),list) else []):
        if not isinstance(rec,dict):
            safe_rec={'record_type':'non_object'}
        else:
            safe_rec={k:v for k,v in rec.items() if k not in ('device_token','token','secret','api_key','credential')}
            token=rec.get('device_token')
            if token: safe_rec['device_token_sha256']=sha_bytes(str(token).encode())
        store.emit('legacy.device.imported_redacted',{'source_sha256':source_sha,'index':i,'record':safe_rec},
                   event_id=f'legacy-device:{source_sha}:{i}')
        counts['devices_redacted']+=1
    store.emit('legacy.import.completed',{'source_sha256':source_sha,'counts':counts,'integrity':store.verify()},
               event_id='legacy-import-complete:'+source_sha)
    if not store.verify().get('ok'): raise ValueError('destination history integrity failed')
    return {'status':'IMPORTED_TO_NEW_TARGET_ONLY','source_sha256':source_sha,'counts':counts,
            'target':str(target),'integrity':store.verify(),'memory_active_count':len(memory.list_active(grants={'global','HG'},limit=500))}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--state',type=Path,required=True); p.add_argument('--product-root',type=Path,required=True)
    p.add_argument('--target',type=Path,required=True); p.add_argument('--apply',action='store_true')
    a=p.parse_args(); print(json.dumps(import_snapshot(a.state,a.product_root,a.target,a.apply),ensure_ascii=False,sort_keys=True,indent=2))
if __name__=='__main__': main()
