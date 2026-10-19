# HG2 Brain Runtime Composition — 2026-10-19

- Target: `stt/hg2-brain-consolidation-20261018`
- Base HEAD: `9ad55387a3de9bd51a02bcca395074afcf15b41f`
- Source of API surface: existing target `stt/hg2-single-system-20261017` at `644972deef5921817e6b2d048112330530f72f45`.
- Ported: `hg/server.py`, `hg/limits.py`, `hg/model_gateway.py`, `ui/index.html` and their four focused test modules. Source SHA-256 and local SHA-256 are recorded in the JSON report.
- Adaptation: `PhoneRuntime` composes `MemoryStore` and `ModelGateway` over its existing `StateStore`; the existing `SyncContext`/`AuthenticatedBatchGate` path remains. No second state store is created and the alternate branch's incompatible `PhoneRuntime` was not copied over.
- Verification: `python -m unittest discover -s tests -v` — **219 tests, OK**; `git diff --check` — PASS. See adjacent test log.
- Security design cross-check: Python's official `http.server` documentation warns the module is not intended as a production server and notes symlink/header sanitization risks; the imported API implementation is custom, authenticated, rate-limited and has no `SimpleHTTPRequestHandler` file-serving route. This is not a substitute for deployment TLS/reverse-proxy review. [Python documentation](https://docs.python.org/3.14/library/http.server.html). HTTP retry semantics were checked against [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html).
- No source branch was deleted.
