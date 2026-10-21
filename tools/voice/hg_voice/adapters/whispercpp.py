"""Offline-only whisper.cpp subprocess adapter; never downloads or falls back remotely."""
import hashlib
import re
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..errors import ErrorCode

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_AUDIO_BYTES = 32 * 1024 * 1024
_MAX_DURATION_SECONDS = 30

class WhisperAdapterError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code

@dataclass(frozen=True)
class WhisperConfig:
    executable: Path
    model: Path
    executable_sha256: str
    model_sha256: str
    timeout_seconds: float = 30.0
    threads: int = 2
    max_audio_bytes: int = _MAX_AUDIO_BYTES
    max_duration_seconds: int = _MAX_DURATION_SECONDS

class WhisperCppAdapter:
    def __init__(self, config: WhisperConfig):
        self.config = config

    @staticmethod
    def _digest(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()

    def _check_artifact(self, path: Path, expected: str, label: str) -> None:
        if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
            raise WhisperAdapterError(ErrorCode.ARTIFACT_DIGEST_MISMATCH, f"invalid {label} SHA-256")
        if not path.is_file():
            code = ErrorCode.MODEL_NOT_INSTALLED if label == "model" else ErrorCode.ENGINE_UNAVAILABLE
            raise WhisperAdapterError(code, f"{label} artifact is not installed")
        if self._digest(path) != expected:
            raise WhisperAdapterError(ErrorCode.ARTIFACT_DIGEST_MISMATCH, f"{label} SHA-256 mismatch")

    def transcribe_wav(self, audio_path: Path, language: Optional[str] = "vi") -> str:
        cfg = self.config
        if language is not None and (not isinstance(language, str) or not re.fullmatch(r"[a-z]{2,3}", language)):
            raise WhisperAdapterError(ErrorCode.INVALID_ARGUMENT, "language must be a short language code")
        if cfg.timeout_seconds <= 0 or cfg.timeout_seconds > 300 or cfg.threads < 1 or cfg.threads > 8:
            raise WhisperAdapterError(ErrorCode.INVALID_ARGUMENT, "invalid timeout or thread limit")
        # Validate bounded, uncompressed PCM WAV before starting the subprocess.
        try:
            if not audio_path.is_file():
                raise WhisperAdapterError(ErrorCode.INVALID_AUDIO, "audio file does not exist")
            size = audio_path.stat().st_size
            if size <= 44 or size > min(cfg.max_audio_bytes, _MAX_AUDIO_BYTES):
                raise WhisperAdapterError(ErrorCode.INVALID_AUDIO, "audio size outside allowed bounds")
        except WhisperAdapterError:
            raise
        except (OSError, EOFError, wave.Error) as exc:
            raise WhisperAdapterError(ErrorCode.INVALID_AUDIO, "input is not a valid PCM WAV") from exc
        # Re-open explicitly; wave.getparams() tuple is stable on Python 3.10+.
        try:
            with wave.open(str(audio_path), "rb") as wav:
                params = wav.getparams()
                if params.comptype != "NONE" or params.nchannels not in (1, 2) or params.sampwidth not in (2, 4) or params.framerate not in (8000, 16000, 22050, 24000, 32000, 44100, 48000):
                    raise WhisperAdapterError(ErrorCode.INVALID_AUDIO, "unsupported WAV encoding")
                duration = params.nframes / params.framerate
                if duration <= 0 or duration > min(cfg.max_duration_seconds, _MAX_DURATION_SECONDS):
                    raise WhisperAdapterError(ErrorCode.INVALID_AUDIO, "audio duration outside allowed bounds")
        except WhisperAdapterError:
            raise
        except (OSError, EOFError, wave.Error) as exc:
            raise WhisperAdapterError(ErrorCode.INVALID_AUDIO, "input is not a valid PCM WAV") from exc

        self._check_artifact(cfg.executable, cfg.executable_sha256, "executable")
        self._check_artifact(cfg.model, cfg.model_sha256, "model")
        command = [str(cfg.executable), "-m", str(cfg.model), "-f", str(audio_path), "-t", str(cfg.threads), "--no-gpu", "--no-prints"]
        if language:
            command.extend(["-l", language])
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=cfg.timeout_seconds, check=False, shell=False, close_fds=True)
        except subprocess.TimeoutExpired as exc:
            raise WhisperAdapterError(ErrorCode.ENGINE_TIMEOUT, "local speech engine timed out") from exc
        except OSError as exc:
            raise WhisperAdapterError(ErrorCode.ENGINE_UNAVAILABLE, "local speech engine could not start") from exc
        if result.returncode != 0:
            raise WhisperAdapterError(ErrorCode.ENGINE_FAILED, "local speech engine failed")
        try:
            output = result.stdout.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError as exc:
            raise WhisperAdapterError(ErrorCode.ENGINE_FAILED, "engine output was not valid UTF-8") from exc
        if not output:
            raise WhisperAdapterError(ErrorCode.ENGINE_FAILED, "engine returned no transcript")
        return output
