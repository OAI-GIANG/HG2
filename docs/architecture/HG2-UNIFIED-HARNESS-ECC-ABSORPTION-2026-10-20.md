# HG2 Unified Harness + ECC Absorption
Date: 2026-10-20

## Decision

HG will absorb engineering patterns from the upstream Everything Claude Code (ECC)
project, not its runtime, dependency tree, hook scripts, agents, or command names.
The implementation is HG-native, Python standard library only, offline-first, and
keeps OAI-GIANG/HG2 as the sole execution repository. Product identity:
**HG Remote Desktop Commander**.

Upstream reference: https://github.com/affaan-m/ECC
Upstream declares MIT licensing and describes a cross-harness toolbox spanning
agents, skills, hooks, rules, persistent context, continuous learning, research-first
development, verification loops, and security scanning. Reviewed 2026-10-20.
No third-party source files were copied into HG2 in this change.

## Integration map

| ECC pattern | HG-native integration | Safety boundary |
| --- | --- | --- |
| Harness profiles | HG_HARNESS_PROFILE=minimal, standard, strict | Standard default; strict blocks external/destructive routes when required controls are not proven |
| Hooks/lifecycle | hg.unified_harness.HarnessHookRunner | Injected in-process hooks only; no loading code from disk; guards only before dispatch; only redacted metadata |
| Verification loops | UnifiedHarness.before_dispatch + verify_outcome | Source revision, selected capabilities, owner domain, readiness, plan/trace identity, status-vs-evidence consistency |
| Skills catalog | hg.skill_contract | Exact JSON schema, content hash, license, trust level, explicit capability requirements; no instruction evaluation |
| Continuous learning | Existing HG memory/provenance remain state owners | This change does not autonomously promote generated observations into trusted skills |
| Security checks | hg.remote_desktop_commander | No free-form shell operation; explicit adapter registration; capability grants; digest-bound approval verifier |
| Research-first / plan-before-build | Existing Brain planning and registry remain authoritative | Harness is an independent validation layer, not a second orchestrator or authority |
| Durable state and receipts | Existing PhoneRuntime.store journal | Dispatch gate receipt persisted before brain.request.started; no new store and no dual-write |
| Tool adapters | Existing runtime capability registry | Unregistered, stale-revision, unready or wrongly owned capabilities block |

## Request flow

1. Existing request authentication, schema validation, idempotency and redacted acceptance receipt run first.
2. The Brain creates a plan and the runtime capability registry produces its source-bound snapshot.
3. Unified Harness checks each planned capability against a ready registered entry and checks that the entry belongs to the planned domain.
4. The harness gate receipt is appended to the existing PhoneRuntime StateStore. Failure to persist that receipt prevents dispatch.
5. Brain executes through its existing adapter registry and evidence verifier.
6. Harness independently checks request/correlation/revision/plan binding, branch uniqueness, invocation/result trace, and consistency of SUCCESS, PARTIAL, FAIL, BLOCKED, and IN_DOUBT.
7. The existing terminal event and response carry redacted harness receipt digests. The harness does not upgrade response-only provider output into execution proof.

## HG Remote Desktop Commander contract

Remote commands are structured by HG_REMOTE_DESKTOP_COMMAND_V1; they name a registered
operation, target, idempotency key, required capabilities, risk class, revision, and
optional approval reference. They do not accept an arbitrary shell string in place
of an operation. Unknown operations and missing capabilities fail closed. Raw-shell
operation names and secret-bearing argument keys are rejected.

RemoteDesktopCommander.prepare() returns a deterministic, redacted decision only; it
does not execute an adapter. For high-risk operations it requires a trusted approval
verifier to attest the exact request/target/operation/arguments digest and approval
reference. Destructive operations also need the explicit destructive feature switch.
Actual adapters must separately enforce their own timeout, cancellation and audit
contracts. An admitted decision is not evidence that a command has run.

## Skill trust model

HG_SKILL_V1 separates declarative metadata from executable code. Only skills tagged
BUILTIN_VERIFIED or THIRD_PARTY_REVIEWED, with verification enabled and their
capabilities available, can be metadata-eligible for dispatch. Unreviewed imports may
be catalogued as disabled. The validator does not parse arbitrary YAML, load code,
evaluate prompts, or interpret a skill document as trusted instructions.

## Profiles

- minimal: still enforces schema, source binding, readiness, and trace invariants; it does not weaken the core contract.
- standard (default): same invariant checks and emits a warning when adapter metadata does not prove a hard timeout.
- strict: blocks outbound-provider routes without proven hard timeout and blocks external-write/destructive routes pending a separate explicit approval-gate integration.

No profile makes a missing capability ready or makes an evidence verifier optional.

## Free/offline-first implementation

- Runtime requirements remain Python standard library only.
- No ECC package, Node runtime, paid API, service, or background job was installed.
- Upstream ECC was read as design reference; no source snapshot/vendor dependency is in the runtime.
- No external skills, agents, hooks or MCP configs were installed.
- The RemoteDesktopCommander core has no generic shell executor.

## Acceptance and non-goals

Tests must verify source revision mismatch, unbound and unready capability rejection, strict timeout rejection, hook guard denial/exception, observer redaction, success/partial/in-doubt consistency, raw shell and secret-field rejection, command capability/approval requirements, skill trust and license requirements, and zero execution for dry-run paths.

This stage does not prove full live desktop actuation, true OS-enforced timeouts, a remote-target
agent, independent approval service, semantic model verification, or end-to-end deployment.
The command-gate executable flag means an approved adapter may be called; the policy method
itself never calls one. Deployable desktop operations remain unavailable until a target adapter
and evidence suite are bound through the runtime capability registry.

## Rollback

Revert only this feature commit or disable the integrated gate by reverting its server call sites
together with the harness modules and tests. Do not delete state journals, mutate PhoneRuntime
state, rotate credentials, or modify the live service as part of code rollback. Before any
production rollout, perform a disposable-state API smoke test and verify the
brain.request.harness.gated receipt is persisted before provider start.
