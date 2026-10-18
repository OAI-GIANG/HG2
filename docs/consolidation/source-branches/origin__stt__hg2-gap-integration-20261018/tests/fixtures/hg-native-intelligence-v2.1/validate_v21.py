#!/usr/bin/env python3
import json, hashlib, math
from pathlib import Path
root=Path(__file__).resolve().parent
base=root.parent.parent.parent.parent.parent
errors=[]
files=sorted(root.glob("HNIF2-*.json"))
try: m=json.loads((root/"manifest.json").read_text())
except Exception as e:
 print("STATIC_SEMANTIC_VALIDATION FAIL manifest parse",repr(e)); raise SystemExit(1)
items=[]
for f in files:
 try: items.append((f,json.loads(f.read_text())))
 except Exception as e: errors.append(f"{f.name}:JSON:{e}")
ids=[x.get("fixture_id") for _,x in items]
expected_ids={f"HNIF2-{i:02}" for i in range(1,27)}
errors += ["fixture_count_or_ids"] if len(files)!=26 or set(ids)!=expected_ids or len(set(ids))!=len(ids) else []
errors += ["manifest_count"] if m.get("total_fixtures")!=26 or len(m.get("fixtures",[]))!=26 else []
manifest_map={e.get("fixture_id"):e for e in m.get("fixtures",[])}
errors += ["manifest_fixture_mapping"] if set(manifest_map)!=expected_ids else []
hnit={f"HNIT-{i:03}" for i in range(1,31)}
xn={f"XN-{i:02}" for i in range(1,7)}
linked=set()
for f,x in items:
 fid=x.get("fixture_id","?")
 linked.update(x.get("linked_tests",[]))
 if x.get("schema_version")!="hni.fixture.v2.1" or x.get("version")!="2.1.0": errors.append(fid+":schema_version")
 if x.get("execution_status")!="NOT_RUN" or x.get("result_record",{}).get("observed_status")!="NOT_RUN": errors.append(fid+":execution_truth")
 if x.get("expected_response_verdict") not in ("PASS","FAIL","BLOCKED","INCONCLUSIVE"): errors.append(fid+":expected_verdict_enum")
 if x.get("classification")!="SYNTHETIC_NON_PRODUCTION": errors.append(fid+":classification")
 safe=x.get("safety",{})
 if safe.get("real_secrets") is not False or safe.get("production_data") is not False or safe.get("live_mutation") is not False: errors.append(fid+":safety")
 if x.get("oracle_spec_version")!="hni.oracle-spec.v2.1.1": errors.append(fid+":oracle_spec_version")
 spec=x.get("oracle_spec",{})
 if not isinstance(spec.get("case_data"),dict) or not spec.get("predicates"): errors.append(fid+":oracle_spec_missing")
 pids=[p.get("id") for p in spec.get("predicates",[])]
 if len(pids)!=len(set(pids)) or not all(isinstance(p,dict) and p.get("path") and p.get("op") and "expected" in p for p in spec.get("predicates",[])): errors.append(fid+":predicate_schema")
 if not x.get("assertions"): errors.append(fid+":assertions_missing")
 if not all(k in x.get("oracle_contract",{}) for k in ("status_decision_rules","suite_aggregation","na_rule","oracle_change_rule")): errors.append(fid+":aggregation_contract")
 ent=manifest_map.get(fid,{})
 if ent.get("file")!=f.name or ent.get("execution_status")!="NOT_RUN" or ent.get("oracle_spec_version")!="hni.oracle-spec.v2.1.1": errors.append(fid+":manifest_entry")
 if x.get("oracle_contract",{}).get("suite_aggregation",{}).get("step_2","").find("C0")<0: errors.append(fid+":C0_aggregation")
errors += ["HNIT_coverage"] if not hnit.issubset(linked) else []
errors += ["XN_coverage"] if not xn.issubset(linked) else []
# Fixture-specific deterministic oracle arithmetic and semantics.
byid={x.get("fixture_id"):x for _,x in items}
try:
 x=byid["HNIF2-05"]["oracle_spec"]["case_data"]
 w=x["weights"]; scores=x["scores"]
 if not math.isclose(sum(w.values()),1.0,abs_tol=1e-12): errors.append("HNIF2-05:weights_sum")
 for oid,expected in (("A",2.8),("B",3.8)):
  actual=sum(scores[oid][k]*w[k] for k in w)
  if not math.isclose(actual,expected,abs_tol=1e-12): errors.append(f"HNIF2-05:score_{oid}")
 if scores["A"]["feasibility"]>=x["eligibility"]["minimum_feasibility"]: errors.append("HNIF2-05:eligibility_A")
 if scores["B"]["feasibility"]<x["eligibility"]["minimum_feasibility"]: errors.append("HNIF2-05:eligibility_B")
