import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from evaluate_wer_cer import main


class EvaluatorCliTests(unittest.TestCase):
    def test_outputs_metrics_and_error_atlas_for_synthetic_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'pairs.jsonl'
            data.write_text('\n'.join([
                json.dumps({'reference': 'xin chào', 'hypothesis': 'xin chào'}, ensure_ascii=False),
                json.dumps({'reference': 'ma', 'hypothesis': 'má'}, ensure_ascii=False),
            ]) + '\n', encoding='utf-8')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main([str(data)]), 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result['utterances'], 2)
            self.assertEqual(result['status'], 'SCORED_NOT_ACCEPTANCE')
            self.assertEqual(result['error_atlas']['diacritic_difference']['count'], 1)
            self.assertEqual(result['error_atlas']['diacritic_difference']['denominator'], 2)
            self.assertEqual(result['error_atlas_scope'], 'observable_text_difference_not_acoustic_causality')

    def test_empty_input_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'empty.jsonl'
            data.write_text('', encoding='utf-8')
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(main([str(data)]), 2)
            self.assertIn('no scored utterances', err.getvalue())


if __name__ == '__main__':
    unittest.main()
