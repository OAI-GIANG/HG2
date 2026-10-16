#!/usr/bin/env python3
"""Run HG2 synthetic benchmark V2; fixture hashes and expected graph are preregistered."""
from __future__ import annotations
import hashlib, importlib.util, json, platform, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = ROOT / "docs/evidence/HG2_CI_GROUND_TRUTH_REGISTRATION_V2.json"
OUT = ROOT / "docs/evidence/HG2_CI_GROUND_TRUTH_RESULT_V2.json"
MOD_PATH = ROOT / "tools/hg_code_intelligence.py"
spec = importlib.util.spec_from_file_location("hg_code_intelligence_benchmark_target", MOD_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

reg_bytes = REGISTRATION.read_bytes()
reg = json.loads(reg_bytes)
reg_hash = hashlib.sha256(reg_bytes).hexdigest()
fixture_root = ROOT / "tests/fixtures/code_intelligence_benchmark"
actual_fixture_hashes = {p.relative_to(fixture_root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(fixture_root.rglob("*")) if p.is_file()}
if actual_fixture_hashes != reg.get("fixture_files_sha256"):
    raise SystemExit("BENCHMARK_BLOCKED_FIXTURE_HASH_MISMATCH")
if len(reg.get("cases", [])) < reg["acceptance_thresholds"]["minimum_cases"]:
    raise SystemExit("BENCHMARK_BLOCKED_TOO_FEW_CASES")

def f1(p, r): return 0.0 if p+r == 0 else 2*p*r/(p+r)
def ratio(n,d): return 1.0 if d == 0 and n == 0 else (n/d if d else 0.0)

results=[]
for case in reg["cases"]:
 root = ROOT / case["root"]
 report = module.index_repository(root, source_revision=case["revision"], changed_paths=case["changed_paths"])
 predicted_edges={(e["source_path"],e["target_path"]) for e in report["edges"] if e["target_path"] is not None}
 expected_edges={(e["source"],e["target"]) for e in case["expected_edges"]}
 tp=len(predicted_edges & expected_edges); fp=len(predicted_edges-expected_edges); fn=len(expected_edges-predicted_edges)
 ep=ratio(tp,tp+fp); er=ratio(tp,tp+fn); ef=f1(ep,er)
 predicted_deps=set(report["impact"]["known_impacted_dependents"]); expected_deps=set(case["expected_dependents"])
 dtp=len(predicted_deps & expected_deps)
 dp=ratio(dtp,len(predicted_deps)); dr=ratio(dtp,len(expected_deps)); df=f1(dp,dr)
 cov=report["coverage"]
 metrics={"edge_precision":round(ep,6),"edge_recall":round(er,6),"edge_f1":round(ef,6),"dependent_precision":round(dp,6),"dependent_recall":round(dr,6),"dependent_f1":round(df,6),"coverage_state_correct":cov["coverage_complete_for_all_repository_source"] is case["expected_coverage_complete"],"impact_status_correct":report["impact"]["status"] == case["expected_impact_status"]}
 metrics["minimum_dynamic_import_sites_met"] = cov["dynamic_import_sites"] >= case.get("minimum_dynamic_import_sites",0)
 metrics["minimum_unsupported_source_files_met"] = cov["unsupported_source_files"] >= case.get("minimum_unsupported_source_files",0)
 metrics["minimum_unclassified_files_met"] = cov["unclassified_files_count"] >= case.get("minimum_unclassified_files",0)
 metrics["minimum_parse_failures_met"] = cov["python_files_parse_failed"] >= case.get("minimum_parse_failures",0)
 metrics["minimum_duplicate_module_names_met"] = cov["duplicate_module_names_count"] >= case.get("minimum_duplicate_module_names",0)
 case_pass=all(metrics[k] for k in ["coverage_state_correct","impact_status_correct","minimum_dynamic_import_sites_met","minimum_unsupported_source_files_met","minimum_unclassified_files_met","minimum_parse_failures_met","minimum_duplicate_module_names_met"]) and ep == 1.0 and er == 1.0 and dp == 1.0 and dr == 1.0
 results.append({"case_id":case["id"],"truth_type":case["truth_type"],"expected_edges":len(expected_edges),"predicted_edges":len(predicted_edges),"edge_tp":tp,"edge_fp":fp,"edge_fn":fn,"expected_dependents":sorted(expected_deps),"predicted_dependents":sorted(predicted_deps),"metrics":metrics,"candidate_snapshot_sha256":report["snapshot_sha256"],"candidate_report_sha256":report["report_sha256"],"pass":case_pass})

all_clean=[r for r,c in zip(results,reg["cases"]) if c["truth_type"].startswith("clean_python") or c["truth_type"]=="transitive_reverse_dependents"]
incomplete=[r for r,c in zip(results,reg["cases"]) if c["truth_type"] not in {"clean_python","clean_python_package","transitive_reverse_dependents"}]
edge_precision=ratio(sum(r["edge_tp"] for r in results),sum(r["edge_tp"]+r["edge_fp"] for r in results))
edge_recall=ratio(sum(r["edge_tp"] for r in results),sum(r["edge_tp"]+r["edge_fn"] for r in results))
dep_tp=sum(len(set(r["predicted_dependents"]) & set(r["expected_dependents"])) for r in results)
dep_pred=sum(len(r["predicted_dependents"]) for r in results); dep_expected=sum(len(r["expected_dependents"]) for r in results)
coverage_acc=sum(r["metrics"]["coverage_state_correct"] for r in results)/len(results)
impact_acc=sum(r["metrics"]["impact_status_correct"] for r in results)/len(results)
failclosed=sum(r["metrics"]["coverage_state_correct"] and r["metrics"]["impact_status_correct"] and r["metrics"]["minimum_dynamic_import_sites_met"] and r["metrics"]["minimum_unsupported_source_files_met"] and r["metrics"]["minimum_unclassified_files_met"] and r["metrics"]["minimum_parse_failures_met"] and r["metrics"]["minimum_duplicate_module_names_met"] for r in incomplete)/len(incomplete)
clean_tp=sum(r["edge_tp"] for r in all_clean)
clean_fp=sum(r["edge_fp"] for r in all_clean)
clean_fn=sum(r["edge_fn"] for r in all_clean)
clean_ep=ratio(clean_tp,clean_tp+clean_fp)
clean_er=ratio(clean_tp,clean_tp+clean_fn)
clean_dp=ratio(sum(len(set(r["predicted_dependents"]) & set(r["expected_dependents"])) for r in all_clean),sum(len(r["predicted_dependents"]) for r in all_clean))
clean_dr=ratio(sum(len(set(r["predicted_dependents"]) & set(r["expected_dependents"])) for r in all_clean),sum(len(r["expected_dependents"]) for r in all_clean))
summary={"case_count":len(results),"case_pass_count":sum(r["pass"] for r in results),"case_fail_count":sum(not r["pass"] for r in results),"overall_edge_precision":round(edge_precision,6),"overall_edge_recall":round(edge_recall,6),"clean_case_edge_precision":round(clean_ep,6),"clean_case_edge_recall":round(clean_er,6),"clean_case_dependent_precision":round(clean_dp,6),"clean_case_dependent_recall":round(clean_dr,6),"overall_coverage_state_accuracy":round(coverage_acc,6),"overall_impact_status_accuracy":round(impact_acc,6),"fail_closed_recall":round(failclosed,6),"overall_known_dependent_precision":round(ratio(dep_tp,dep_pred),6),"overall_known_dependent_recall":round(ratio(dep_tp,dep_expected),6)}
thresholds=reg["acceptance_thresholds"]
summary["thresholds_met"]={
 "minimum_cases":len(results)>=thresholds["minimum_cases"],
 "clean_cases_edge_precision_min":clean_ep>=thresholds["clean_cases_edge_precision_min"],
 "clean_cases_edge_recall_min":clean_er>=thresholds["clean_cases_edge_recall_min"],
 "clean_cases_dependent_precision_min":clean_dp>=thresholds["clean_cases_dependent_precision_min"],
 "clean_cases_dependent_recall_min":clean_dr>=thresholds["clean_cases_dependent_recall_min"],
 "overall_static_edge_precision_min":edge_precision>=thresholds["overall_static_edge_precision_min"],
 "overall_static_edge_recall_min":edge_recall>=thresholds["overall_static_edge_recall_min"],
 "overall_known_dependent_precision_min":ratio(dep_tp,dep_pred)>=thresholds["overall_known_dependent_precision_min"],
 "overall_known_dependent_recall_min":ratio(dep_tp,dep_expected)>=thresholds["overall_known_dependent_recall_min"],
 "overall_coverage_state_accuracy_min":coverage_acc>=thresholds["overall_coverage_state_accuracy_min"],
 "overall_impact_status_accuracy_min":impact_acc>=thresholds["overall_impact_status_accuracy_min"],
 "fail_closed_recall_min":failclosed>=thresholds["fail_closed_recall_min"],
 "all_cases_pass":all(r["pass"] for r in results)}
summary["benchmark_pass"] = all(summary["thresholds_met"].values())
try:
 import subprocess
 git_head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
 git_status=subprocess.check_output(["git","status","--porcelain"],cwd=ROOT,text=True).strip()
except Exception:
 git_head="UNAVAILABLE";git_status="UNAVAILABLE"
output={"benchmark_id":reg["benchmark_id"],"registration_sha256":reg_hash,"registration_self_hash":"NOT_IN_REGISTRATION; registration_sha256 in this result binds the exact preregistration bytes", "command":"PYTHONDONTWRITEBYTECODE=1 python tools/run_code_intelligence_benchmark.py", "environment":{"python":sys.version,"platform":platform.platform(),"machine":platform.machine(),"system":platform.system()},"candidate":{"git_head_before_run":git_head,"working_tree_status_before_run":git_status,"source_path":"tools/hg_code_intelligence.py","source_sha256":hashlib.sha256(MOD_PATH.read_bytes()).hexdigest()},"summary":summary,"cases":results,"limitations":reg["limitations"]}
body=(json.dumps(output,sort_keys=True,indent=2)+"\n").encode()
OUT.write_bytes(body)
print(json.dumps({"output":str(OUT.relative_to(ROOT)),"registration_sha256":reg_hash,"result_sha256":hashlib.sha256(body).hexdigest(),"summary":summary},sort_keys=True,indent=2))
