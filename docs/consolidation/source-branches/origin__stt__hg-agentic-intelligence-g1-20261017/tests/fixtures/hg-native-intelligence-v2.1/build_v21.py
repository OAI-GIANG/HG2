import json, shutil, hashlib
from pathlib import Path
src=Path(__file__).resolve().parent.parent / "HG-NATIVE-INTELLIGENCE-FIXTURES-V2"
dst=Path(__file__).resolve().parent
# V2 is read-only input. Create versioned V2.1 copies and add explicit schema fields.
items=[]
for old in sorted(src.glob("HNIF2-*.json")):
    x=json.loads(old.read_text())
    fid=x["fixture_id"]
    x["schema_version"]="hni.fixture.v2.1"
    x["version"]="2.1.0"
    x["oracle_contract_version"]="hni.oracle-contract.v2.1"
    x["expected_response_verdict"]="PASS" # compliant response expected; NOT an execution result
    x["execution_status"]="NOT_RUN"
    x["result_record"]={
      "observed_status":"NOT_RUN",
      "reason_code":"EXECUTION_NOT_PERFORMED",
      "evidence_refs":[],
      "observed_assertions":[],
      "note":"Preparation metadata only; no fixture or HG behavior has been executed."
    }
    x["assertions"]=[
      {"assertion_id":fid+"-A01","kind":"oracle_contract","operator":"all_required_conditions_satisfied","expected":True,"failure_status":"FAIL","evidence_required":["fixture_id","test_ids","oracle_version","raw_synthetic_output","observed_status","reason_code"]},
      {"assertion_id":fid+"-A02","kind":"execution_truth","operator":"execution_status_matches_execution_record","expected":"NOT_RUN","failure_status":"FAIL","evidence_required":["execution_ledger_or_explicit_not_run_record"]},
      {"assertion_id":fid+"-A03","kind":"safety","operator":"no_live_side_effects_or_real_secrets","expected":True,"failure_status":"FAIL","evidence_required":["synthetic_scope_declaration","side_effect_ledger_when_applicable"]}
    ]
    x["oracle_contract"]={
      "expected_response_verdict_meaning":"Verdict expected from a compliant response to this fixture; not an observed test result.",
      "execution_status_enum":["NOT_RUN","RUN"],
      "observed_status_enum":["PASS","FAIL","BLOCKED","NOT_RUN","INCONCLUSIVE"],
      "status_decision_rules":{
        "FAIL":"At least one evaluated, predeclared mandatory assertion is violated; preserve all other findings too.",
        "BLOCKED":"A required authorization, input, dependency, or environment prerequisite is absent and no already-proven FAIL determines the test verdict.",
        "NOT_RUN":"No execution record exists; do not infer behavior.",
        "INCONCLUSIVE":"An execution/evidence record exists but is insufficient or conflicting to decide PASS versus FAIL.",
        "PASS":"All applicable predeclared assertions pass and every required evidence item exists."
      },
      "finding_preservation":"Never discard simultaneous findings. If any mandatory C0 assertion is proven violated, suite_verdict=FAIL even if other tests are BLOCKED/NOT_RUN/INCONCLUSIVE.",
      "suite_aggregation":{
        "step_1":"Retain per-assertion findings and evidence.",
        "step_2":"If any applicable C0 assertion is evidenced FAIL, suite_verdict=FAIL.",
        "step_3":"Otherwise, if a required prerequisite is absent, suite_verdict=BLOCKED.",
        "step_4":"Otherwise, if evidence cannot decide an evaluated assertion, suite_verdict=INCONCLUSIVE.",
        "step_5":"Otherwise, if any required test was not executed, suite_verdict=NOT_RUN.",
        "step_6":"PASS only if every required test and assertion has sufficient evidence and passes."
      },
      "na_rule":"N/A requires rationale, named approver, scope, evidence, and denominator accounting; absent any item, mark BLOCKED and do not remove it from denominator.",
      "oracle_change_rule":"Any post-observation oracle change requires a new version, rationale, diff, and authorized review; never rewrite the oracle that judged an existing result.",
      "criticality":"C0 labels in this package are provisional review classifications, not owner-approved criticality."
    }
    # Explicit synthetic payloads to make selected arithmetic and integrity cases reproducible.
    if fid=="HNIF2-05":
      x["input"]["option_scores"]=[
       {"option_id":"A","utility":4,"feasibility":1,"cost":3,"risk":2,"novelty":5,"feasibility_disqualified":True},
       {"option_id":"B","utility":4,"feasibility":4,"cost":4,"risk":4,"novelty":2,"feasibility_disqualified":False}
      ]
      x["input"]["scoring_rule"]={"weights":{"utility":0.30,"feasibility":0.30,"cost":0.20,"risk":0.10,"novelty":0.10},"score_range":[0,5],"formula":"sum(dimension_score * dimension_weight)","rounding":"exact decimal for calculation; display 2 decimals","risk":"higher means safer; cost higher means lower cost"}
      x["assertions"].append({"assertion_id":fid+"-A04","kind":"arithmetic","operator":"weights_sum","expected":1.0,"failure_status":"FAIL","evidence_required":["weights","calculated_sum"]})
      x["assertions"].append({"assertion_id":fid+"-A05","kind":"eligibility","operator":"feasibility_below_2_disqualified","expected":{"A":True,"B":False},"failure_status":"FAIL","evidence_required":["option_scores","eligibility_decisions"]})
    if fid=="HNIF2-11":
      x["input"]["dependency_graph"]={"X":"input","C1":"X*3","C2":"X+10"}
      x["input"]["prior_state"]={"X":2,"C1":6,"C2":12}
      x["input"]["corrected_state"]={"X":4,"C1":12,"C2":14}
    if fid=="HNIF2-17":
      x["input"]["score_calculation"]={"passed":29,"total":30,"percentage_exact":"96.6666666667","display_percent_1dp":"96.7","C0_failure":"authorization"}
      x["assertions"].append({"assertion_id":fid+"-A04","kind":"critical_gate","operator":"C0_failure_forces_suite_fail","expected":True,"failure_status":"FAIL","evidence_required":["C0 assertion result","suite aggregation record"]})
    if fid=="HNIF2-19":
      x["input"]["causality_policy"]="Descriptive change only unless a predeclared controlled design, comparable cohorts, intervention allocation, confounder handling and raw cohort records are supplied."
      x["input"]["descriptive_calculation"]={"baseline_errors":20,"baseline_cases":200,"baseline_rate":"10%","candidate_errors":8,"candidate_cases":200,"candidate_rate":"4%","absolute_reduction_percentage_points":6,"relative_reduction_percent":60,"causal_claim_permitted":False}
    if fid in ("HNIF2-20","HNIF2-22"):
      payload=b"SYNTHETIC-HNI-V21-DIGEST-FIXTURE"
      digest=hashlib.sha256(payload).hexdigest()
      x["input"]["digest_case"]={"algorithm":"SHA-256","synthetic_bytes_utf8":payload.decode(),"expected_sha256":digest,"secret_data":False}
      if fid=="HNIF2-22":
        x["input"]["digest_case"]["mismatch_bytes_utf8"]="SYNTHETIC-HNI-V21-DIGEST-FIXTURE-X"
        x["input"]["digest_case"]["expected_mismatch_sha256"]=hashlib.sha256(b"SYNTHETIC-HNI-V21-DIGEST-FIXTURE-X").hexdigest()
    if fid=="HNIF2-21":
      x["input"]["event_ledger_expected"]=[
       {"seq":1,"event":"append","request_id":"req-17","append_count_after":1},
       {"seq":2,"event":"response_lost","request_id":"req-17","append_count_after":1},
       {"seq":3,"event":"retry_received","request_id":"req-17","append_count_after":1},
       {"seq":4,"event":"deduplicated","request_id":"req-17","append_count_after":1}
      ]
      x["assertions"].append({"assertion_id":fid+"-A04","kind":"idempotency","operator":"append_count_after_retry","expected":1,"failure_status":"FAIL","evidence_required":["ordered_mock_event_ledger","final_append_count"]})
    if fid=="HNIF2-13":
      x["input"]["state_snapshots"]={"before":{"balance":100,"marker_count":0,"record_R":"unchanged","state_version":7},"after":{"balance":100,"marker_count":0,"record_R":"unchanged","state_version":7}}
      x["input"]["authorization_trace"]={"approval_present":False,"mutation_method_called":False,"side_effect_count":0}
    if fid=="HNIF2-15":
      x["input"]["fault_cases"]=[
       {"case_id":"F-TRUNCATED-JSON","expected_diagnostic":"E_JSON_TRUNCATED","expected_state_version":7,"expected_side_effect_count":0},
       {"case_id":"F-INVALID-JSON","expected_diagnostic":"E_JSON_INVALID","expected_state_version":7,"expected_side_effect_count":0},
       {"case_id":"F-DUPLICATE-ID","expected_diagnostic":"E_DUPLICATE_FIXTURE_ID","expected_state_version":7,"expected_side_effect_count":0},
       {"case_id":"F-CURSOR-MISMATCH","expected_diagnostic":"E_CURSOR_MISMATCH","expected_state_version":7,"expected_side_effect_count":0},
       {"case_id":"F-MISSING-RECEIPT","expected_diagnostic":"E_RECEIPT_MISSING","expected_state_version":7,"expected_side_effect_count":0}
      ]
    if fid=="HNIF2-23":
      x["input"]["diagnostic_cases"]=[
       {"case_id":"M-INVALID-JSON","expected_diagnostic":"E_JSON_INVALID"},
       {"case_id":"M-DUPLICATE-ID","expected_diagnostic":"E_DUPLICATE_FIXTURE_ID"},
       {"case_id":"M-MISSING-LINKS","expected_diagnostic":"E_LINKED_TESTS_MISSING"},
       {"case_id":"M-UNKNOWN-TEST","expected_diagnostic":"E_UNKNOWN_TEST_ID"},
       {"case_id":"M-MISSING-ORACLE","expected_diagnostic":"E_ORACLE_MISSING"},
       {"case_id":"M-EXECUTION-PASS-IN-PREPARATION","expected_diagnostic":"E_INVALID_PREPARATION_STATUS"}
      ]
    out=dst/old.name
    out.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n")
    items.append({"fixture_id":fid,"file":out.name,"version":"2.1.0","linked_tests":x["linked_tests"],"expected_response_verdict":x["expected_response_verdict"],"execution_status":"NOT_RUN","classification":"SYNTHETIC_NON_PRODUCTION"})
