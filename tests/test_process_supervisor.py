import os
import subprocess
import sys
import time
import unittest

from hg.process_supervisor import PosixProcessSupervisor, ProcessSupervisorError


@unittest.skipUnless(os.name == "posix" and hasattr(os, "killpg"),
                     "requires POSIX process-group signaling")
class PosixProcessSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.supervisor = PosixProcessSupervisor(termination_grace_seconds=0.05)

    def test_completes_allowlisted_argv_without_shell(self):
        result = self.supervisor.run(
            [sys.executable, "-c", "print('ok')"], timeout_seconds=2
        )
        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "ok")

    def test_timeout_terminates_and_reaps_local_process(self):
        result = self.supervisor.run(
            [sys.executable, "-c", "import time; time.sleep(20)"],
            timeout_seconds=0.1,
        )
        self.assertEqual(result.status, "TIMED_OUT")
        self.assertNotEqual(result.returncode, 0)
        self.assertLess(result.elapsed_seconds, 3)

    def test_explicit_cancellation_terminates_and_reaps_process(self):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(20)"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, start_new_session=True,
        )
        result = self.supervisor.cancel(process)
        self.assertEqual(result.status, "CANCELLED")
        self.assertIsNotNone(process.poll())
        self.assertNotEqual(result.returncode, 0)

    def test_timeout_kills_child_process_group(self):
        # Parent spawns a grandchild which ignores SIGTERM. The supervisor's
        # process-group SIGKILL must prevent it from continuing after timeout.
        script = (
            "import signal, subprocess, sys, time; "
            "p=subprocess.Popen([sys.executable,'-c',"
            "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(20)']); "
            "print(p.pid, flush=True); time.sleep(20)"
        )
        result = self.supervisor.run([sys.executable, "-c", script], timeout_seconds=0.15)
        self.assertEqual(result.status, "TIMED_OUT")
        self.assertTrue(result.stdout.strip())
        grandchild_pid = int(result.stdout.strip().splitlines()[0])
        # Linux /proc state Z means the grandchild was killed but not yet reaped
        # by init; it is no longer running. If /proc is unavailable, skip this
        # process-state detail rather than claiming stronger evidence.
        status_path = f"/proc/{grandchild_pid}/stat"
        if os.path.exists(status_path):
            deadline = time.monotonic() + 1.5
            state = None
            while time.monotonic() < deadline:
                try:
                    with open(status_path, encoding="utf-8") as stream:
                        state = stream.read().split()[2]
                except (FileNotFoundError, ProcessLookupError):
                    state = None
                    break
                if state == "Z":
                    break
                time.sleep(0.02)
            self.assertIn(state, (None, "Z"), f"grandchild still active, state={state}")

    def test_timeout_kills_descendant_even_if_group_leader_exits_first(self):
        # The leader exits immediately; its child inherits stdout/stderr pipes and
        # ignores SIGTERM. Timeout handling must still kill the process group rather
        # than return early because the leader has already exited.
        script = (
            "import subprocess,sys; "
            "subprocess.Popen([sys.executable,'-c',"
            "'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(1.5)']); "
            "print('leader-exited', flush=True)"
        )
        result = self.supervisor.run([sys.executable, "-c", script], timeout_seconds=0.15)
        self.assertEqual(result.status, "TIMED_OUT")
        self.assertLess(result.elapsed_seconds, 1.0,
                        "descendant holding inherited pipes survived the timeout")

    def test_rejects_shell_strings_and_relative_executables(self):
        with self.assertRaisesRegex(ProcessSupervisorError, "PROCESS_ARGV_SEQUENCE_REQUIRED"):
            self.supervisor.run("echo unsafe", timeout_seconds=1)
        with self.assertRaisesRegex(ProcessSupervisorError, "PROCESS_EXECUTABLE_MUST_BE_ABSOLUTE"):
            self.supervisor.run(["python", "-c", "pass"], timeout_seconds=1)

    def test_rejects_invalid_timeout(self):
        for timeout in (0, -1, True, float("inf"), 3601):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ProcessSupervisorError):
                    self.supervisor.run([sys.executable, "-c", "pass"],
                                        timeout_seconds=timeout)


if __name__ == "__main__":
    unittest.main()
