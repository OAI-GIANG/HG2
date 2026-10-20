# HG2 Memory Anti-Forgetting — M2 Acceptance Contract (2026-10-19)

## Scope

Single repository: OAI-GIANG/HG2. P0-A remains closed for its tested crash windows. This contract adds a fixed synthetic retrieval oracle and separates persistence integrity from retrieval quality.

## Evidence-grounded current behavior

- `hg/memory.py` stores mutations as events in the existing canonical `StateStore`; no second authoritative store is introduced.
- Retrieval is deterministic lexical token overlap, capped at 500 visible records and filtered by explicit grants before returning text. It is not a general semantic search engine. Explicitly curated aliases can cover known paraphrases, but arbitrary paraphrase recall remains unproven.
- Legacy records without `provenance_metadata` remain searchable for backward compatibility; their context is labeled `FRESHNESS_UNKNOWN` and `UNVERIFIED`. Records that opt into provenance metadata are withheld from recall when their metadata digest is invalid, expiry is missing/invalid, the record is expired, or it is revoked.
- Retrieval normalizes Unicode to NFC around casefold, covering canonically equivalent composed/decomposed Vietnamese.
- Search manifests bind query digest, source head hash, selected memory IDs/version/checksum and matching scores.
- `hg/provenance_memory.py` does not promote caller-supplied trust claims. A verifier callback alone cannot elevate a record to VERIFIED.
- `hg/replica.py` is a backup/persistence receiver, not a second query authority.

## M2 gates

1. A fixed synthetic oracle covers exact terms, Vietnamese composed/decomposed Unicode, casefold, curated-alias paraphrase, partial-overlap paraphrase, natural-language paraphrase, no-match, false-positive and scope isolation. Aliases are explicitly supplied metadata, not autonomous semantic understanding.
2. Report precision, recall, reciprocal rank for relevant results, false positives/negatives and forbidden IDs. A miss in an explicitly expected case fails the case.
3. Authorization acceptance is absolute: zero returned IDs outside explicit grants.
4. Restart acceptance checks that an active record is identical after reopening the same StateStore directory.
5. No semantic-recall claim may be inferred from lexical scores. Q13/Q14 are known-limit probes; failures must be visible.
6. Standard library only; no remote model or paid API.

## M3 — Trust, Conflict and Freshness Acceptance

- Caller-supplied trust labels always remain UNVERIFIED except an explicit REVOKED signal; a self-asserted verifier callback does not promote trust without a trust-root-bound adapter.
- Conflicting exact `(source_ref, memory_key)` claims remain `CONFLICT_UNRESOLVED`; no automatic last-write-wins policy is permitted.
- `memory_freshness()` classifies records as `WITHIN_EXPIRY`, `EXPIRED`, or `FRESHNESS_UNKNOWN`; missing/invalid expiry fails closed and expired claims are not deleted or silently rewritten.
- The standalone provenance SQLite store is currently not the canonical runtime store. It is only assessed as an isolated primitive; do not wire it into runtime without explicit migration and single-authority proof.
- CONFIDENTIAL/SECRET persistence remains BLOCKED until encryption-at-rest is independently specified and tested.
- The isolated SQLite provenance store now rejects a symlink database path, requires a private parent directory (0700), sets the database file to 0600, and has targeted restart/integrity tests. This is storage hardening of a non-canonical primitive, not proof it is part of production runtime.

## Remaining acceptance boundaries

Passing this synthetic oracle is limited to this corpus and these queries. Overall anti-forgetting closure still needs evidence for memory admission/capture completeness, contradictions/updates, expiry policy, a larger held-out Vietnamese paraphrase benchmark with human labels, multi-session/device continuity, backup restoration drills, sensitive-data erasure and replica tombstones, and runtime/deployment build identity. Process-crash tests do not imply hardware power-cut validation.

## External design references

- Unicode normalization: https://www.unicode.org/faq/normalization.html — canonically equivalent sequences should compare consistently; NFC is a general-text form.
- OWASP Authorization Regression Testing: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Regression_Testing_Cheat_Sheet.html — define actor/resource/action policies and automate horizontal and tenant-boundary tests.
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework/ai-rmf-development — treat trustworthiness as lifecycle-wide testing, provenance, security and resilience.

## Status rule

M2 is PASS only when the fixed oracle exits 0, expected queries pass, Unicode-equivalent forms yield identical IDs, restart replay matches, ACL forbidden IDs remain empty, full regression passes and SHA-256 manifests validate. This is not closure of all anti-forgetting requirements.
