# HG2 Semantic Runner Receipt V1

Status: verifier implemented and unit-tested in the candidate workspace; production trust root and an authenticated receipt from the actual CI runner are not provisioned yet.

## Claims bound by the signed receipt

The receipt records repository, runner identity and image digest, full Git commit and tree, clean working tree claim, exact suite ID and argv command, suite digest, OS/architecture/Python, timestamps, exit code, semantic test counts, and SHA-256 plus byte size for both captured logs.

The receipt body uses canonical UTF-8 JSON (sorted keys, compact separators, one trailing newline) and is signed with OpenSSH ssh-keygen -Y sign in namespace hg2-runner-receipt. The verifier uses ssh-keygen -Y verify and binds the signer to the expected runner identity. It rehashes the actual log bytes, requires exit code zero, a positive test count, zero failures/errors, exactly one matching unittest summary line, an OK terminal line, and no FAILED terminal line.

## Trust-root rule

The trust root is not the receipt itself, a self-declared digest, a public repository file, or a runner-provided unsigned value. An administrator must provision the allowed-signers file outside the repository. The expected SHA-256 pin must be delivered through a separate trusted channel. The verifier rejects a root located inside the repository, symlinks, unsafe write permissions, missing/mismatched root pins, untrusted signatures, a mismatched signer identity, a mismatched image digest, and a suite command that differs from the separately expected command.

The test suite generates ephemeral Ed25519 keys only for isolated unit tests. Those temporary keys are destroyed with the test directory and are not trusted production identities. Until the actual CI runner signs a receipt under an independently provisioned key whose pin is delivered independently, production semantic verification remains BLOCKED.

## Strict receipt object schema

- schema_version: HG2_SEMANTIC_RUNNER_RECEIPT_V1
- repository: OAI-GIANG/HG2
- runner: id, signer, image_digest
- source: commit, tree, working_tree_clean=true
- suite: id, command (argv array), suite_sha256
- environment: os, architecture, python
- execution: started_at, finished_at, exit_code, stdout, stderr, test_summary (total, failures, errors)

The stdout/stderr objects each have path, sha256 and bytes. Paths are relative to the receipt bundle and reject traversal and symlink escapes; each log is limited to 32 MiB. The verifier compares the received values to expected values supplied separately by the verifying policy: repository, commit/tree, suite ID/argv/digest, environment, runner ID/image digest, and trust-root pin.

## CLI

The expected values below must come from independently provisioned CI/admin configuration, not be copied from the receipt under verification:

    python3 -m hg.runner_receipt \
      --receipt evidence/<run>/receipt.json \
      --signature evidence/<run>/receipt.json.sig \
      --trusted-signers "$HG2_TRUSTED_SIGNERS_FILE" \
      --repository-root . \
      --expected-commit "$HG2_EXPECTED_COMMIT" \
      --expected-tree "$HG2_EXPECTED_TREE" \
      --expected-suite-id "$HG2_EXPECTED_SUITE_ID" \
      --expected-suite-command-json "$HG2_EXPECTED_SUITE_COMMAND_JSON" \
      --expected-suite-sha256 "$HG2_EXPECTED_SUITE_SHA256" \
      --expected-runner-image-digest "$HG2_EXPECTED_RUNNER_IMAGE_DIGEST" \
      --expected-trust-root-sha256 "$HG2_TRUSTED_SIGNERS_SHA256" \
      --expected-environment-json "$HG2_EXPECTED_ENVIRONMENT_JSON" \
      --expected-runner-id "$HG2_EXPECTED_RUNNER_ID"

A VERIFIED result means the named configured signer authenticated the claim and the declared test/log semantics match policy. It is not a mathematical proof of code correctness; trust depends on the independently operated signer and the correctness of the runner itself.

## Design references

- SLSA Build Provenance v1.2: https://slsa.dev/spec/v1.2/build-provenance
- in-toto Attestation framework: https://github.com/in-toto/attestation
- SQLite transaction guarantees: https://www.sqlite.org/transactional.html

SQLite transaction atomicity by itself does not prove application-level outbox delivery, remote deduplication, or acknowledgement reconciliation.
