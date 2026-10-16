# HG2 Source Decisions — Current Candidate

Only modules required for the phone-local product remain in the candidate manifest. Remote router/client code and utilities requiring external-host configuration are not part of the product. Old design/evidence bundles that described removed remote functionality have been preserved in a private local archive, outside the repository tree.

Core product invariants:
- The phone owns local state and history.
- Session creation requires an explicit verifier and fails closed.
- Event exchange, if enabled, is local filesystem spool only.
- The product has no remote edge module, network HTTP client, server listener, or host endpoint configuration.
- Canonical branch changes only after separate authorization; this candidate has not been merged.
