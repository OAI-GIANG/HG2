"""Run the synthetic HG Native Intelligence V2.1 package checks."""
import subprocess
import sys
import unittest
from pathlib import Path

PACKAGE = Path(__file__).parent / "fixtures" / "hg-native-intelligence-v2.1"


class NativeIntelligenceFixturePackageTests(unittest.TestCase):
    def test_fixture_package_regression(self):
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "-v", "test_fixture_package_v21.py"],
            cwd=PACKAGE, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Ran 12 tests", result.stderr)

    def test_static_semantic_validator(self):
        result = subprocess.run(
            [sys.executable, "validate_v21.py"], cwd=PACKAGE,
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("STATIC_SEMANTIC_VALIDATION PASS", result.stdout)
        self.assertIn("fixtures=26 unique_ids=26 oracle_specs=26/26", result.stdout)

    def test_all_fixtures_explicitly_not_run(self):
        import json
        for path in sorted(PACKAGE.glob("HNIF2-*.json")):
            with self.subTest(fixture=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(data["execution_status"], "NOT_RUN")
                self.assertEqual(data["result_record"]["observed_status"], "NOT_RUN")
                self.assertEqual(data["classification"], "SYNTHETIC_NON_PRODUCTION")
