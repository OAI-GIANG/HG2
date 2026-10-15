# HG Phone-only Architecture V2

1. The phone is the sole runtime and sole authority for local durable state and history.
2. The core runtime has no remote edge client, server listener, host endpoint configuration, or external-host integration.
3. Session creation requires an explicit credential verifier; absence, rejection, or verifier failure denies the operation.
4. The runtime functions offline and does not require a PC or remote server to read or verify local state.
5. Event exchange, if used, is local filesystem spool only. It is not a network transport, remote replica, second primary, or automatic failover.
6. Do not add host connectivity or remote administration to the core product without a separately authorized scope change.
