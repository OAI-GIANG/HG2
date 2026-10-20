# Trust-root provisioning gap — R1

Status: BLOCKED_NOT_PROVISIONED

Read-only discovery found no actual runner signing identity, administrator-provisioned allowed-signers file, independently delivered fingerprint pin, or actual runner-signed receipt in the inspected scope. This is a bounded search finding, not proof such resources cannot exist elsewhere.

No production key was generated and no fingerprint was self-trusted. Unit tests use ephemeral test-only keys and cannot close this gate.

Closure requires CI/admin provisioning outside the repository, installing the public key into a restricted allowed-signers file, delivering that file's SHA-256 through an independent channel, an actual runner signing a receipt bound to commit/tree/suite/environment/log bytes, and independent verification/review.