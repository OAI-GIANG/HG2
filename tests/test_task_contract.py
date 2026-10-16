"""Adversarial P0 tests for HG Task Contract and pure Task Compiler.

Oracles assert public status/error codes and expected graph properties; test inputs are
constructed independently from the compiler output. No runtime/authority adapter is used.
"""
from __future__ import annotations

import copy
import hashlib
import json
import unittest

from hg.task_contract import (
    ContractError, SCHEMA_VERSION, canonical_json, contract_digest, parse_json_strict,
    validate_contract,
)
from hg.task_compiler import CompileError, compile_contract, compile_task_graph, dependency_gate


def make_contract(task_id: str = "task:A", dependencies: list[dict] | None = None) -> dict:
    value = {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "objective": "Validate a bounded declaration without executing it.",
        "scope": {"include": ["contract.validation"], "exclude": ["shell.exec"]},
        "input": [],
        "output": [{"output_id": f"out:{task_id}", "media_type": "application/json",
                    "description": "Validated compiler result", "validation_rule_refs": ["rule:json"]}],
        "acceptance_criteria": [{
            "criterion_id": f"crit:{task_id}", "description": "Contract accepted by independent schema oracle",
            "severity": "P0", "oracle_ref": "oracle:g1-contract-schema-v1", "required": True,
        }],
        "evidence_requirements": [{
            "requirement_id": f"ev:{task_id}", "evidence_type": "unit-test-result",
            "source_policy": "local-test-harness", "integrity_policy": "bind-to-exact-source-sha",
            "required": True,
        }],
        "risks": [],
        "stop_conditions": [{
            "condition_id": f"stop:{task_id}", "predicate_ref": "predicate:invalid-or-unauthorized",
            "reason_code": "BLOCKED", "minimum_status": "BLOCKED",
        }],
        "next_action": {
            "action_id": f"next:{task_id}", "description": "Wait for authorized orchestration",
            "preconditions": ["all-p0-pass"], "on_blocked": "stop-and-preserve-evidence",
        },
        "dependencies": copy.deepcopy(dependencies or []),
        "required_capabilities": [],
        "authorization_requirement": {
            "policy_ref": "policy:HG_AUTHORITY_V1", "action": "health.read",
            "approval_required": False, "scope_ref": "scope:read-only-test",
        },
        "created_at": "2026-10-17T10:00:00+00:00",
        "created_by": "test-harness",
        "approval_ref": None,
    }
    value["contract_digest"] = contract_digest(value)
    return value


def dep(task_id: str, required_status: str = "PASS") -> dict:
    return {
        "dependency_task_id": task_id,
        "required_terminal_status": required_status,
        "dependency_kind": "HARD",
    }


class StrictJsonTests(unittest.TestCase):
    def test_duplicate_keys_rejected(self):
        with self.assertRaises(ContractError) as ctx:
            parse_json_strict('{"task_id":"A","task_id":"B"}')
        self.assertEqual(ctx.exception.code, "CONTRACT_INVALID_JSON")

    def test_nan_rejected(self):
        with self.assertRaises(ContractError) as ctx:
            parse_json_strict('{"x":NaN}')
        self.assertEqual(ctx.exception.code, "CONTRACT_INVALID_JSON")

    def test_non_object_rejected(self):
        with self.assertRaises(ContractError) as ctx:
            parse_json_strict("[]")
        self.assertEqual(ctx.exception.code, "CONTRACT_SCHEMA_INVALID")

    def test_too_large_rejected(self):
        from hg.task_contract import MAX_CONTRACT_BYTES
        with self.assertRaises(ContractError) as ctx:
            parse_json_strict(b" " * (MAX_CONTRACT_BYTES + 1))
        self.assertEqual(ctx.exception.code, "CONTRACT_RESOURCE_LIMIT")


