import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.hg_code_intelligence import (
    CodeIntelligenceError,
    ResourceLimitError,
    compare_staleness,
    index_repository,
)


class CodeIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def put(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_builds_python_import_graph_and_hashes_without_source_text(self):
        self.put("pkg/__init__.py", "")
        self.put("pkg/core.py", "VALUE = 7\n")
        self.put("app.py", "from pkg.core import VALUE\n")
        report = index_repository(self.root, source_revision="test-commit")
        self.assertEqual(report["schema"], "HG_CODE_INTELLIGENCE_V1")
        self.assertTrue(any(e["source_path"] == "app.py" and e["target_path"] == "pkg/core.py" for e in report["edges"]))
        self.assertEqual(report["coverage"]["python_files_parsed"], 3)
        self.assertNotIn("VALUE = 7", json.dumps(report))
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertEqual(len(report["snapshot_sha256"]), 64)
        self.assertEqual(len(report["report_sha256"]), 64)

    def test_impact_returns_known_reverse_dependents(self):
        self.put("pkg/core.py", "VALUE = 7\n")
        self.put("app.py", "from pkg.core import VALUE\n")
        self.put("entry.py", "import app\n")
        report = index_repository(self.root, source_revision="rev-1", changed_paths=["pkg/core.py"])
        self.assertEqual(report["impact"]["known_impacted_dependents"], ["app.py", "entry.py"])
        self.assertEqual(report["impact"]["status"], "KNOWN_LOCAL_PYTHON_DEPENDENTS")

    def test_non_python_source_marks_impact_incomplete_and_changes_snapshot(self):
        self.put("pkg/core.py", "VALUE = 1\n")
        non_python = self.put("ui/client.ts", "export const value = 1;\n")
        first = index_repository(self.root, source_revision="rev-1", changed_paths=["pkg/core.py"])
        self.assertEqual(first["coverage"]["unsupported_source_files"], 1)
        self.assertFalse(first["coverage"]["coverage_complete_for_all_repository_source"])
        self.assertEqual(first["impact"]["status"], "KNOWN_DEPENDENTS_ONLY_INCOMPLETE_COVERAGE")
        record = next(item for item in first["files"] if item["path"] == "ui/client.ts")
        self.assertEqual(record["status"], "UNSUPPORTED_LANGUAGE")
        self.assertEqual(len(record["sha256"]), 64)
        non_python.write_text("export const value = 2;\\n", encoding="utf-8")
        second = index_repository(self.root, source_revision="rev-1", changed_paths=["pkg/core.py"])
        self.assertNotEqual(first["snapshot_sha256"], second["snapshot_sha256"])
        self.assertEqual(compare_staleness(first, second)["status"], "STALE")

    def test_syntax_error_is_disclosed_and_reduces_coverage(self):
        self.put("broken.py", "def broken(:\n    pass\n")
        report = index_repository(self.root, source_revision="rev")
        self.assertEqual(report["coverage"]["python_files_parse_failed"], 1)
        self.assertFalse(report["coverage"]["coverage_complete_for_all_repository_source"])
        record = next(item for item in report["files"] if item["path"] == "broken.py")
        self.assertEqual(record["status"], "PARSE_ERROR_SYNTAX")

    def test_secret_files_are_not_enumerated_or_hashed(self):
        self.put("app.py", "VALUE = 1\n")
        self.put(".env", "TOKEN=do-not-leak\n")
        self.put("credentials.json", '{"secret":"do-not-leak"}')
        self.put("keys/private.pem", "PRIVATE KEY MATERIAL")
        report = index_repository(self.root, source_revision="rev")
        serialized = json.dumps(report)
        self.assertEqual(report["coverage"]["secret_files_excluded_count"], 3)
        self.assertNotIn("do-not-leak", serialized)
        self.assertNotIn("private.pem", serialized)
        self.assertNotIn("credentials.json", serialized)

    def test_symlinks_are_not_followed(self):
        outside = Path(self.temp.name) / "outside.py"
        outside.write_text("SECRET_FROM_OUTSIDE = True\n", encoding="utf-8")
        (self.root / "link.py").symlink_to(outside)
        report = index_repository(self.root, source_revision="rev")
        self.assertEqual(report["coverage"]["symlink_entries_excluded_count"], 1)
        self.assertFalse(any(rec["path"] == "link.py" for rec in report["files"]))

    def test_file_count_limit_fails_without_partial_report(self):
        self.put("a.py", "A=1\n")
        self.put("b.py", "B=2\n")
        with self.assertRaisesRegex(ResourceLimitError, "MAX_FILES_EXCEEDED"):
            index_repository(self.root, source_revision="rev", max_files=1)

    def test_total_byte_limit_fails_without_partial_report(self):
        self.put("a.py", "A='1234567890'\n")
        with self.assertRaisesRegex(ResourceLimitError, "MAX_TOTAL_SOURCE_BYTES_EXCEEDED"):
            index_repository(self.root, source_revision="rev", max_total_bytes=4)

    def test_oversize_python_file_is_disclosed(self):
        self.put("large.py", "A='1234567890'\n")
        report = index_repository(self.root, source_revision="rev", max_file_bytes=4)
        self.assertEqual(report["coverage"]["python_files_skipped_file_size"], 1)
        self.assertFalse(report["coverage"]["coverage_complete_for_all_repository_source"])

    def test_changed_path_escape_is_rejected(self):
        self.put("a.py", "A=1\n")
        with self.assertRaisesRegex(CodeIntelligenceError, "CHANGED_PATH_OUTSIDE_ROOT"):
            index_repository(self.root, source_revision="rev", changed_paths=["../outside.py"])

    def test_missing_changed_path_is_unresolved(self):
        self.put("a.py", "A=1\n")
        report = index_repository(self.root, source_revision="rev", changed_paths=["missing.py"])
        self.assertEqual(report["impact"]["status"], "UNRESOLVED_CHANGED_PATH")
        self.assertEqual(report["impact"]["missing_or_unparsed_changed_paths"], ["missing.py"])

    def test_reproducible_snapshot_and_staleness_detection(self):
        self.put("a.py", "A=1\n")
        first = index_repository(self.root, source_revision="rev-1")
        same = index_repository(self.root, source_revision="rev-1")
        self.assertEqual(first["snapshot_sha256"], same["snapshot_sha256"])
        self.assertEqual(first["report_sha256"], same["report_sha256"])
        self.assertEqual(compare_staleness(first, same)["status"], "CURRENT_BY_DECLARED_IDENTITIES")
        self.put("a.py", "A=2\n")
        updated = index_repository(self.root, source_revision="rev-1")
        self.assertEqual(compare_staleness(first, updated)["status"], "STALE")
        self.assertIn("SOURCE_SNAPSHOT_CHANGED", compare_staleness(first, updated)["reasons"])
        different_revision = index_repository(self.root, source_revision="rev-2")
        self.assertIn("SOURCE_REVISION_CHANGED", compare_staleness(updated, different_revision)["reasons"])

    def test_dynamic_import_marks_impact_incomplete(self):
        self.put("a.py", "import importlib\nmodule = importlib.import_module('b')\n")
        self.put("b.py", "VALUE = 1\n")
        report = index_repository(self.root, source_revision="rev", changed_paths=["b.py"])
        self.assertGreaterEqual(report["coverage"]["dynamic_import_sites"], 1)
        self.assertEqual(report["impact"]["status"], "KNOWN_DEPENDENTS_ONLY_INCOMPLETE_COVERAGE")

    def test_dynamic_import_alias_marks_impact_incomplete(self):
        self.put("a.py", "from importlib import import_module as load\nmodule = load('b')\n")
        self.put("b.py", "VALUE = 1\n")
        report = index_repository(self.root, source_revision="rev", changed_paths=["b.py"])
        self.assertGreaterEqual(report["coverage"]["dynamic_import_sites"], 1)
        self.assertEqual(report["impact"]["status"], "KNOWN_DEPENDENTS_ONLY_INCOMPLETE_COVERAGE")

    def test_dotfile_changed_path_is_not_mangled(self):
        self.put("app.py", "VALUE = 1\n")
        report = index_repository(self.root, source_revision="rev", changed_paths=["./.env"])
        self.assertEqual(report["impact"]["missing_or_unparsed_changed_paths"], [".env"])

    def test_indexing_does_not_execute_repository_code(self):
        marker = Path(self.temp.name) / "executed.marker"
        payload = (
            "from pathlib import Path\n"
            "Path(" + repr(str(marker)) + ").write_text('bad', encoding='utf-8')\n"
        )
        self.put("dangerous.py", payload)
        report = index_repository(self.root, source_revision="rev")
        self.assertFalse(marker.exists())
        self.assertEqual(report["coverage"]["python_files_parsed"], 1)

    def test_source_revision_must_be_present_but_unknown_is_allowed(self):
        self.put("a.py", "A=1\n")
        report = index_repository(self.root, source_revision="UNKNOWN")
        self.assertEqual(report["source"]["source_revision_status"], "CALLER_DECLARED_NOT_VERIFIED")
        with self.assertRaisesRegex(CodeIntelligenceError, "SOURCE_REVISION_REQUIRED"):
            index_repository(self.root, source_revision="")


if __name__ == "__main__":
    unittest.main()
