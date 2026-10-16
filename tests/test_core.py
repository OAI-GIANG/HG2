import json, os, shutil, subprocess, sys, tempfile, unittest
from hg.authority import ALLOWED, FORBIDDEN, authorize
from hg.history import GENESIS_EVENT, ZERO, HistoryError, StateStore, digest
from hg.identity import PRODUCT_ID, identity
from hg.phone_runtime import PhoneRuntime


def _read_bytes(path):
    with open(path, "rb") as stream:
        return stream.read()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lines(d):
    with open(os.path.join(d, "history.jsonl"), encoding="utf-8") as fh:
        return [line for line in fh.read().splitlines() if line.strip()]


def put(d, ls):
    with open(os.path.join(d, "history.jsonl"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(ls) + "\n")


class IdentityTests(unittest.TestCase):
    def test_identity(self):
        self.assertEqual(PRODUCT_ID, "HG")
        self.assertEqual(identity()["origin"], "clean_room_parentless_genesis")

    def test_no_legacy_reference(self):
        found = []
        for base, _dirs, files in os.walk(os.path.join(ROOT, "hg")):
            for name in files:
                if name.endswith(".py"):
                    with open(os.path.join(base, name), encoding="utf-8") as fh:
                        text = fh.read().lower()
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

    def test_every_forbidden_and_unknown_action_fails_closed(self):
        self.assertTrue(FORBIDDEN)
        for action in FORBIDDEN:
            with self.subTest(action=action):
                decision = authorize(action, authenticated=True)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, "EXPLICITLY_FORBIDDEN")
        for action in ("", "unknown.action", "shell.exec ", None, 7):
            with self.subTest(action=action):
                self.assertFalse(authorize(action, authenticated=True).allowed)

    def test_allowlist_requires_auth_for_every_sensitive_action(self):
        for action in ALLOWED:
            with self.subTest(action=action):
                decision = authorize(action, authenticated=False)
                if action == "health.read":
                    self.assertTrue(decision.allowed)
                else:
                    self.assertFalse(decision.allowed)
                    self.assertEqual(decision.reason, "AUTHENTICATION_REQUIRED")
                self.assertEqual(authorize(action, authenticated=True).allowed, True)


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
        with open(os.path.join(d, "head.json"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"seq": 99, "head_hash": ZERO}))
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


class PhoneTests(unittest.TestCase):
    def test_local_only_runtime_has_no_network_integration(self):
        with tempfile.TemporaryDirectory() as d:
            rt = PhoneRuntime(state_dir=d, session_authenticator=lambda credential: credential == "test-credential")
            health = rt.health()
            self.assertTrue(health["ok"])
            self.assertFalse(health["network_integration"])
            session = rt.start_session(credential="test-credential")
            self.assertEqual(session["product"], "HG")
            self.assertEqual(rt.store.audit_export()["events"], 2)

    def test_session_creation_fails_closed_for_absent_or_invalid_verifier(self):
        with tempfile.TemporaryDirectory() as d:
            rt = PhoneRuntime(state_dir=d)
            before = _read_bytes(os.path.join(d, "history.jsonl"))
            with self.assertRaises(PermissionError):
                rt.start_session(credential="not-a-verified-credential")
            self.assertEqual(_read_bytes(os.path.join(d, "history.jsonl")), before)

        for verifier in (lambda credential: False, lambda credential: "true",
                         lambda credential: (_ for _ in ()).throw(RuntimeError("verifier unavailable"))):
            with tempfile.TemporaryDirectory() as d:
                rt = PhoneRuntime(state_dir=d, session_authenticator=verifier)
                before = _read_bytes(os.path.join(d, "history.jsonl"))
                with self.subTest(verifier=verifier), self.assertRaises(PermissionError):
                    rt.start_session(credential="not-a-verified-credential")
                self.assertEqual(_read_bytes(os.path.join(d, "history.jsonl")), before)


if __name__ == "__main__":
    unittest.main()
