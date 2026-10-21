# HG (clean-slate)

Independent HG product: new repository, parentless genesis, fresh implementation.
Roles: PHONE = single primary runtime and state owner; VPS1 = HTTPS edge relay (never the
primary runtime, never holds the model key); VPS2 = standby/worker only.
No fork, no inherited history, no reused runtime/authority/state engine, standard library only.

HG Remote Desktop Commander — unified, offline-first harness

The HG-native harness wraps the existing Brain and runtime capability registry with
source-bound dispatch checks, redacted lifecycle hooks, execution-trace verification,
and explicit response-only/partial/in-doubt outcomes. The Remote Desktop Commander
contract is an adapter boundary, not a free-form shell bridge: operations must be
registered, capabilities granted, and high-risk actions backed by a verifier that
binds approval to the exact command digest. Skills use a JSON contract, explicit
trust metadata, capability admission, and required verification. All three remain
Python-standard-library-only; no external harness package is required.

ECC research reference (MIT-licensed upstream): https://github.com/affaan-m/ECC
HG absorbs selected engineering patterns, not ECC runtime code or command names.
HG schemas, policy, state authority, and Remote Desktop Commander identity remain
native to HG. Third-party skills are untrusted until their source, hash, license,
capabilities, and verification path are reviewed.

## Functional architecture and local tools

The target layout is one central Brain plus four subordinate logical domains. See
[`docs/architecture/HG2-FIVE-BRANCH-ARCHITECTURE-V1.md`](docs/architecture/HG2-FIVE-BRANCH-ARCHITECTURE-V1.md)
for ownership boundaries and readiness rules.

Offline local utilities include repository code intelligence (`tools/hg_code_intelligence.py`),
creative-assimilation candidate evaluation (`hg/creative_assimilation.py`), and the optional
voice CLI (`tools/voice`). Their unit tests do not imply that they are wired as production Brain
capabilities. Voice synthesis quality is not accepted; local model-backed ASR/TTS remains gated
on pinned artifacts, rights/license review and target-device quality evidence.
