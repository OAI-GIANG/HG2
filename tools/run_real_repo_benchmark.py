#!/usr/bin/env python3
"""Run the preregistered HG2 real-repository static import/impact benchmark."""
from __future__ import annotations
import hashlib, json, os, platform, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REG=ROOT/"docs/evidence/HG2_CI_REAL_REPO_REGISTRATION_V1.json"
OUT=ROOT/"docs/evidence/HG2_CI_REAL_REPO_RESULT_V1.json"
ANALYZER=ROOT/"tools/hg_code_intelligence.py"
def sha(b): return hashlib.sha256(b).hexdigest()
def git(repo,*args): return subprocess.check_output(["git",*args],cwd=repo,text=True).strip()
def archive_sha(repo): return sha(subprocess.check_output(["git","archive","--format=tar","HEAD"],cwd=repo))
def ratio(tp,denom): return round(tp/denom,6) if denom else 1.0
rb=REG.read_bytes(); reg=json.loads(rb)
if reg.get("status")!="PRE_REGISTERED": raise SystemExit("BLOCKED_REGISTRATION_NOT_PREREGISTERED")
if sha(ANALYZER.read_bytes())!=reg["analyzer_sha256"]: raise SystemExit("BLOCKED_ANALYZER_HASH_MISMATCH")
if sha(Path(__file__).read_bytes())!=reg["runner_sha256"]: raise SystemExit("BLOCKED_RUNNER_HASH_MISMATCH")
results=[]
with tempfile.TemporaryDirectory(prefix="hg2-real-benchmark-") as td:
 for case in reg["cases"]:
  repo=Path(case["local_path"]).resolve(strict=True)
  head=git(repo,"rev-parse","HEAD"); tree=git(repo,"rev-parse","HEAD^{tree}"); status=git(repo,"status","--porcelain"); tarsha=archive_sha(repo)
  ident={"head":head==case["commit"],"tree":tree==case["tree"],"archive_sha256":tarsha==case["archive_sha256"],"clean_worktree":status==""}
  if not all(ident.values()): raise SystemExit("BLOCKED_CORPUS_IDENTITY:"+case["id"]+":"+json.dumps(ident))
  rp=Path(td)/(case["id"]+".json")
  cmd=[sys.executable,str(ANALYZER),"--repo",str(repo),"--revision",case["commit"],"--changed",case["changed_path"],"--output",str(rp)]
  env=dict(os.environ); env["PYTHONDONTWRITEBYTECODE"]="1"
  proc=subprocess.run(cmd,cwd=ROOT,env=env,text=True,capture_output=True)
  if proc.returncode: raise SystemExit("BLOCKED_ANALYZER_EXECUTION:"+case["id"]+":"+proc.stderr[-2000:])
  raw=rp.read_bytes(); report=json.loads(raw)
  pe=sorted({(e["source_path"],e["target_path"]) for e in report["edges"] if e.get("target_path") is not None})
  ee=sorted((e["source"],e["target"]) for e in case["expected_edges"]); ps,es=set(pe),set(ee)
  tp,fp,fn=len(ps&es),len(ps-es),len(es-ps); ep,er=ratio(tp,tp+fp),ratio(tp,tp+fn)
  pd=sorted(report["impact"]["known_impacted_dependents"]); ed=sorted(case["expected_dependents"]); pds,eds=set(pd),set(ed)
  dtp=len(pds&eds); dp,dr=ratio(dtp,len(pds)),ratio(dtp,len(eds))
  cov=report["coverage"]; cc=cov["coverage_complete_for_all_repository_source"] is case["expected_coverage_complete"]
  ic=report["impact"]["status"]==case["expected_impact_status"]
  metrics={"edge_precision":ep,"edge_recall":er,"dependent_precision":dp,"dependent_recall":dr,"coverage_state_correct":cc,"impact_status_correct":ic,"all_expected_edges_exact":ps==es,"all_expected_dependents_exact":pds==eds}
  passed=all([ep==1.0,er==1.0,dp==1.0,dr==1.0,cc,ic,ps==es,pds==eds])
  results.append({"case_id":case["id"],"repo_url":case["repo_url"],"commit":head,"tree":tree,"archive_sha256":tarsha,"corpus_identity_checks":ident,"changed_path":case["changed_path"],"expected_edges":[list(x) for x in ee],"predicted_edges":[list(x) for x in pe],"edge_tp":tp,"edge_fp":fp,"edge_fn":fn,"expected_dependents":ed,"predicted_dependents":pd,"coverage":{k:cov[k] for k in ["files_seen","source_files_recognized","python_files_total","python_files_parsed","python_files_parse_failed","unsupported_source_files","unclassified_files_count","dynamic_import_sites","coverage_complete_for_all_repository_source"]},"expected_coverage_complete":case["expected_coverage_complete"],"predicted_impact_status":report["impact"]["status"],"expected_impact_status":case["expected_impact_status"],"metrics":metrics,"snapshot_sha256":report["snapshot_sha256"],"report_sha256":report["report_sha256"],"raw_report_sha256":sha(raw),"command":cmd,"pass":passed})
