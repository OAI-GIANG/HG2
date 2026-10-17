"""Small pure reference implementation used to test audit verifier semantics."""
import hashlib
import json
from pathlib import Path


def verify_audit(path):
    p = Path(path)
    prev = "GENESIS"
    bad = []
    legacy_prefix_records = 0
    chained_records = 0
    chain_start_line = None
    lines = p.read_text(errors="replace").splitlines()
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("record is not an object")
            if "h" not in record:
                if chain_start_line is None:
                    legacy_prefix_records += 1
                    continue
                bad.append({"line": i, "reason": "missing chain hash after chain start"})
                continue
            if chain_start_line is None:
                chain_start_line = i
            chained_records += 1
            digest = record.pop("h")
            if record.get("prev") != prev:
                bad.append({"line": i, "reason": "prev mismatch"})
            if hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest() != digest:
                bad.append({"line": i, "reason": "hash mismatch"})
            prev = digest
        except Exception as exc:
            bad.append({"line": i, "reason": type(exc).__name__})
    chain_ok = bool(chained_records) and not bad
    return {"ok": chain_ok and legacy_prefix_records == 0, "chain_ok": chain_ok,
            "records": sum(bool(x.strip()) for x in lines),
            "legacy_prefix_records": legacy_prefix_records,
            "chained_records": chained_records, "chain_start_line": chain_start_line,
            "chain_end_hash": prev if chained_records else None, "bad": bad[:10]}
