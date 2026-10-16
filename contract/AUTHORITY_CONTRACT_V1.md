# HG2 Host-Supplied Session Authority Contract V1

Status: IMPLEMENTED FAIL-CLOSED BOUNDARY / PRODUCTION VERIFIER NOT PROVIDED / RELEASE BLOCKED.

## Purpose

The phone runtime must not equate the presence of a credential string, a non-empty environment variable, or caller intent with authenticated identity. Session creation is denied unless the host injects a verifier and that verifier returns the literal boolean true.

## Required verifier responsibilities

The host-supplied session_authenticator(credential) must independently validate, using a trusted issuer/configuration and protected replay/revocation state:

1. Credential authenticity and approved issuer/key status, validated against the trusted issuer/configuration selected for the deployment.
2. Subject and audience binding to the intended HG2 phone runtime.
3. Explicit action scope for session.create and least privilege.
4. Not-before and expiry with a defined clock-skew policy.
5. Revocation status and token/session replay protection (unique identifier and durable replay state).
6. Expected state/runtime version where the authorization decision is version-bound.
7. Credential parsing limits and safe error behavior; never return or log secret values.

The runtime intentionally accepts only a literal True result. Exceptions, False, None, truthy non-booleans, absent verifier, and missing credentials are denied. The verifier must not return True until every applicable requirement above is satisfied.

## Limits and acceptance

This repository includes the fail-closed injection boundary and deterministic denial tests. It does NOT include a production issuer/key verifier, revocation service, durable replay store, trusted clock policy, or current live credential authority. Therefore this contract and unit tests do not prove production authentication. No real credential is stored in source or test fixtures. Production auth and end-to-end runtime remain BLOCKED until an actual authorized verifier implementation and its technical evidence are supplied and validated.
