"""P2 closure probes: process-crash recovery, snapshot rollback, and real-loopback outbox retry."""
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from hg.durable import CONTRACT, DurableDeliveryError, DurableOutbox
from hg.history import HistoryError, StateStore
from hg.phone_runtime import PhoneRuntime
from hg.server import HGHTTPServer


CAPABILITIES = {
    "contract": CONTRACT,
    "memory_schema": "HG_MEMORY_V1",
    "supports_tombstones": True,
    "supports_scopes": True,
    "required_scope": "MEMORY_PERSIST",
}


def memory_record():
    record = {
        "id": "p2-closure-record",
        "type": "fact",
        "title": "P2",
        "content": "test payload only",
        "scope_id": "closure-test",
        "owner_id": "test-owner",
        "source": "unit-test",
        "provenance": "p2-closure",
        "status": "active",
        "version": 1,
    }
    from hg.history import digest
    record["checksum"] = digest(record)
    return record


def crash_after_model_start(state_dir, request_id, *, complete=False):
    code = r'''
import os, sys
from hg.history import StateStore
state_dir, request_id, complete = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
store = StateStore(state_dir)
correlation_id = "corr:" + request_id
store.emit("model.call.started", {
    "operation": "model_answer", "brain_request_id": request_id,
    "query_sha256": "a" * 64, "context_manifest_sha256": "b" * 64,
    "brain_plan_digest": "c" * 64,
}, correlation_id=correlation_id, event_id="model-call-start:" + request_id)
if complete:
    store.emit("model.call.completed", {"brain_request_id": request_id},
               correlation_id=correlation_id, event_id="model-call-completed:" + request_id)
os._exit(86)
'''
    return subprocess.run(
        [sys.executable, "-c", code, str(state_dir), request_id, "1" if complete else "0"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False,
    )


class OutboxReceiver(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    logical_batches = set()
    post_attempts = []
    lose_first_receipt = True

    def log_message(self, *_args):
        pass

    def _send_json(self, status, value):
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path != "/backend/hg2/capabilities":
            self._send_json(404, {"error": "not found"})
            return
        self._send_json(200, CAPABILITIES)

    def do_POST(self):
        if self.path != "/backend/hg2/memory/batch":
            self._send_json(404, {"error": "not found"})
            return
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        batch = json.loads(raw.decode("utf-8"))
        batch_id = batch["batch_id"]
        self.__class__.post_attempts.append(batch_id)
        self.__class__.logical_batches.add(batch_id)
        if self.__class__.lose_first_receipt:
            self.__class__.lose_first_receipt = False
            # Model the failure window: receiver committed, but the acknowledgement was lost.
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
            return
        self._send_json(200, {
            "ok": True, "contract": CONTRACT, "batch_id": batch_id,
            "accepted_count": len(batch["events"]),
        })


class P2BlockerClosureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hg2-p2-closure-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _markers(self, runtime, request_id):
        events = runtime.store.replay()
        return [e for e in events
                if e.get("event_type") == "model.call.in_doubt"
                and (e.get("payload") or {}).get("brain_request_id") == request_id]

    def test_real_child_process_crash_recovers_in_doubt_exactly_once_across_restarts(self):
        state = self.root / "state-crash"
        process = crash_after_model_start(state, "orphan-provider-call")
        self.assertEqual(process.returncode, 86, process.stderr.decode("utf-8", "replace"))
        restarted = PhoneRuntime(state_dir=str(state))
        self.assertTrue(restarted.health()["integrity"]["ok"])
        markers = self._markers(restarted, "orphan-provider-call")
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["payload"]["reason"], "OUTCOME_UNKNOWN_AFTER_START")
        restarted_again = PhoneRuntime(state_dir=str(state))
        self.assertEqual(len(self._markers(restarted_again, "orphan-provider-call")), 1)
        self.assertTrue(restarted_again.health()["integrity"]["ok"])

    def test_http_runtime_restart_recovers_in_doubt_under_server_startup_lock(self):
        # Exercise the real HTTP server constructor and PhoneRuntime startup path,
        # but only against a temporary state directory and ephemeral loopback port.
        state = tempfile.mkdtemp(prefix="hg2-p2-http-restart-")
        self.addCleanup(shutil.rmtree, state, ignore_errors=True)
        env = {
            "HG_STATE_DIR": state,
            "HG_API_READ_TOKEN": "test-read-token",
            "HG_API_WRITE_TOKEN": "test-write-token",
            "HG_API_READ_TOKEN_ID": "read-v1",
            "HG_API_WRITE_TOKEN_ID": "write-v1",
            "HG_API_READ_TOKEN_EXPIRES_AT": "4102444800",
            "HG_API_WRITE_TOKEN_EXPIRES_AT": "4102444800",
            "HG_API_REVOKED_TOKEN_IDS": "",
            "HG_API_PRINCIPAL_ID": "p2-test-owner",
            "HG_MEMORY_READ_SCOPES": "owner",
            "HG_MEMORY_WRITE_SCOPES": "owner",
        }
        request_id = "ask-http-restart-p2"
        correlation_id = "corr-http-restart-p2"
        with mock.patch.dict(os.environ, env, clear=False):
            first = HGHTTPServer(("127.0.0.1", 0))
            try:
                first.runtime.store.emit(
                    "model.call.started",
                    {"operation": "model_answer", "brain_request_id": request_id,
                     "query_sha256": "a" * 64, "context_manifest_sha256": "b" * 64,
                     "brain_plan_digest": "c" * 64},
                    correlation_id=correlation_id,
                    event_id="model-call-start:" + request_id,
                )
                self.assertTrue(first.runtime.store.verify()["ok"])
            finally:
                first.server_close()

            # New server instance reopens the same temporary state and must recover
            # before serving, without retrying the uncertain model call.
            second = HGHTTPServer(("127.0.0.1", 0))
            try:
                events = second.runtime.store.replay()
                doubts = [event for event in events
                          if event.get("event_type") == "model.call.in_doubt"
                          and (event.get("payload") or {}).get("brain_request_id") == request_id]
                self.assertEqual(len(doubts), 1)
                self.assertEqual(doubts[0]["payload"]["reason"], "OUTCOME_UNKNOWN_AFTER_START")
                self.assertTrue(second.runtime.store.verify()["ok"])
            finally:
                second.server_close()

        recovered_again = PhoneRuntime(state_dir=state)
        self.assertEqual(
            len([event for event in recovered_again.store.replay()
                 if event.get("event_type") == "model.call.in_doubt"
                 and (event.get("payload") or {}).get("brain_request_id") == request_id]),
            1,
        )

    def test_real_child_process_crash_after_completion_does_not_mark_in_doubt(self):
        state = self.root / "state-completed"
        process = crash_after_model_start(state, "completed-provider-call", complete=True)
        self.assertEqual(process.returncode, 86, process.stderr.decode("utf-8", "replace"))
        restarted = PhoneRuntime(state_dir=str(state))
        events = restarted.store.replay()
        self.assertTrue(any(
            e.get("event_type") == "model.call.completed"
            and (e.get("payload") or {}).get("brain_request_id") == "completed-provider-call"
            for e in events
        ))
        self.assertEqual(len(self._markers(restarted, "completed-provider-call")), 0)
        self.assertTrue(restarted.health()["integrity"]["ok"])

    def test_snapshot_restore_after_corruption_returns_to_verified_state(self):
        active = self.root / "state-active"
        store = StateStore(str(active))
        store.emit("checkpoint.marker", {"marker": "before-crash"}, event_id="p2-checkpoint-marker")
        store_before = store.verify()
        self.assertTrue(store_before["ok"])
        backup = self.root / "snapshot"
        shutil.copytree(active, backup)
        damaged = active / "history.jsonl"
        with damaged.open("ab") as stream:
            stream.write(b'{"tampered":true}\n')
        with self.assertRaises(HistoryError):
            StateStore(str(active))
        restored = self.root / "state-restored"
        shutil.copytree(backup, restored)
        server_env = {
            "HG_STATE_DIR": str(restored),
            "HG_API_READ_TOKEN": "test-read-token",
            "HG_API_WRITE_TOKEN": "test-write-token",
            "HG_API_READ_TOKEN_ID": "read-v1",
            "HG_API_WRITE_TOKEN_ID": "write-v1",
            "HG_API_READ_TOKEN_EXPIRES_AT": "4102444800",
            "HG_API_WRITE_TOKEN_EXPIRES_AT": "4102444800",
            "HG_API_REVOKED_TOKEN_IDS": "",
            "HG_API_PRINCIPAL_ID": "p2-test-owner",
            "HG_MEMORY_READ_SCOPES": "owner",
            "HG_MEMORY_WRITE_SCOPES": "owner",
        }
        with mock.patch.dict(os.environ, server_env, clear=False):
            # Exercise rollback at the real server startup boundary, using only a
            # restored temporary snapshot; the corrupted directory stays untouched.
            restored_server = HGHTTPServer(("127.0.0.1", 0))
            try:
                self.assertTrue(restored_server.runtime.health()["integrity"]["ok"])
                self.assertTrue(any(
                    e.get("event_id") == "p2-checkpoint-marker"
                    for e in restored_server.runtime.store.replay()
                ))
            finally:
                restored_server.server_close()

    def test_http_outbox_retry_after_lost_ack_is_idempotent_across_store_restart(self):
        OutboxReceiver.logical_batches = set()
        OutboxReceiver.post_attempts = []
        OutboxReceiver.lose_first_receipt = True
        server = ThreadingHTTPServer(("127.0.0.1", 0), OutboxReceiver)
        server.daemon_threads = True
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(lambda: server.shutdown())
        base_url = "http://127.0.0.1:" + str(server.server_address[1])
        state = self.root / "outbox-state"
        first_store = StateStore(str(state))
        first_store.emit(
            "memory.mutated",
            {"record": memory_record(), "idempotency_key": "p2-record-key"},
            event_id="p2-outbox-event",
        )
        first = DurableOutbox(
            first_store, base_url=base_url, token="loopback-test-token",
            allowed_scopes={"closure-test"}, timeout=2,
        )
        with self.assertRaises(DurableDeliveryError):
            first.deliver_once()
        self.assertEqual(len(OutboxReceiver.logical_batches), 1)
        # Reopen durable state as a distinct runtime would after restart.
        second_store = StateStore(str(state))
        second = DurableOutbox(
            second_store, base_url=base_url, token="loopback-test-token",
            allowed_scopes={"closure-test"}, timeout=2,
        )
        result = second.deliver_once()
        self.assertEqual(result["status"], "ACKNOWLEDGED")
        self.assertEqual(second.status()["pending_count"], 0)
        self.assertEqual(len(OutboxReceiver.post_attempts), 2)
        self.assertEqual(len(OutboxReceiver.logical_batches), 1)
        ack_events = [e for e in second_store.replay()
                      if e.get("event_type") == "durable.batch.acknowledged"]
        self.assertEqual(len(ack_events), 1)
        self.assertTrue(second_store.verify()["ok"])


if __name__ == "__main__":
    unittest.main()
