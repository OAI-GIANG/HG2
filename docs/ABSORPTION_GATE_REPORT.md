# HG2 Product Gate — Phone-only

Current candidate design: the phone owns local durable state and history. The product does not ship a remote HTTP router, network client, external-host configuration, remote administrator, or host-specific deployment tooling.

Acceptance scope is local state integrity, deterministic history validation, explicit session-verifier behavior, bounded offline analysis, and local filesystem-only spool exchange. Any future network capability requires a separately authorized scope change and new technical acceptance evidence.

Status: candidate-only. The canonical branch remains unchanged while the current pull request is open.
