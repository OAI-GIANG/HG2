"""Durability and concurrency tests for the SQLite transaction coordinator."""
from __future__ import annotations

import multiprocessing as mp
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from hg.durable_transactions import DurableTransactionError, DurableTransactionStore


CONTRACT = "a" * 64
PLAN = "b" * 64


def _competing_begin(db_path: str, queue, worker: int) -> None:
    try:
        store = DurableTransactionStore(db_path)
        result = store.begin(
            transaction_id=f"tx:{worker}", idempotency_key="same-key",
            contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["validate", "summarize"],
        )
        queue.put(("ok", result["state"], result["transaction_id"]))
    except Exception as exc:
        queue.put(("error", type(exc).__name__, str(exc)))


class DurableTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hg-tx-test-")
        self.db_path = str(Path(self.tmp.name) / "transactions.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def _store(self, **kwargs):
        return DurableTransactionStore(self.db_path, **kwargs)

    @staticmethod
    def _allow_prepare(request):
        return True, "test-authorizer:prepare"

    @staticmethod
    def _allow_evidence(evidence_ids):
        return bool(evidence_ids), "test-evidence-verifier"

    @staticmethod
    def _allow_commit(record):
        return record["state"] == "EVIDENCE_PENDING", "test-commit-authorizer"

    def _start_complete_transaction(self, store):
        record = store.begin(
            transaction_id="tx:1", idempotency_key="key:1",
            contract_digest=CONTRACT, plan_digest=PLAN,
            step_ids=["step:1", "step:2"],
        )
        self.assertEqual(record["state"], "BLOCKED")
        return record

    def test_default_begin_is_blocked_without_trusted_authorizer(self):
        store = self._store()
        record = store.begin(
            transaction_id="tx:1", idempotency_key="key:1",
            contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["step:1"],
        )
        self.assertEqual(record["state"], "BLOCKED")
        self.assertEqual(record["reason"], "PREPARE_AUTHORIZER_UNAVAILABLE")
        with self.assertRaises(DurableTransactionError) as ctx:
            store.start("key:1")
        self.assertEqual(ctx.exception.code, "TRANSACTION_BLOCKED")

    def test_persistence_survives_store_reopen(self):
        store = self._store(prepare_authorizer=self._allow_prepare)
        record = store.begin(
            transaction_id="tx:1", idempotency_key="key:1",
            contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["step:1"],
        )
        self.assertEqual(record["state"], "PREPARED")
        reopened = self._store()
        self.assertEqual(reopened.get("key:1")["state"], "PREPARED")
        self.assertEqual(reopened.verify_event_chain()["ok"], True)

    def test_idempotent_begin_has_one_record_and_one_initial_event(self):
        store = self._store()
        first = store.begin(
            transaction_id="tx:1", idempotency_key="same-key",
            contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["step:1"],
        )
        second = store.begin(
            transaction_id="tx:other", idempotency_key="same-key",
            contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["step:1"],
        )
        self.assertEqual(first, second)
        with closing(sqlite3.connect(self.db_path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM hg_txn").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM hg_txn_event").fetchone()[0], 1)

    def test_same_idempotency_key_different_payload_rejected(self):
        store = self._store()
        store.begin(
            transaction_id="tx:1", idempotency_key="same-key",
            contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["step:1"],
        )
        with self.assertRaises(DurableTransactionError) as ctx:
            store.begin(
                transaction_id="tx:2", idempotency_key="same-key",
                contract_digest="c" * 64, plan_digest=PLAN, step_ids=["step:1"],
            )
        self.assertEqual(ctx.exception.code, "IDEMPOTENCY_KEY_CONFLICT")

    def test_full_state_path_commits_only_with_injected_verifiers(self):
        store = self._store(
            prepare_authorizer=self._allow_prepare,
            evidence_verifier=self._allow_evidence,
            commit_authorizer=self._allow_commit,
        )
        record = store.begin(
            transaction_id="tx:1", idempotency_key="key:1",
            contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["step:1", "step:2"],
        )
        self.assertEqual(record["state"], "PREPARED")
        self.assertEqual(store.start("key:1")["state"], "RUNNING")
        self.assertEqual(store.record_step("key:1", "step:1", succeeded=True)["completed_steps"], ["step:1"])
        # Repeated observation is idempotent and creates no duplicate event.
        before = len(store.events())
        self.assertEqual(store.record_step("key:1", "step:1", succeeded=True)["completed_steps"], ["step:1"])
        self.assertEqual(len(store.events()), before)
        store.record_step("key:1", "step:2", succeeded=True)
        self.assertEqual(store.evidence_pending("key:1", ["evidence:1"])["state"], "EVIDENCE_PENDING")
        committed = store.commit("key:1")
        self.assertEqual(committed["state"], "COMMITTED")
        self.assertTrue(store.verify_event_chain()["ok"])
        self.assertTrue(store.verify_state_integrity()["ok"])
        self.assertFalse(any(e["detail"].get("side_effect_performed") is True for e in store.events()))

    def test_commit_blocked_without_evidence_verifier(self):
        store = self._store(prepare_authorizer=self._allow_prepare)
        store.begin(transaction_id="tx:1", idempotency_key="key:1",
                    contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["step:1"])
        store.start("key:1")
        store.record_step("key:1", "step:1", succeeded=True)
        store.evidence_pending("key:1", ["evidence:1"])
        result = store.commit("key:1")
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["reason"], "EVIDENCE_VERIFIER_UNAVAILABLE")

    def test_incomplete_steps_enter_in_doubt(self):
        store = self._store(prepare_authorizer=self._allow_prepare)
        store.begin(transaction_id="tx:1", idempotency_key="key:1",
                    contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["step:1", "step:2"])
        store.start("key:1")
        store.record_step("key:1", "step:1", succeeded=True)
        record = store.evidence_pending("key:1", ["evidence:1"])
        self.assertEqual(record["state"], "IN_DOUBT")
        self.assertEqual(record["reason"], "NOT_ALL_STEPS_OBSERVED")

    def test_restart_recovery_moves_running_to_in_doubt(self):
        store = self._store(prepare_authorizer=self._allow_prepare)
        store.begin(transaction_id="tx:1", idempotency_key="key:1",
                    contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["step:1"])
        store.start("key:1")
        reopened = self._store()
        results = reopened.recover_incomplete()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["state"], "IN_DOUBT")
        self.assertEqual(reopened.get("key:1")["reason"], "PROCESS_RESTART_RECOVERY_REQUIRED")

    def test_failed_event_append_rolls_back_state_transition_atomically(self):
        store = self._store(prepare_authorizer=self._allow_prepare)
        store.begin(transaction_id="tx:1", idempotency_key="key:1",
                    contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["step:1"])
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("""CREATE TRIGGER fail_running_event BEFORE INSERT ON hg_txn_event
                          WHEN NEW.event_type='RUNNING' BEGIN SELECT RAISE(ABORT,'injected event failure'); END""")
            db.commit()
        before_events = len(store.events())
        with self.assertRaises(DurableTransactionError) as ctx:
            store.start("key:1")
        self.assertEqual(ctx.exception.code, "TRANSACTION_STORAGE_UNAVAILABLE")
        self.assertEqual(store.get("key:1")["state"], "PREPARED")
        self.assertEqual(len(store.events()), before_events)
        self.assertTrue(store.verify_event_chain()["ok"])

    def test_transaction_projection_tampering_detected(self):
        store = self._store()
        store.begin(transaction_id="tx:1", idempotency_key="key:1",
                    contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["step:1"])
        self.assertTrue(store.verify_state_integrity()["ok"])
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE hg_txn SET state='ABORTED' WHERE idempotency_key='key:1'")
            db.commit()
        result = store.verify_state_integrity()
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "TRANSACTION_EVENT_PROJECTION_MISMATCH")

    def test_transaction_digest_projection_tampering_detected(self):
        store = self._store()
        store.begin(transaction_id="tx:1", idempotency_key="key:1",
                    contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["step:1"])
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE hg_txn SET contract_digest=? WHERE idempotency_key='key:1'", ("c" * 64,))
            db.commit()
        result = store.verify_state_integrity()
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "TRANSACTION_EVENT_PROJECTION_MISMATCH")

    def test_corrupt_transaction_projection_json_fails_closed(self):
        store = self._store()
        store.begin(transaction_id="tx:1", idempotency_key="key:1",
                    contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["step:1"])
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE hg_txn SET completed_steps_json='not-json' WHERE idempotency_key='key:1'")
            db.commit()
        result = store.verify_state_integrity()
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "TRANSACTION_STORED_RECORD_INVALID")

    def test_malformed_event_detail_json_fails_closed(self):
        store = self._store()
        store.begin(transaction_id="tx:1", idempotency_key="key:1",
                    contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["step:1"])
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE hg_txn_event SET detail_json='not-json' WHERE seq=1")
            db.commit()
        result = store.verify_event_chain()
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "EVENT_DETAIL_INVALID")

    def test_event_chain_tampering_detected(self):
        store = self._store()
        store.begin(transaction_id="tx:1", idempotency_key="key:1",
                    contract_digest=CONTRACT, plan_digest=PLAN, step_ids=["step:1"])
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute("UPDATE hg_txn_event SET detail_json='{}' WHERE seq=1")
            db.commit()
        result = store.verify_event_chain()
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "EVENT_CHAIN_DIGEST_MISMATCH")

    def test_concurrent_processes_share_single_idempotency_record(self):
        store = self._store()
        # Initialize schema before concurrent writers start.
        queue = mp.get_context("fork").Queue()
        context = mp.get_context("fork")
        processes = [
            context.Process(target=_competing_begin, args=(self.db_path, queue, i))
            for i in range(4)
        ]
        for process in processes:
            process.start()
        results = [queue.get(timeout=15) for _ in processes]
        for process in processes:
            process.join(timeout=15)
            self.assertEqual(process.exitcode, 0)
        self.assertTrue(all(item[0] == "ok" for item in results), results)
        with closing(sqlite3.connect(self.db_path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM hg_txn").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM hg_txn_event").fetchone()[0], 1)
        self.assertTrue(store.verify_event_chain()["ok"])

    def test_invalid_storage_and_digest_fail_closed(self):
        with self.assertRaises(DurableTransactionError):
            DurableTransactionStore(":memory:")
        store = self._store()
        with self.assertRaises(DurableTransactionError) as ctx:
            store.begin(transaction_id="tx:1", idempotency_key="key:1",
                        contract_digest="bad", plan_digest=PLAN, step_ids=["step:1"])
        self.assertEqual(ctx.exception.code, "TRANSACTION_SCHEMA_INVALID")


if __name__ == "__main__":
    unittest.main(verbosity=2)
