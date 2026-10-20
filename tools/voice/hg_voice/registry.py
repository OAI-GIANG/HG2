"""Static engine registry: metadata only, no model probing or network access."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Engine:
    id: str
    task: str
    processing: str
    status: str
    note: str

ENGINES = (
    Engine("whisper.cpp", "stt", "LOCAL", "candidate", "Requires an explicitly installed, hash-pinned executable and model."),
    Engine("espeak-ng", "tts", "LOCAL", "available-if-installed", "Produces a local WAV using bundled Vietnamese voices; intelligibility/quality has not been independently accepted."),
    Engine("vieneu-nano", "tts", "LOCAL", "blocked-unverified", "Termux inference and Vietnamese quality are not yet verified."),
    Engine("termux-system-tts", "tts", "DEVICE_SYSTEM_OR_UNKNOWN", "optional-unverified", "May use external services; disabled unless explicitly allowed."),
)

def list_engines():
    return list(ENGINES)