class ContractP0Tests(unittest.TestCase):
    def test_minimal_complete_contract_validates(self):
        value = make_contract()
        self.assertEqual(validate_contract(value)["task_id"], "task:A")

    def test_p001_missing_objective_fails_closed(self):
        value = make_contract()
        value.pop("objective")
        with self.assertRaises(ContractError) as ctx:
            validate_contract(value, check_digest=False)
        self.assertEqual(ctx.exception.code, "CONTRACT_REQUIRED_FIELD_MISSING")

    def test_p003_missing_acceptance_oracle_fails(self):
        value = make_contract()
        value["acceptance_criteria"] = []
        value["contract_digest"] = contract_digest(value)
        with self.assertRaises(ContractError) as ctx:
            validate_contract(value)
        self.assertEqual(ctx.exception.code, "CONTRACT_REQUIRED_FIELD_MISSING")

    def test_p004_missing_evidence_requirement_fails(self):
        value = make_contract()
        value["evidence_requirements"] = []
        value["contract_digest"] = contract_digest(value)
        with self.assertRaises(ContractError) as ctx:
            validate_contract(value)
        self.assertEqual(ctx.exception.code, "CONTRACT_REQUIRED_FIELD_MISSING")

    def test_unknown_field_fails(self):
        value = make_contract()
        value["surprise"] = True
        value["contract_digest"] = contract_digest(value)
        with self.assertRaises(ContractError) as ctx:
            validate_contract(value)
        self.assertEqual(ctx.exception.code, "CONTRACT_SCHEMA_INVALID")

    def test_wrong_boolean_type_not_coerced(self):
        value = make_contract()
        value["acceptance_criteria"][0]["required"] = "true"
        value["contract_digest"] = contract_digest(value)
        with self.assertRaises(ContractError) as ctx:
            validate_contract(value)
        self.assertEqual(ctx.exception.code, "CONTRACT_SCHEMA_INVALID")

    def test_nested_required_boolean_wrong_type_rejected(self):
        value = make_contract()
        value["evidence_requirements"][0]["required"] = 1
        value["contract_digest"] = contract_digest(value)
        with self.assertRaises(ContractError) as ctx:
            validate_contract(value)
        self.assertEqual(ctx.exception.code, "CONTRACT_SCHEMA_INVALID")

    def test_duplicate_nested_ids_rejected(self):
        value = make_contract()
        duplicate = dict(value["output"][0])
        value["output"].append(duplicate)
        value["contract_digest"] = contract_digest(value)
        with self.assertRaises(ContractError) as ctx:
            validate_contract(value)
        self.assertEqual(ctx.exception.code, "CONTRACT_DUPLICATE_ID")

    def test_bad_digest_shape_rejected_before_compare(self):
        value = make_contract()
        value["contract_digest"] = "not-a-digest"
        with self.assertRaises(ContractError) as ctx:
            validate_contract(value)
        self.assertEqual(ctx.exception.code, "CONTRACT_SCHEMA_INVALID")

    def test_digest_mismatch_rejected(self):
        value = make_contract()
        value["objective"] = "changed after digest"
        with self.assertRaises(ContractError) as ctx:
            validate_contract(value)
        self.assertEqual(ctx.exception.code, "CONTRACT_DIGEST_MISMATCH")

    def test_include_exclude_overlap_rejected(self):
        value = make_contract()
        value["scope"]["exclude"].append("contract.validation")
        value["contract_digest"] = contract_digest(value)
        with self.assertRaises(ContractError) as ctx:
            validate_contract(value)
        self.assertEqual(ctx.exception.code, "CONTRACT_SCOPE_INVALID")

    def test_naive_timestamp_rejected(self):
        value = make_contract()
        value["created_at"] = "2026-10-17T10:00:00"
        value["contract_digest"] = contract_digest(value)
        with self.assertRaises(ContractError) as ctx:
            validate_contract(value)
        self.assertEqual(ctx.exception.code, "CONTRACT_SCHEMA_INVALID")

    def test_explicitly_forbidden_action_rejected(self):
        value = make_contract()
        value["authorization_requirement"]["action"] = "shell.exec"
        value["contract_digest"] = contract_digest(value)
        with self.assertRaises(ContractError) as ctx:
            validate_contract(value)
        self.assertEqual(ctx.exception.code, "AUTHORIZATION_DENIED")

    def test_approval_required_without_reference_rejected(self):
        value = make_contract()
        value["authorization_requirement"]["approval_required"] = True
        value["contract_digest"] = contract_digest(value)
        with self.assertRaises(ContractError) as ctx:
            validate_contract(value)
        self.assertEqual(ctx.exception.code, "APPROVAL_REQUIRED")

    def test_same_semantic_contract_stable_digest(self):
        value = make_contract()
        raw = json.dumps(value, ensure_ascii=False)
        parsed = parse_json_strict(raw)
        self.assertEqual(contract_digest(value), contract_digest(parsed))

    def test_compiler_never_marks_executable(self):
        plan = compile_contract(make_contract())
        self.assertEqual(plan["state"], "VALIDATED")
        self.assertIs(plan["executable"], False)

    def test_capability_reference_does_not_imply_capability_exists(self):
        value = make_contract()
        value["required_capabilities"] = [{
            "capability_id": "network.fetch", "contract_version": "v1", "required": True,
        }]
        value["contract_digest"] = contract_digest(value)
        plan = compile_contract(value)
        self.assertIn("capability_registry", plan["unresolved_prerequisites"])
        self.assertIs(plan["executable"], False)

    def test_approval_reference_does_not_imply_approval_verified(self):
        value = make_contract()
        value["approval_ref"] = "approval:external-123"
        value["authorization_requirement"]["approval_required"] = True
        value["contract_digest"] = contract_digest(value)
        plan = compile_contract(value)
        self.assertIn("approval_verifier", plan["unresolved_prerequisites"])
        self.assertIs(plan["executable"], False)


