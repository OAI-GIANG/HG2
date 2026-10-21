# MAEP 2.0 — Elevated Capability Integration

## Implemented in the isolated candidate

`hg/elevated_capability_registry.py` introduces a sealed-principal dispatcher for the declared elevated actions. The built-in `file.read` handler is a real, bounded read from configured `FilesystemEvidenceVerifier` roots. It requires the exact `file.read` scope, a relative allowlisted reference, and a matching SHA-256. Symlinks, path traversal, non-regular files, size violations and digest mismatch fail closed. The returned receipt distinguishes byte integrity from semantic truth.

The adapter can be registered in the existing `RuntimeCapabilityRegistry` as `security_verification/evidence.verify`, and can be bound to MAEP through `MaepHostBinding`, the existing canonical SQLite store and the real filesystem evidence verifier. The integration tests exercise both dispatch routes and one MAEP S0 checkpoint transition end-to-end using temporary fixtures only.

## Deliberately not implemented or enabled

`file.write`, `shell.exec`, `network.fetch`, `deploy`, `identity.change`, `state.import` and `provider.invoke` do not have built-in production handlers in this integration. Even when a principal carries those scopes, dispatch returns `ELEVATED_HANDLER_NOT_REGISTERED` until a fixed, reviewed adapter is registered. The registry does not convert prompts into shell commands, URLs, deployment instructions, identity mutations or import paths. Production routes and credentials are not changed.

## Evidence boundaries

- Fixture verification proves the test bytes matched the expected digest under the configured test root; it does not prove source authenticity or semantic truth.
- MAEP S0 fixture integration proves the registered read-only path, authorization, evidence checks, and same-store checkpoint transition; it is not production runtime integration.
- The runtime binding declares `hard_timeout_enforced=False`; no claim is made that arbitrary adapters are universally preempted by a hard timeout.
- Production HTTP runtime, services, durable data, and cutover state remain unchanged.
