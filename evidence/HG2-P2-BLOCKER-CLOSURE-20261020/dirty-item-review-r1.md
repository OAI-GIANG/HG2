# Per-item live dirty review — 2026-10-20

Candidate: `a8dc8bf5c0abb5570b6ac0c141f98c24c5b34562`
Live HEAD: `4d97c34d8bb7c1091265330aef63dd78d0e72c49`
Disposition: **BLOCKED**. All 16 items are classified by provenance confidence/risk/review requirements; this is not equivalent to full semantic attribution. Restricted logs remain hash-only and are neither read nor copied.

## README.md
- Git status at snapshot: ` M`; class: **UNATTRIBUTED_DOC_OR_CONTRACT_CHANGE**
- Live bytes/hash: 701 / `f2db15dcb0f5b2af04705248605bcaf58d16687ec80dadb845919c9aaa26452e`
- Candidate bytes/hash: 1453 / `9eda05a708369480e767d4fd8afe46b9eff018688e93a40ffebd80a0b88869d4`
- Impact: Unverified intent; may describe behavior that implementation does not enforce.
- Required validation: Compare contract statements to candidate implementation; Identify affected acceptance checks; Maintainer records intended disposition
- Acceptance: **BLOCKED**

## contract/ARCHITECTURE_V1.md
- Git status at snapshot: ` M`; class: **UNATTRIBUTED_DOC_OR_CONTRACT_CHANGE**
- Live bytes/hash: 745 / `c20fb2dddd71556f1f18eb3cba2a233bbcb2e57504409182061ac82e8f34ff74`
- Candidate bytes/hash: 595 / `9a257ec56ba83910ad5b87a0e2e995d5c2d78f42d4f7c89d27ffff47a9cbf996`
- Impact: Unverified intent; may describe behavior that implementation does not enforce.
- Required validation: Compare contract statements to candidate implementation; Identify affected acceptance checks; Maintainer records intended disposition
- Acceptance: **BLOCKED**

## hg/authority.py
- Git status at snapshot: ` M`; class: **UNATTRIBUTED_AUTHORIZATION_CHANGE**
- Live bytes/hash: 868 / `6e844fe754c6ee285d0bf5e3943e2082f44a2c1c383cd7d4290698d0fb19daa5`
- Candidate bytes/hash: 968 / `1531473ebe1f3534a91bb9c992ae8bf7d6944f5f6ce5ebcb48008d8267572068`
- Impact: High security: authority policy and authorization decisions may differ.
- Required validation: Allow/deny matrix for every operation; Negative tests for missing/expired/revoked credentials; Capability mismatch and privilege escalation tests
- Acceptance: **BLOCKED**

## hg/edge.py
- Git status at snapshot: ` D`; class: **LIVE_DELETION_NOT_PROPAGATED**
- Live bytes/hash: None / `None`
- Candidate bytes/hash: 6472 / `489eecdaa7166143416db81d0ed4ae4787c6da6a39f86b8d129468543307a6c1`
- Impact: Potential edge/relay/network surface removal; security and topology consequences unknown.
- Required validation: Search callers/importers of hg.edge; Compare service/edge route contract; Test authenticated loopback-to-edge relay behavior; Record explicit maintainer deprecation approval
- Acceptance: **BLOCKED**

## hg/history.py
- Git status at snapshot: ` M`; class: **UNATTRIBUTED_STATESTORE_CHANGE**
- Live bytes/hash: 15643 / `8979e48f9d94c571d5e90691be16fc1b719a1cd8e4f51240f1a1ece254f92495`
- Candidate bytes/hash: 35229 / `e68bafc9bfc2579e763a29be6b35e4573e0f1850282ebb7a7558157e38ed856b`
- Impact: High: event journal/checkpoint integrity, replay, crash recovery and durable state semantics.
- Required validation: Hunk-by-hunk diff against candidate and archived branch; Crash at every fsync/write boundary; Replay/hash-chain/checkpoint divergence tests; Idempotent restart recovery and safe refusal cases
- Acceptance: **BLOCKED**

## hg/phone_runtime.py
- Git status at snapshot: ` M`; class: **UNATTRIBUTED_RUNTIME_CHANGE**
- Live bytes/hash: 3847 / `2bb9cb4b22d199fd1c5f7bee1ad34071ded60d13aa3f344ca88ff01f783110eb`
- Candidate bytes/hash: 8465 / `d415b3249f3332ff406b35c5883e2c26603ad680b5da0b3490999da58592a730`
- Impact: High: startup ordering, model-call in-doubt recovery and durable sync ownership.
- Required validation: Compare startup lifecycle and state owner; Crash after model.call.started before terminal receipt; Multiple restart idempotency; Concurrent startup process-lock test
- Acceptance: **BLOCKED**

## hg/sync.py
- Git status at snapshot: ` M`; class: **UNATTRIBUTED_SYNC_CHANGE**
- Live bytes/hash: 17219 / `81681392d7294055aeba7ffa147ed7e6d6402d354b2d9efc55c5ec096f87271a`
- Candidate bytes/hash: 16859 / `311c62e97a7122f04cf0f7025e43b9131e80afb2ad466ac3953c942a89328e35`
- Impact: Medium-high: sync context, replication ordering, deduplication and durable data movement.
- Required validation: Schema/contract compatibility; Reordered/duplicate/missing event tests; Restart and lost-ACK idempotency; Unauthorized batch rejection
- Acceptance: **BLOCKED**

