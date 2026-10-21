"""Fixed fault-injection oracle for atomic StateStore checkpoint recovery.

Only disposable TemporaryDirectory stores are used. These tests never open application state.
"""
import builtins
import hashlib
import json
import os
import tempfile
import unittest
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from hg.history import HistoryError, StateStore, PRODUCT_ID, SCHEMA, canonical, digest


class FaultingFile:
    def __init__(self, handle, *, stage, captured=None):
        self._handle = handle
        self._stage = stage
        self._captured = captured
        self._fired = False

    def __getattr__(self, name):
        return getattr(self._handle, name)

    def __enter__(self):
        self._handle.__enter__()
        return self

    def __exit__(self, *exc):
        return self._handle.__exit__(*exc)

    def write(self, data):
        if not self._fired and self._stage == "write":
            self._fired = True
            partial = data[:max(1, len(data) // 2)]
            self._handle.write(partial)
            self._handle.flush()
            if self._captured is not None:
                self._captured.append(partial.encode("utf-8") if isinstance(partial, str) else bytes(partial))
            raise OSError("injected write failure")
        return self._handle.write(data)

    def flush(self):
        if not self._fired and self._stage == "flush":
            self._fired = True
            # Persist the buffered content, then report an ambiguous flush outcome.
            self._handle.flush()
            raise OSError("injected flush failure")
        return self._handle.flush()


class StateRecoveryTests(unittest.TestCase):
    def make_store(self, directory):
        store = StateStore(directory)
        store.emit("session.created", {"session_id": "before"}, event_id="recovery-oracle-before")
        self.assertTrue(store.verify()["ok"])
        return store

    def assert_recovered_once(self, directory, session_id, event_id):
        reopened = StateStore(directory)
        matches = [e for e in reopened.replay() if e["event_id"] == event_id]
        self.assertEqual(len(matches), 1, "operation event must appear exactly once")
        self.assertEqual(matches[0]["payload"]["session_id"], session_id)
        self.assertEqual(list(reopened._sessions).count(session_id), 1)
        self.assertTrue(reopened.verify()["ok"])
        again = StateStore(directory)
        self.assertEqual(len([e for e in again.replay() if e["event_id"] == event_id]), 1)
        self.assertTrue(again.verify()["ok"])
        return again

    def test_recover_when_state_write_raises_after_journal_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            with patch.object(store, "_write_state", side_effect=OSError("injected state write")):
                with self.assertRaisesRegex(OSError, "injected state write"):
                    store.emit("session.created", {"session_id": "target"}, event_id="recovered-state-write")
            recovered = self.assert_recovered_once(directory, "target", "recovered-state-write")
            self.assertTrue(any(e["event_type"] == "history.state.recovered" for e in recovered.replay()))

    def test_recover_when_head_write_raises_after_projection_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            with patch.object(store, "_write_head", side_effect=OSError("injected head write")):
                with self.assertRaisesRegex(OSError, "injected head write"):
                    store.emit("session.created", {"session_id": "target"}, event_id="recovered-head-write")
            self.assert_recovered_once(directory, "target", "recovered-head-write")

    def test_recovery_is_retryable_if_recovery_state_write_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            with patch.object(store, "_write_state", side_effect=OSError("first state write fault")):
                with self.assertRaises(OSError):
                    store.emit("session.created", {"session_id": "target"}, event_id="recovery-retry-state")
            with patch.object(StateStore, "_write_state", side_effect=OSError("recovery state write fault")):
                with self.assertRaisesRegex(OSError, "recovery state write fault"):
                    StateStore(directory)
            recovered = self.assert_recovered_once(directory, "target", "recovery-retry-state")
            self.assertTrue(recovered.verify()["ok"])

    def test_recovery_is_retryable_if_recovery_head_write_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            with patch.object(store, "_write_state", side_effect=OSError("first state write fault")):
                with self.assertRaises(OSError):
                    store.emit("session.created", {"session_id": "target"}, event_id="recovery-retry-head")
            with patch.object(StateStore, "_write_head", side_effect=OSError("recovery head write fault")):
                with self.assertRaisesRegex(OSError, "recovery head write fault"):
                    StateStore(directory)
            recovered = self.assert_recovered_once(directory, "target", "recovery-retry-head")
            self.assertTrue(recovered.verify()["ok"])

    def test_replace_failure_for_state_is_recoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            real_replace = os.replace
            fired = {"value": False}
            def replace(src, dst):
                if os.fspath(dst) == store.state and not fired["value"]:
                    fired["value"] = True
                    raise OSError("injected state rename")
                return real_replace(src, dst)
            with patch("hg.history.os.replace", side_effect=replace):
                with self.assertRaisesRegex(OSError, "injected state rename"):
                    store.emit("session.created", {"session_id": "target"}, event_id="recovered-state-rename")
            self.assertTrue(fired["value"])
            self.assert_recovered_once(directory, "target", "recovered-state-rename")

    def test_replace_failure_for_head_is_recoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            real_replace = os.replace
            fired = {"value": False}
            def replace(src, dst):
                if os.fspath(dst) == store.head and not fired["value"]:
                    fired["value"] = True
                    raise OSError("injected head rename")
                return real_replace(src, dst)
            with patch("hg.history.os.replace", side_effect=replace):
                with self.assertRaisesRegex(OSError, "injected head rename"):
                    store.emit("session.created", {"session_id": "target"}, event_id="recovered-head-rename")
            self.assertTrue(fired["value"])
            self.assert_recovered_once(directory, "target", "recovered-head-rename")

    def test_state_and_head_temp_write_failures_are_recoverable(self):
        for target_name, event_id in (("state.json.tmp", "recovered-state-temp-write"),
                                      ("head.json.tmp", "recovered-head-temp-write")):
            with self.subTest(target=target_name), tempfile.TemporaryDirectory() as directory:
                store = self.make_store(directory)
                target = os.path.join(directory, target_name)
                real_open = builtins.open
                armed = {"value": True}
                def open_wrapper(file, *args, **kwargs):
                    handle = real_open(file, *args, **kwargs)
                    mode = args[0] if args else kwargs.get("mode", "r")
                    if armed["value"] and os.fspath(file) == target and "w" in mode:
                        armed["value"] = False
                        return FaultingFile(handle, stage="write")
                    return handle
                with patch("builtins.open", side_effect=open_wrapper):
                    with self.assertRaisesRegex(OSError, "injected write failure"):
                        store.emit("session.created", {"session_id": "target"}, event_id=event_id)
                self.assertFalse(armed["value"])
                self.assert_recovered_once(directory, "target", event_id)

    def test_state_and_head_temp_flush_failures_are_recoverable(self):
        for target_name, event_id in (("state.json.tmp", "recovered-state-temp-flush"),
                                      ("head.json.tmp", "recovered-head-temp-flush")):
            with self.subTest(target=target_name), tempfile.TemporaryDirectory() as directory:
                store = self.make_store(directory)
                target = os.path.join(directory, target_name)
                real_open = builtins.open
                armed = {"value": True}
                def open_wrapper(file, *args, **kwargs):
                    handle = real_open(file, *args, **kwargs)
                    mode = args[0] if args else kwargs.get("mode", "r")
                    if armed["value"] and os.fspath(file) == target and "w" in mode:
                        armed["value"] = False
                        return FaultingFile(handle, stage="flush")
                    return handle
                with patch("builtins.open", side_effect=open_wrapper):
                    with self.assertRaisesRegex(OSError, "injected flush failure"):
                        store.emit("session.created", {"session_id": "target"}, event_id=event_id)
                self.assertFalse(armed["value"])
                self.assert_recovered_once(directory, "target", event_id)

    def test_fsync_fault_at_each_normal_emit_boundary_is_idempotently_recovered(self):
        # emit has five fsync sites: journal, state temp, dir-after-state rename,
        # head temp, and dir-after-head rename. The last boundary may have committed
        # both files before reporting an fsync error; both outcomes are acceptable.
        for fail_on in range(1, 6):
            with self.subTest(fsync_call=fail_on), tempfile.TemporaryDirectory() as directory:
                store = self.make_store(directory)
                real_fsync = os.fsync
                calls = {"n": 0}
                def fsync(fd):
                    calls["n"] += 1
                    if calls["n"] == fail_on:
                        raise OSError("injected fsync %d" % fail_on)
                    return real_fsync(fd)
                with patch("hg.history.os.fsync", side_effect=fsync):
                    with self.assertRaisesRegex(OSError, "injected fsync"):
                        store.emit("session.created", {"session_id": "target"}, event_id="recovered-fsync-%d" % fail_on)
                self.assertEqual(calls["n"], fail_on)
                self.assert_recovered_once(directory, "target", "recovered-fsync-%d" % fail_on)

    def test_journal_flush_failure_after_complete_frame_recovers_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            log = store.log
            real_open = builtins.open
            armed = {"value": True}
            def open_wrapper(file, *args, **kwargs):
                handle = real_open(file, *args, **kwargs)
                mode = args[0] if args else kwargs.get("mode", "r")
                if armed["value"] and os.fspath(file) == log and "a" in mode:
                    armed["value"] = False
                    return FaultingFile(handle, stage="flush")
                return handle
            with patch("builtins.open", side_effect=open_wrapper):
                with self.assertRaisesRegex(OSError, "injected flush failure"):
                    store.emit("session.created", {"session_id": "target"}, event_id="recovered-journal-flush")
            self.assertFalse(armed["value"])
            self.assert_recovered_once(directory, "target", "recovered-journal-flush")

    def test_partial_journal_write_is_quarantined_and_recovery_is_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            log = store.log
            real_open = builtins.open
            captured = []
            armed = {"value": True}
            def open_wrapper(file, *args, **kwargs):
                handle = real_open(file, *args, **kwargs)
                mode = args[0] if args else kwargs.get("mode", "r")
                if armed["value"] and os.fspath(file) == log and "a" in mode:
                    armed["value"] = False
                    return FaultingFile(handle, stage="write", captured=captured)
                return handle
            with patch("builtins.open", side_effect=open_wrapper):
                with self.assertRaisesRegex(OSError, "injected write failure"):
                    store.emit("session.created", {"session_id": "uncommitted-partial"}, event_id="partial-frame")
            self.assertFalse(armed["value"])
            recovered = StateStore(directory)
            self.assertTrue(recovered.verify()["ok"])
            self.assertNotIn("uncommitted-partial", recovered._sessions)
            self.assertFalse(any(e["event_id"] == "partial-frame" for e in recovered.replay()))
            self.assertEqual(len(captured), 1)
            raw_tail = captured[0]
            tail_hash = hashlib.sha256(raw_tail).hexdigest()
            quarantine = Path(directory, "history.incomplete-tail." + tail_hash + ".bin")
            self.assertEqual(quarantine.read_bytes(), raw_tail)
            recovery_events = [e for e in recovered.replay()
                               if e["event_type"] == "history.state.recovered"
                               and (e["payload"].get("evidence") or {}).get("tail_sha256") == tail_hash]
            self.assertEqual(len(recovery_events), 1)
            again = StateStore(directory)
            self.assertEqual(len([e for e in again.replay() if e["event_id"] == recovery_events[0]["event_id"]]), 1)
            self.assertTrue(again.verify()["ok"])

    def test_refuses_recovery_when_head_is_missing_or_not_anchored(self):
        for mode in ("missing", "unanchored"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                store = self.make_store(directory)
                with patch.object(store, "_write_state", side_effect=OSError("injected")):
                    with self.assertRaises(OSError):
                        store.emit("session.created", {"session_id": "target"}, event_id="unsafe-" + mode)
                if mode == "missing":
                    os.remove(store.head)
                else:
                    Path(store.head).write_text(json.dumps({"seq": 99, "head_hash": "0" * 64}), encoding="utf-8")
                with self.assertRaises(HistoryError):
                    StateStore(directory)


    def test_complete_json_without_delimiter_is_ambiguous_and_not_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            before_head = Path(store.head).read_bytes()
            before_state = Path(store.state).read_bytes()
            prev = store.replay()[-1]["record_hash"]
            core = {"seq": len(store.replay()) + 1, "event_id": "ambiguous-no-newline",
                    "event_type": "session.created", "recorded_at": 1800000000.0,
                    "correlation_id": "ambiguous-no-newline", "causation_id": None,
                    "product_id": PRODUCT_ID, "runtime_id": store.runtime_id, "schema": SCHEMA,
                    "payload": {"session_id": "ambiguous"}, "prev_hash": prev}
            record = dict(core, record_hash=digest(core))
            raw_frame = canonical(record).encode("utf-8")  # valid JSON, deliberately no newline delimiter
            with open(store.log, "ab") as fh:
                fh.write(raw_frame)
            with self.assertRaisesRegex(HistoryError, "complete journal record missing final newline"):
                StateStore(directory)
            self.assertEqual(Path(store.head).read_bytes(), before_head)
            self.assertEqual(Path(store.state).read_bytes(), before_state)
            self.assertTrue(Path(store.log).read_bytes().endswith(raw_frame))
            self.assertFalse(any(name.startswith("history.incomplete-tail.") for name in os.listdir(directory)))

    def test_bootstrap_fsync_fault_at_every_initialization_boundary_recovers(self):
        # Bootstrap has 14 fsync boundaries: marker, runtime identity, zero projection,
        # zero checkpoint, genesis journal, committed projection/checkpoint, marker removal.
        for fail_on in range(1, 15):
            with self.subTest(fsync_call=fail_on), tempfile.TemporaryDirectory() as directory:
                real_fsync = os.fsync
                calls = {"n": 0}
                def fsync(fd):
                    calls["n"] += 1
                    if calls["n"] == fail_on:
                        raise OSError("injected bootstrap fsync %d" % fail_on)
                    return real_fsync(fd)
                with patch("hg.history.os.fsync", side_effect=fsync):
                    with self.assertRaisesRegex(OSError, "injected bootstrap fsync"):
                        StateStore(directory)
                self.assertEqual(calls["n"], fail_on)
                recovered = StateStore(directory)
                events = recovered.replay()
                self.assertEqual(sum(1 for e in events if e["event_type"] == "hg.genesis"), 1)
                self.assertEqual(len({e["event_id"] for e in events}), len(events))
                self.assertTrue(recovered.verify()["ok"])
                self.assertFalse(os.path.exists(os.path.join(directory, "history.bootstrap.pending")))
                reopened = StateStore(directory)
                self.assertEqual(sum(1 for e in reopened.replay() if e["event_type"] == "hg.genesis"), 1)
                self.assertTrue(reopened.verify()["ok"])

    def test_bootstrap_atomic_replace_failures_recover(self):
        for target_name in ("history.bootstrap.pending", "runtime_id", "state.json", "head.json"):
            with self.subTest(target=target_name), tempfile.TemporaryDirectory() as directory:
                target = os.path.join(directory, target_name)
                real_replace = os.replace
                fired = {"value": False}
                def replace(src, dst):
                    if os.fspath(dst) == target and not fired["value"]:
                        fired["value"] = True
                        raise OSError("injected bootstrap rename: " + target_name)
                    return real_replace(src, dst)
                with patch("hg.history.os.replace", side_effect=replace):
                    with self.assertRaisesRegex(OSError, "injected bootstrap rename"):
                        StateStore(directory)
                self.assertTrue(fired["value"])
                recovered = StateStore(directory)
                self.assertEqual(sum(1 for e in recovered.replay() if e["event_type"] == "hg.genesis"), 1)
                self.assertTrue(recovered.verify()["ok"])
                self.assertFalse(os.path.exists(os.path.join(directory, "history.bootstrap.pending")))

    def test_partial_genesis_frame_is_preserved_then_bootstrap_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            log = os.path.join(directory, "history.jsonl")
            real_open = builtins.open
            captured = []
            armed = {"value": True}
            def open_wrapper(file, *args, **kwargs):
                handle = real_open(file, *args, **kwargs)
                mode = args[0] if args else kwargs.get("mode", "r")
                if armed["value"] and os.fspath(file) == log and "a" in mode:
                    armed["value"] = False
                    return FaultingFile(handle, stage="write", captured=captured)
                return handle
            with patch("builtins.open", side_effect=open_wrapper):
                with self.assertRaisesRegex(OSError, "injected write failure"):
                    StateStore(directory)
            self.assertEqual(len(captured), 1)
            recovered = StateStore(directory)
            events = recovered.replay()
            self.assertEqual(sum(1 for e in events if e["event_type"] == "hg.genesis"), 1)
            tail_hash = hashlib.sha256(captured[0]).hexdigest()
            self.assertEqual(Path(directory, "history.incomplete-tail." + tail_hash + ".bin").read_bytes(), captured[0])
            self.assertTrue(any(e["event_type"] == "history.state.recovered"
                                and (e["payload"].get("evidence") or {}).get("tail_sha256") == tail_hash
                                for e in events))
            self.assertTrue(recovered.verify()["ok"])
            self.assertFalse(os.path.exists(os.path.join(directory, "history.bootstrap.pending")))


    def test_invalid_emit_envelopes_are_rejected_before_journal_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            before = {name: Path(directory, name).read_bytes()
                      for name in ("history.jsonl", "state.json", "head.json")}
            bad_calls = [
                ([], {"ok": True}, {}),
                ("test.bad-payload", ["not", "object"], {}),
                ("test.nan", {"value": float("nan")}, {}),
                ("session.created", {"session_id": ["not", "hashable"]}, {}),
                ("test.correlation", {"ok": True}, {"correlation_id": 42}),
                ("test.causation", {"ok": True}, {"causation_id": []}),
            ]
            for event_type, payload, kwargs in bad_calls:
                with self.subTest(event_type=repr(event_type), kwargs=kwargs):
                    with self.assertRaises(HistoryError):
                        store.emit(event_type, payload, **kwargs)
                    self.assertFalse(store._recovery_required)
                    self.assertEqual(before["history.jsonl"], Path(directory, "history.jsonl").read_bytes())
                    self.assertEqual(before["state.json"], Path(directory, "state.json").read_bytes())
                    self.assertEqual(before["head.json"], Path(directory, "head.json").read_bytes())
            saved = store.emit("session.created", {"session_id": "valid-after-reject"},
                               event_id="valid-after-reject")
            self.assertEqual(saved["event_id"], "valid-after-reject")
            self.assertTrue(StateStore(directory).verify()["ok"])

    def test_invalid_clock_is_rejected_before_journal_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(directory)
            before = Path(store.log).read_bytes()
            store._clock = lambda: float("nan")
            with self.assertRaisesRegex(HistoryError, "finite number"):
                store.emit("session.created", {"session_id": "bad-clock"}, event_id="bad-clock")
            self.assertEqual(Path(store.log).read_bytes(), before)
            self.assertFalse(store._recovery_required)
            self.assertTrue(StateStore(directory).verify()["ok"])

    def test_failed_emit_poisons_same_instance_until_restart_reconciles(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            with patch.object(store, "_write_state", side_effect=OSError("injected projection write")):
                with self.assertRaisesRegex(OSError, "injected projection write"):
                    store.emit("session.created", {"session_id": "first-target"}, event_id="poison-first")
            before_second_attempt = Path(store.log).read_bytes()
            with self.assertRaisesRegex(HistoryError, "state recovery required"):
                store.emit("session.created", {"session_id": "second-target"}, event_id="poison-second")
            self.assertEqual(Path(store.log).read_bytes(), before_second_attempt)
            recovered = StateStore(directory)
            self.assertTrue(recovered.verify()["ok"])
            self.assertIn("first-target", recovered._sessions)
            self.assertNotIn("second-target", recovered._sessions)
            self.assertEqual(len([e for e in recovered.replay() if e["event_id"] == "poison-first"]), 1)
            self.assertEqual(len([e for e in recovered.replay() if e["event_id"] == "poison-second"]), 0)
            self.assertTrue(StateStore(directory).verify()["ok"])

    def test_journal_append_error_poisons_same_instance_until_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            real_open = builtins.open
            armed = {"value": True}
            def open_wrapper(file, *args, **kwargs):
                handle = real_open(file, *args, **kwargs)
                mode = args[0] if args else kwargs.get("mode", "r")
                if armed["value"] and os.fspath(file) == store.log and "a" in mode:
                    armed["value"] = False
                    return FaultingFile(handle, stage="write")
                return handle
            with patch("builtins.open", side_effect=open_wrapper):
                with self.assertRaisesRegex(OSError, "injected write failure"):
                    store.emit("session.created", {"session_id": "partial-target"}, event_id="poison-partial")
            after_fault = Path(store.log).read_bytes()
            with self.assertRaisesRegex(HistoryError, "state recovery required"):
                store.emit("session.created", {"session_id": "later-target"}, event_id="poison-later")
            self.assertEqual(Path(store.log).read_bytes(), after_fault)
            recovered = StateStore(directory)
            self.assertTrue(recovered.verify()["ok"])
            self.assertNotIn("partial-target", recovered._sessions)
            self.assertNotIn("later-target", recovered._sessions)
            self.assertTrue(any(e["event_type"] == "history.state.recovered" for e in recovered.replay()))
            self.assertTrue(StateStore(directory).verify()["ok"])

    def test_process_crash_at_runtime_write_flush_fsync_and_rename_boundaries(self):
        root = str(Path(__file__).resolve().parents[1])
        child_lines = [
            'import builtins, os, sys',
            'from hg.history import StateStore',
            'path, mode = sys.argv[1], sys.argv[2]',
            'store = StateStore(path)',
            'event_id = "process-crash-" + mode',
            'real_fsync, real_replace, real_open = os.fsync, os.replace, builtins.open',
            'code = 71',
            'if mode.startswith("fsync-"):',
            ' target = int(mode.split("-")[1]); counter = {"n": 0}',
            ' def fsync(fd):',
            '  counter["n"] += 1',
            '  if counter["n"] == target:',
            '   real_fsync(fd); os._exit(code + target)',
            '  return real_fsync(fd)',
            ' os.fsync = fsync',
            'elif mode in ("replace-state", "replace-head"):',
            ' target_path = store.state if mode == "replace-state" else store.head',
            ' def replace(src, dst):',
            '  result = real_replace(src, dst)',
            '  if os.fspath(dst) == target_path: os._exit(code + (10 if mode == "replace-state" else 11))',
            '  return result',
            ' os.replace = replace',
            'elif mode in ("partial-journal-write", "flush-journal", "partial-state-write", "partial-head-write", "flush-state", "flush-head"):',
            ' if mode.endswith("state-write") or mode.endswith("state"): target_path = store.state + ".tmp"',
            ' elif mode.endswith("head-write") or mode.endswith("head"): target_path = store.head + ".tmp"',
            ' else: target_path = store.log',
            ' class ExitFile:',
            '  def __init__(self, handle): self.handle = handle',
            '  def __getattr__(self, name): return getattr(self.handle, name)',
            '  def __enter__(self): self.handle.__enter__(); return self',
            '  def __exit__(self, *exc): return self.handle.__exit__(*exc)',
            '  def write(self, value):',
            '   if mode in ("partial-journal-write", "partial-state-write", "partial-head-write"):',
            '    data = value.encode("utf-8") if isinstance(value, str) else bytes(value)',
            '    os.write(self.handle.fileno(), data[:max(1, len(data)//2)]); os._exit(code + 12)',
            '   return self.handle.write(value)',
            '  def flush(self): self.handle.flush(); os._exit(code + 13)',
            ' def open_wrapper(file, *args, **kwargs):',
            '  handle = real_open(file, *args, **kwargs); mode_arg = args[0] if args else kwargs.get("mode", "r")',
            '  if os.fspath(file) == target_path and ((target_path == store.log and "a" in mode_arg) or (target_path != store.log and "w" in mode_arg)): return ExitFile(handle)',
            '  return handle',
            ' builtins.open = open_wrapper',
            'store.emit("session.created", {"session_id": "target-" + mode}, event_id=event_id)',
            'os._exit(0)',
        ]
        child = "\n".join(child_lines)
        modes = ["fsync-1", "fsync-2", "fsync-3", "fsync-4", "fsync-5",
                 "replace-state", "replace-head", "partial-journal-write", "flush-journal",
                 "partial-state-write", "partial-head-write", "flush-state", "flush-head"]
        for mode in modes:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                self.make_store(directory)
                proc = subprocess.run([sys.executable, "-c", child, directory, mode],
                                      cwd=root, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                                      capture_output=True, text=True, timeout=10)
                self.assertNotEqual(proc.returncode, 0, (mode, proc.stdout, proc.stderr))
                recovered = StateStore(directory)
                self.assertTrue(recovered.verify()["ok"], mode)
                event_id = "process-crash-" + mode
                matches = [e for e in recovered.replay() if e["event_id"] == event_id]
                if mode == "partial-journal-write":
                    self.assertEqual(matches, [])
                    self.assertNotIn("target-" + mode, recovered._sessions)
                    self.assertTrue(any(e["event_type"] == "history.state.recovered"
                                        and (e["payload"].get("evidence") or {}).get("tail_sha256")
                                        for e in recovered.replay()))
                else:
                    self.assertEqual(len(matches), 1, mode)
                    self.assertIn("target-" + mode, recovered._sessions)
                again = StateStore(directory)
                self.assertTrue(again.verify()["ok"], mode)
                self.assertEqual(len([e for e in again.replay() if e["event_id"] == event_id]), len(matches))

    def test_process_crash_at_every_bootstrap_fsync_boundary_recovers(self):
        root = str(Path(__file__).resolve().parents[1])
        child = '\n'.join([
            'import os, sys',
            'from hg.history import StateStore',
            'path, target_raw = sys.argv[1], sys.argv[2]',
            'target = int(target_raw); real_fsync = os.fsync; counter = {"n": 0}',
            'def fsync(fd):',
            ' counter["n"] += 1',
            ' if counter["n"] == target: real_fsync(fd); os._exit(90 + target)',
            ' return real_fsync(fd)',
            'os.fsync = fsync',
            'StateStore(path)',
            'os._exit(0)',
        ])
        for boundary in range(1, 15):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                proc = subprocess.run([sys.executable, "-c", child, directory, str(boundary)],
                                      cwd=root, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                                      capture_output=True, text=True, timeout=10)
                self.assertEqual(proc.returncode, 90 + boundary, (boundary, proc.stdout, proc.stderr))
                recovered = StateStore(directory)
                self.assertTrue(recovered.verify()["ok"], boundary)
                self.assertEqual(sum(1 for e in recovered.replay() if e["event_type"] == "hg.genesis"), 1)
                self.assertEqual(len({e["event_id"] for e in recovered.replay()}), len(recovered.replay()))
                self.assertFalse(os.path.exists(os.path.join(directory, "history.bootstrap.pending")))
                self.assertTrue(StateStore(directory).verify()["ok"])

if __name__ == "__main__":
    unittest.main()
