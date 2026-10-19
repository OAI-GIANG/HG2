# HG Native Intelligence V2.1 — synthetic fixture package

This directory contains 26 synthetic, non-production evaluation fixtures with machine-readable oracle specifications, a manifest, validators, regression tests, closure notes and a SHA-256 inventory.

## Run from repository root or this directory

```sh
python -m unittest -v tests/fixtures/hg-native-intelligence-v2.1/test_fixture_package_v21.py
python tests/fixtures/hg-native-intelligence-v2.1/validate_v21.py
(cd tests/fixtures/hg-native-intelligence-v2.1 && sha256sum -c SHA256SUMS-V2.1.txt)
```

`validate_v21.py` checks package-local identity, schema, traceability, selected deterministic arithmetic, synthetic digest examples and aggregation truth-table behavior. These are static package checks, not a semantic judge for arbitrary natural-language responses.

**Execution boundary:** all fixtures remain `NOT_RUN`; this package does not invoke HG or establish HG implementation acceptance. It does not verify the historical authority or byte-for-byte provenance of CP0's original 26 criteria.
