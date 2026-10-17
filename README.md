# HG (clean-slate)

Independent HG product with canonical source in OAI-GIANG/HG2.
The phone-primary architecture is documented in contract/ARCHITECTURE_V1.md; it owns canonical state and history. The edge is a narrow authenticated relay, not an authority or model-key store.

## Canonical source modules

- hg/identity.py — product identity and architecture label.
- hg/auth.py — constant-time Bearer authentication and scoped principal creation.
- hg/authority.py — deny-by-default actions and provider/session authorization policy.
- hg/history.py — append-only SHA-256-chained event history and integrity verification.
- hg/phone_runtime.py — phone-primary state owner and edge registration/heartbeat client.
- hg/edge.py — strict payload validation and authenticated edge relay.
- hg/provider.py — bounded HTTPS OpenAI-compatible Chat Completions adapter.
- hg/toolplane.py — fixed allowlist, limited tool orchestration, validation, iteration bound and hash-only audit.
- hg/agent.py — application entry point connecting the phone-owned StateStore, provider, authenticator and tool plane.

No third-party runtime dependency is introduced. The built-in tool plane intentionally has no shell, arbitrary file, deployment or generic network-fetch tool. Provider calls require HG_AUTH_TOKEN and an Authorization: Bearer header; only provider.invoke is enabled by default. session.create requires an explicit HG_AUTH_SCOPES=provider.invoke,session.create grant.

## Tests and contracts

Run the strict suite and source provenance hash check as recorded in contract/ACCEPTANCE_MATRIX_V1.md. The acceptance matrix distinguishes tested implementation from missing or unverified capabilities; synthetic AI fixtures are not treated as proof of actual HG semantic quality.
