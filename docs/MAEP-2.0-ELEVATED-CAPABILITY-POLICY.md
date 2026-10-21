# MAEP 2.0 — Elevated Capability Policy

## Decision

The blanket-deny entries for the elevated HG application capabilities have been removed. These actions are now declarable as exact scopes on an authenticated, sealed principal.

## Authorization behavior

- Legacy boolean-only authorization cannot authorize elevated capabilities; it returns `SEALED_PRINCIPAL_REQUIRED`.
- The principal must carry the exact configured capability scope. Other scopes are denied.
- Generic approval/grant records do not authorize principal-only elevated capabilities.
- Unknown actions remain denied by the explicit allowlist. Wildcard scopes are not introduced.

## Boundary

This changes HG application policy only. It does not grant an OS process, remote-control connector, HTTP route, or production service a capability it has not been wired to use. Existing raw-shell guards, operation registry, high-risk approval checks, path restrictions, and deployment/cutover gates remain. A declared import capability is not proof that a production import route exists or that an import is safe.

## Verification

- Targeted policy/core/RDC/MAEP-host-binding tests: 39 passed.
- Full test suite: 509 passed, 0 failed, exit code 0.
- `py_compile`: passed.
- `git diff --check`: passed.
- Production service, durable state, live routes, and deployment were not modified.
