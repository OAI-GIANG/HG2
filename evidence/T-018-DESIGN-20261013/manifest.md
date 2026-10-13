# T-018 Design Evidence Manifest — 2026-10-13

## Evidence class
Design and source-inspection evidence only. No implementation patch, runtime change, canonical mutation, audit mutation, merge or deployment is included.

## Exact source refs
- Repository: `OAI-GIANG/HG2`
- Design base / prior feature head: `4d97c34d8bb7c1091265330aef63dd78d0e72c49`
- Canonical branch expected unchanged: `hg-genesis` at `d11e71ed8b34338b8568664b39bc777c926826d5`
- PR #8: https://github.com/OAI-GIANG/HG2/pull/8 — expected OPEN / DRAFT / NOT MERGED
- Design branch: `design/t018-auth-checkpoint-memory-20261013`
- Local device used: Remote Desktop Commander device `localhost`; Android/aarch64; Python 3.14.6
- Local checkout before documentation: clean at exact feature head; remote `origin` refs observed at the hashes above.

## Source blob hashes at the design base
- `hg/phone_runtime.py`: `75fa6bcda1e29bf08aeb5341dbe8f0e124684199`
- `hg/sync.py`: `f5c706348de6b2364fe2286a4121594d08e74a22`
- `hg/history.py`: `acb466e8a4c2b8882db58b783028b59804ecc812`
- `hg/authority.py`: `a9fb1ddae181944e2e87decb806368e916ac6379`
- `hg/edge.py`: `8a018ac5a7fd6113d979f4f0e2a65bb5ae192f91`
- `hg/identity.py`: `58df90a6b7d69d87df75bead52a3b3435a88f23f`
- `contract/ARCHITECTURE_V1.md`: `7defc59985b2ea291b614a63de0a3152b64d064d`
- `docs/T-018-SYNC-V2-CONTRACT.md`: `35aba35631b8a74b0366d52f9f4c381ffc2c2a4b`
- `manifest.json`: `f30da194e246dba2773125d074488a30912635eb`

## Design artifacts
- `docs/design/T-018-IMPLEMENTATION-DESIGN-V1.md`: implementation design, actual-source findings, API/wire contract proposals, key lifecycle, checkpoint rules, storage migration alternatives, SQLite logical schema proposal, transaction algorithm, test matrix, rollback, acceptance gates and unresolved owner decisions.
- `docs/design/T-018-THREAT-MODEL-V1.md`: assets, trust boundaries, attacker assumptions, 25 threat cases, required mitigations and residual risks.
- `evidence/T-018-DESIGN-20261013/manifest.md`: this provenance record.
- `evidence/T-018-DESIGN-20261013/SHA256SUMS.txt`: file digests (excludes itself by design).

## Validation performed
- `git diff --check` passed before commit.
- Design and threat-model files were checked for required sections.
- SHA-256 values are recorded in `SHA256SUMS.txt`; verification must be rerun from the committed branch.
- This manifest does not assert an independent review or implementation correctness.

## Normative/reference links
- RFC 8705: https://www.rfc-editor.org/rfc/rfc8705.html
- RFC 9700: https://www.rfc-editor.org/rfc/rfc9700.html
- RFC 9421: https://www.rfc-editor.org/rfc/rfc9421.html
- RFC 8785: https://www.rfc-editor.org/rfc/rfc8785.html
- RFC 9162: https://www.rfc-editor.org/rfc/rfc9162.html
- TUF: https://theupdateframework.github.io/specification/latest/
- Android Keystore: https://developer.android.com/privacy-and-security/keystore
- CloudEvents: https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md
- SQLite atomic commit: https://www.sqlite.org/atomiccommit.html
- SQLite transactions: https://www.sqlite.org/lang_transaction.html
- Microsoft Event Sourcing: https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing
- AWS Transactional Outbox: https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html

## Gate state
- `DESIGN=PREPARED_FOR_REVIEW`
- `IMPLEMENTATION=NOT_STARTED`
- `INDEPENDENT_REVIEW=PENDING`
- `CANONICAL_MUTATION=NONE_INTENDED`
- `PR_8_MERGE=NOT_AUTHORIZED`
- `DEPLOYMENT=NOT_AUTHORIZED`
- `RELEASE=BLOCKED`
