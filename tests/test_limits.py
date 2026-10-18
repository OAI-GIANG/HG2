import unittest
from unittest.mock import patch

from hg.limits import FixedWindowRateLimiter


class FixedWindowRateLimiterTests(unittest.TestCase):
    def test_enforces_limit_and_returns_retry_after(self):
        limiter = FixedWindowRateLimiter(2, 10)
        with patch("hg.limits.time.monotonic", side_effect=[100.0, 100.1, 100.2]):
            self.assertEqual(limiter.allow("127.0.0.1"), (True, 0))
            self.assertEqual(limiter.allow("127.0.0.1"), (True, 0))
            allowed, retry_after = limiter.allow("127.0.0.1")
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry_after, 1)
        self.assertLessEqual(retry_after, 10)

    def test_resets_after_window(self):
        limiter = FixedWindowRateLimiter(1, 2)
        with patch("hg.limits.time.monotonic", side_effect=[10.0, 11.0, 12.1]):
            self.assertEqual(limiter.allow("client"), (True, 0))
            self.assertEqual(limiter.allow("client")[0], False)
            self.assertEqual(limiter.allow("client"), (True, 0))

    def test_bounds_client_state(self):
        limiter = FixedWindowRateLimiter(2, 60, max_clients=2)
        with patch("hg.limits.time.monotonic", side_effect=[1.0, 2.0, 3.0]):
            self.assertTrue(limiter.allow("a")[0])
            self.assertTrue(limiter.allow("b")[0])
            self.assertTrue(limiter.allow("c")[0])
        self.assertLessEqual(len(limiter._buckets), 2)

    def test_rejects_invalid_configuration(self):
        for args in ((0, 60), (True, 60), (1, 0), (1, 60, 0)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                FixedWindowRateLimiter(*args)


if __name__ == "__main__":
    unittest.main()
