"""Architecture boundary tests for the circulatory restructuring baseline."""
from pathlib import Path
import ast
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hg"
CONTRACT = ROOT / "contract" / "CIRCULATORY_ARCHITECTURE_V1.md"
MODULE_MAP = ROOT / "docs" / "HG2_CIRCULATORY_MODULE_MAP_V1.md"
ROADMAP = ROOT / "docs" / "HG2_CIRCULATORY_RESTRUCTURE_ROADMAP_V1.md"
MANIFEST = ROOT / "manifest.json"


class CirculatoryArchitectureTests(unittest.TestCase):
    def test_architecture_documents_are_present_and_explicitly_not_certified(self):
        self.assertTrue(CONTRACT.is_file())
        self.assertTrue(MODULE_MAP.is_file())
        self.assertTrue(ROADMAP.is_file())
        contract = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("DESIGN BASELINE", contract)
        self.assertIn("implementation not yet certified", contract)
        self.assertIn("No gate is passed by documentation alone", contract)

    def test_manifest_declares_one_brain_command_root_and_subordinate_layers(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        brain = manifest["architecture"]["unified_brain_group"]
        self.assertEqual(brain["command_root"], "hg.agent.HGAgent")
        self.assertEqual(brain["subordinate_turn_router"], "hg.toolplane.ToolPlane")
        self.assertEqual(brain["authorization_owner"], "hg.policy")
        self.assertEqual(brain["durable_state_owner"], "hg.phone_runtime.PhoneRuntime")
        self.assertEqual(brain["provider_boundary"], "hg.provider")
        self.assertEqual(brain["production_status"], "NOT_RELEASED")

    def test_manifest_registers_policy_contract_workflow_sync_state_migration_and_recovery(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for module in ("hg.policy", "hg.contracts", "hg.sqlite_state", "hg.migration", "hg.recovery", "hg.workflow", "hg.sync"):
            self.assertIn(module, manifest["modules"])
        self.assertEqual(manifest["architecture"]["status"], "DESIGN_BASELINE_NOT_CERTIFIED")

    def test_phone_is_the_only_runtime_composition_root_for_state_store(self):
        users = []
        for path in SOURCE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == "StateStore":
                    users.append(path.name)
                    break
                if isinstance(node, ast.Attribute) and node.attr == "StateStore":
                    users.append(path.name)
                    break
        self.assertEqual(sorted(set(users)), ["phone_runtime.py"])

    def test_code_intelligence_is_dev_only_and_uses_shared_canonicalization(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertNotIn("tools.hg_code_intelligence", manifest["modules"])
        analyser = (ROOT / "tools" / "hg_code_intelligence.py").read_text(encoding="utf-8")
        self.assertIn("from hg.contracts import canonical_digest, canonical_json", analyser)
        self.assertIn("return canonical_json(value, max_bytes=4 * DEFAULT_MAX_TOTAL_BYTES).encode", analyser)
        self.assertIn("snapshot_sha = canonical_digest(snapshot_material, max_bytes=4 * DEFAULT_MAX_TOTAL_BYTES)", analyser)
        self.assertNotIn("json.dumps(value, sort_keys=True", analyser)

    def test_agent_stack_is_registered_with_one_provider_boundary(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for module in ("hg.auth", "hg.provider", "hg.toolplane", "hg.agent"):
            self.assertIn(module, manifest["modules"])
        provider_modules = [name for name in manifest["modules"]
                            if name.rsplit(".", 1)[-1] in {"provider", "model_gateway", "model_provider"}]
        self.assertEqual(provider_modules, ["hg.provider"])

    def test_authority_module_is_only_a_compatibility_facade(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertNotIn("hg.authority", manifest["modules"])
        self.assertEqual(
            manifest.get("compatibility_facades", {}).get("hg.authority"),
            "hg.policy (legacy import path only; no policy logic)",
        )
        for path in SOURCE.glob("*.py"):
            if path.name == "authority.py":
                continue
            self.assertNotIn("from .authority import", path.read_text(encoding="utf-8"), path.name)

    def test_json_parser_and_digest_are_not_reimplemented_by_provider_or_toolplane(self):
        provider = (SOURCE / "provider.py").read_text(encoding="utf-8")
        toolplane = (SOURCE / "toolplane.py").read_text(encoding="utf-8")
        self.assertNotIn("def _no_duplicate_json_keys", provider)
        self.assertNotIn("def _reject_json_constant", provider)
        self.assertNotIn("def _no_duplicate_keys", toolplane)
        self.assertNotIn("def _reject_json_constant", toolplane)
        self.assertIn("parse_json_no_duplicate_keys", provider)
        self.assertIn("parse_json_no_duplicate_keys", toolplane)
        self.assertIn("canonical_digest", toolplane)
        self.assertIn("canonical_json", provider)

    def test_toolplane_routes_session_creation_through_runtime(self):
        source = (SOURCE / "toolplane.py").read_text(encoding="utf-8")
        self.assertNotIn('self.store.emit("session.created"', source)
        self.assertIn('self.runtime.start_session(principal=principal, correlation_id=correlation_id)', source)
        self.assertIn('authorize_principal("provider.invoke", principal)', source)

    def test_workflow_and_approval_mutations_call_the_single_policy_guard(self):
        policy = (SOURCE / "policy.py").read_text(encoding="utf-8")
        workflow = (SOURCE / "workflow.py").read_text(encoding="utf-8")
        agent = (SOURCE / "agent.py").read_text(encoding="utf-8")
        self.assertIn("def authorize_service_mutation", policy)
        self.assertIn('authorize_service_mutation("workflow.task.create", self.principal)', workflow)
        self.assertIn('authorize_service_mutation("workflow.task.transition", self.principal)', workflow)
        self.assertIn('authorize_service_mutation("policy.approval.request", self.principal)', policy)
        self.assertIn('authorize_service_mutation("policy.approval.vote", self.principal)', policy)
        self.assertIn('authorize_service_mutation("brain.request", principal)', agent)

    def test_all_literal_domain_event_emits_carry_single_use_mutation_permit(self):
        guarded = {
            "session.created", "workflow.task.created", "workflow.task.transitioned",
            "policy.approval.created", "policy.approval.decided",
        }
        found = []
        for path in SOURCE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "emit":
                    continue
                if not node.args or not isinstance(node.args[0], ast.Constant) or node.args[0].value not in guarded:
                    continue
                event_type = node.args[0].value
                self.assertIn("mutation_permit", {kw.arg for kw in node.keywords}, f"{path}:{node.lineno} {event_type}")
                found.append(event_type)
        self.assertEqual(set(found), guarded)

    def test_all_store_event_emits_require_a_policy_permit_except_bootstrap_genesis(self):
        for path in SOURCE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "emit":
                    continue
                is_bootstrap = (
                    path.name == "history.py" and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "self" and node.args
                    and isinstance(node.args[0], ast.Name) and node.args[0].id == "GENESIS_EVENT"
                )
                if is_bootstrap:
                    continue
                self.assertIn("mutation_permit", {kw.arg for kw in node.keywords}, f"{path}:{node.lineno}")

    def test_state_store_mutation_ports_enforce_the_single_policy_guard(self):
        policy = (SOURCE / "policy.py").read_text(encoding="utf-8")
        history = (SOURCE / "history.py").read_text(encoding="utf-8")
        sqlite = (SOURCE / "sqlite_state.py").read_text(encoding="utf-8")
        sync = (SOURCE / "sync.py").read_text(encoding="utf-8")
        migration = (SOURCE / "migration.py").read_text(encoding="utf-8")
        recovery = (SOURCE / "recovery.py").read_text(encoding="utf-8")
        self.assertIn("def issue_mutation_permit", policy)
        self.assertIn("def consume_mutation_permit", policy)
        self.assertIn("consume_mutation_permit(", history)
        self.assertIn("consume_mutation_permit(", sqlite)
        for method in ("record_outbox_attempt", "acknowledge_outbox", "import_verified_events"):
            start = sqlite.index("def " + method)
            self.assertIn("consume_mutation_permit(", sqlite[start:start + 4500], method)
        self.assertIn('authorize_service_mutation("state.migration.import", principal)', migration)
        self.assertIn('authorize_service_mutation(action, principal)', recovery)
        self.assertIn('for action in ("sync.outbox.attempt", "sync.outbox.acknowledge")', sync)

    def test_only_hgagent_composes_the_runtime_toolplane(self):
        toolplane_importers = set()
        toolplane_constructors = set()
        for path in SOURCE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == "toolplane":
                    if any(alias.name == "ToolPlane" for alias in node.names):
                        toolplane_importers.add(path.name)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ToolPlane":
                    toolplane_constructors.add(path.name)
        self.assertEqual(toolplane_importers, {"agent.py"})
        self.assertEqual(toolplane_constructors, {"agent.py"})

    def test_toolplane_is_a_brain_subordinate_not_an_alternate_goal_entry(self):
        agent = (SOURCE / "agent.py").read_text(encoding="utf-8")
        toolplane = (SOURCE / "toolplane.py").read_text(encoding="utf-8")
        self.assertEqual(agent.count("ToolPlane("), 1)
        self.assertIn('authorize_service_mutation("brain.request", principal)', agent)
        self.assertIn('authorize_service_mutation("brain.request", principal)', toolplane)

    def test_brain_request_and_result_contracts_are_versioned(self):
        contracts = (SOURCE / "contracts.py").read_text(encoding="utf-8")
        agent = (SOURCE / "agent.py").read_text(encoding="utf-8")
        self.assertIn("BRAIN_REQUEST_V1", contracts)
        self.assertIn("BRAIN_REQUEST_AUDIT_V1", contracts)
        self.assertIn("validate_brain_request_audit", agent)
        self.assertIn("CAPABILITY_RESULT_V1", contracts)
        self.assertIn("validate_brain_request", agent)
        self.assertIn("validate_capability_result", agent)
        self.assertIn('expected_request_id=request_id', agent)
        self.assertIn('expected_correlation_id=correlation_id', agent)
        self.assertIn('"brain.request.accepted"', agent)
        self.assertIn('"brain.request.completed"', agent)
        self.assertIn("CAPABILITY_SUCCESS_SOURCE_REVISION_UNATTESTED", contracts)

    def test_edge_relay_does_not_import_canonical_state_store(self):
        tree = ast.parse((SOURCE / "edge.py").read_text(encoding="utf-8"), filename="edge.py")
        imported = []
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                modules.append(node.module)
                imported.extend(alias.name for alias in node.names)
        self.assertNotIn("StateStore", imported)
        self.assertNotIn("hg.history", modules)
        self.assertNotIn(".history", modules)

    def test_only_history_module_writes_legacy_persistence_files(self):
        protected_names = ("history.jsonl", "head.json", "state.json")
        writers = set()
        for path in SOURCE.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            if not any(name in source for name in protected_names):
                continue
            tree = ast.parse(source, filename=str(path))
            writes_files = any(
                isinstance(node, ast.Call) and (
                    (
                        isinstance(node.func, ast.Name)
                        and node.func.id == "open"
                        and len(node.args) > 1
                        and isinstance(node.args[1], ast.Constant)
                        and isinstance(node.args[1].value, str)
                        and any(mode in node.args[1].value for mode in ("w", "a", "x", "+"))
                    )
                    or (isinstance(node.func, ast.Attribute) and node.func.attr in {"replace", "fsync"})
                )
                for node in ast.walk(tree)
            )
            if writes_files:
                writers.add(path.name)
        self.assertEqual(writers, {"history.py"})

    def test_remote_roles_cannot_be_promoted_by_implicit_failover(self):
        contract = CONTRACT.read_text(encoding="utf-8").lower()
        self.assertIn("never a second primary", contract)
        self.assertIn("no second runtime may independently advance canonical history", contract)
        self.assertIn("explicit promotion protocol", contract)

    def test_restructure_has_staged_work_packages(self):
        roadmap = ROADMAP.read_text(encoding="utf-8")
        for marker in ("WP0", "WP1", "WP2", "WP3", "WP4", "WP5", "WP6", "WP7", "WP8", "WP9"):
            self.assertIn(marker, roadmap)


if __name__ == "__main__":
    unittest.main()
