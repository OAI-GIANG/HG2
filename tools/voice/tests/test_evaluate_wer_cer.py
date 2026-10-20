import contextlib
import io
import json
import hashlib
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
            self.assertEqual(result['input_sha256'], hashlib.sha256(data.read_bytes()).hexdigest())
            self.assertIn('punctuation retained', result['scoring_policy'])

    def test_malformed_jsonl_returns_line_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'bad.jsonl'
            data.write_text('{\"reference\": \"a\", nope}\n', encoding='utf-8')
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(main([str(data)]), 2)
            self.assertIn('line 1: invalid JSON', err.getvalue())

    def test_invalid_utf8_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'invalid-utf8.jsonl'
            data.write_bytes(b'{\"reference\": \"x\", \"hypothesis\": \"x\"}\n\xff')
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(main([str(data)]), 2)
            self.assertIn('ERROR', err.getvalue())

    def test_missing_or_nonstring_fields_rejected(self):
        for value in ({'reference': 'a'}, {'reference': 'a', 'hypothesis': 1}, ['a', 'b']):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                data = Path(tmp) / 'bad-schema.jsonl'
                data.write_text(json.dumps(value) + '\n', encoding='utf-8')
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    self.assertEqual(main([str(data)]), 2)
                self.assertIn('expected string fields', err.getvalue())

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
