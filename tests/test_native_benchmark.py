from __future__ import annotations
import json
import subprocess
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts/hg-native-benchmark'
class NativeBenchmarkTests(unittest.TestCase):
    def test_candidate_improves_synthetic_control_cases_without_regression(self):
        run=subprocess.run([sys.executable,str(SCRIPT)],cwd=ROOT,capture_output=True,text=True,check=False)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        data=json.loads(run.stdout)
        self.assertEqual(data['classification'],'SYNTHETIC_CONTROL_POLICY_COMPARISON_NOT_LIVE_MODEL')
        self.assertEqual(data['observed_model_runs'],0)
        self.assertEqual(data['policies']['baseline_v0']['total'],20)
        self.assertEqual(data['policies']['baseline_v0']['passed'],5)
        self.assertEqual(data['policies']['candidate_v1']['passed'],20)
        self.assertAlmostEqual(data['delta_pass_rate'],15/20,places=5)
        self.assertEqual(data['regressions'],[])
        self.assertTrue(data['acceptance']['accepted'])
        self.assertEqual(data['production_acceptance'],'NOT_ESTABLISHED')

    def test_acceptance_floor_is_predeclared(self):
        run=subprocess.run([sys.executable,str(SCRIPT)],cwd=ROOT,capture_output=True,text=True,check=False)
        data=json.loads(run.stdout)
        self.assertEqual(data['acceptance']['predeclared_minimum_delta'],0.25)
        self.assertTrue(data['acceptance']['zero_regressions_required'])

if __name__=='__main__': unittest.main()
