import unittest
from hg_voice.error_atlas import build_error_atlas, classify_difference


class ErrorAtlasTests(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(classify_difference('Xin chào!', 'Xin chào!'), 'exact_match')

    def test_vietnamese_diacritics_are_not_stripped_from_primary_metrics(self):
        self.assertEqual(classify_difference('ma', 'má'), 'diacritic_difference')

    def test_punctuation_difference(self):
        self.assertEqual(classify_difference('Xin chào!', 'Xin chào'), 'punctuation_only_difference')

    def test_whitespace_difference(self):
        self.assertEqual(classify_difference('xin  chào', 'xin chào'), 'whitespace_or_unicode_normalization')

    def test_tokenization_difference(self):
        self.assertEqual(classify_difference('xin chào', 'xinchào'), 'whitespace_or_tokenization_difference')

    def test_lexical_difference(self):
        self.assertEqual(classify_difference('xin chào bạn', 'xin gặp bạn'), 'lexical_or_word_sequence_difference')

    def test_empty_reference_and_hypothesis(self):
        self.assertEqual(classify_difference('', 'xin'), 'insertion_or_empty_reference')
        self.assertEqual(classify_difference('xin', ''), 'deletion_or_empty_hypothesis')

    def test_aggregate_has_denominator_and_no_examples_by_default(self):
        result = build_error_atlas([
            {'reference': 'xin chào', 'hypothesis': 'xin chào'},
            {'reference': 'ma', 'hypothesis': 'má'},
        ])
        self.assertEqual(result['utterance_denominator'], 2)
        self.assertEqual(result['classes']['exact_match']['count'], 1)
        self.assertEqual(result['classes']['exact_match']['denominator'], 2)
        self.assertNotIn('examples', result['classes']['exact_match'])
        self.assertEqual(result['status'], 'DIAGNOSTIC_ONLY_NOT_ACCEPTANCE')

    def test_examples_are_opt_in_and_bounded(self):
        result = build_error_atlas([
            {'reference': 'a', 'hypothesis': 'b'},
            {'reference': 'c', 'hypothesis': 'd'},
        ], include_examples=True, max_examples_per_class=1)
        bucket = result['classes']['lexical_or_word_sequence_difference']
        self.assertEqual(len(bucket['examples']), 1)

    def test_bad_pair_rejected(self):
        with self.assertRaises(ValueError):
            build_error_atlas([{'reference': 'x'}])


if __name__ == '__main__':
    unittest.main()
