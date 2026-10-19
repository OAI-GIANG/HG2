"""Fail-closed metadata-only admission checks for speech evaluation corpora."""
import re

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_RIGHTS = {"approved", "not_applicable"}


def validate_admission(record: dict) -> dict:
    """Validate declarations only; this does not independently prove legal rights.

    A PASS means required declarations are present and internally admissible,
    not that a reviewer has verified the underlying claims.
    """
    if not isinstance(record, dict):
        raise TypeError("record must be a dict")
    required = (
        "schema_version", "corpus_id", "source_sha256", "permitted_purpose",
        "audio_rights", "transcript_rights", "speaker_consent", "review_status",
    )
    missing = [key for key in required if not record.get(key)]
    reasons = [f"missing:{key}" for key in missing]
    digest = record.get("source_sha256", "")
    if digest and not _SHA256.fullmatch(digest):
        reasons.append("invalid:source_sha256")
    if record.get("schema_version") != "1":
        reasons.append("unsupported:schema_version")
    if record.get("audio_rights") not in _ALLOWED_RIGHTS:
        reasons.append("blocked:audio_rights")
    if record.get("transcript_rights") not in _ALLOWED_RIGHTS:
        reasons.append("blocked:transcript_rights")
    if record.get("speaker_consent") not in _ALLOWED_RIGHTS:
        reasons.append("blocked:speaker_consent")
    if record.get("review_status") != "approved":
        reasons.append("blocked:review_status")
    return {
        "status": "ADMISSIBLE_DECLARATIONS" if not reasons else "BLOCKED",
        "reasons": sorted(set(reasons)),
        "rights_independently_verified": False,
    }
