# HG2 PR #29 — Acceptance Gap Audit

Date: 2026-10-20
Repository: `OAI-GIANG/HG2`
Audit target at start: `31db6ef4fedaaf6eb04f65bc88487e7c14e17ad1`

Latest HEAD before owner-approval policy update: `b8e70219f98f5fd529b4dc6e03fb02ee5a40c9f1` (CircleCI #292 passed).

## Decision

**NOT CLOSED — MERGE/DEPLOY BLOCKED.** This is an evidence audit, not an approval.

## Verified evidence

- PR #29 is open, based on `hg-genesis`, and the reviewed HEAD at audit start was `31db6ef4fedaaf6eb04f65bc88487e7c14e17ad1`.
- GitHub records review `5575758755` from `doquocoai07-sys` on that exact commit with state `COMMENTED`. It is not an approval.
- The authenticated GitHub CLI session on the Termux host is `OAI-GIANG`; the repository collaborator listing contains only `OAI-GIANG`. The reviewer's permission endpoint reports `read`.
- Commit status reports `ci/circleci: verify` as `success` at `https://circleci.com/gh/OAI-GIANG/HG2/289`.
- Targeted `python -m unittest tests.test_remote_desktop_commander -v`: 9 tests passed before and after the latest admission-receipt metadata change. The latest tests also assert registered adapter identity is present in decision receipts and absent for unregistered operations. Coverage includes unregistered operation denial, missing capability denial, raw shell/secret-key rejection, high-risk approval verifier requirement, exact command/argument digest binding, verifier rejection, destructive feature switch, dry-run non-execution, and duplicate registration denial.
- The previously recorded full suite result for the earlier implementation commit is 333 tests passed. The present focused source/test change ran the 9 targeted Remote Desktop Commander tests and compiled only the changed Python files; the full suite has not been rerun.
- `adb devices -l` returned no attached target devices. The current host was identified as OPPO PKC110, Android 15/Termux (`aarch64`, Android kernel); `cmd.exe`, `powershell.exe`, and `xfreerdp` were not found. The intended desktop OS/device is therefore **UNIDENTIFIED**, not assumed to be Windows or Linux desktop. This does not identify or validate a desktop target.
- Source inventory shows `hg.remote_desktop_commander.RemoteDesktopCommander` is an admission contract only; it deliberately does not invoke adapters. `hg.capability_registry.RuntimeDomainBinding` can bind Python callables but does not itself enforce hard timeouts. Existing `/api/ask` bindings explicitly set `hard_timeout_enforced=False`. No target-side desktop operation adapter or OS process supervisor was found in this scope.

## Acceptance gate matrix

| Gate | Status | Evidence / remaining work |
|---|---|---|
| Correct PR and reviewed commit | PASS at audit start | PR #29 HEAD matched `31db6ef4fedaaf6eb04f65bc88487e7c14e17ad1`; re-check after this audit note is pushed. |
| CI on reviewed commit | PASS at audit start | CircleCI commit status was success for that HEAD; verify new HEAD after push. |
| High-risk approval fail-closed | PARTIAL / contract tests pass | Unit tests show no verifier or false verifier blocks and bind digest fields. A trusted production approval adapter/service and target-side enforcement are not evidenced. |
| Actual target desktop adapter | BLOCKED | No target device was attached/discovered and no OS-specific desktop adapter is bound through the runtime registry. Do not infer execution from an admitted decision. |
| OS-enforced timeout | BLOCKED | No target adapter/process supervisor or target-side timeout/cancellation evidence was found. HTTP client timeout settings are not proof of process-tree termination on a desktop target. |
| Adapter identity in admission receipts | IMPLEMENTED / TARGET UNVERIFIED | Commit `32959616bbed62e99d2b10ada64c56fbbea4b848` carries registered `adapter_id` and `adapter_version` in the decision digest, including null values for unregistered operations. Focused tests and CircleCI #291 pass. This improves audit binding only; it does not execute or authenticate a target adapter. |
| Independent review | NOT A MANDATORY GATE (owner policy) | The repository owner may approve their own change under explicit owner authorization. GitHub still records the actual review state; `COMMENTED` is not `APPROVED`. No independent-review claim is made. If GitHub branch protection/rulesets separately require approving reviews, the repository owner must adjust that repository policy intentionally; do not bypass technical safety gates. |
| Live integration/deployment | NOT RUN | No target adapter and target integration fixture are available; no live desktop operation or deployment was attempted. |

## Safety conclusion

`RemoteDesktopCommander.prepare()` is an admission/decision boundary and does not execute an adapter. A positive `executable` decision is not execution evidence. Do not merge or deploy the live runtime until a named target, adapter implementation, OS-specific timeout/cancellation behavior, trusted approval integration, and target integration evidence are available. Independent human review is not a mandatory HG2 gate under the owner-approval policy; the owner remains responsible for authorizing the release. Do not invent target details or claim OS-enforced timeout based only on a unit test.

## Revalidation protocol

After the latest source/test change, the targeted Remote Desktop Commander module passed (9 tests), the changed Python files compiled, `git diff --check` passed, and CircleCI #291 passed on HEAD `32959616bbed62e99d2b10ada64c56fbbea4b848`. The full 333-test suite was not rerun. The PR remains open and unmerged. Independent human review has been removed as a mandatory HG2 acceptance gate by owner decision; actual GitHub review states must still be reported accurately. The PR HEAD/CI should be rechecked after this policy change. Keep the pre-existing untracked `docs/architecture/HG2-P0-CONTRACT-STATE-OWNER-PREFLIGHT-2026-10-20.md` untouched.