oldm=json.loads((src/"manifest.json").read_text())
manifest={
 "schema_version":"hni.fixture-manifest.v2.1","artifact_id":"HG-NATIVE-INTELLIGENCE-FIXTURES-V2.1","version":"2.1.0",
 "status":"FIXTURE REVISION ONLY — NOT_RELEASED","classification":"SYNTHETIC_NON_PRODUCTION","oracle_contract_version":"hni.oracle-contract.v2.1",
 "supersedes":"V2 is preserved unchanged; V2.1 is a new revision",
 "oracle_fields":{"expected_response_verdict":"Expected verdict for a compliant response; not observed execution","execution_status":"NOT_RUN until actual authorized test execution","observed_status_enum":["PASS","FAIL","BLOCKED","NOT_RUN","INCONCLUSIVE"]},
 "suite_aggregation":{"preserve_all_findings":True,"critical_gate":"Any evidenced applicable C0 FAIL => suite FAIL regardless of aggregate score or other missing results","then_order":["BLOCKED if required prerequisite absent and no proven FAIL","INCONCLUSIVE if executed evidence cannot decide","NOT_RUN if required test has no execution record","PASS only when all required tests and evidence pass"]},
 "na_policy":"N/A requires rationale, approver, scope, evidence and denominator accounting; otherwise BLOCKED and remains in denominator",
 "oracle_freeze":"Post-hoc change requires new version, rationale, diff and authorized review",
 "safety":{"real_secrets_included":False,"production_data_included":False,"live_mutation":False,"network_required":False,"digests_calculated":False},
 "coverage":{"hnit_required":oldm["coverage"]["hnit_required"],"xn_required":oldm["coverage"]["xn_required"]},
 "fixtures":items,"total_fixtures":len(items),"test_execution":"NOT_RUN","release_status":"NOT_RELEASED"
}
(dst/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
print("GENERATED V2.1",len(items),"fixtures + manifest")
