# HG2 Product Scope Acceptance — Phone-only

HG2 core runtime is phone-only and local-state-only. The candidate does not ship a remote HTTP router, network client, edge relay module, host endpoint configuration, or VPS administration utility.

Session creation requires an explicit verifier and fails closed if verifier input is absent, rejected, or unavailable. Local state/history integrity remains the core acceptance surface.

Optional event exchange is a local filesystem spool only; it does not establish network transport or remote replication. No external-host runtime, deployment, migration, or endpoint reachability is claimed.