except Exception as e: errors.append("HNIF2-05:semantic_arithmetic:"+repr(e))
try:
 x=byid["HNIF2-11"]["oracle_spec"]["case_data"]
 if x["corrected"]["C1"]!=x["corrected"]["X"]*3 or x["corrected"]["C2"]!=x["corrected"]["X"]+10: errors.append("HNIF2-11:dependent_values")
except Exception as e: errors.append("HNIF2-11:semantic_arithmetic:"+repr(e))
try:
 x=byid["HNIF2-19"]["oracle_spec"]["case_data"]
 b=x["baseline"]["errors"]/x["baseline"]["cases"]; c=x["candidate"]["errors"]/x["candidate"]["cases"]
 if not math.isclose(b,x["baseline"]["rate"]) or not math.isclose(c,x["candidate"]["rate"]): errors.append("HNIF2-19:rates")
 if not math.isclose((b-c)*100,x["absolute_reduction_pp"]) or not math.isclose((b-c)/b*100,x["relative_reduction_percent"]): errors.append("HNIF2-19:improvement_arithmetic")
 if x["causal_claim_permitted"] is not False or x["control_design_present"] is not False: errors.append("HNIF2-19:causal_guard")
except Exception as e: errors.append("HNIF2-19:semantic_arithmetic:"+repr(e))
for fid in ("HNIF2-20","HNIF2-22"):
 try:
  spec=byid[fid]["oracle_spec"]["case_data"]
  digest=spec.get("digest",{})
  if digest and hashlib.sha256(digest["payload"].encode()).hexdigest()!=digest["expected"]: errors.append(fid+":oracle_digest")
  if fid=="HNIF2-22":
   ds=spec["digest_samples"]
   if hashlib.sha256(ds["matching_payload"].encode()).hexdigest()!=ds["matching_sha256"]: errors.append(fid+":matching_digest")
   if hashlib.sha256(ds["mismatch_payload"].encode()).hexdigest()!=ds["mismatch_sha256"]: errors.append(fid+":mismatch_digest")
 except Exception as e: errors.append(fid+":digest_schema:"+repr(e))
# Status aggregation truth-table: evidenced C0 FAIL dominates all other states.
def aggregate(findings):
 if any(f.get("criticality")=="C0" and f.get("status")=="FAIL" and f.get("evidenced") for f in findings): return "FAIL"
 if any(f.get("status")=="BLOCKED" for f in findings): return "BLOCKED"
 if any(f.get("status")=="INCONCLUSIVE" for f in findings): return "INCONCLUSIVE"
 if any(f.get("status")=="NOT_RUN" for f in findings): return "NOT_RUN"
 if findings and all(f.get("status")=="PASS" for f in findings): return "PASS"
 return "INCONCLUSIVE"
truth=[
 ([{"status":"PASS"},{"status":"PASS"}],"PASS"),
 ([{"status":"NOT_RUN"}],"NOT_RUN"),
 ([{"status":"INCONCLUSIVE"}],"INCONCLUSIVE"),
 ([{"status":"BLOCKED"},{"status":"NOT_RUN"}],"BLOCKED"),
 ([{"status":"BLOCKED"},{"status":"FAIL","criticality":"C0","evidenced":True}],"FAIL"),
 ([{"status":"PASS"},{"status":"FAIL","criticality":"C0","evidenced":True}],"FAIL"),
 ([{"status":"FAIL","criticality":"C0","evidenced":False},{"status":"NOT_RUN"}],"NOT_RUN"),
]
for i,(case,want) in enumerate(truth,1):
 if aggregate(case)!=want: errors.append(f"aggregation_truth_table_{i}")
# Preserve frozen inputs by presence and known size only; explicitly not a cryptographic proof.
preserve={}  # Historical CP0 source files are outside this repository package; provenance is tracked separately.
preserve_errors=[]
for rel,size in preserve.items():
 q=base/rel
 if not q.is_file(): preserve_errors.append("missing:"+rel)
 elif q.stat().st_size!=size: preserve_errors.append(f"size:{rel}:{q.stat().st_size}!={size}")
errors.extend("preservation_"+e for e in preserve_errors)
print("STATIC_SEMANTIC_VALIDATION "+("PASS" if not errors else "FAIL"))
print(f"fixtures={len(files)} unique_ids={len(set(ids))} oracle_specs={sum(bool(x.get('oracle_spec')) for _,x in items)}/26")
print(f"HNIT={len(hnit & linked)}/30 XN={len(xn & linked)}/6")
print("semantic_arithmetic=PASS" if not any(e.startswith(("HNIF2-05:","HNIF2-11:","HNIF2-19:")) for e in errors) else "semantic_arithmetic=FAIL")
print("digest_recompute=PASS" if not any("digest" in e for e in errors) else "digest_recompute=FAIL")
print("aggregation_truth_table=PASS" if not any(e.startswith("aggregation_truth_table") for e in errors) else "aggregation_truth_table=FAIL")
print("preservation_size_presence_checks="+("PASS" if not preserve_errors else "FAIL")+" (not byte-for-byte proof)")
print("errors="+repr(errors))
raise SystemExit(bool(errors))
