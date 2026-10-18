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

    def test_edit_distance(self):
        self.assertEqual(edit_distance(list('kitten'), list('sitting')), 3)

if __name__ == '__main__':
    unittest.main()
