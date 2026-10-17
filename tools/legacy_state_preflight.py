#!/usr/bin/env python3
"""Read-only inventory for migration from the former HG JSON state.

The tool never follows a Library path outside the canonical Library root and
never prints memory/message content. It reports hashes and structural counts.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from collections import Counter


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def audit(state_path: Path, product_root: Path) -> dict:
    raw=state_path.read_bytes(); state=json.loads(raw)
    if not isinstance(state,dict): raise ValueError('state root must be an object')
    memories=state.get('memory',[]); memories=memories if isinstance(memories,list) else []
    mem_safe=[]; mem_quarantine=[]
    for i,m in enumerate(memories):
        reason=None
        if not isinstance(m,dict): reason='NOT_OBJECT'
        elif not str(m.get('id','')): reason='MISSING_ID'
        elif not str(m.get('title','')).strip(): reason='MISSING_TITLE'
        elif not str(m.get('content','')).strip(): reason='MISSING_CONTENT'
        elif m.get('scope') not in ('global','HG'): reason='MISSING_OR_UNRECOGNIZED_SCOPE'
        elif str(m.get('status','active')) not in ('active','superseded'): reason='UNRECOGNIZED_STATUS'
        target=mem_safe if reason is None else mem_quarantine
        target.append({'index':i,'id':m.get('id') if isinstance(m,dict) else None,'reason':reason})
    lib=state.get('library',[]); lib=lib if isinstance(lib,list) else []
    library_root=(product_root/'core/runtime/data/library').resolve()
    lib_items=[]
    for i,item in enumerate(lib):
        if not isinstance(item,dict):
            lib_items.append({'index':i,'id':None,'status':'QUARANTINE_NOT_OBJECT'}); continue
        raw_path=str(item.get('path',''))
        resolved=(product_root/raw_path).resolve()
        try: contained=resolved.is_relative_to(library_root)
        except AttributeError: contained=str(resolved).startswith(str(library_root)+str(Path('/')))
        exists=resolved.is_file() if contained else False
        lib_items.append({'index':i,'id':item.get('id'),'name':item.get('name'),
                          'status':'SAFE_PRESENT' if contained and exists else ('QUARANTINE_OUTSIDE_ROOT' if not contained else 'MISSING_ASSET'),
                          'size_metadata':item.get('size'),'actual_size':resolved.stat().st_size if exists else None,
                          'sha256':sha(resolved) if exists else None})
    counts={k:(len(v) if isinstance(v,list) else None) for k,v in state.items()}
    return {'schema':'HG_LEGACY_MIGRATION_PREFLIGHT_V1','status':'READ_ONLY_INVENTORY',
      'source':{'path':str(state_path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)},
      'counts':counts,'memory':{'total':len(memories),'safe_candidate_count':len(mem_safe),
       'quarantine_count':len(mem_quarantine),'quarantine':mem_quarantine},
      'library':{'total':len(lib),'safe_present_count':sum(x['status']=='SAFE_PRESENT' for x in lib_items),
       'quarantine_or_missing_count':sum(x['status']!='SAFE_PRESENT' for x in lib_items),'items':lib_items},
      'message_count':counts.get('message',0),'conversation_count':len(state.get('conversations',[])) if isinstance(state.get('conversations',[]),list) else None}


def main():
    p=argparse.ArgumentParser(); p.add_argument('--state',type=Path,required=True); p.add_argument('--product-root',type=Path,required=True); p.add_argument('--output',type=Path)
    a=p.parse_args(); result=audit(a.state,a.product_root)
    out=json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(out,encoding='utf-8')
    print(out,end='')
if __name__=='__main__': main()
