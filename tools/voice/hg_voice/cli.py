"""On-demand CLI foundation. Commands are read-only; no model downloads or mic access."""
import argparse
import json
import sys
from pathlib import Path
from . import __version__
from .errors import ErrorCode
from .manifest import ManifestError, load_manifest, verify_artifact
from .registry import list_engines

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "models.example.json"

def build_parser():
    parser = argparse.ArgumentParser(prog="hg-voice", description="Standalone HG2 voice tools (no background recording).")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="read-only local manifest path")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="read-only environment and manifest check")
    sub.add_parser("engines", help="list known engines and processing boundaries")
    verify = sub.add_parser("verify", help="verify a local artifact against a SHA-256 digest")
    verify.add_argument("path", type=Path)
    verify.add_argument("--sha256", required=True)
    return parser

def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        if args.command == "engines":
            print(json.dumps([e.__dict__ if hasattr(e, "__dict__") else {k: getattr(e, k) for k in e.__dataclass_fields__} for e in list_engines()], indent=2))
            return 0
        if args.command == "verify":
            ok = verify_artifact(args.path, args.sha256)
            print(json.dumps({"verified": ok, "path_exists": args.path.is_file()}))
            return 0 if ok else 6
        if args.command == "doctor":
            print(json.dumps({"tool": "hg-voice", "version": __version__, "python": sys.version.split()[0], "manifest": str(args.manifest), "manifest_valid": True, "engine_count": len(manifest["engines"]), "microphone_accessed": False, "network_used": False, "downloads_performed": False, "runtime_integration": False, "status": "FOUNDATION_ONLY"}, indent=2))
            return 0
    except ManifestError:
        print(json.dumps({"error_code": ErrorCode.OPERATION_FAILED, "message": "manifest validation failed"}), file=sys.stderr)
        return 6
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
