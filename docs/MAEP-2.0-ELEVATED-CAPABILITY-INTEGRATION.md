# MAEP 2.0 — Elevated Capability Integration

## Implemented in the isolated candidate

`hg/elevated_capability_registry.py` introduces a sealed-principal dispatcher for the declared elevated actions. The built-in `file.read` handler is a real, bounded read from configured `FilesystemEvidenceVerifier` roots. It requires the exact `file.read` scope, a relative allowlisted reference, and a matching SHA-256. Symlinks, path traversal, non-regular files, size violations and digest mismatch fail closed. The returned receipt distinguishes byte integrity from semantic truth.

`file.write` is available only when the trusted host explicitly supplies separate `write_roots`. It accepts relative paths and content whose SHA-256 is predeclared, caps content at 1 MB by default, refuses symlinks/traversal, and publishes through a create-only atomic operation (no replacement of existing bytes). A retry to the same path with identical bytes returns `IDEMPOTENT_NOOP`; different bytes return `FILE_WRITE_TARGET_CONFLICT`. The temporary file is fsynced before publication, and injected interruption tests verify that no target or temporary file remains after a pre-publication failure. Write roots are not inferred from the evidence verifier roots.

`shell.exec` can be explicitly bound to a trusted `PosixLocalRdcAdapter` allowlist using `bind_registered_rdc_shell_exec`. The caller supplies only an allowlisted operation ID and typed arguments; target ID, source revision, risk class, required capabilities, and command envelope are assembled by trusted host code from the registered operation. The RDC gate rejects raw-shell operation IDs and command-like/secret argument keys, and the POSIX supervisor receives an argv sequence, never a shell string. High-risk registered operations still require an approval verifier. The integration test runs one harmless fixed local operation and proves an unregistered operation ID is denied.

The adapter can be registered in the existing `RuntimeCapabilityRegistry` as `security_verification/evidence.verify`, and can be bound to MAEP through `MaepHostBinding`, the existing canonical SQLite store and the real filesystem evidence verifier. The integration tests exercise both dispatch routes and one MAEP S0 checkpoint transition end-to-end using temporary fixtures only.

## Pending network/provider adapter contracts — design only

Neither adapter is implemented or registered. The following are admission requirements for a future reviewed implementation, not a grant of authority or a claim that numeric limits have been approved.

| Gate | `network.fetch` | `provider.invoke` |
|---|---|---|
| Principal and authorization | Sealed principal must carry exact `network.fetch` scope; host-owned scheme/host/port policy is mandatory. | Sealed principal must carry exact `provider.invoke` scope; provider and model IDs must come from a host-owned allowlist. |
| Destination / authentication | HTTPS by default; reject userinfo and ambiguous URL forms; validate DNS results and every redirect; block loopback, private, link-local, multicast, and metadata destinations unless a separately reviewed exception exists. TLS verification stays enabled. Caller-supplied credentials are forbidden. | Credentials come only from a host credential provider. Caller-supplied API keys, arbitrary base URLs, and unapproved model identifiers are forbidden. |
| Resource bounds | Explicit connect/read/total deadlines, bounded redirects, response-byte cap, bounded header count/size, and bounded concurrency must be configured before enablement. | Explicit request-byte/input-token/output-token caps, per-call deadline, retry budget, concurrency/rate limit, and cost/usage ceiling must be configured before enablement. |
| Outbound-data policy | Request URL, headers, and body must be schema-validated; secret-bearing headers/query parameters must not enter logs or evidence. | Outbound prompt/context requires an explicit data-classification and approval policy; no silent upload of local files, memory, or credentials. |
| Evidence | Record policy decision, request digest, sanitized destination, redirect decisions, status/content metadata, byte count, body SHA-256, timing, and a redacted error code. | Record provider/model, approval reference, request/output digests, timing, status, bounded usage/cost metadata when available, and redacted errors. Do not store raw secrets or unrestricted prompt/response bodies in audit logs. |
| Acceptance gate | Tests for DNS rebinding, redirect-to-private-IP, malformed URLs, TLS failure, oversized response, timeout/cancellation, credential leakage, and fail-closed policy denial. | Tests for missing/invalid approval, disallowed provider/model, oversized input/output, timeout, retry exhaustion, rate/cost limit, credential isolation, data-redaction, and fail-closed denial. |

No default timeout, redirect count, response limit, token budget, or cost ceiling is approved by this design note. Those values must be selected and reviewed per adapter before implementation. Both actions must remain unregistered until a fixed adapter, host-owned policy, bounded execution path, and evidence tests pass.

## Deliberately not implemented or enabled

`network.fetch`, `provider.invoke`, `deploy`, `identity.change` and `state.import` remain unregistered and fail closed. These require separate contracts: network fetch needs an explicit host/URL policy, redirect and response-size bounds, and SSRF controls; provider invocation needs explicit outbound-data approval and provider/request limits; deploy needs an operation-specific approval and rollback plan; identity change needs a verified identity-change authority contract; state import needs source provenance, loss/replay semantics, backup/rollback, and import-specific approval. A generic scope alone does not satisfy these gates. The registry never converts prompts into shell commands, arbitrary URLs, deployment instructions, identity mutations or import paths. Production routes and credentials are not changed.

## Evidence boundaries

- Fixture verification proves the test bytes matched the expected digest under the configured test root; it does not prove source authenticity or semantic truth.
- MAEP S0 fixture integration proves the registered read-only path, authorization, evidence checks, and same-store checkpoint transition; it is not production runtime integration.
- The runtime binding declares `hard_timeout_enforced=False`; no claim is made that arbitrary adapters are universally preempted by a hard timeout.
- Production HTTP runtime, services, durable data, and cutover state remain unchanged.
