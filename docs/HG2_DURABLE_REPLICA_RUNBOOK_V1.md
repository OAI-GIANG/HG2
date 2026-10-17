# HG2 Durable Replica Runbook V1

Status: code/test contract only; NOT deployed to production.

## Role and trust boundary

The hg.replica module is a backup/relay receiver only. The phone-local HG2 event log remains authoritative. The receiver exposes only authenticated capability negotiation and append-only batch ingestion; it exposes no memory read API and cannot mutate the phone's local state. Receiver state is derived replication, not a competing authority.

## Configuration

Use a dedicated private environment file owned by the service account, mode 0600, outside the repository:

- HG_REPLICA_TOKEN: a dedicated secret with at least 32 characters and only the MEMORY_PERSIST capability.
- HG_REPLICA_ALLOWED_SCOPES: explicit comma-separated memory scopes accepted by policy; wildcard is forbidden.
- HG_DURABLE_MEMORY_SCOPES (phone sender): explicit comma-separated allowlist of scopes that the phone may replicate to this receiver. The sender rejects an absent/wildcard allowlist and never sends events outside this set. Excluded events remain only on the phone and are reported separately.
- HG_REPLICA_DB: SQLite database path on a private durable filesystem.
- HG_REPLICA_BIND=127.0.0.1 and HG_REPLICA_PORT=8890.

Never copy a legacy token to another endpoint until its authorization contract and intended scope have been verified. The receiver must be exposed only through an authenticated HTTPS reverse proxy. It refuses non-loopback binds.

## Data integrity and durability

Each batch is bounded, schema-validated, scoped, checksum-validated and ingested within a SQLite BEGIN IMMEDIATE transaction. Batch receipts are idempotent and conflicting reuse is rejected. Records remain append-only; a tombstone adds a new event and does not erase prior events. SQLite uses WAL and synchronous FULL; the database file is chmod 0600 in a mode-0700 directory. Backups must include a consistent SQLite snapshot (use the SQLite backup API or VACUUM INTO) rather than copying only the main database file while open. Reference: https://www.sqlite.org/transactional.html and https://www.sqlite.org/wal.html.

This replica stores replicated event payloads in local SQLite in plaintext. Restrict filesystem permissions and encrypt the disk/volume before using it for production data. TLS and token authentication do not provide encryption at rest. Do not cut over replication until hosting storage and restore path are verified.

## Test and cutover gates

Run python -m pytest -q, python -m py_compile hg/replica.py, then an isolated client/receiver integration rehearsal. Capture database SHA-256, event and batch counts, receipt IDs, and restored state verification. Do not point production HG_DURABLE_URL at a receiver until a scoped credential exists and TLS, backup/restore, access controls, and rollback are verified.
