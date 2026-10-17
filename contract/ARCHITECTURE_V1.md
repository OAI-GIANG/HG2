# HG canonical architecture V1

1. Exactly one canonical runtime design: the phone runtime (hg/phone_runtime.py); it owns state and history.
2. hg/history.py provides append-only, hash-chained state/history and fail-closed integrity verification.
3. hg/auth.py validates the real bearer header and issues scoped authenticated-principal objects. hg/authority.py remains the deny-by-default action policy.
4. hg/provider.py is the only model-provider transport. It uses an explicit HTTPS URL, bounded requests/responses, refuses redirects and returns sanitized error codes.
5. hg/toolplane.py implements a fixed set of internal tools and a bounded model/tool loop. Its built-in tools cannot execute shell commands, read/write arbitrary files, deploy or make generic network requests.
6. hg/agent.py wires the phone-owned StateStore, provider adapter, bearer authenticator and tool plane into the application entry point. Authentication is derived from the token, not a caller-provided boolean.
7. Provider/tool calls are audited through StateStore before action. Audit records store action metadata and content hashes, not prompts, arguments, tool outputs or credentials. Unknown tool/event names are redacted.
8. VPS1 runs only hg/edge.py: /health, /edge/register, /edge/heartbeat, /edge/status behind HG_EDGE_TOKEN. It stores device identity, last-seen and sequence only, and rejects payloads carrying model-key material.
9. VPS2 may mirror the edge for standby/worker/failover; it must never own canonical state.
10. The phone dials outbound over HTTPS; it needs no inbound port and works offline.
11. Two primaries or implicit failover that forks history are prohibited.

See contract/AUTHENTICATION_V1.md, contract/STATE_V1.md and contract/ACCEPTANCE_MATRIX_V1.md for behavioral contracts and evidence scope.
