#!/usr/bin/env python3
"""Deterministic rehearsal importer for a frozen legacy HG JSON snapshot.

Default is dry-run. --apply requires a new/empty destination and writes only
there. Library paths are resolved and constrained to the canonical library root.
No model/provider/network calls are made. Device tokens are never imported into
the event log; their source snapshot remains protected in the rollback backup.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, sqlite3, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from hg.history import StateStore
from hg.memory import MemoryStore
try:
    from .legacy_state_preflight import audit
    from .legacy_backend_reconcile import reconcile as reconcile_backend
except ImportError:  # direct script execution
    from legacy_state_preflight import audit
    from legacy_backend_reconcile import reconcile as reconcile_backend

TYPE_MAP={'profile':'fact','preference':'preference','working_rule':'rule','project_rule':'rule',
          'note':'other','goal':'project','fact':'fact','rule':'rule','project':'project','event':'event','other':'other'}

def sha_bytes(raw): return hashlib.sha256(raw).hexdigest()

def import_snapshot(state_path: Path, product_root: Path, target: Path, apply=False,
                    backend_db: Path | None = None, expected_backend_sha256: str | None = None):
    raw=state_path.read_bytes(); source_sha=sha_bytes(raw); state=json.loads(raw)
    plan=audit(state_path,product_root)
    if plan['source']['sha256'] != source_sha:
        raise ValueError('state source changed during preflight audit')
    backend_report=reconcile_backend(state_path,backend_db) if backend_db else None
    if backend_report:
        if (backend_report['state_source']['sha256'] != source_sha
                or not backend_report['state_source']['stable_during_audit']):
            raise ValueError('state source changed during backend reconciliation')
        if expected_backend_sha256 and backend_report['backend_source']['database_sha256'] != expected_backend_sha256:
            raise ValueError('backend database hash does not match the approved snapshot manifest')
        mem_reconcile=backend_report['memory_reconciliation']
        if not backend_report['backend_source']['stable_during_audit']:
            raise ValueError('backend source changed during read-only reconciliation')
        if mem_reconcile['backend_duplicate_ids'] or mem_reconcile['state_duplicate_ids']:
            raise ValueError('duplicate IDs in a source prevent safe reconciliation')
        if mem_reconcile['overlap_conflicts']:
            raise ValueError('JSON/backend content or version conflicts require quarantine review before import')
    if not apply:
        result={'status':'DRY_RUN_ONLY','source_sha256':source_sha,'counts':plan['counts'],
                'memory_safe':plan['memory']['safe_candidate_count'],'memory_quarantined':plan['memory']['quarantine_count'],
                'library_safe':plan['library']['safe_present_count'],'library_quarantined':plan['library']['quarantine_or_missing_count'],
                'message_count':plan['message_count'],'conversation_count':plan['conversation_count']}
        if backend_report:
            result['backend_reconciliation']={
                'database_sha256':backend_report['backend_source']['database_sha256'],
                'memory_reconciliation':backend_report['memory_reconciliation'],
                'operations':backend_report['operations'],
                'database_stable_during_audit':backend_report['backend_source']['stable_during_audit']}
            result['backend_import_plan']={
                'exact_duplicate_events':backend_report['memory_reconciliation']['exact_duplicate_matches'],
                'backend_only_quarantine_events':backend_report['memory_reconciliation']['backend_only_count'],
                'operation_reconciliation_events':backend_report['operations']['row_count'],
                'database_mutation_performed':False,
                'backend_only_records_activated':False,
                'target_created':False}
        return result
    final_target=target
    if final_target.exists(): raise ValueError('destination must be absent for atomic import publication')
    final_target.parent.mkdir(parents=True,exist_ok=True)
    target=final_target.with_name(f'.{final_target.name}.staging-{os.getpid()}')
    if target.exists(): raise ValueError('incomplete staging destination already exists')
    target.mkdir(parents=True,exist_ok=False)
    os.chmod(target,0o700)
    try:
        return _build_and_publish(state_path, state, raw, source_sha, plan, product_root, final_target, target, backend_report, backend_db)
    except Exception:
        # The staging directory is an unpublished build artifact. Remove only this
        # exact private path created by this invocation; never touch final/live data.
        shutil.rmtree(target, ignore_errors=True)
        raise

def _build_and_publish(state_path, state, raw, source_sha, plan, product_root, final_target, target, backend_report, backend_db):
    store=StateStore(str(target)); memory=MemoryStore(store)
    store.emit('legacy.import.started',{'source_sha256':source_sha,'source_bytes':len(raw),'schema':'HG_LEGACY_MIGRATION_PREFLIGHT_V1'},
               event_id='legacy-import-start:'+source_sha)
    counts={'memory_imported':0,'memory_quarantined':0,'messages_imported':0,'conversations_imported':0,
            'library_imported':0,'library_quarantined':0,'devices_redacted':0,
            'backend_memory_deduplicated':0,'backend_memory_quarantined':0,'backend_operations_reconciled':0}
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
    if backend_report and backend_db:
        # Keep every backend record accounted for. Exact duplicates are represented
        # by hash-only reconciliation events; records without a JSON counterpart
        # remain inert quarantine events because the legacy DB has no scope_id.
        db_sha=backend_report['backend_source']['database_sha256']
        if sha_bytes(backend_db.resolve().read_bytes()) != db_sha:
            raise ValueError('backend snapshot changed after reconciliation')
        database_uri=backend_db.resolve().as_uri() + '?mode=ro'
        con=sqlite3.connect(database_uri,uri=True,timeout=3,isolation_level=None)
        con.row_factory=sqlite3.Row
        con.execute('PRAGMA query_only=ON'); con.execute('BEGIN')
        try:
            db_cols={r[1] for r in con.execute('PRAGMA table_info(memory)')}
            base_columns=['memory_id','version','claim','checksum']
            optional_columns=['provenance','evidence_refs','source','confidence','authority','created_at','updated_at']
            selected=base_columns+[name for name in optional_columns if name in db_cols]
            if not set(base_columns).issubset(db_cols):
                raise ValueError('legacy backend memory schema is incomplete')
            db_rows=[dict(row) for row in con.execute(
                'SELECT '+','.join('"'+c+'"' for c in selected)+' FROM memory')]
            json_by_id={str(rec.get('id')):rec for rec in state.get('memory',[])
                        if isinstance(rec,dict) and rec.get('id') is not None}
            for rec in db_rows:
                memory_id=str(rec.get('memory_id') or '')
                source_id_hash=sha_bytes(memory_id.encode('utf-8'))
                legacy=json_by_id.get(memory_id)
                if legacy is not None:
                    claim_match=legacy.get('content') == rec.get('claim')
                    version_match=legacy.get('version') == rec.get('version')
                    if not claim_match or not version_match:
                        raise ValueError('source changed or reconciliation conflict discovered during import')
                    store.emit('legacy.backend.memory.deduplicated',{
                        'backend_db_sha256':db_sha,'memory_id_sha256':source_id_hash,
                        'version':rec.get('version'),'claim_sha256':sha_bytes(str(rec.get('claim','')).encode('utf-8')),
                        'backend_checksum':rec.get('checksum'),'json_scope':legacy.get('scope'),
                        'disposition':'EXACT_ID_VERSION_CONTENT_MATCH'
                    },event_id=f'legacy-backend-memory-dedup:{db_sha}:{source_id_hash}')
                    counts['backend_memory_deduplicated']+=1
                else:
                    # No backend-only memory may be promoted without explicit scope authority.
                    # Quarantine metadata must not copy raw legacy claims or provenance.
                    # A hash-only pointer preserves auditability without leaking content.
                    store.emit('legacy.backend.memory.quarantined',{
                        'backend_db_sha256':db_sha,'source':'legacy-backend-sqlite',
                        'reason':'MISSING_JSON_COUNTERPART_AND_SCOPE_NOT_AVAILABLE',
                        'memory_id_sha256':source_id_hash,
                        'version':rec.get('version'),
                        'claim_sha256':sha_bytes(str(rec.get('claim','')).encode('utf-8')),
                        'backend_checksum':rec.get('checksum'),
                        'disposition':'INERT_QUARANTINE_NO_SCOPE_AUTHORITY'
                    },event_id=f'legacy-backend-memory-quarantine:{db_sha}:{source_id_hash}')
                    counts['backend_memory_quarantined']+=1
            if 'operations' in {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
                op_cols={r[1] for r in con.execute('PRAGMA table_info(operations)')}
                required_ops={'op_key','op_id','kind','result_json','created_at'}
                if not required_ops.issubset(op_cols):
                    raise ValueError('legacy backend operations schema is incomplete')
                for i,row in enumerate(con.execute('SELECT op_key,op_id,kind,result_json,created_at FROM operations')):
                    raw_result=str(row['result_json'] or '{}')
                    try: result=json.loads(raw_result)
                    except Exception: result={}
                    if isinstance(result,dict) and result.get('ok') is True:
                        result_category='SUCCESS_NOOP' if result.get('noop') is True else 'SUCCESS'
                    elif isinstance(result,dict):
                        error=result.get('error'); code=error.get('code') if isinstance(error,dict) else None
                        result_category='FAIL_'+str(code or 'UNKNOWN')
                    else: result_category='NON_OBJECT_RESULT'
                    op_key_hash=sha_bytes(str(row['op_key'] or '').encode('utf-8'))
                    op_id_hash=sha_bytes(str(row['op_id'] or '').encode('utf-8')) if row['op_id'] else None
                    record_payload={'backend_db_sha256':db_sha,'row_index':i,'kind':row['kind'],
                        'operation_key_sha256':op_key_hash,'operation_id_sha256':op_id_hash,
                        'result_category':result_category,'result_sha256':sha_bytes(raw_result.encode('utf-8')),
                        'memory_id_sha256':sha_bytes(str(result.get('memory_id')).encode('utf-8'))
                            if isinstance(result,dict) and result.get('memory_id') else None,
                        'created_at':row['created_at']}
                    store.emit('legacy.backend.operation.reconciled',record_payload,
                        event_id=f'legacy-backend-operation:{db_sha}:{op_key_hash}')
                    counts['backend_operations_reconciled']+=1
            store.emit('legacy.backend.reconciliation.completed',{
                'backend_db_sha256':db_sha,
                'summary':backend_report['memory_reconciliation'],
                'operations':backend_report['operations'],
                'record_disposition':'JSON_SCOPE_AUTHORITY; DB_ONLY_RECORDS_QUARANTINED'
            },event_id=f'legacy-backend-reconcile-complete:{db_sha}')
        finally:
            con.rollback(); con.close()
        if sha_bytes(backend_db.resolve().read_bytes()) != db_sha:
            raise ValueError('backend snapshot changed while importing reconciliation events')
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
    staged_integrity=store.verify()
    if not staged_integrity.get('ok'): raise ValueError('staging history integrity failed; final destination was not published')
    # Bind publication to the exact source snapshots audited before import.
    if sha_bytes(state_path.resolve().read_bytes()) != source_sha:
        raise ValueError('JSON state changed during import; refusing publication')
    if backend_report and backend_db:
        if sha_bytes(backend_db.resolve().read_bytes()) != backend_report['backend_source']['database_sha256']:
            raise ValueError('backend database changed during import; refusing publication')
    if final_target.exists(): raise ValueError('final destination appeared during import; refusing publication')
    target.rename(final_target)
    final_store=StateStore(str(final_target)); final_memory=MemoryStore(final_store)
    final_integrity=final_store.verify()
    if not final_integrity.get('ok'): raise ValueError('published destination failed post-rename integrity')
    result={'status':'IMPORTED_TO_NEW_TARGET_ONLY','source_sha256':source_sha,'counts':counts,
            'target':str(final_target),'integrity':final_integrity,'memory_active_count':len(final_memory.list_active(grants={'global','HG'},limit=500))}
    if backend_report:
        result['backend_reconciliation']={
            'database_sha256':backend_report['backend_source']['database_sha256'],
            'memory_reconciliation':backend_report['memory_reconciliation'],
            'operations':backend_report['operations'],
            'database_stable_during_audit':backend_report['backend_source']['stable_during_audit']}
    return result

def main():
    p=argparse.ArgumentParser(); p.add_argument('--state',type=Path,required=True); p.add_argument('--product-root',type=Path,required=True)
    p.add_argument('--target',type=Path,required=True); p.add_argument('--backend-db',type=Path)
    p.add_argument('--expected-backend-sha256')
    p.add_argument('--apply',action='store_true')
    a=p.parse_args(); print(json.dumps(import_snapshot(a.state,a.product_root,a.target,a.apply,backend_db=a.backend_db,expected_backend_sha256=a.expected_backend_sha256),ensure_ascii=False,sort_keys=True,indent=2))
if __name__=='__main__': main()
