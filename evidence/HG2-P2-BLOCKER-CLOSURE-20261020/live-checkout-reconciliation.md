# Live checkout reconciliation — 2026-10-20

## Scope and disposition

Read-only inspection of the active Termux checkout at HEAD 4d97c34d8bb7c1091265330aef63dd78d0e72c49 against candidate f855bd3728bfad5f91c53aa64652067aa7639aa7. The live checkout and live state owner were not changed. All 16 dirty entries have been inventoried by status, size and SHA-256; snapshot manifest checks passed. Raw logs were not opened or copied into this repository.

## Findings

- hg/history.py and hg/sync_bootstrap.py are exact byte matches to archived HG2 source files from origin__stt__hg2-unification-p0-20261016.
- hg/edge.py is deleted in the live worktree but remains present in the candidate; the deletion is not propagated.
- n1.log, n2.log, raw1.log and raw2.log remain restricted checkpoint content; only names, sizes and hashes are recorded here.
- The remaining local file deltas have no exact match in the source-branch snapshots or reachable Git object/path inventory examined. Their origin and semantic intent are not asserted.
- Because provenance of those deltas remains incomplete, the candidate uses the clean f855bd base and imports none of the unidentified live modifications. The live checkout cannot be called reconciled for cutover purposes until a maintainer supplies source/intent or those deltas receive a targeted review and tests.

## Integrity

The snapshot integrity checks are recorded in live-checkout-reconciliation.json. The original snapshot remains at the restricted cache location; this report deliberately excludes raw log contents.

## Closure decision

BLOCKED for live cutover. Inventory and preservation are verified; full provenance/impact attribution and integrated rollback are not yet verified.