class DependencyGraphP0Tests(unittest.TestCase):
    def test_p013_acyclic_graph_topological_order_respects_edges(self):
        a = make_contract("A")
        b = make_contract("B", [dep("A")])
        c = make_contract("C", [dep("B")])
        result = compile_task_graph([c, a, b])
        order = result["topological_order"]
        self.assertLess(order.index("A"), order.index("B"))
        self.assertLess(order.index("B"), order.index("C"))

    def test_p014_cycle_rejected(self):
        a = make_contract("A", [dep("B")])
        b = make_contract("B", [dep("A")])
        with self.assertRaises(CompileError) as ctx:
            compile_task_graph([a, b])
        self.assertEqual(ctx.exception.code, "DEPENDENCY_CYCLE")

    def test_p015_self_cycle_rejected(self):
        a = make_contract("A", [dep("A")])
        with self.assertRaises(CompileError) as ctx:
            compile_task_graph([a])
        self.assertEqual(ctx.exception.code, "DEPENDENCY_CYCLE")

    def test_p016_unknown_dependency_rejected(self):
        a = make_contract("A", [dep("MISSING")])
        with self.assertRaises(CompileError) as ctx:
            compile_task_graph([a])
        self.assertEqual(ctx.exception.code, "DEPENDENCY_UNRESOLVED")

    def test_p017_duplicate_task_ids_rejected(self):
        with self.assertRaises(CompileError) as ctx:
            compile_task_graph([make_contract("A"), make_contract("A")])
        self.assertEqual(ctx.exception.code, "CONTRACT_DUPLICATE_ID")

    def test_p018_topological_tie_break_is_deterministic(self):
        tasks = [make_contract("Z"), make_contract("B"), make_contract("A"), make_contract("C", [dep("Z")])]
        expected = compile_task_graph(tasks)["topological_order"]
        for _ in range(5):
            self.assertEqual(compile_task_graph(list(reversed(tasks)))["topological_order"], expected)
        self.assertEqual(expected, ["A", "B", "Z", "C"])

    def test_p021_shared_dependency_preserved_as_single_node(self):
        tasks = [make_contract("A"), make_contract("B", [dep("A")]), make_contract("C", [dep("A")])]
        graph = compile_task_graph(tasks)
        self.assertEqual(graph["topological_order"].count("A"), 1)
        self.assertIn(["A", "B"], graph["edges"])
        self.assertIn(["A", "C"], graph["edges"])

    def test_p022_task_limit(self):
        from hg.task_compiler import MAX_TASKS
        # Exceed limit before any task-level work; input values are intentionally empty.
        with self.assertRaises(CompileError) as ctx:
            compile_task_graph([{}] * (MAX_TASKS + 1))
        self.assertEqual(ctx.exception.code, "CONTRACT_RESOURCE_LIMIT")

    def test_dependency_status_gate_is_fail_closed(self):
        dependent = make_contract("B", [dep("A", "PASS")])
        blocked = dependency_gate(dependent, {"A": "BLOCKED"})
        self.assertFalse(blocked["ready"])
        self.assertIs(blocked["executable"], False)
        self.assertEqual(blocked["state"], "BLOCKED")
        not_run = dependency_gate(dependent, {})
        self.assertFalse(not_run["ready"])
        passed = dependency_gate(dependent, {"A": "PASS"})
        self.assertTrue(passed["ready"])
        self.assertIs(passed["executable"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
