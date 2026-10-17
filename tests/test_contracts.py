"""Tests for HG2's versioned canonical event contract."""
import unittest

from hg.contracts import (
    ContractError,
    SCHEMA_VERSION,
    ZERO_DIGEST,
    canonical_digest,
    canonical_json,
    create_event,
    parse_json_no_duplicate_keys,
    validate_event,
    verify_event,
)


def sample_event(**overrides):
    args = {
        "event_type": "task.created",
        "sequence": 1,
        "actor_id": "local-user",
        "authority_context": {"principal": "local-user", "grant": "task.create"},
        "runtime_id": "phone-runtime-1",
        "state_owner_id": "phone",
        "payload": {"task_id": "t-001", "description": "contains the word token in ordinary text"},
        "previous_digest": ZERO_DIGEST,
        "correlation_id": "corr-001",
        "idempotency_key": "idem-001",
        "event_id": "event-001",
        "recorded_at": 1000.25,
    }
    args.update(overrides)
    return create_event(**args)


class CanonicalSerializerTests(unittest.TestCase):
    def test_object_key_order_does_not_change_canonical_bytes_or_digest(self):
        left = {"b": [2, 1], "a": {"y": True, "x": None}}
        right = {"a": {"x": None, "y": True}, "b": [2, 1]}
        self.assertEqual(canonical_json(left), canonical_json(right))
        self.assertEqual(canonical_digest(left), canonical_digest(right))

    def test_non_finite_numbers_are_rejected(self):
        with self.assertRaisesRegex(ContractError, "NON_FINITE_NUMBER"):
            canonical_json({"score": float("nan")})

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(ContractError, "DUPLICATE_JSON_KEY"):
            parse_json_no_duplicate_keys('{"task": {"id": 1, "id": 2}}')

    def test_non_standard_json_constants_are_rejected(self):
        with self.assertRaisesRegex(ContractError, "NON_STANDARD_JSON_CONSTANT"):
            parse_json_no_duplicate_keys('{"value": Infinity}')


class EventEnvelopeTests(unittest.TestCase):
    def test_create_validate_and_verify_event(self):
        event = sample_event()
        self.assertEqual(event["schema_version"], SCHEMA_VERSION)
        self.assertEqual(validate_event(event), event)
        self.assertTrue(verify_event(event)["ok"])

    def test_tampered_payload_fails_digest_verification(self):
        event = sample_event()
        event["payload"]["task_id"] = "changed"
        result = verify_event(event)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "RECORD_DIGEST_MISMATCH")

    def test_unknown_schema_version_fails_closed(self):
        event = sample_event()
        event["schema_version"] = "HG_EVENT_V999"
        event["record_digest"] = canonical_digest({
            key: value for key, value in event.items() if key != "record_digest"
        })
        with self.assertRaisesRegex(ContractError, "UNSUPPORTED_SCHEMA_VERSION"):
            validate_event(event)

    def test_unknown_fields_fail_closed(self):
        event = sample_event()
        event["extra"] = "not allowed"
        with self.assertRaisesRegex(ContractError, "UNKNOWN_EVENT_FIELDS"):
            validate_event(event)

    def test_boolean_is_not_a_valid_sequence(self):
        with self.assertRaisesRegex(ContractError, "INVALID_SEQUENCE"):
            sample_event(sequence=True)

    def test_sensitive_field_names_are_rejected_but_plain_text_is_allowed(self):
        with self.assertRaisesRegex(ContractError, "SENSITIVE_FIELD_NAME_FORBIDDEN"):
            sample_event(payload={"api_key": "must not be carried"})
        event = sample_event(payload={"message": "this text mentions a secret but is not a credential field"})
        self.assertTrue(verify_event(event)["ok"])

    def test_previous_digest_must_be_sha256_hex(self):
        with self.assertRaisesRegex(ContractError, "PREVIOUS_DIGEST_INVALID"):
            sample_event(previous_digest="not-a-digest")


if __name__ == "__main__":
    unittest.main()
