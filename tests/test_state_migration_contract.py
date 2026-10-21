"""Tracked regression tests for fail-closed migration envelope semantics."""
import base64
import hashlib
import unittest
from hg.state_migration import (
    LEGACY_AUTHORITY_UNATTESTED, MigrationEnvelopeError,
    build_envelope, canonical_envelope_bytes, validate_envelope,
)


def sha(label): return hashlib.sha256(label.encode()).hexdigest()


class StateMigrationContractTests(unittest.TestCase):
    def setUp(self):
        self.log = b'{"event_id":"e1","sequence":1}\n{"event_id":"e2","sequence":2}\n'
        self.envelope = build_envelope(
            source_log=self.log, source_runtime_id='legacy-runtime',
            source_head_digest=sha('head'), source_state_sha256=sha('state'),
            source_head_sha256=sha('head-file'), source_runtime_id_sha256=sha('runtime-file'))

    def test_round_trip_preserves_exact_source_and_never_authorizes_import(self):
        result = validate_envelope(self.envelope)
        self.assertTrue(result['ok'])
        self.assertEqual(result['event_count'], 2)
        self.assertEqual(result['legacy_authority'], LEGACY_AUTHORITY_UNATTESTED)
        self.assertFalse(result['production_import_authorized'])
        self.assertEqual(base64.b64decode(self.envelope['source_log_base64']), self.log)
        self.assertEqual(canonical_envelope_bytes(self.envelope), canonical_envelope_bytes(self.envelope))

    def test_tampered_source_bytes_rejected(self):
        broken = dict(self.envelope, source_log_base64='e30K')
        with self.assertRaisesRegex(MigrationEnvelopeError, 'SOURCE_METADATA_MISMATCH'):
            validate_envelope(broken)

    def test_fabricated_authority_rejected(self):
        broken = dict(self.envelope, legacy_authority='AUTHENTICATED')
        with self.assertRaisesRegex(MigrationEnvelopeError, 'LEGACY_AUTHORITY_MUST_REMAIN_UNATTESTED'):
            validate_envelope(broken)

    def test_import_enablement_rejected(self):
        broken = dict(self.envelope, production_import_authorized=True)
        with self.assertRaisesRegex(MigrationEnvelopeError, 'PRODUCTION_IMPORT_MUST_REMAIN_DISABLED'):
            validate_envelope(broken)

    def test_invalid_jsonl_rejected(self):
        with self.assertRaisesRegex(MigrationEnvelopeError, 'SOURCE_EVENT_JSON_INVALID'):
            build_envelope(source_log=b'not-json\n', source_runtime_id='legacy-runtime',
                source_head_digest=sha('head'), source_state_sha256=sha('state'),
                source_head_sha256=sha('head-file'), source_runtime_id_sha256=sha('runtime-file'))


if __name__ == '__main__': unittest.main()
