"""On-demand CLI: no background recording, implicit downloads, or provider fallback."""
import argparse
import json
import shutil
import sys
from pathlib import Path
from . import __version__
from .errors import ErrorCode
from .manifest import ManifestError, load_manifest, verify_artifact
from .registry import list_engines
from .adapters.espeakng import EspeakNgAdapter, EspeakTTSAdapterError, play_wav

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "models.example.json"
VOICE_CHOICES = ("vi", "vi-vn-x-central", "vi-vn-x-south")


def build_parser():
    parser = argparse.ArgumentParser(prog="hg-voice", description="Standalone HG2 voice tools (explicit, on-demand operations).")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="read-only local manifest path")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="read-only environment and manifest check")
    sub.add_parser("engines", help="list known engines and processing boundaries")
    verify = sub.add_parser("verify", help="verify a local artifact against a SHA-256 digest")
    verify.add_argument("path", type=Path)
    verify.add_argument("--sha256", required=True)
    tts = sub.add_parser("tts", help="synthesize a UTF-8 text file into a local WAV")
    tts.add_argument("--text-file", required=True, type=Path, help="UTF-8 text file; spoken text is not accepted on the command line")
    tts.add_argument("--output", required=True, type=Path, help="new WAV output path")
    tts.add_argument("--voice", choices=VOICE_CHOICES, default="vi", help="Vietnamese eSpeak NG voice (default: northern Vietnamese)")
    tts.add_argument("--rate", type=int, default=135, help="speech rate, 90–220 (default: 135)")
    tts.add_argument("--overwrite", action="store_true", help="explicitly allow replacing an existing output file")
    tts.add_argument("--play", action="store_true", help="play the generated WAV using the local play-audio utility")
    play = sub.add_parser("play", help="play an existing validated PCM WAV locally")
    play.add_argument("path", type=Path)
    return parser


def _exit_for_error(code):
    if code == ErrorCode.INVALID_ARGUMENT:
        return 2
    if code in {ErrorCode.MODEL_NOT_INSTALLED, ErrorCode.ENGINE_UNAVAILABLE, ErrorCode.TTS_BACKEND_UNAVAILABLE, ErrorCode.PLAYBACK_UNAVAILABLE}:
        return 3
    if code in {ErrorCode.MICROPHONE_CONSENT_REQUIRED, ErrorCode.NONLOCAL_PROCESSING_DISABLED}:
        return 4
    if code == ErrorCode.ARTIFACT_DIGEST_MISMATCH:
        return 6
    return 5


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        if args.command == "engines":
            print(json.dumps([{k: getattr(e, k) for k in e.__dataclass_fields__} for e in list_engines()], ensure_ascii=False, indent=2))
            return 0
        if args.command == "verify":
            ok = verify_artifact(args.path, args.sha256)
            print(json.dumps({"verified": ok, "path_exists": args.path.is_file()}))
            return 0 if ok else 6
        if args.command == "doctor":
            espeak_available = shutil.which("espeak-ng") is not None
            player_available = shutil.which("play-audio") is not None
            print(json.dumps({
                "tool": "hg-voice", "version": __version__, "python": sys.version.split()[0],
                "manifest": str(args.manifest), "manifest_valid": True, "engine_count": len(manifest["engines"]),
                "tts": {"engine": "espeak-ng", "available": espeak_available, "processing": "LOCAL",
                        "audio_player_available": player_available, "quality_acceptance": "NOT_ASSESSED"},
                "microphone_accessed": False, "network_used": False, "downloads_performed": False,
                "runtime_integration": False,
                "status": "TTS_ENGINE_AVAILABLE_QUALITY_NOT_ACCEPTED" if espeak_available else "FOUNDATION_ONLY",
            }, ensure_ascii=False, indent=2))
            return 0
        if args.command == "tts":
            try:
                text = args.text_file.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                raise EspeakTTSAdapterError(ErrorCode.INVALID_ARGUMENT, "text file could not be read as UTF-8")
            adapter = EspeakNgAdapter()
            result = adapter.synthesize_to_wav(text, args.output, voice=args.voice, rate=args.rate, overwrite=args.overwrite)
            response = {"synthesis": "PASS", "audio": result.as_dict(), "playback": None,
                        "quality_acceptance": "NOT_ASSESSED", "network_used": False}
            if args.play:
                response["playback"] = play_wav(Path(result.path))
            print(json.dumps(response, ensure_ascii=False, indent=2))
            return 0
        if args.command == "play":
            result = play_wav(args.path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
    except ManifestError:
        print(json.dumps({"error_code": ErrorCode.OPERATION_FAILED.value, "message": "manifest validation failed"}), file=sys.stderr)
        return 6
    except EspeakTTSAdapterError as exc:
        print(json.dumps({"error_code": exc.code.value, "message": str(exc)}), file=sys.stderr)
        return _exit_for_error(exc.code)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
