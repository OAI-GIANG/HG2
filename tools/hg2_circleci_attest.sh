#!/usr/bin/env bash
set -eu
EVIDENCE_DIR="${1:?usage: hg2_circleci_attest.sh EVIDENCE_DIR}"
test -d "$EVIDENCE_DIR"

# Other branches run tests but do not mint provenance for this candidate.
if [ "${CIRCLE_BRANCH:-}" != "stt/hg2-unification-p0-20261016" ]; then
  echo "ATTESTATION_SKIPPED_NONCANDIDATE_BRANCH"
  exit 0
fi

test "$(git rev-parse HEAD)" = "${CIRCLE_SHA1:?missing CIRCLE_SHA1}"

COSIGN_VERSION="v3.1.3"
COSIGN_SHA256="4629c757b7618056f8ddd7e2625ae9fdd94c0372a65049520bc7d9df9efc7f71"
curl -fsSL --retry 3 \
  "https://github.com/sigstore/cosign/releases/download/${COSIGN_VERSION}/cosign-linux-amd64" \
  -o "$EVIDENCE_DIR/cosign"
printf '%s  %s\n' "$COSIGN_SHA256" "$EVIDENCE_DIR/cosign" | sha256sum -c -
chmod 700 "$EVIDENCE_DIR/cosign"

CIRCLECI_BIN="$(command -v circleci || true)"
if [ -z "$CIRCLECI_BIN" ]; then
  echo "PROV_UNVERIFIABLE: CircleCI environment CLI is not available in this executor" >&2
  exit 1
fi

# Token is deliberately never printed or persisted to the evidence directory.
SIGSTORE_ID_TOKEN="$("$CIRCLECI_BIN" run oidc get --claims '{"aud":"sigstore"}' --root-issuer)"
export SIGSTORE_ID_TOKEN
python - "$EVIDENCE_DIR/candidate-manifest.json" "$EVIDENCE_DIR/slsa-predicate.json" <<'PY'
import base64, hashlib, json, os, re, subprocess, sys
from pathlib import Path
manifest_path, predicate_path = map(Path, sys.argv[1:])
token = os.environ.get("SIGSTORE_ID_TOKEN", "")
parts = token.split(".")
if len(parts) != 3:
    raise SystemExit("PROV_UNTRUSTED_SOURCE: CircleCI OIDC token is not a JWT")
try:
    claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
except Exception as exc:
    raise SystemExit("PROV_UNTRUSTED_SOURCE: cannot decode OIDC claims") from exc
expected_sha = os.environ["CIRCLE_SHA1"]
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
audience = claims.get("aud")
if not (claims.get("iss") == "https://oidc.circleci.com" and
        (audience == "sigstore" or isinstance(audience, list) and "sigstore" in audience)):
    raise SystemExit("PROV_UNTRUSTED_SOURCE: unexpected CircleCI OIDC issuer/audience")
if claims.get("oidc.circleci.com/vcs-origin") != "github.com/OAI-GIANG/HG2":
    raise SystemExit("PROV_UNTRUSTED_SOURCE: OIDC repository claim mismatch")
if claims.get("oidc.circleci.com/vcs-ref") != "refs/heads/stt/hg2-unification-p0-20261016":
    raise SystemExit("PROV_UNTRUSTED_SOURCE: OIDC ref claim mismatch")
if claims.get("oidc.circleci.com/project-id") != os.environ.get("CIRCLE_PROJECT_ID"):
    raise SystemExit("PROV_UNTRUSTED_SOURCE: OIDC project claim mismatch")
