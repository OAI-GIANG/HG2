#!/usr/bin/env python3
"""Recompute ZIP digests and CRC checks against the captured HG-CTI archive manifest."""
import hashlib, json, sys, zipfile
from pathlib import Path

manifest_path = Path(__file__).with_name("archive-manifest.json")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
failures = []
for item in manifest["archives"]:
    if not item.get("present"):
        failures.append(item["archive"] + ":MISSING_FROM_CAPTURE")
        continue
    path = Path(item["path"])
    if not path.is_file():
        failures.append(item["archive"] + ":FILE_MISSING")
        continue
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != item["sha256"]:
        failures.append(item["archive"] + ":SHA256_MISMATCH")
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:
            failures.append(item["archive"] + ":CRC_FAILURE")
if len(manifest["archives"]) != manifest["archive_count_expected"]:
    failures.append("ARCHIVE_COUNT_MISMATCH")
print(json.dumps({"archives_checked": len(manifest["archives"]), "failures": failures,
                  "result": "PASS" if not failures else "FAIL"}, indent=2))
sys.exit(1 if failures else 0)
