# HG2 acceptance matrix V1

Scope: source structure, software features, and designed operating mechanisms in the canonical HG2 repository only. This matrix does not evaluate a running process or deployment.

Status vocabulary:
- IMPLEMENTED_AND_TESTED: implementation exists and a directly relevant test exercises it.
- IMPLEMENTED_UNVERIFIED: code or contract exists, but behavior is not yet tested directly.
- MISSING: no canonical implementation was found for the stated required capability.
- DEFECTIVE: direct test or code review demonstrates behavior contrary to the contract.

| Domain | Required behavior | Status after this change | Evidence |
|---|---|---|---|
| Product identity | Stable HG identity and phone-primary architecture | IMPLEMENTED_AND_TESTED | hg/identity.py; tests/test_core.py |
| Authentication | Actual constant-time Bearer validation; scoped principal; default fail-closed; fabricated principal cannot grant scope | IMPLEMENTED_AND_TESTED for auth module and injected agent boundary | hg/auth.py; tests/test_auth.py; tests/test_agent.py |
| Authorization | Deny by default; provider invocation requires validated principal; shell/file/fetch/deploy remain forbidden | IMPLEMENTED_AND_TESTED for policy gate; application host must supply the real header | hg/authority.py; hg/toolplane.py; tests/test_toolplane.py |
| Provider | HTTPS-only OpenAI-compatible Chat Completions, bounded request/response, safe error codes, no key leakage, no redirect forwarding | IMPLEMENTED_AND_TESTED with mocked transport | hg/provider.py; tests/test_provider.py |
| Tool orchestration | Model tool calls, strict arguments, max iterations/calls, repeated-call cycle stop | IMPLEMENTED_AND_TESTED with injected provider doubles | hg/toolplane.py; tests/test_toolplane.py |
| Agent entry point | Wire phone-owned StateStore, provider, authenticator and tool plane behind an explicit Bearer header | IMPLEMENTED_AND_TESTED with test doubles | hg/agent.py; tests/test_agent.py |
| Tool capability boundary | Fixed built-in tools only; no shell, arbitrary file, deploy or generic network tool | IMPLEMENTED_AND_TESTED | hg/toolplane.py; tests/test_toolplane.py; tests/test_contract_completeness.py |
| Audit | Audit starts before provider/tool actions; prompts/credentials/arguments/results omitted; hashes and outcomes recorded; audit outage fails closed before side-effecting tool | IMPLEMENTED_AND_TESTED | hg/toolplane.py; tests/test_toolplane.py |
| History integrity | Hash-chained history and checkpoint checks | IMPLEMENTED_AND_TESTED | hg/history.py; tests/test_core.py |
| State/memory scope | Durable event/history state exists; semantic retrieval and general-purpose memory are not yet claimed | IMPLEMENTED_UNVERIFIED for event history; MISSING for semantic memory | hg/history.py; tests/test_core.py |
| Authentication contract | Explicit token, scopes and trusted-host boundary | IMPLEMENTED_AND_TESTED for auth behavior; HTTP ingress middleware itself is not provided by this feature | contract/AUTHENTICATION_V1.md; hg/auth.py; tests |
| State contract | Hash-chained append-only state and metadata-minimizing tool readouts | IMPLEMENTED_AND_TESTED for tested path | contract/STATE_V1.md; hg/history.py; tests |
| Source provenance | SHA-256 and Git blob hash graph for selected source/docs/tests, verified by test; graph is not external attestation | IMPLEMENTED_AND_TESTED for integrity inventory; IMPLEMENTED_UNVERIFIED for origin claims | provenance/HG2_SOURCE_PROVENANCE_GRAPH_V1.json; scripts/update_provenance_graph.py; tests/test_contract_completeness.py |
| AI semantic quality | Actual HG responses evaluated against all 26 V2.1 synthetic fixture oracles | MISSING / NOT RUN | tests/fixtures/hg-native-intelligence-v2.1: fixtures explicitly remain NOT_RUN |

Completion rule: this matrix is not a blanket product certification. Provider/toolplane integration can be accepted only if the directly relevant suite passes and source hashes match. Broader HG feature completeness remains blocked by semantic-memory and real AI acceptance gaps. Synthetic fixtures are not proof that actual HG behavior meets their oracles.

## Acceptance commands

    PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest discover -s tests -v
    python -m py_compile hg/*.py tests/test_auth.py tests/test_provider.py tests/test_toolplane.py tests/test_agent.py tests/test_contract_completeness.py scripts/update_provenance_graph.py
    python scripts/update_provenance_graph.py
    git diff --check
