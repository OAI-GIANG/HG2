"""POSIX process supervision for explicitly registered local adapters.

This module is intentionally separate from RemoteDesktopCommander admission.
It accepts argv sequences only (never a shell string), starts a new process
session, and kills that process group when a deadline expires or cancellation
is requested. This is local-runtime evidence, not proof of a remote desktop
target adapter.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Sequence


class ProcessSupervisorError(RuntimeError):
    """Stable process supervision failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ProcessResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    status: str


class PosixProcessSupervisor:
    """Run a local argv command with deadline and process-group termination.

    Available only on POSIX platforms exposing start_new_session and killpg.
    The caller must provide an allowlisted executable/argv; this class is not
    a policy layer and must not be used as a general remote shell executor.
    """

    def __init__(self, *, termination_grace_seconds: float = 0.25):
        if os.name != "posix" or not hasattr(os, "killpg"):
            raise ProcessSupervisorError("PROCESS_SUPERVISOR_POSIX_REQUIRED")
        if (isinstance(termination_grace_seconds, bool)
                or not isinstance(termination_grace_seconds, (int, float))
                or not 0 <= termination_grace_seconds <= 10):
            raise ProcessSupervisorError("PROCESS_SUPERVISOR_GRACE_INVALID")
        self.termination_grace_seconds = float(termination_grace_seconds)

    @staticmethod
    def _validate_argv(argv: Sequence[str]) -> tuple[str, ...]:
        if isinstance(argv, (str, bytes)) or not isinstance(argv, (list, tuple)):
            raise ProcessSupervisorError("PROCESS_ARGV_SEQUENCE_REQUIRED")
        if not argv or len(argv) > 128:
            raise ProcessSupervisorError("PROCESS_ARGV_INVALID")
        if any(not isinstance(x, str) or not x or "\x00" in x or len(x) > 8192 for x in argv):
            raise ProcessSupervisorError("PROCESS_ARGV_INVALID")
        if not os.path.isabs(argv[0]):
            raise ProcessSupervisorError("PROCESS_EXECUTABLE_MUST_BE_ABSOLUTE")
        return tuple(argv)

    @staticmethod
    def _validate_timeout(timeout_seconds: float) -> float:
        if (isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or not 0.01 <= timeout_seconds <= 3600):
            raise ProcessSupervisorError("PROCESS_TIMEOUT_INVALID")
        return float(timeout_seconds)

    def run(self, argv: Sequence[str], *, timeout_seconds: float,
            cwd: str | None = None, env: dict[str, str] | None = None) -> ProcessResult:
        """Run and collect output. Deadline expiry terminates the entire process group."""
        args = self._validate_argv(argv)
        timeout = self._validate_timeout(timeout_seconds)
        start = time.monotonic()
        try:
            child = subprocess.Popen(
                args,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                close_fds=True,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            raise ProcessSupervisorError("PROCESS_START_FAILED") from exc

        try:
            stdout, stderr = child.communicate(timeout=timeout)
            return ProcessResult(args, int(child.returncode), stdout, stderr,
                                 time.monotonic() - start, "COMPLETED")
        except subprocess.TimeoutExpired:
            self._terminate_group(child)
            stdout, stderr = child.communicate()
            return ProcessResult(args, int(child.returncode), stdout, stderr,
                                 time.monotonic() - start, "TIMED_OUT")

    def cancel(self, process: subprocess.Popen[str]) -> ProcessResult:
        """Cancel a process started by a caller with start_new_session=True."""
        if not isinstance(process, subprocess.Popen) or process.pid <= 0:
            raise ProcessSupervisorError("PROCESS_HANDLE_INVALID")
        start = time.monotonic()
        self._terminate_group(process)
        try:
            stdout, stderr = process.communicate(timeout=self.termination_grace_seconds + 1)
        except subprocess.TimeoutExpired as exc:
            raise ProcessSupervisorError("PROCESS_REAP_TIMEOUT") from exc
        return ProcessResult(("<cancelled-process>",), int(process.returncode),
                             stdout, stderr, time.monotonic() - start, "CANCELLED")

    def _terminate_group(self, child: subprocess.Popen[str]) -> None:
        """TERM the process group, then KILL it if it does not finish promptly."""
        if child.poll() is not None:
            return
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        # Waiting only for the group leader is insufficient: descendants can
        # ignore SIGTERM and keep inherited stdout/stderr pipes open. After the
        # grace period, SIGKILL the whole group even if the leader has exited.
        if self.termination_grace_seconds:
            time.sleep(self.termination_grace_seconds)
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=max(1.0, self.termination_grace_seconds + 0.5))
        except subprocess.TimeoutExpired as exc:
            raise ProcessSupervisorError("PROCESS_REAP_TIMEOUT") from exc
