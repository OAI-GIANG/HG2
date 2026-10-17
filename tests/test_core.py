import json, os, shutil, subprocess, sys, tempfile, threading, unittest, urllib.error, urllib.request
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from hg import edge
from hg.authority import ALLOWED, FORBIDDEN, authorize
from hg.history import GENESIS_EVENT, ZERO, HistoryError, StateStore, digest
from hg.identity import PRODUCT_ID, identity
from hg.phone_runtime import PhoneRuntime
from hg.sqlite_state import SQLiteStateStore

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "edge-token-x"


def lines(d):
    with open(os.path.join(d, "history.jsonl"), encoding="utf-8") as stream:
        return [line for line in stream.read().splitlines() if line.strip()]


def put(d, ls):
    with open(os.path.join(d, "history.jsonl"), "w", encoding="utf-8") as stream:
        stream.write("\n".join(ls) + "\n")


class IdentityTests(unittest.TestCase):
    def test_identity(self):
        self.assertEqual(PRODUCT_ID, "HG")
        self.assertEqual(identity()["origin"], "clean_room_parentless_genesis")

    def test_no_legacy_reference(self):
        found = []
        for base, _dirs, files in os.walk(os.path.join(ROOT, "hg")):
            for name in files:
                if name.endswith(".py"):
                    with open(os.path.join(base, name), encoding="utf-8") as stream:
                        text = stream.read().lower()
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
        with open(os.path.join(d, "head.json"), "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"seq": 99, "head_hash": ZERO}))
        self.assertEqual(s.verify()["reason"], "checkpoint_mismatch")
        with self.assertRaises(HistoryError):
            StateStore(d)

    def test_duplicate_json_keys_in_history_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            s = StateStore(d, clock=lambda: 1750000000.0)
            raw = lines(d)[0]
            self.assertIn('"seq":1', raw)
            put(d, [raw.replace('"seq":1', '"seq":1,"seq":1', 1)])
            self.assertFalse(s.verify()["ok"])
            with self.assertRaises(HistoryError):
                StateStore(d)

    def test_non_standard_json_constant_in_history_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            s = StateStore(d, clock=lambda: 1750000000.0)
            raw = lines(d)[0]
            self.assertIn('"recorded_at":1750000000.0', raw)
            put(d, [raw.replace('"recorded_at":1750000000.0', '"recorded_at":NaN', 1)])
            self.assertFalse(s.verify()["ok"])
            with self.assertRaises(HistoryError):
                StateStore(d)

    def test_duplicate_json_keys_in_checkpoint_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            s = StateStore(d, clock=lambda: 1750000000.0)
            with open(os.path.join(d, "head.json"), encoding="utf-8") as stream:
                raw = stream.read()
            self.assertIn('"seq":1', raw)
            with open(os.path.join(d, "head.json"), "w", encoding="utf-8") as stream:
                stream.write(raw.replace('"seq":1', '"seq":1,"seq":1', 1))
            self.assertEqual(s.verify()["reason"], "malformed_checkpoint")
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
            try:
                return e.code, e.read().decode()
            finally:
                e.close()

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

    def test_sqlite_backend_is_explicit_opt_in_and_offline_capable(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"HG_STATE_BACKEND": "sqlite"}, clear=False):
            rt = PhoneRuntime(state_dir=d, edge_url="http://127.0.0.1:9", edge_token="x", timeout=0.1)
            try:
                self.assertTrue(rt.health()["ok"])
                self.assertFalse(rt.heartbeat())
                session = rt.start_session()
                self.assertEqual(session["product"], "HG")
                self.assertEqual(rt.store.audit_export()["events"], 2)
                self.assertTrue(os.path.exists(os.path.join(d, "hg2-state.sqlite3")))
            finally:
                rt.store.close()

    def test_sqlite_backend_refuses_legacy_state_without_migration(self):
        with tempfile.TemporaryDirectory() as d:
            StateStore(d)
            with patch.dict(os.environ, {"HG_STATE_BACKEND": "sqlite"}, clear=False):
                with self.assertRaisesRegex(RuntimeError, "HG_STATE_MIGRATION_REQUIRED"):
                    PhoneRuntime(state_dir=d)

    def test_mixed_state_backends_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            sqlite_store = SQLiteStateStore(d)
            sqlite_store.close()
            StateStore(d)
            with patch.dict(os.environ, {"HG_STATE_BACKEND": "sqlite"}, clear=False):
                with self.assertRaisesRegex(RuntimeError, "HG_STATE_BACKEND_CONFLICT"):
                    PhoneRuntime(state_dir=d)

    def test_unknown_state_backend_fails_closed(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"HG_STATE_BACKEND": "invalid"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "UNSUPPORTED_HG_STATE_BACKEND"):
                PhoneRuntime(state_dir=d)

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
