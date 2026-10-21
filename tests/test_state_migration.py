import base64
import hashlib
import unittest

from hg.state_migration import (
    LEGACY_AUTHORITY_UNATTESTED,
    SCHEMA_VERSION,
    MigrationEnvelopeError,
    build_envelope,
    canonical_envelope_bytes,
    validate_envelope,
)


def digest(label):
    return hashlib.sha256(label.encode()).hexdigest()


class StateMigrationEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.source_log = b'{"event_id":"legacy-1","sequence":1}\n{"event_id":"legacy-2","sequence":2}\n'
        self.envelope = build_envelope(
            source_log=self.source_log,
            source_runtime_id="legacy-runtime",
            source_head_digest=digest("head"),
            source_state_sha256=digest("state"),
            source_head_sha256=digest("head-file"),
            source_runtime_id_sha256=digest("runtime-file"),
        )

    def test_round_trip_preserves_exact_bytes_and_fails_closed(self):
        result = validate_envelope(self.envelope)
        self.assertTrue(result["ok"])
        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertEqual(result["event_count"], 2)
        self.assertEqual(result["legacy_authority"], LEGACY_AUTHORITY_UNATTESTED)
        self.assertFalse(result["production_import_authorized"])
        self.assertFalse(result["migration_performed"])
        self.assertEqual(base64.b64decode(self.envelope["source_log_base64"]), self.source_log)
        self.assertEqual(canonical_envelope_bytes(self.envelope), canonical_envelope_bytes(self.envelope))

    def test_rejects_tampered_log(self):
        broken = dict(self.envelope)
        broken["source_log_base64"] = base64.b64encode(b'{"different":true}\n').decode()
        with self.assertRaisesRegex(MigrationEnvelopeError, "SOURCE_METADATA_MISMATCH"):
            validate_envelope(broken)

    def test_rejects_fabricated_authority(self):
        broken = dict(self.envelope)
        broken["legacy_authority"] = "AUTHENTICATED"
        with self.assertRaisesRegex(MigrationEnvelopeError, "LEGACY_AUTHORITY_MUST_REMAIN_UNATTESTED"):
            validate_envelope(broken)

    def test_rejects_production_import_enablement(self):
        broken = dict(self.envelope)
        broken["production_import_authorized"] = True
        with self.assertRaisesRegex(MigrationEnvelopeError, "PRODUCTION_IMPORT_MUST_REMAIN_DISABLED"):
            validate_envelope(broken)

    def test_rejects_invalid_jsonl(self):
        with self.assertRaisesRegex(MigrationEnvelopeError, "SOURCE_EVENT_JSON_INVALID"):
            build_envelope(
                source_log=b"not-json\n",
                source_runtime_id="legacy-runtime",
                source_head_digest=digest("head"),
                source_state_sha256=digest("state"),
                source_head_sha256=digest("head-file"),
                source_runtime_id_sha256=digest("runtime-file"),
            )

    def test_rejects_duplicate_json_keys(self):
        with self.assertRaisesRegex(MigrationEnvelopeError, "SOURCE_EVENT_JSON_INVALID"):
            build_envelope(
                source_log=b'{"event_id":"one","event_id":"two"}\\n',
                source_runtime_id="legacy-runtime",
                source_head_digest=digest("head"),
                source_state_sha256=digest("state"),
                source_head_sha256=digest("head-file"),
                source_runtime_id_sha256=digest("runtime-file"),
            )

    def test_rejects_nonfinite_json(self):
        with self.assertRaisesRegex(MigrationEnvelopeError, "SOURCE_EVENT_JSON_INVALID"):
            build_envelope(
                source_log=b'{"value":NaN}\n',
                source_runtime_id="legacy-runtime",
                source_head_digest=digest("head"),
                source_state_sha256=digest("state"),
                source_head_sha256=digest("head-file"),
                source_runtime_id_sha256=digest("runtime-file"),
            )

    def test_rejects_extra_or_missing_fields(self):
        broken = dict(self.envelope)
        broken["unrecognized"] = "value"
        with self.assertRaisesRegex(MigrationEnvelopeError, "ENVELOPE_SCHEMA_INVALID"):
            validate_envelope(broken)

    def test_rejects_wrong_schema_version(self):
        broken = dict(self.envelope)
        broken["schema_version"] = "HG_STATE_MIGRATION_ENVELOPE_V0"
        with self.assertRaisesRegex(MigrationEnvelopeError, "ENVELOPE_SCHEMA_VERSION_INVALID"):
            validate_envelope(broken)

    def test_rejects_malformed_digest(self):
        with self.assertRaisesRegex(MigrationEnvelopeError, "SOURCE_DIGEST_INVALID"):
            build_envelope(
                source_log=self.source_log,
                source_runtime_id="legacy-runtime",
                source_head_digest="not-a-sha256",
                source_state_sha256=digest("state"),
                source_head_sha256=digest("head-file"),
                source_runtime_id_sha256=digest("runtime-file"),
            )


if __name__ == "__main__":
    unittest.main()
