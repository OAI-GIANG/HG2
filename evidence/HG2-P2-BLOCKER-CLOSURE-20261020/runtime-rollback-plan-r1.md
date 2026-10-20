# Runtime recovery and rollback integration plan — R1

Status: DESIGN ONLY / BLOCKED. This is not proof that live runtime rollback works.

## Safety boundary
- Test targets must be unique temporary directories created by the test harness and verified to reside under the test temporary root.
- Do not use the live checkout, live state directory, live service environment, or live backups as test targets.
- Instantiate HGHTTPServer on 127.0.0.1 with an ephemeral port and test-only credentials.
- Never mutate the source state during rollback testing. Corrupt only a disposable copy; preserve the snapshot immutable and restore to a separate new directory.

## Procedure
1. Create temporary state A and start HGHTTPServer with test-only credentials.
2. Append a synthetic model.call.started and assert the event journal verifies.
3. Close the server; for OS-crash simulation, run a subprocess against only disposable state and stop it after the durable start. Never signal a production PID.
4. Start a second server on the same test state. Assert exactly one model.call.in_doubt is appended, the start remains, no false completion appears, and repeated restarts preserve one marker.
5. Stop test writers, copy the full StateStore directory, and produce a manifest with relative paths, sizes, modes and SHA-256 for each regular file. Verify the snapshot.
6. Corrupt a separate disposable copy, run integrity checks on it, and confirm the source and snapshot hashes are unchanged.
7. Restore into a new temporary directory, verify manifest plus StateStore hash chain, and instantiate HGHTTPServer on the restored copy. Confirm expected event IDs and projected state.
8. Inject faults only in test harnesses at each write/fsync boundary. Accept only verified recovery or fail-closed startup. Never replay an uncertain provider request.
9. Preserve stdout/stderr, exit code, commit/tree, environment and hashes. Separate local observations from signed runner claims.

## Acceptance gates
- The process lock prevents a second owner for one active state directory.
- Snapshot stays immutable and hash-verified.
- Restored copy has a valid chain and expected projection.
- Recovery markers are idempotent for at least three startups.
- No provider request is replayed from IN_DOUBT.
- Outbox retry uses stable batch identity; ACK binds to the expected contract and batch contents.
- All testing is isolated; full regression passes after each code change.
- Independent reviewer checks evidence and interpretation.

## Remaining blockers
- Provenance of the 16 dirty live entries is not fully attributed; cutover prohibited.
- No independent production runner signer/trust-root pin or actual signed runner receipt is available.
- Offline model gate fails: SQLite crash scored 4/10 with a critical failure; interrupted in-doubt attempt is not a pass.
- Candidate tests do not prove live-service rollback.