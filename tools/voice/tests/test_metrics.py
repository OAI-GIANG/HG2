import unittest
from hg_voice.metrics import edit_distance, normalize_text, score_pair


class MetricsTests(unittest.TestCase):
    def test_nfc_casefold_and_whitespace(self):
        self.assertEqual(normalize_text('  ĐIỆN   thoại\n'), normalize_text('điện thoại'))

    def test_identical_vietnamese(self):
        result = score_pair('Xin chào thế giới', 'Xin chào thế giới')
        self.assertEqual(result['wer'], 0)
        self.assertEqual(result['cer'], 0)

    def test_word_and_character_errors(self):
        result = score_pair('xin chào bạn', 'xin bạn')
        self.assertAlmostEqual(result['wer'], 1 / 3)
        self.assertGreater(result['cer'], 0)

    def test_empty_reference_rates_are_undefined(self):
        result = score_pair('', 'xin chào')
        self.assertIsNone(result['wer'])
        self.assertIsNone(result['cer'])

    def test_empty_pair_has_undefined_rates(self):
        result = score_pair('', '')
        self.assertIsNone(result['wer'])
        self.assertIsNone(result['cer'])
        self.assertEqual(result['word_errors'], 0)
        self.assertEqual(result['character_errors'], 0)

    def test_unicode_composed_and_decomposed_normalize_equally(self):
        self.assertEqual(normalize_text('má'), normalize_text('ma\u0301'))
        self.assertEqual(score_pair('má', 'ma\u0301')['cer'], 0)

    def test_edit_distance_empty_and_identity(self):
        self.assertEqual(edit_distance([], []), 0)
        self.assertEqual(edit_distance([], ['a', 'b']), 2)
        self.assertEqual(edit_distance(['a'], ['a']), 0)

    def test_edit_distance(self):
        self.assertEqual(edit_distance(list('kitten'), list('sitting')), 3)

if __name__ == '__main__':
    unittest.main()
