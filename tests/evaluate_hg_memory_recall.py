"""Fixed synthetic oracle for lexical memory retrieval; standard library only."""
from __future__ import annotations
import hashlib, json, sys, tempfile, unicodedata
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from hg.history import StateStore
from hg.memory import MemoryStore
FIXTURE = ROOT / "tests/fixtures/hg_memory_recall_oracle_v1.json"


def main():
    oracle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="hg-memory-oracle-") as td:
        store = MemoryStore(StateStore(td))
        for doc in oracle["documents"]:
            store.remember(
                {k: doc[k] for k in ("id", "title", "content", "scope_id")},
                principal_id="oracle-fixture",
                grants={doc["scope_id"]},
                idempotency_key="oracle:" + doc["id"],
            )
        cases = []
        tp_total = fp_total = fn_total = 0
        reciprocal = []
        all_pass = True
        for case in oracle["cases"]:
            result = store.retrieve(case["query"], grants=set(case["grants"]), limit=50)
            got = [r["id"] for r in result["matches"]]
            relevant = set(case["relevant"])
            allowed = {d["id"] for d in oracle["documents"] if d["scope_id"] in set(case["grants"])}
            tp = len(set(got) & relevant)
            fp = len(set(got) - relevant)
            fn = len(relevant - set(got))
            tp_total += tp
            fp_total += fp
            fn_total += fn
            rank = next((i + 1 for i, value in enumerate(got) if value in relevant), None)
            if rank:
                reciprocal.append(1 / rank)
            forbidden = sorted(set(got) - allowed)
            if case["kind"] in ("acl_leakage_negative", "negative_false_positive", "no_match"):
                passed = not got and not forbidden
            elif case["id"] in oracle["acceptance"]["expected_retrievable"]:
                passed = bool(set(got) & relevant) and not forbidden
            else:
                passed = not forbidden
            all_pass = all_pass and passed
            cases.append({
                "id": case["id"], "kind": case["kind"], "query": case["query"],
                "relevant_ids": sorted(relevant), "retrieved_ids": got,
                "true_positives": tp, "false_positives": fp, "false_negatives": fn,
                "first_relevant_rank": rank, "forbidden_ids": forbidden,
                "case_pass": passed, "query_id": result["query_id"],
                "manifest_sha256": result["manifest"]["manifest_sha256"],
            })
        query = "Cơ chế ghi nhớ phải truy hồi thông tin"
        composed = store.retrieve(query, grants={"owner"}, limit=50)
        decomposed = store.retrieve(unicodedata.normalize("NFD", query), grants={"owner"}, limit=50)
        unicode_equal = [r["id"] for r in composed["matches"]] == [r["id"] for r in decomposed["matches"]]
        reopened = MemoryStore(StateStore(td))
        replay_ok = reopened.get("mem-project-canonical", grants={"owner"}) == store.get(
            "mem-project-canonical", grants={"owner"})
        expected_ids = set(oracle["acceptance"]["expected_retrievable"])
        expected_hits_ok = all(
            bool(set(case["retrieved_ids"]) & set(case["relevant_ids"]))
            for case in cases if case["id"] in expected_ids
        )
        no_acl_leaks = not any(case["forbidden_ids"] for case in cases)
        precision = tp_total / (tp_total + fp_total) if tp_total + fp_total else 1.0
        recall = tp_total / (tp_total + fn_total) if tp_total + fn_total else 1.0
        report = {
            "schema_version": "hg.memory-recall-evaluation.v1",
            "oracle_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            "python": sys.version, "cases_total": len(cases),
            "cases_passed": sum(c["case_pass"] for c in cases),
            "cases_failed": sum(not c["case_pass"] for c in cases),
            "micro_precision": round(precision, 6),
            "micro_recall": round(recall, 6),
            "expected_retrieval_cases_pass": expected_hits_ok,
            "acl_isolation_pass": no_acl_leaks,
            "precision_gate_pass": precision >= 0.95,
            "recall_gate_pass": recall >= 0.95,
            "mrr_over_retrieved_relevant_cases": round(sum(reciprocal) / len(reciprocal), 6) if reciprocal else 0,
            "unicode_composed_decomposed_same_results": unicode_equal,
            "restart_replay_same_record": replay_ok,
            "acl_leakage_ids_observed": sorted({item for c in cases for item in c["forbidden_ids"]}),
            "semantic_recall_claim": False,
            "all_pass": all_pass and unicode_equal and replay_ok and expected_hits_ok and no_acl_leaks and precision >= 0.95 and recall >= 0.95,
            "cases": cases,
        }
        output = ROOT / "evidence/HG2-MEMORY-ANTI-FORGETTING-20261019"
        output.mkdir(parents=True, exist_ok=True)
        (output / "recall-evaluation.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
