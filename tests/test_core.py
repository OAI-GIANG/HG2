import json, os, shutil, subprocess, sys, tempfile, threading, unittest, urllib.error, urllib.request
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from hg import edge
from hg.authority import ALLOWED, FORBIDDEN, authorize
from hg.history import GENESIS_EVENT, ZERO, HistoryError, StateStore, digest, canonical
from hg.identity import PRODUCT_ID, identity
from hg.phone_runtime import PhoneRuntime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "edge-token-x"


def lines(d):
    return [l for l in open(os.path.join(d, "history.jsonl"), encoding="utf-8").read().splitlines() if l.strip()]


def put(d, ls):
    open(os.path.join(d, "history.jsonl"), "w", encoding="utf-8").write("\n".join(ls) + "\n")


class IdentityTests(unittest.TestCase):
    def test_identity(self):
        self.assertEqual(PRODUCT_ID, "HG")
        self.assertEqual(identity()["origin"], "clean_room_parentless_genesis")

    def test_no_legacy_reference(self):
        found = []
        for base, _dirs, files in os.walk(os.path.join(ROOT, "hg")):
            for name in files:
                if name.endswith(".py"):
                    text = open(os.path.join(base, name), encoding="utf-8").read().lower()
                    for m in ("go_runtime", "paradise", "love", "hg_ops", "governance_engine"):
                        if m in text:
                            found.append((name, m))
        self.assertEqual(found, [])


class AuthorityTests(unittest.TestCase):
    def test_disjoint_and_deny(self):
        self.assertFalse(ALLOWED & FORBIDDEN)
        self.assertFalse(authorize("shell.exec", authenticated=True).allowed)
        self.assertEqual(authorize("session.create").reason, "AUTHENTICATION_REQUIRED")
        self.assertTrue(authorize("session.create", authenticated=True).allowed)


