from __future__ import annotations
import hashlib
import json
from importlib.machinery import SourceFileLoader
import subprocess
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'tests/testdata/hg-native-oracle-cases.v1.json'
SCRIPT=ROOT/'scripts/hg-native-oracle'
class NativeOracleTests(unittest.TestCase):
    @staticmethod
    def _expected_dataset_digest():
        return 'cfeb9b2cbdc05ce7238f236e942a167b1d40549af2678d1f879b67253fde9916'

    def test_all_fixed_expected_oracles(self):
        target=ROOT/'tests/testdata/hg-native-oracle-observed.test.json'
        run=subprocess.run([sys.executable,str(SCRIPT),str(target)],cwd=ROOT,capture_output=True,text=True,check=False)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        result=json.loads(target.read_text())
        self.assertEqual(result['run_status'],'PASS')
        self.assertEqual((result['case_count'],result['pass_count'],result['fail_count']),(20,20,0))
        self.assertEqual(result['classification'],'SYNTHETIC_ORACLE_IMPLEMENTATION_TEST')
        self.assertEqual(result['dataset_sha256'],hashlib.sha256(DATA.read_bytes()).hexdigest())
        self.assertEqual(result['dataset_sha256'],self._expected_dataset_digest())
        self.assertEqual(result['production_acceptance'],'NOT_ESTABLISHED')
        target.unlink(missing_ok=True)

    def test_dataset_is_pinned_and_separate_from_historical_cp0(self):
        data=json.loads(DATA.read_text())
        self.assertEqual(data['dataset_id'],'HNO-SYNTH-001')
        self.assertEqual(data['cp0_historical_equivalence'],'NOT_CLAIMED')
        self.assertEqual(len(data['cases']),20)
        self.assertEqual(len({x['case_id'] for x in data['cases']}),20)
        self.assertTrue(any(x['criterion_id']=='HNI-04' for x in data['cases']))
        self.assertEqual({x['criterion_id'] for x in data['cases']}, {f'HNI-{i:02d}' for i in range(1,17)})
        for case in data['cases']:
            self.assertIn('expected',case)
            self.assertIn('criterion_id',case)

    def test_corrected_brier_expected_value_is_pinned(self):
        data=json.loads(DATA.read_text())
        self.assertEqual(data['cases'][6]['expected']['brier_score'],0.23)
        self.assertAlmostEqual(sum((x['predicted']-x['observed'])**2 for x in data['cases'][6]['input']['events'])/3, 0.23)

class NativeOracleNegativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle=SourceFileLoader('hg_native_oracle_under_test',str(SCRIPT)).load_module()

    def test_dataset_digest_is_pinned_and_report_matches_it(self):
        raw=DATA.read_bytes()
        doc=json.loads(raw)
        self.oracle.validate_document(doc,raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),self.oracle.EXPECTED_DATASET_SHA256)

    def test_tampered_dataset_fails_closed(self):
        raw=DATA.read_bytes()+b' '
        doc=json.loads(raw)
        with self.assertRaisesRegex(ValueError,'DATASET_DIGEST_MISMATCH'):
            self.oracle.validate_document(doc,raw)

    def test_missing_or_duplicate_case_fails_closed(self):
        raw=DATA.read_bytes(); doc=json.loads(raw)
        doc['cases'].pop()
        changed=json.dumps(doc,sort_keys=True).encode()
        with self.assertRaisesRegex(ValueError,'DATASET_CASE_INVENTORY_MISMATCH'):
            self.oracle.validate_document(doc,changed)

    def test_brier_oracle_rejects_empty_and_out_of_domain_events(self):
        with self.assertRaisesRegex(ValueError,'Brier_EVENTS_EMPTY'):
            self.oracle.evaluate({'case_id':'OR-07','input':{'events':[]}})
        with self.assertRaisesRegex(ValueError,'Brier_INPUT_OUT_OF_DOMAIN'):
            self.oracle.evaluate({'case_id':'OR-07','input':{'events':[{'predicted':1.2,'observed':1}]}})

    def test_pass_rate_oracle_rejects_zero_denominator(self):
        case={'case_id':'OR-08','input':{'baseline':{'passed':0,'total':0},'candidate':{'passed':1,'total':1,'critical_failures':0}}}
        with self.assertRaisesRegex(ValueError,'PASS_RATE_DENOMINATOR_OR_COUNT_INVALID'):
            self.oracle.evaluate(case)

    def test_error_rate_oracle_rejects_invalid_counts(self):
        case={'case_id':'OR-14','input':{'baseline':{'errors':21,'cases':20},'candidate':{'errors':0,'cases':20},'dataset_match':True,'config_match':True,'oracle_pinned':True}}
        with self.assertRaisesRegex(ValueError,'ERROR_RATE_DENOMINATOR_OR_COUNT_INVALID'):
            self.oracle.evaluate(case)

    def test_critical_regression_oracle_rejects_zero_denominator(self):
        case={'case_id':'OR-09','input':{'baseline':{'passed':0,'total':0},'candidate':{'passed':1,'total':1,'critical_failures':0}}}
        with self.assertRaisesRegex(ValueError,'PASS_RATE_DENOMINATOR_OR_COUNT_INVALID'):
            self.oracle.evaluate(case)

    def test_repeatability_oracle_rejects_empty_runs(self):
        with self.assertRaisesRegex(ValueError,'REPEATABILITY_RUNS_EMPTY'):
            self.oracle.evaluate({'case_id':'OR-10','input':{'runs':[]}})

if __name__=='__main__': unittest.main()