## manifest.json
- Git status at snapshot: ` M`; class: **UNATTRIBUTED_BUILD_MANIFEST_CHANGE**
- Live bytes/hash: 218 / `cebb0be691e8003a7b5d8e9458d3485f456a9634e3066b9d25585d5634bc8196`
- Candidate bytes/hash: 459 / `58f5b20ad670c0b95465b7e1425287046f79a4691f41d416288b3e494e52e001`
- Impact: High: source identity and artifact allowlist may not bind actual runtime bytes.
- Required validation: Regenerate in temporary worktree; Verify every listed digest and missing/unlisted source behavior; Tie manifest to the exact candidate tree
- Acceptance: **BLOCKED**

## tests/test_core.py
- Git status at snapshot: ` M`; class: **UNATTRIBUTED_TEST_SUITE_CHANGE**
- Live bytes/hash: 7266 / `013becf13365963b90938c42463c86aa03e157dda31cd35a5b007130d44a7c58`
- Candidate bytes/hash: 10440 / `57933d4503fcb9a487bcdd554d121de5b4355cf2160cd8e58aa41225283fb406`
- Impact: Unknown coverage additions/removals; risk of missing safety guarantees.
- Required validation: Review test hunk additions/removals; Map changed assertions to contracts; Run affected module tests and full suite
- Acceptance: **BLOCKED**

## hg/provenance.py
- Git status at snapshot: `??`; class: **UNATTRIBUTED_UNTRACKED_PROVENANCE_MODULE**
- Live bytes/hash: 28652 / `fe5d09b4dd458c41f0e6bc8fdbc78c2493f067757f2f234a94c96379a8bf8379`
- Candidate bytes/hash: 3350 / `2081ff229d92c4a3b82d1a360f14fb207c98410fad17127c97b2178bcc20f629`
- Impact: High provenance: runtime build identity, tree cleanliness and on-disk digest claims.
- Required validation: Compare against committed provenance contract; Dirty-tree and changed-file mutation tests; Import origin and runtime artifact binding tests
- Acceptance: **BLOCKED**

## hg/sync_auth.py
- Git status at snapshot: `??`; class: **UNATTRIBUTED_UNTRACKED_SYNC_AUTH_MODULE**
- Live bytes/hash: 13020 / `cea8f52d5636d53475578fb26e685b6fd2a63fc1349224c18feab8964c37f107`
- Candidate bytes/hash: 13079 / `4b36ef364a98a9e36b6924b28a6092b6a0ad091e2c6f0985bd33c999ee077099`
- Impact: High security: sync authentication and trust boundary.
- Required validation: Adversarial MAC/signature and credential mismatch tests; Replay and expiry tests; Malformed input and key rotation tests; Negative authorization tests
- Acceptance: **BLOCKED**

## hg/sync_bootstrap.py
- Git status at snapshot: `??`; class: **SOURCE_BYTES_MATCH_ARCHIVED_BRANCH**
- Live bytes/hash: 4536 / `5698c150a63cd889c380539bdaf3c52ef9e9e70f13da7c78ad124b61d1f8b753`
- Candidate bytes/hash: 4536 / `5698c150a63cd889c380539bdaf3c52ef9e9e70f13da7c78ad124b61d1f8b753`
- Impact: Byte provenance supported, but runtime compatibility and intent still need code review.
- Required validation: Check dependency/import path; Run relevant protocol/recovery regressions
- Acceptance: **PROVENANCE_PARTIAL**

## n1.log
- Git status at snapshot: `??`; class: **RESTRICTED_LOG_HASH_ONLY**
- Live bytes/hash: 0 / `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Candidate bytes/hash: None / `None`
- Impact: UNDETERMINED_WITHOUT_AUTHORIZED_REVIEW
- Required validation: Review metadata and purpose through authorized maintainer; do not import or execute.
- Acceptance: **BLOCKED**

## n2.log
- Git status at snapshot: `??`; class: **RESTRICTED_LOG_HASH_ONLY**
- Live bytes/hash: 0 / `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Candidate bytes/hash: None / `None`
- Impact: UNDETERMINED_WITHOUT_AUTHORIZED_REVIEW
- Required validation: Review metadata and purpose through authorized maintainer; do not import or execute.
- Acceptance: **BLOCKED**

## raw1.log
- Git status at snapshot: `??`; class: **RESTRICTED_LOG_HASH_ONLY**
- Live bytes/hash: 7730 / `78201bcccf466b29805d8e558217b596dbf5114d816eaaa48dcdd442f00499bd`
- Candidate bytes/hash: None / `None`
- Impact: UNDETERMINED_WITHOUT_AUTHORIZED_REVIEW
- Required validation: Review metadata and purpose through authorized maintainer; do not import or execute.
- Acceptance: **BLOCKED**

## raw2.log
- Git status at snapshot: `??`; class: **RESTRICTED_LOG_HASH_ONLY**
- Live bytes/hash: 7730 / `1d0aa92815658c8952f1c129b0b52a12a3a113bb407a464ed568d5bb73fdb021`
- Candidate bytes/hash: None / `None`
- Impact: UNDETERMINED_WITHOUT_AUTHORIZED_REVIEW
- Required validation: Review metadata and purpose through authorized maintainer; do not import or execute.
- Acceptance: **BLOCKED**
