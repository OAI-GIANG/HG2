"""Emit machine-readable pre/post-state evidence for P0-A recovery.

Standard library only. All scenarios use TemporaryDirectory and child processes; no live
HG state path is accepted as an argument or opened.
"""
from __future__ import annotations

import builtins
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hg.history import GENESIS_EVENT, PRODUCT_ID, SCHEMA, StateStore, canonical, digest, HistoryError


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def snapshot(directory: str) -> dict:
    root = Path(directory)
    log_path = root / "history.jsonl"
    raw = log_path.read_bytes() if log_path.exists() else b""
    complete = []
    for line in raw.splitlines():
        try:
            record = json.loads(line)
            if isinstance(record, dict) and "record_hash" in record:
                complete.append(record)
        except (UnicodeDecodeError, json.JSONDecodeError):
            break
    head = None
    if (root / "head.json").exists():
        try:
            head = json.loads((root / "head.json").read_text(encoding="utf-8"))
        except Exception as exc:
            head = {"read_error": type(exc).__name__}
    projection = None
    if (root / "state.json").exists():
        try:
            projection = json.loads((root / "state.json").read_text(encoding="utf-8"))
        except Exception as exc:
            projection = {"read_error": type(exc).__name__}
    runtime_id = None
    if (root / "runtime_id").exists():
        runtime_id = (root / "runtime_id").read_text(encoding="utf-8").strip()
    incomplete = []
    if raw and not raw.endswith(b"\n"):
        incomplete = [{"bytes": len(raw) - (raw.rfind(b"\n") + 1),
                       "sha256": sha(raw[raw.rfind(b"\n") + 1:])}]
    quarantines = sorted(
        ({"name": p.name, "bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
         for p in root.glob("history.incomplete-tail.*.bin")),
        key=lambda x: x["name"])
    receipts = []
    for p in sorted(root.glob("history.recovery.*.json")):
        b = p.read_bytes()
        try:
            value = json.loads(b)
            receipts.append({"name": p.name, "sha256": sha(b),
                             "recovery_id": value.get("recovery_id"),
                             "reason": value.get("reason")})
        except Exception:
            receipts.append({"name": p.name, "sha256": sha(b), "parse": "FAILED"})
    return {
        "journal_exists": log_path.exists(),
        "journal_bytes": len(raw),
        "journal_sha256": sha(raw) if log_path.exists() else None,
        "complete_event_count": len(complete),
        "event_ids": [r.get("event_id") for r in complete],
        "event_types": [r.get("event_type") for r in complete],
        "last_seq": complete[-1].get("seq") if complete else 0,
        "last_record_hash": complete[-1].get("record_hash") if complete else None,
        "head": head,
        "state_projection": projection,
        "runtime_id_present": runtime_id is not None,
        "runtime_id_sha256": sha(runtime_id.encode()) if runtime_id is not None else None,
        "bootstrap_marker_present": (root / "history.bootstrap.pending").exists(),
        "incomplete_tail": incomplete,
        "quarantines": quarantines,
        "recovery_receipts": receipts,
    }


CHILD_EMIT = r'''
import builtins, os, sys
from hg.history import StateStore
path, mode = sys.argv[1], sys.argv[2]
store = StateStore(path)
event_id = "process-crash-" + mode
real_fsync, real_replace, real_open = os.fsync, os.replace, builtins.open
code = 71
if mode.startswith("fsync-"):
    target = int(mode.split("-")[1]); counter = {"n": 0}
    def fsync(fd):
        counter["n"] += 1
        if counter["n"] == target:
            real_fsync(fd); os._exit(code + target)
        return real_fsync(fd)
    os.fsync = fsync
elif mode in ("replace-state", "replace-head"):
    target_path = store.state if mode == "replace-state" else store.head
    def replace(src, dst):
        result = real_replace(src, dst)
        if os.fspath(dst) == target_path:
            os._exit(code + (10 if mode == "replace-state" else 11))
        return result
    os.replace = replace
elif mode in ("partial-journal-write", "flush-journal", "partial-state-write",
              "partial-head-write", "flush-state", "flush-head"):
    if mode.endswith("state-write") or mode.endswith("state"):
        target_path = store.state + ".tmp"
    elif mode.endswith("head-write") or mode.endswith("head"):
        target_path = store.head + ".tmp"
    else:
        target_path = store.log
    class ExitFile:
        def __init__(self, handle): self.handle = handle
        def __getattr__(self, name): return getattr(self.handle, name)
        def __enter__(self): self.handle.__enter__(); return self
        def __exit__(self, *exc): return self.handle.__exit__(*exc)
        def write(self, value):
            if mode in ("partial-journal-write", "partial-state-write", "partial-head-write"):
                data = value.encode("utf-8") if isinstance(value, str) else bytes(value)
                os.write(self.handle.fileno(), data[:max(1, len(data)//2)])
                os._exit(code + 12)
            return self.handle.write(value)
        def flush(self):
            self.handle.flush()
            os._exit(code + 13)
    def open_wrapper(file, *args, **kwargs):
        handle = real_open(file, *args, **kwargs)
        mode_arg = args[0] if args else kwargs.get("mode", "r")
        if os.fspath(file) == target_path and (
            (target_path == store.log and "a" in mode_arg) or
            (target_path != store.log and "w" in mode_arg)
        ):
            return ExitFile(handle)
        return handle
    builtins.open = open_wrapper
store.emit("session.created", {"session_id": "target-" + mode}, event_id=event_id)
os._exit(0)
'''

CHILD_BOOTSTRAP = r'''
import os, sys
from hg.history import StateStore
path, target_raw = sys.argv[1], sys.argv[2]
target = int(target_raw); real_fsync = os.fsync; counter = {"n": 0}
def fsync(fd):
    counter["n"] += 1
    if counter["n"] == target:
        real_fsync(fd); os._exit(90 + target)
    return real_fsync(fd)
os.fsync = fsync
StateStore(path)
os._exit(0)
'''


def add_case(report, case_id, mode, before, exit_code, expected_code, after_crash, after_recovery, ok, error=None):
    report["cases"].append({
        "case_id": case_id, "mode": mode,
        "before_state": before, "process_exit_code": exit_code,
        "expected_exit_code": expected_code, "after_crash_state": after_crash,
        "after_recovery_state": after_recovery, "recovery_error": error,
        "oracle_pass": bool(ok),
    })


def main() -> int:
    report = {
        "schema_version": "hg2.p0a.recovery-observations.v1",
        "oracle_id": "HG2-P0A-PREPOST-ORACLE-20261019-R1",
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "platform": sys.platform, "python": sys.version.split()[0],
        "scope": "TemporaryDirectory only; no application runtime path opened",
        "cases": [],
    }
    # 13 ordinary-operation process-kill scenarios.
    modes = ["fsync-1", "fsync-2", "fsync-3", "fsync-4", "fsync-5",
             "replace-state", "replace-head", "partial-journal-write", "flush-journal",
             "partial-state-write", "partial-head-write", "flush-state", "flush-head"]
    for mode in modes:
        with tempfile.TemporaryDirectory() as directory:
            base_store = StateStore(directory)
            base_store.emit("session.created", {"session_id": "before"}, event_id="oracle-before")
            before = snapshot(directory)
            proc = subprocess.run([sys.executable, "-c", CHILD_EMIT, directory, mode],
                                  cwd=ROOT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            after_crash = snapshot(directory)
            error = None
            try:
                recovered = StateStore(directory)
                verify = recovered.verify()
                after_recovery = snapshot(directory)
                event_id = "process-crash-" + mode
                matches = [e for e in recovered.replay() if e["event_id"] == event_id]
                if mode == "partial-journal-write":
                    ok = (verify["ok"] and not matches
                          and "target-" + mode not in recovered._sessions
                          and bool(after_recovery["quarantines"])
                          and any(e["event_type"] == "history.state.recovered" for e in recovered.replay()))
                else:
                    ok = (verify["ok"] and len(matches) == 1
                          and "target-" + mode in recovered._sessions)
                again = StateStore(directory)
                ok = bool(ok and again.verify()["ok"]
                          and len([e for e in again.replay() if e["event_id"] == event_id]) == len(matches))
            except Exception as exc:
                error = {"type": type(exc).__name__, "message": str(exc)}
                after_recovery = snapshot(directory)
                ok = False
            expected_code = (71 + int(mode.split("-")[1]) if mode.startswith("fsync-")
                             else 81 if mode == "replace-state"
                             else 82 if mode == "replace-head"
                             else 83 if "write" in mode
                             else 84)
            ok = bool(ok and proc.returncode == expected_code)
            add_case(report, "RUNTIME-CRASH-" + mode.upper().replace("-", "_"), mode,
                     before, proc.returncode, expected_code, after_crash, after_recovery, ok, error)
    # 14 bootstrap process-kill scenarios.
    for boundary in range(1, 15):
        with tempfile.TemporaryDirectory() as directory:
            before = snapshot(directory)
            proc = subprocess.run([sys.executable, "-c", CHILD_BOOTSTRAP, directory, str(boundary)],
                                  cwd=ROOT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            after_crash = snapshot(directory)
            error = None
            try:
                recovered = StateStore(directory)
                events = recovered.replay()
                after_recovery = snapshot(directory)
                ok = (recovered.verify()["ok"]
                      and sum(1 for e in events if e["event_type"] == GENESIS_EVENT) == 1
                      and len({e["event_id"] for e in events}) == len(events)
                      and not after_recovery["bootstrap_marker_present"]
                      and StateStore(directory).verify()["ok"])
            except Exception as exc:
                error = {"type": type(exc).__name__, "message": str(exc)}
                after_recovery = snapshot(directory)
                ok = False
            expected = 90 + boundary
            ok = bool(ok and proc.returncode == expected)
            add_case(report, "BOOTSTRAP-CRASH-FSYNC-%02d" % boundary, "bootstrap-fsync-%d" % boundary,
                     before, proc.returncode, expected, after_crash, after_recovery, ok, error)
    report["case_count"] = len(report["cases"])
    report["passed"] = sum(1 for c in report["cases"] if c["oracle_pass"])
    report["failed"] = report["case_count"] - report["passed"]
    report["verdict"] = "PASS" if report["failed"] == 0 else "FAIL"
    report["limitations"] = [
        "os._exit models abrupt process termination after an observed syscall; it does not simulate a hardware power cut or device flash loss.",
        "A complete valid JSON frame without a trailing newline is treated as ambiguous and remains fail-closed.",
        "Missing/corrupt/unanchored checkpoints and projections outside the allowed one-event recovery window remain fail-closed."
    ]
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
