# HG — Phone-only, clean-slate product

HG is an independent software product whose runtime and durable state are owned by the phone. The core runtime performs local state/history operations and does not integrate with external servers, host-specific endpoints, remote administration, or network relays.

The core runtime contains no remote HTTP client, server listener, host endpoint configuration, or automatic failover. Optional event exchange is local filesystem spool only and does not imply a network connection or remote replica.

HG2 is the product/repository label; `PRODUCT_ID=HG` remains the durable event and on-disk identity for compatibility. Historical event bytes are not rewritten.
