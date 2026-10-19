"""Redacted audit metadata only; caller supplies no user text or audio."""
import json
import re
from datetime import datetime, timezone

_SAFE = re.compile(r"^[a-zA-Z0-9_.:-]{1,80}$")

def audit_record(operation_id: str, engine_id: str, phase: str, duration_ms: int, input_bytes: int, output_chars: int, error_code: str | None = None) -> str:
    values = (operation_id, engine_id, phase)
    if not all(isinstance(v, str) and _SAFE.fullmatch(v) for v in values):
        raise ValueError("audit metadata contains invalid identifiers")
    nums = (duration_ms, input_bytes, output_chars)
    if any(type(v) is not int or v < 0 for v in nums):
        raise ValueError("audit counters must be non-negative integers")
    if error_code is not None and (not isinstance(error_code, str) or not _SAFE.fullmatch(error_code)):
        raise ValueError("invalid error code")
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "operation_id": operation_id, "engine_id": engine_id, "phase": phase, "duration_ms": duration_ms, "input_bytes": input_bytes, "output_chars": output_chars, "error_code": error_code}
    return json.dumps(record, sort_keys=True, separators=(",", ":"))
