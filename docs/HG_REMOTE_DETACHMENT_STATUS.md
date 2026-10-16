# HG2 Remote Dependency Detachment — Candidate Evidence

Status: PHONE-ONLY CANDIDATE TREE; CANONICAL ADOPTION PENDING.

- The candidate runtime contains no remote HTTP client, server listener module, host endpoint configuration, host administrator, remote persistence worker, remote backup uploader, or host-specific preflight utility.
- Session creation remains fail-closed and requires an explicit verifier.
- Optional event exchange is limited to local filesystem spool.
- Source/configuration evidence from removed integrations is preserved in a private local archive outside the product tree.
- Candidate tests are executed locally on Termux; this does not claim a live host probe.
- No remote host has been contacted, changed, stopped, or deployed to.
- The canonical branch remains unchanged until a separate explicit change-acceptance decision.
