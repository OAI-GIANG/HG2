"""Local Vietnamese TTS via eSpeak NG; no network, model downloads, or text in argv."""
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import wave

from ..errors import ErrorCode
from ..manifest import sha256_file

MAX_TEXT_CHARS = 10_000
MAX_WAV_BYTES = 32 * 1024 * 1024
MAX_DURATION_SECONDS = 180
ALLOWED_VOICES = frozenset({"vi", "vi-vn-x-central", "vi-vn-x-south"})


class EspeakTTSAdapterError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TTSResult:
    path: str
    sha256: str
    size_bytes: int
    sample_rate_hz: int
    channels: int
    duration_seconds: float
    voice: str
    engine: str = "espeak-ng"
    processing: str = "LOCAL"

    def as_dict(self):
        return {
            "engine": self.engine,
            "processing": self.processing,
            "voice": self.voice,
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "duration_seconds": round(self.duration_seconds, 3),
        }


class EspeakNgAdapter:
    """Synthesize UTF-8 Vietnamese text into a validated PCM WAV artifact."""

    def __init__(self, executable: str | None = None, timeout_seconds: float = 60.0):
        candidate = executable or "espeak-ng"
        resolved = shutil.which(candidate) if not Path(candidate).is_absolute() else candidate
        if not resolved or not Path(resolved).is_file() or not os.access(resolved, os.X_OK):
            raise EspeakTTSAdapterError(ErrorCode.TTS_BACKEND_UNAVAILABLE, "eSpeak NG executable is unavailable")
        if timeout_seconds <= 0 or timeout_seconds > 180:
            raise ValueError("timeout_seconds must be in (0, 180]")
        self.executable = str(Path(resolved).resolve())
        self.timeout_seconds = float(timeout_seconds)

    @staticmethod
    def _validate_text(text: str, voice: str, rate: int) -> None:
        if not isinstance(text, str) or not text.strip() or "\x00" in text:
            raise EspeakTTSAdapterError(ErrorCode.INVALID_ARGUMENT, "text must be non-empty UTF-8 text")
        if len(text) > MAX_TEXT_CHARS:
            raise EspeakTTSAdapterError(ErrorCode.INVALID_ARGUMENT, "text exceeds the configured character limit")
        if voice not in ALLOWED_VOICES:
            raise EspeakTTSAdapterError(ErrorCode.INVALID_ARGUMENT, "voice must be one of the registered Vietnamese voices")
        if type(rate) is not int or not 90 <= rate <= 220:
            raise EspeakTTSAdapterError(ErrorCode.INVALID_ARGUMENT, "rate must be an integer from 90 to 220")

    @staticmethod
    def _inspect_wav(path: Path):
        try:
            size = path.stat().st_size
            if size < 44 or size > MAX_WAV_BYTES:
                raise ValueError("WAV size is outside the allowed range")
            with wave.open(str(path), "rb") as wav:
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                rate = wav.getframerate()
                frames = wav.getnframes()
                compression = wav.getcomptype()
            duration = frames / rate if rate else 0.0
            if channels not in (1, 2) or sample_width != 2 or not 8_000 <= rate <= 48_000:
                raise ValueError("unsupported WAV format")
            if compression != "NONE" or frames <= 0 or duration <= 0 or duration > MAX_DURATION_SECONDS:
                raise ValueError("invalid WAV duration or encoding")
            return size, rate, channels, duration
        except (OSError, EOFError, wave.Error, ValueError) as exc:
            raise EspeakTTSAdapterError(ErrorCode.ENGINE_FAILED, "generated audio failed WAV validation") from exc

    def synthesize_to_wav(self, text: str, output_path: Path, voice: str = "vi", rate: int = 135, overwrite: bool = False) -> TTSResult:
        self._validate_text(text, voice, rate)
        target = Path(output_path).expanduser()
        try:
            if target.is_symlink():
                raise EspeakTTSAdapterError(ErrorCode.OUTPUT_WRITE_FAILED, "symbolic-link output is not permitted")
            target = target.resolve(strict=False)
            if target.exists() and not overwrite:
                raise EspeakTTSAdapterError(ErrorCode.OUTPUT_WRITE_FAILED, "output already exists; pass overwrite explicitly to replace it")
            if not target.parent.is_dir():
                raise EspeakTTSAdapterError(ErrorCode.OUTPUT_WRITE_FAILED, "output directory is unavailable")
            fd, temp_name = tempfile.mkstemp(prefix=".hg-voice-", suffix=".wav", dir=str(target.parent))
            os.close(fd)
            temp_path = Path(temp_name)
            os.chmod(temp_path, 0o600)
        except EspeakTTSAdapterError:
            raise
        except OSError as exc:
            raise EspeakTTSAdapterError(ErrorCode.OUTPUT_WRITE_FAILED, "unable to prepare output file") from exc

        try:
            try:
                completed = subprocess.run(
                    [self.executable, "-v", voice, "-s", str(rate), "-w", str(temp_path), "--stdin"],
                    input=text,
                    text=True,
                    encoding="utf-8",
                    errors="strict",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise EspeakTTSAdapterError(ErrorCode.ENGINE_TIMEOUT, "speech synthesis timed out") from exc
            except (OSError, UnicodeError) as exc:
                raise EspeakTTSAdapterError(ErrorCode.TTS_BACKEND_UNAVAILABLE, "speech synthesis process could not run") from exc
            if completed.returncode != 0:
                raise EspeakTTSAdapterError(ErrorCode.ENGINE_FAILED, "speech synthesis failed")
            size, sample_rate, channels, duration = self._inspect_wav(temp_path)
            digest = sha256_file(temp_path)
            os.chmod(temp_path, 0o600)
            if overwrite:
                os.replace(temp_path, target)
            else:
                # Android's Bionic-backed Python may not expose os.link; reserve with O_EXCL.
                try:
                    out_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError as exc:
                    raise EspeakTTSAdapterError(ErrorCode.OUTPUT_WRITE_FAILED, "output already exists") from exc
                try:
                    with os.fdopen(out_fd, "wb") as out_stream, temp_path.open("rb") as in_stream:
                        shutil.copyfileobj(in_stream, out_stream, length=1024 * 1024)
                        out_stream.flush()
                        os.fsync(out_stream.fileno())
                except OSError:
                    target.unlink(missing_ok=True)
                    raise
                finally:
                    temp_path.unlink(missing_ok=True)
            return TTSResult(str(target), digest, size, sample_rate, channels, duration, voice)
        except EspeakTTSAdapterError:
            temp_path.unlink(missing_ok=True)
            raise
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise EspeakTTSAdapterError(ErrorCode.OUTPUT_WRITE_FAILED, "unable to finalize audio output") from exc


def play_wav(path: Path, player: str = "play-audio", timeout_seconds: float = 90.0) -> dict:
    """Play an existing local WAV with Termux's local OpenSLES audio player."""
    target = Path(path).expanduser().resolve(strict=False)
    if not target.is_file():
        raise EspeakTTSAdapterError(ErrorCode.OUTPUT_WRITE_FAILED, "audio file does not exist")
    EspeakNgAdapter._inspect_wav(target)
    resolved = shutil.which(player) if not Path(player).is_absolute() else player
    if not resolved or not Path(resolved).is_file() or not os.access(resolved, os.X_OK):
        raise EspeakTTSAdapterError(ErrorCode.PLAYBACK_UNAVAILABLE, "local audio player is unavailable")
    try:
        completed = subprocess.run(
            [str(resolved), str(target)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            shell=False, timeout=timeout_seconds, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise EspeakTTSAdapterError(ErrorCode.ENGINE_TIMEOUT, "audio playback timed out") from exc
    except OSError as exc:
        raise EspeakTTSAdapterError(ErrorCode.PLAYBACK_UNAVAILABLE, "local audio player could not run") from exc
    if completed.returncode != 0:
        raise EspeakTTSAdapterError(ErrorCode.ENGINE_FAILED, "audio playback failed")
    return {"played": True, "player": Path(resolved).name, "exit_code": completed.returncode}
