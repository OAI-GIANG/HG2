# HG Authentication and authority contract V1

1. hg/auth.py validates an exact Authorization: Bearer header against HG_AUTH_TOKEN using a constant-time comparison. Missing token configuration, a malformed header or a mismatch fails closed. Tokens are never returned or logged.
2. HG_AUTH_SCOPES accepts only provider.invoke and session.create. The default is provider.invoke only. Any unknown scope invalidates the configuration; session.create requires its explicit separate grant.
3. hg/agent.py passes the validated header to the tool plane. A caller-controlled boolean is not accepted as proof of authentication. The trusted host must supply the actual header from its authentication boundary.
4. Provider API keys are read only from HG_MODEL_API_KEY or the three allowlisted HG_MODEL_* keys in HG_PROVIDER_CONFIG_FILE (default ~/.config/hg/secret.env). The file is read as data; it is never sourced or evaluated.
5. Provider URLs must use HTTPS and must not contain embedded user credentials, query parameters or fragments. Redirects are not followed, so the bearer key is not forwarded to a different location.
6. The provider client uses bounded request/response sizes and a finite timeout. Remote error bodies and credentials are never copied into error messages or audit records.
7. Built-in tools are a fixed allowlist: identity.get, history.verify, history.summary, history.recent and session.create.
8. Shell execution, arbitrary file read/write, generic network fetch, deployment, identity mutation and state import remain explicitly forbidden. Tool schemas are not an authorization mechanism; the tool plane validates each call again.
9. Tool arguments must be JSON objects without duplicate keys or unknown fields. Lists, iteration counts, string sizes and outputs are bounded.
10. Audit payloads must not contain prompts, tool arguments, tool outputs, authorization headers or API keys. They may contain event type, approved tool name, outcome, error code and SHA-256 digests. Unrecognized tool names/event types are redacted.
11. If the audit store cannot accept the pre-action record, the provider/tool action does not start. Authorization decisions fail closed.

This contract does not grant the model direct filesystem, shell or arbitrary HTTP access.
