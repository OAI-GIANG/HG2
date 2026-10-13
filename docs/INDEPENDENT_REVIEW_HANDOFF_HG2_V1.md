# HG2 Independent Review Handoff — V1

**Review state:** `PENDING — NO INDEPENDENT REVIEW RECORDED`
**PR:** [OAI-GIANG/HG2 #5](https://github.com/OAI-GIANG/HG2/pull/5)
**Required target:** reviewer must record the full PR head commit SHA at review start and verify that the PR head has not moved before submitting the review.
**Canonical baseline (read-only):** `hg-genesis` at `d11e71ed8b34338b8568664b39bc777c926826d5`.
**Candidate branch:** `fix/hg2-single-product-readiness-20261013`.

## Review independence and boundaries

The author-run test suite and CI are implementation evidence, not an independent review. The reviewer must be a person other than the author and must review the exact full commit SHA, the complete diff against the canonical baseline, relevant tests, and evidence artifacts. Do not infer approval from a request, comment, passing CI, or the author's own review.

This handoff does not authorize merge, deployment, canonical-branch mutation, repository/branch archive or deletion, or history rewriting. Keep PR #5 OPEN and DRAFT during this handoff. Do not amend, rebase, or move the reviewed head while review is in progress; if the head changes, restart the review against the new exact SHA.

## Required reviewer checklist

1. Confirm `hg-genesis` still resolves to `d11e71ed8b34338b8568664b39bc777c926826d5` and the candidate is the only branch being reviewed.
2. Independently inspect the entire candidate diff, including durability/fsync paths, error handling, concurrency, identity mapping, route removal, and test fixtures. Verify no unapproved change reaches the canonical branch.
3. Re-run or independently verify the strict test command on the exact target SHA:
   `PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest discover -s tests -v`
4. Verify the complete log, its SHA-256, clean checkout/worktree, and CI success all bind to the same full SHA.
5. Inspect the product-scope decisions and source inventory. Confirm the explicit choices are HTTP API removal (C), Phone Bridge 1.1 removal from HG2 (C), and preservation of `PRODUCT_ID=HG` with `product_name=HG2` (A).
6. Treat external-consumer impact as unresolved unless there is direct evidence covering external clients, deployments, DNS/proxies, integrations, and operational users. Repository grep or an empty GitHub deployment list is not proof that no external consumer exists.
7. Verify production authentication uses a real verifier and applicable VPS/HTTPS/device end-to-end checks have genuine execution evidence. Do not accept mocks or source-only tests as production evidence.
8. Confirm the unsigned-commit and metadata exception `b5f49770cba13cd995533cd140b7560d999c441e` remains explicitly documented and has not been erased by history rewriting.
9. Do not claim an actual power-loss test unless a real forced power-loss/kernel-crash test was performed and its provenance captured.
10. Record findings by severity, exact file/line and reproduction evidence. Submit a formal GitHub review (`APPROVE` only if all required gates are genuinely satisfied; otherwise `REQUEST_CHANGES` or `COMMENT`) and identify any remaining blockers explicitly.

## Known open gates at handoff preparation

- External consumers/deployments of the legacy HG HTTP API: `BLOCKED — UNKNOWN`.
- External consumers/deployments of Phone Bridge 1.1: `BLOCKED — UNKNOWN`.
- Independent review: `BLOCKED — PENDING`.
- Production authentication integration: `BLOCKED — NOT PROVEN`.
- VPS/HTTPS/production-device E2E: `BLOCKED — NOT RUN/NOT EVIDENCED`.
- Actual power-loss test: `NOT RUN`.
- Provenance: current candidate commit is unsigned; historical exception remains unresolved without history rewrite.

## Evidence pointers

- Product scope acceptance: `docs/PRODUCT_SCOPE_ACCEPTANCE_HG2_V1.md`.
- Owner scope decisions (not implementation evidence): `contract/PRODUCT_SCOPE_DECISIONS_V1.json`.
- Dependency inventory: `evidence/HG2_PRODUCT_SCOPE_DEPENDENCY_INVENTORY_V1.json`.
- Exact-SHA acceptance snapshots: `evidence/HG2_PRODUCT_SCOPE_ACCEPTANCE_EVIDENCE_46E90FB.json` and `evidence/HG2_PRODUCT_SCOPE_ACCEPTANCE_EVIDENCE_74ECB9E.json`.
- The most recent previously verified candidate before this handoff document was `f7f3065707066dbccfbb70ab976140bef567d5cf`, with 54/54 strict tests and CircleCI run #20 successful. Because this handoff document changes the tree, those results do not automatically attest to the new commit; repeat verification and record the resulting exact SHA before review.

## Review outcome record (reviewer completes this section)

- Reviewer identity:
- Full target SHA:
- Review started (UTC):
- Clean checkout and diff verified:
- Exact-SHA test command/result/log SHA-256:
- CI provider/run/status:
- Findings and severity:
- External-consumer evidence or residual-risk decision:
- Production auth and VPS/HTTPS/device evidence:
- Provenance exception disposition:
- Formal GitHub review URL and state:
- Remaining blockers:
