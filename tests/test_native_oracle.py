from __future__ import annotations
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'tests/testdata/hg-native-oracle-cases.v1.json'
SCRIPT=ROOT/'scripts/hg-native-oracle'
class NativeOracleTests(unittest.TestCase):
    def test_all_fixed_expected_oracles(self):
        target=ROOT/'tests/testdata/hg-native-oracle-observed.test.json'
        run=subprocess.run([sys.executable,str(SCRIPT),str(target)],cwd=ROOT,capture_output=True,text=True,check=False)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        result=json.loads(target.read_text())
        self.assertEqual(result['run_status'],'PASS')
        self.assertEqual((result['case_count'],result['pass_count'],result['fail_count']),(20,20,0))
        self.assertEqual(result['classification'],'SYNTHETIC_ORACLE_IMPLEMENTATION_TEST')
        self.assertEqual(result['production_acceptance'],'NOT_ESTABLISHED')
        target.unlink(missing_ok=True)

    def test_dataset_is_pinned_and_separate_from_historical_cp0(self):
        data=json.loads(DATA.read_text())
        self.assertEqual(data['dataset_id'],'HNO-SYNTH-001')
        self.assertEqual(data['cp0_historical_equivalence'],'NOT_CLAIMED')
        self.assertEqual(len(data['cases']),20)
        self.assertEqual(len({x['case_id'] for x in data['cases']}),20)
        self.assertTrue(any(x['criterion_id']=='HNI-04' for x in data['cases']))
        for case in data['cases']:
            self.assertIn('expected',case)
            self.assertIn('criterion_id',case)

    def test_corrected_brier_expected_value_is_pinned(self):
        data=json.loads(DATA.read_text())
        self.assertEqual(data['cases'][6]['expected']['brier_score'],0.23)
        self.assertAlmostEqual(sum((x['predicted']-x['observed'])**2 for x in data['cases'][6]['input']['events'])/3, 0.23)

if __name__=='__main__': unittest.main()
