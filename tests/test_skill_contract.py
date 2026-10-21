import hashlib
import unittest

from hg.skill_contract import (
    SKILL_SCHEMA_VERSION, SkillContractError, skill_digest,
    skill_dispatchability, validate_skill,
)


def skill(**overrides):
    value = {
        "schema_version": SKILL_SCHEMA_VERSION,
        "skill_id": "memory-research",
        "version": "1.0.0",
        "name": "Memory Research",
        "description": "Collect and compare sources before synthesis.",
        "triggers": ["research request", "source comparison"],
        "required_capabilities": ["research.analyze"],
        "risk_class": "LOCAL_READ_ONLY",
        "input_contract": "schema:HG_BRAIN_REQUEST_V1",
        "output_contract": "schema:HG_CAPABILITY_RESULT_V1",
        "verification_required": True,
        "source": {
            "kind": "BUILTIN",
            "uri": "builtin:hg.skill.memory-research",
            "sha256": hashlib.sha256(b"hg-native-skill").hexdigest(),
            "license_id": "HG-INTERNAL",
        },
        "trust_level": "BUILTIN_VERIFIED",
        "enabled": True,
    }
    value.update(overrides)
    return value


class SkillContractTests(unittest.TestCase):
    def test_builtin_verified_skill_is_dispatchable_with_required_capability(self):
        item = validate_skill(skill())
        self.assertEqual(item["schema_version"], SKILL_SCHEMA_VERSION)
        self.assertEqual(len(skill_digest(item)), 64)
        decision = skill_dispatchability(item, {"research.analyze"})
        self.assertTrue(decision["dispatchable"])
        self.assertEqual(decision["reason_code"], "SKILL_METADATA_ELIGIBLE")

    def test_missing_capability_blocks(self):
        decision = skill_dispatchability(skill(), set())
        self.assertFalse(decision["dispatchable"])
        self.assertEqual(decision["reason_code"], "SKILL_CAPABILITY_GAP")
        self.assertEqual(decision["missing_capabilities"], ["research.analyze"])

    def test_unreviewed_import_cannot_be_enabled(self):
        value = skill(
            source={
                "kind": "THIRD_PARTY", "uri": "https://github.com/example/skill",
                "sha256": hashlib.sha256(b"unreviewed").hexdigest(), "license_id": "MIT",
            },
            trust_level="UNREVIEWED",
            enabled=True,
        )
        with self.assertRaisesRegex(SkillContractError, "SKILL_UNTRUSTED_CANNOT_BE_ENABLED"):
            validate_skill(value)

    def test_unreviewed_import_can_be_catalogued_but_never_dispatched(self):
        value = skill(
            source={
                "kind": "THIRD_PARTY", "uri": "https://github.com/example/skill",
                "sha256": hashlib.sha256(b"unreviewed").hexdigest(), "license_id": "MIT",
            },
            trust_level="UNREVIEWED",
            enabled=False,
        )
        decision = skill_dispatchability(value, {"research.analyze"})
        self.assertFalse(decision["dispatchable"])
        self.assertEqual(decision["reason_code"], "SKILL_DISABLED")

    def test_enabled_skill_must_require_verification(self):
        with self.assertRaisesRegex(SkillContractError, "SKILL_VERIFICATION_MUST_BE_REQUIRED"):
            validate_skill(skill(verification_required=False))

    def test_unknown_fields_or_missing_license_fail_closed(self):
        extra = skill()
        extra["runtime_code"] = "import os"
        with self.assertRaisesRegex(SkillContractError, "SKILL_SCHEMA_FIELDS_INVALID"):
            validate_skill(extra)
        broken = skill(source={
            "kind": "THIRD_PARTY", "uri": "https://github.com/example/skill",
            "sha256": hashlib.sha256(b"skill").hexdigest(), "license_id": "",
        }, trust_level="THIRD_PARTY_REVIEWED")
        with self.assertRaisesRegex(SkillContractError, "SKILL_SOURCE_LICENSE_REQUIRED"):
            validate_skill(broken)

    def test_unhashable_fields_never_escape_as_type_errors(self):
        with self.assertRaises(SkillContractError):
            validate_skill(skill(triggers=[{}]))
        with self.assertRaises(SkillContractError):
            validate_skill(skill(required_capabilities=[{}]))
        with self.assertRaises(SkillContractError):
            validate_skill(skill(risk_class={}))


if __name__ == "__main__":
    unittest.main()