etp=sum(r["edge_tp"] for r in results); efp=sum(r["edge_fp"] for r in results); efn=sum(r["edge_fn"] for r in results)
dtp=sum(len(set(r["predicted_dependents"])&set(r["expected_dependents"])) for r in results); dpn=sum(len(r["predicted_dependents"]) for r in results); den=sum(len(r["expected_dependents"]) for r in results)
summary={"case_count":len(results),"case_pass_count":sum(r["pass"] for r in results),"case_fail_count":sum(not r["pass"] for r in results),"overall_edge_precision":ratio(etp,etp+efp),"overall_edge_recall":ratio(etp,etp+efn),"overall_dependent_precision":ratio(dtp,dpn),"overall_dependent_recall":ratio(dtp,den),"coverage_state_accuracy":sum(r["metrics"]["coverage_state_correct"] for r in results)/len(results),"impact_status_accuracy":sum(r["metrics"]["impact_status_correct"] for r in results)/len(results)}
th=reg["acceptance_thresholds"]
summary["thresholds_met"]={"minimum_cases":len(results)>=th["minimum_cases"],"overall_edge_precision_min":summary["overall_edge_precision"]>=th["overall_edge_precision_min"],"overall_edge_recall_min":summary["overall_edge_recall"]>=th["overall_edge_recall_min"],"overall_dependent_precision_min":summary["overall_dependent_precision"]>=th["overall_dependent_precision_min"],"overall_dependent_recall_min":summary["overall_dependent_recall"]>=th["overall_dependent_recall_min"],"coverage_state_accuracy_min":summary["coverage_state_accuracy"]>=th["coverage_state_accuracy_min"],"impact_status_accuracy_min":summary["impact_status_accuracy"]>=th["impact_status_accuracy_min"],"all_cases_pass":summary["case_fail_count"]==0}
summary["benchmark_pass"]=all(summary["thresholds_met"].values())
out={"benchmark_id":reg["benchmark_id"],"registration_sha256":sha(rb),"runner_sha256":sha(Path(__file__).read_bytes()),"analyzer_sha256":sha(ANALYZER.read_bytes()),"completed_utc":datetime.now(timezone.utc).isoformat(),"command":"PYTHONDONTWRITEBYTECODE=1 python tools/run_real_repo_benchmark.py","environment":{"python":sys.version,"platform":platform.platform(),"machine":platform.machine(),"system":platform.system()},"candidate":{"git_head":git(ROOT,"rev-parse","HEAD"),"git_tree":git(ROOT,"rev-parse","HEAD^{tree}"),"working_tree_status_before_run":git(ROOT,"status","--porcelain")},"method":"Run analyzer CLI on pinned clean public repositories; compare exact resolved local import-edge set, reverse-dependent set for preregistered changed path, repository coverage state, and impact status. Repository code is parsed as data and never executed.","summary":summary,"cases":results,"limitations":["Static import edges are not runtime call/data-flow edges.","Exact-name module resolution does not model src-layout package installation; unresolved imports are not counted as local edges.","Unsupported source/config files and unclassified files intentionally make repository-wide coverage incomplete.","Passing two repositories does not establish correctness for all repositories or languages."]}
body=(json.dumps(out,sort_keys=True,indent=2)+"\n").encode(); OUT.write_bytes(body)
print(json.dumps({"result_path":str(OUT.relative_to(ROOT)),"registration_sha256":out["registration_sha256"],"runner_sha256":out["runner_sha256"],"result_sha256":sha(body),"summary":summary},sort_keys=True,indent=2))
