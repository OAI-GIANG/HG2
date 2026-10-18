# HG State and tool-audit contract V1

1. Canonical state belongs to the StateStore used by HG2; every accepted event is append-only and hash chained.
2. The provider/tool plane may not bypass StateStore for session creation or tool audit.
3. A tool-plane audit record is written before every provider call and before every individual tool call.
4. Audit records omit user prompts, provider response text, tool arguments, tool outputs, authorization headers and API keys. SHA-256 digests may be recorded to correlate evidence without storing content.
5. Tool history functions return event metadata only; they do not expose event payloads. Event types not in the fixed public allowlist appear only as OTHER.
6. Audit write failure is fail-closed before provider invocation or tool execution. If recording completion fails after an action, the prior start record remains as evidence and the caller receives a sanitized error.
7. session.create requires a valid bearer principal with the separate session.create scope. The model cannot elevate its own authority.
8. This contract describes the canonical code path only; no claim is made about a running process or deployment.