definition_id = claims.get("oidc.circleci.com/pipeline-definition-id")
if not isinstance(definition_id, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", definition_id):
    raise SystemExit("PROV_MISSING: CircleCI pipeline-definition identity missing")
if expected_sha != head:
    raise SystemExit("PROV_MISMATCH: CIRCLE_SHA1 differs from checkout HEAD")
manifest_sha = manifest.get("commit_sha")
if manifest_sha != expected_sha:
    raise SystemExit("PROV_MISMATCH: candidate manifest is not bound to the checked-out commit")
project_id = os.environ["CIRCLE_PROJECT_ID"]
builder_id = f"https://circleci.com/api/v2/projects/{project_id}/pipeline-definitions/{definition_id}"
predicate = {
    "buildDefinition": {
        "buildType": "https://github.com/OAI-GIANG/HG2/blob/hg-genesis/contract/PROVENANCE_CONTRACT_V1.md",
        "externalParameters": {
            "repository": "https://github.com/OAI-GIANG/HG2",
            "ref": "refs/heads/stt/hg2-unification-p0-20261016",
            "commit": expected_sha,
            "workflow": "hg2-p0-strict-verify"
        },
        "resolvedDependencies": [{
            "uri": f"git+https://github.com/OAI-GIANG/HG2@{expected_sha}",
            "digest": {"gitCommit": expected_sha}
        }]
    },
    "runDetails": {
        "builder": {"id": builder_id},
        "metadata": {"invocationId": f"{os.environ.get('CIRCLE_WORKFLOW_ID','unknown')}/{os.environ.get('CIRCLE_BUILD_NUM','unknown')}"}
    }
}
predicate_path.write_text(json.dumps(predicate, sort_keys=True, indent=2) + "\n", encoding="utf-8")
os.chmod(predicate_path, 0o600)
print(json.dumps({"status":"PREDICATE_READY","commit":expected_sha,
                  "builder_id":builder_id,
                  "manifest_sha256":hashlib.sha256(manifest_path.read_bytes()).hexdigest()}))
PY

BUILDER_ID="$(python - "$EVIDENCE_DIR/slsa-predicate.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["runDetails"]["builder"]["id"])
PY
)"
"$EVIDENCE_DIR/cosign" attest-blob "$EVIDENCE_DIR/candidate-manifest.json" \
  --predicate "$EVIDENCE_DIR/slsa-predicate.json" \
  --type "https://slsa.dev/provenance/v1" \
  --bundle "$EVIDENCE_DIR/candidate-manifest.sigstore.json" \
  --yes --identity-token "$SIGSTORE_ID_TOKEN" \
  --fulcio-url "https://fulcio.sigstore.dev" \
  --rekor-url "https://rekor.sigstore.dev" \
  --oidc-issuer "https://oidc.circleci.com" \
  --use-signing-config=false \
  > "$EVIDENCE_DIR/attestation-sign.log" 2>&1

"$EVIDENCE_DIR/cosign" verify-blob-attestation "$EVIDENCE_DIR/candidate-manifest.json" \
  --bundle "$EVIDENCE_DIR/candidate-manifest.sigstore.json" \
  --certificate-identity "$BUILDER_ID" \
  --certificate-oidc-issuer "https://oidc.circleci.com" \
  --type "slsaprovenance1" \
  --rekor-url "https://rekor.sigstore.dev" \
  > "$EVIDENCE_DIR/attestation-verification.log" 2>&1

python - "$EVIDENCE_DIR/candidate-manifest.json" "$EVIDENCE_DIR/slsa-predicate.json" \
  "$EVIDENCE_DIR/candidate-manifest.sigstore.json" "$EVIDENCE_DIR/attestation-verification.json" <<'PY'
import base64, hashlib, json, os, subprocess, sys
from pathlib import Path
manifest, predicate, bundle_path, result_path = map(Path, sys.argv[1:])
bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
cert_b64 = bundle.get("verificationMaterial", {}).get("certificate", {}).get("rawBytes")
if not isinstance(cert_b64, str):
    raise SystemExit("PROV_UNVERIFIABLE: Sigstore bundle has no certificate")
cert_path = bundle_path.with_name("attestation-certificate.der")
cert_path.write_bytes(base64.b64decode(cert_b64))
cert_text = subprocess.check_output(
    ["openssl", "x509", "-inform", "DER", "-in", str(cert_path), "-noout", "-text"],
    text=True, stderr=subprocess.STDOUT)
required = ["https://circleci.com/api/v2/projects/" + os.environ["CIRCLE_PROJECT_ID"] + "/pipeline-definitions/",
            "github.com/OAI-GIANG/HG2", "refs/heads/stt/hg2-unification-p0-20261016"]
if any(value not in cert_text for value in required):
    raise SystemExit("PROV_MISMATCH: certificate identity/repository/ref claims mismatch")
payload_b64 = bundle.get("dsseEnvelope", {}).get("payload")
if not isinstance(payload_b64, str):
    raise SystemExit("PROV_UNVERIFIABLE: Sigstore bundle has no DSSE payload")
statement = json.loads(base64.b64decode(payload_b64))
expected_predicate = json.loads(predicate.read_text(encoding="utf-8"))
expected_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
subjects = statement.get("subject", [])
if statement.get("predicateType") != "https://slsa.dev/provenance/v1" or \
   statement.get("predicate") != expected_predicate or \
   not any(item.get("digest", {}).get("sha256") == expected_sha for item in subjects):
    raise SystemExit("PROV_MISMATCH: signed DSSE statement does not bind the expected commit/predicate/manifest")
result = {
    "status": "PASS",
    "issuer": "https://oidc.circleci.com",
    "builder_id": expected_predicate["runDetails"]["builder"]["id"],
    "repository": "github.com/OAI-GIANG/HG2",
    "ref": "refs/heads/stt/hg2-unification-p0-20261016",
    "commit": expected_predicate["buildDefinition"]["externalParameters"]["commit"],
    "manifest_sha256": expected_sha,
    "bundle_sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
    "verification": "cosign signature, Fulcio identity and Rekor inclusion verified",
    "trust_status": "EXTERNAL_KEYLESS_ATTESTATION_VERIFIED"
}
result_path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
os.chmod(result_path, 0o600)
print(json.dumps(result, sort_keys=True))
PY