class HistoryTests(unittest.TestCase):
    def test_genesis_and_chain(self):
        with tempfile.TemporaryDirectory() as d:
            s = StateStore(d, clock=lambda: 1750000000.0)
            ev = s.replay()
            self.assertEqual(len(ev), 1)
            self.assertEqual(ev[0]["event_type"], GENESIS_EVENT)
            self.assertEqual(ev[0]["prev_hash"], ZERO)
            r = s.emit("session.created", {"session_id": "s1"})
            self.assertEqual(r["seq"], 2)
            prev = ZERO
            for raw in lines(d):
                rec = json.loads(raw)
                rh = rec.pop("record_hash")
                self.assertEqual(rec["prev_hash"], prev)
                self.assertEqual(digest(rec), rh)
                prev = rh
            self.assertTrue(s.verify()["ok"])

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            s = StateStore(d)
            a = s.emit("session.created", {"session_id": "s2"}, event_id="fixed")
            b = s.emit("session.created", {"session_id": "s2"}, event_id="fixed")
            self.assertEqual(a["record_hash"], b["record_hash"])
            self.assertEqual(len(s.replay()), 2)

    def _case(self, mutate):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        s = StateStore(d)
        s.emit("session.created", {"session_id": "a"})
        s.emit("session.created", {"session_id": "b"})
        shutil.copyfile(os.path.join(d, "history.jsonl"), os.path.join(d, "o.jsonl"))
        shutil.copyfile(os.path.join(d, "head.json"), os.path.join(d, "o-head.json"))
        put(d, mutate(lines(d)))
        return s, d

    def test_tamper_matrix(self):
        cases = {
            "edit": lambda L: [L[0], json.dumps({**json.loads(L[1]), "payload": {"session_id": "x"}}, sort_keys=True, separators=(",", ":")), L[2]],
            "tail": lambda L: L[:-1],
            "middle": lambda L: [L[0], L[2]],
            "reorder": lambda L: [L[0], L[2], L[1]],
            "duplicate": lambda L: L + [L[-1]],
            "wipe": lambda L: [],
        }
        for name, mut in cases.items():
            s, d = self._case(mut)
            self.assertFalse(s.verify()["ok"], name)
            with self.assertRaises(HistoryError, msg=name):
                StateStore(d)

    def test_checkpoint_mismatch(self):
        s, d = self._case(lambda L: L)
        open(os.path.join(d, "head.json"), "w", encoding="utf-8").write(json.dumps({"seq": 99, "head_hash": ZERO}))
        self.assertEqual(s.verify()["reason"], "checkpoint_mismatch")
        with self.assertRaises(HistoryError):
            StateStore(d)

    def test_restart_in_new_process(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            w = ("import sys;sys.path.insert(0,%r);from hg.history import StateStore;"
                 "s=StateStore(%r);s.emit('session.created',{'session_id':'p'});print(s.audit_export()['events'])" % (ROOT, d))
            r1 = subprocess.run([sys.executable, "-c", w], capture_output=True, text=True, cwd=ROOT, env=env)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            self.assertEqual(r1.stdout.strip(), "2")
            r2 = subprocess.run([sys.executable, "-c", ("import sys;sys.path.insert(0,%r);from hg.history import StateStore;"
                                "e=StateStore(%r).audit_export();print(e['verify']['ok'],sorted(e['state']['sessions']))" % (ROOT, d))],
                                capture_output=True, text=True, cwd=ROOT, env=env)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            self.assertEqual(r2.stdout.strip(), "True ['p']")


    def test_missing_head_checkpoint_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(d)
            os.unlink(os.path.join(d, "head.json"))
            self.assertFalse(store.verify()["ok"])
            with self.assertRaises(HistoryError):
                StateStore(d)

    def test_missing_state_projection_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(d)
            os.unlink(os.path.join(d, "state.json"))
            self.assertFalse(store.verify()["ok"])
            with self.assertRaises(HistoryError):
                StateStore(d)

    def test_missing_history_with_old_artifacts_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(d)
            os.unlink(os.path.join(d, "history.jsonl"))
            self.assertFalse(store.verify()["ok"])
            with self.assertRaises(HistoryError):
                StateStore(d)

    def test_projection_tampering_all_fields_detected(self):
        mutations = {
            "schema": lambda x: x.update(schema="OTHER"),
            "runtime_id": lambda x: x.update(runtime_id="forged"),
            "last_seq": lambda x: x.update(last_seq=0),
            "head_hash": lambda x: x.update(head_hash=ZERO),
            "sessions": lambda x: x.update(sessions={"fake": {"session_id": "fake"}}),
            "counters": lambda x: x.update(counters={"forged": 900}),
        }
        for name, mutate in mutations.items():
            with self.subTest(field=name), tempfile.TemporaryDirectory() as d:
                StateStore(d).emit("session.created", {"session_id": "real"})
                path = os.path.join(d, "state.json")
                projection = json.load(open(path, encoding="utf-8"))
                mutate(projection)
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(projection, fh)
                probe = StateStore.__new__(StateStore)
                probe.dir, probe.log, probe.head, probe.state = d, os.path.join(d, "history.jsonl"), os.path.join(d, "head.json"), path
                self.assertFalse(probe.verify()["ok"], name)
                with self.assertRaises(HistoryError, msg=name):
                    StateStore(d)

    def test_checkpoint_rollback_detected(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(d)
            store.emit("session.created", {"session_id": "x"})
            records = lines(d)
            old = json.loads(records[-2])
            with open(os.path.join(d, "head.json"), "w", encoding="utf-8") as fh:
                json.dump({"seq": old["seq"], "head_hash": old["record_hash"]}, fh)
            self.assertEqual(store.verify()["reason"], "checkpoint_mismatch")
            with self.assertRaises(HistoryError):
                StateStore(d)

    def test_non_object_history_record_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(d)
            path = os.path.join(d, "history.jsonl")
            with open(path, encoding="utf-8") as fh:
                rows = fh.read().splitlines()
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("[]\n")
            result = store.verify()
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "record_not_object_line_1")
            with self.assertRaises(HistoryError):
                StateStore(d)

    def test_invalid_sequence_and_event_type_fail_closed(self):
        for name, alter in (
            ("boolean_sequence", lambda r: r.update(seq=True)),
            ("empty_event_type", lambda r: r.update(event_type="")),
        ):
            with self.subTest(case=name), tempfile.TemporaryDirectory() as d:
                store = StateStore(d)
                path = os.path.join(d, "history.jsonl")
                with open(path, encoding="utf-8") as fh:
                    rec = json.loads(fh.readline())
                alter(rec)
                core = {k: v for k, v in rec.items() if k != "record_hash"}
                rec["record_hash"] = digest(core)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(canonical(rec) + "\n")
                result = store.verify()
                self.assertFalse(result["ok"], name)
                with self.assertRaises(HistoryError, msg=name):
                    StateStore(d)

    def test_interrupted_append_detected(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(d)
            with open(os.path.join(d, "history.jsonl"), "ab") as fh:
                fh.write(b'{"seq":2,"partial":')
            self.assertFalse(store.verify()["ok"])
            with self.assertRaises(HistoryError):
                StateStore(d)

    def test_duplicate_and_reordered_records_are_rejected(self):
        for name, mutate in (
            ("duplicate", lambda rows: rows + [rows[-1]]),
            ("reordered", lambda rows: [rows[0], rows[2], rows[1]]),
        ):
            with self.subTest(case=name), tempfile.TemporaryDirectory() as d:
                store = StateStore(d)
                store.emit("session.created", {"session_id": "a"})
                store.emit("session.created", {"session_id": "b"})
                put(d, mutate(lines(d)))
                self.assertFalse(store.verify()["ok"])
                with self.assertRaises(HistoryError):
                    StateStore(d)


class EdgeTests(unittest.TestCase):
    def setUp(self):
        self.p = patch.dict(os.environ, {"HG_EDGE_TOKEN": TOKEN}, clear=False)
        self.p.start()
        self.addCleanup(self.p.stop)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), edge.Handler)
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()
        self.addCleanup(self._stop)
        self.base = "http://127.0.0.1:%d" % self.srv.server_port

    def _stop(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.th.join(timeout=2)

    def call(self, path, method="GET", body=None, token=None):
        req = urllib.request.Request(self.base + path, data=body, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=4) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_edge_behaviour(self):
        self.assertEqual(self.call("/health")[0], 200)
        self.assertEqual(self.call("/edge/register", "POST", b'{"device_id":"d1"}')[0], 403)
        self.assertEqual(self.call("/edge/register", "POST", json.dumps({"device_id": "d1"}).encode(), TOKEN)[0], 201)
        self.assertEqual(self.call("/edge/heartbeat", "POST", json.dumps({"device_id": "d1", "seq": 5}).encode(), TOKEN)[0], 201)
        self.assertEqual(edge.DEVICES["d1"]["seq"], 5)
        self.assertEqual(self.call("/edge/register", "POST", b"{", TOKEN)[0], 400)
        self.assertEqual(self.call("/edge/register", "POST", b'{"x":1}', TOKEN)[0], 400)
        self.assertEqual(self.call("/nope")[0], 404)
        self.assertEqual(self.call("/edge/register", "POST", b"a" * 9000, TOKEN)[0], 413)
        status, body = self.call("/edge/status", "GET", None, TOKEN)
        self.assertEqual(status, 200)
        self.assertNotIn(TOKEN, body)
        payload = json.dumps({"device_id": "d2", "model_api_key": "x"}).encode()
        self.assertEqual(self.call("/edge/register", "POST", payload, TOKEN)[0], 400)

    def test_fail_closed_without_token(self):
        with patch.dict(os.environ, {"HG_EDGE_TOKEN": ""}, clear=False):
            self.assertFalse(edge.authenticated("Bearer anything"))


class PhoneTests(unittest.TestCase):
    def test_local_and_offline(self):
        with tempfile.TemporaryDirectory() as d:
            rt = PhoneRuntime(state_dir=d, edge_url="http://127.0.0.1:9", edge_token="x", timeout=0.4)
            self.assertTrue(rt.health()["ok"])
            self.assertFalse(rt.heartbeat())
            s = rt.start_session()
            self.assertEqual(s["product"], "HG")
            self.assertEqual(rt.store.audit_export()["events"], 2)

    def test_edge_roundtrip(self):
        p = patch.dict(os.environ, {"HG_EDGE_TOKEN": TOKEN}, clear=False)
        p.start()
        self.addCleanup(p.stop)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), edge.Handler)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            with tempfile.TemporaryDirectory() as d:
                rt = PhoneRuntime(state_dir=d, edge_url="http://127.0.0.1:%d" % srv.server_port, edge_token=TOKEN, device_id="phone-t")
                self.assertTrue(rt.register())
                self.assertTrue(rt.heartbeat())
                self.assertIn("phone-t", edge.DEVICES)
        finally:
            srv.shutdown()
            srv.server_close()
            th.join(timeout=2)
