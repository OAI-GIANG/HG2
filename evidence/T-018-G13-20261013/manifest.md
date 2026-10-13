# HG2 T-018 G13 Resource-Leak Remediation Evidence

- Repository: `OAI-GIANG/HG2`
- Branch: `feat/hg-t018-cross-context-sync-20261013`
- Baseline commit: `3b160f24e1b0cb446c810b46974612829cace5db`
- Tested code commit: `31f9fcc24af3aa9b8014da8a7faa6dbf8602fb0d`
- Tested code tree: `628f9326f6592d30f8c01abfc62439701882d613`
- Parent: `3b160f24e1b0cb446c810b46974612829cace5db`
- Environment: Python 3.14.6; Android 15; aarch64
- Changes: only `tests/test_core.py` and `tests/test_t018_sync.py` in the code commit.
- Root causes observed before fix: unmanaged file handles in both test files and unclosed `urllib.error.HTTPError` objects in `EdgeTests.call()`.
- Fix: context-manage file reads/writes and close HTTPError in `finally`; no warnings were suppressed.
- Baseline test results: T-018 11 tests / core 12 tests / full suite 23 tests; exit 0, but ResourceWarnings present.
- Post-fix: core 12/12, T-018 11/11, full suite 23/23 twice; exit 0; `ResourceWarning: 0`; `Exception ignored: 0`.
- Clean checkout at tested code commit: full suite 23/23 twice; exit 0; `ResourceWarning: 0`; `Exception ignored: 0`; normalized logs identical.
- Normalization: only `Ran N tests in <duration>s` timing line replaced with a fixed token. No warning/error/test result lines removed.
- Normalized log SHA-256: `e301c03d38105b66c2dabdd11ba8d145568fa655e731343b7aa1f813526f951b` (both clean-checkout runs and both working-copy runs).

## SHA-256 manifest
10d1abe25d9ecb301891b89d0d7e598f28271accf33e62d286b92b9fb6e33ab6  baseline-core.log
5889d3f74229d1a333592fe18059d64010a4efba85a366d13ffc84abbc6949c6  baseline-suite.log
f4385a6307ef23be4f590136acc1fa0aa2f626b0938c6aab6c08994f1cb34a55  baseline-t018.log
61e9be70ceebfe68784deb9a6c41df59164a310ab62cffd3b82748e12f2953c6  clean-suite-1.log
e301c03d38105b66c2dabdd11ba8d145568fa655e731343b7aa1f813526f951b  clean-suite-1.normalized.log
9a262ffd4f18b0fc3bd84da5f880a20ff2b0d8e4693284d564629bd348d4a4f0  clean-suite-2.log
e301c03d38105b66c2dabdd11ba8d145568fa655e731343b7aa1f813526f951b  clean-suite-2.normalized.log
59bc8fe950d99581015ac0fa10cf034e9d0885720d03dd53d929368900b1de9f  fixed-core.log
936e92089bf5db0637a9b58fb3150723ec1207dc8e33f04fa7577a81e86d6604  fixed-suite-1.log
e301c03d38105b66c2dabdd11ba8d145568fa655e731343b7aa1f813526f951b  fixed-suite-1.normalized.log
cbfdcb04fb1c3b72b25af56ef6327d81eab334e2716c6bdbf01030c86cc0838a  fixed-suite-2.log
e301c03d38105b66c2dabdd11ba8d145568fa655e731343b7aa1f813526f951b  fixed-suite-2.normalized.log
4a565fae8a646c5cc89c95442ff6ce0a00b7e7d856616584bdec557bc0ed1b4d  fixed-t018.log
998853c288bc71e2672e4c6a868075898f7c88bce7992c888d94c9bb2625f829  clean-checkout-commit.txt
ba051334ebc33f3162a4fd5be48615e03c8dac8ec7977e7c2752dbc1cf981841  clean-checkout-status.txt
e60c87f7abb069f4ede3076757cce546e71201139adf9abf469d69f25262d6f0  clean-checkout-tree.txt
0afe76de11223644cda0aeea7f928b577c6c58637399123f9edd0e29c5a33a3c  environment-clean-checkout.txt
3313bef641be8b81a7c06ea1bd8466820169d939cd3231356bb206f3dc8c56e3  environment-working-copy.txt
