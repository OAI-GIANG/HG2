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
