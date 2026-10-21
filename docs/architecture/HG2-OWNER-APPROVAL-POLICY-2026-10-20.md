# HG2 Owner Approval Policy

Date: 2026-10-20
Repository: `OAI-GIANG/HG2`
Authority: repository owner / product owner

## Decision

Independent human review is **not a mandatory HG2 acceptance gate**. The owner may decide to approve and merge changes to the software they own. Do not claim an independent review occurred unless a real independent reviewer submitted an auditable review. GitHub review states (`COMMENTED`, `APPROVED`, `CHANGES_REQUESTED`) must be reported as recorded; they are not interchangeable.

## Mandatory technical gates remain

1. The exact PR HEAD and CI result must be verified.
2. Source/test evidence must match the exact candidate commit.
3. Authorization is least-privilege and fail-closed; high-risk approval is bound to the exact request/plan/command digest and principal/target.
4. Actual target adapters, OS-specific timeout/cancellation, audit records, and integration behavior must be evidenced before enabling live execution.
5. Missing target hardware/software is recorded as `BLOCKED`; no adapter, endpoint, or successful execution may be invented to satisfy a gate.
6. Owner authorization to merge is separate from evidence that runtime deployment is safe.
7. No deployment occurs until the target and rollback/recovery behavior are known and verified.

## Infrastructure decision

Do not create a new VPS solely to remove the independent-review gate. Infrastructure is added only for a demonstrated runtime requirement (for example, a required always-on relay/worker or a target that cannot be reached safely from the phone). The current blocking evidence is the unidentified desktop target and absence of a verified target adapter/OS-enforced timeout, not a lack of a second reviewer or a proven need for another VPS.

## Current PR #29 application

PR #29 may be owner-approved under this policy if the owner chooses, but the target desktop integration and OS-enforced timeout gates remain open. This policy does not itself authorize merge or deployment and does not represent an actual GitHub approval event.
