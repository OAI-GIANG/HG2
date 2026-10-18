# Live PHONE credential read-only verification (2026-10-14)

## Scope
This test read the existing private credential in-process and performed only authenticated HTTP GET requests to GitHub. The token value was never printed, stored in the evidence, or sent to VPS. No writes were attempted.

## Results
- Credential file present: yes; mode 0600; nonempty.
- Authenticated user: HTTP 200; `OAI-GIANG`.
- Effective OAuth scope response: `public_repo`.
- `GET /repos/OAI-GIANG/HG2`: HTTP 200; repository `OAI-GIANG/HG2`; default branch `hg-genesis`; public repository.
- `GET /repos/OAI-GIANG/HG2/commits/hg-genesis`: HTTP 200; returned SHA `cdebaeed014371f033f14352f552c6d0d4e69198`; commit URL https://github.com/OAI-GIANG/HG2/commit/cdebaeed014371f033f14352f552c6d0d4e69198.
- Request timestamp: `2026-10-14T03:04:44.094880+00:00`.
- Credential fingerprint is deliberately omitted from this evidence file; no full token or authorization header was recorded.

## What this proves
The credential stored on PHONE is accepted by GitHub for public repository read requests at the observed time.

## What this does not prove
- The running HG runtime consumes this credential. The live `/api/github/status` endpoint still reports `configured=false`.
- The HG runtime has an implemented route to fetch a ref/commit/file through its own connector; the candidate branches/contents routes returned 404.
- The local capability registry's `revocation_state=REVOKED` has been reconciled with the authority provider.
- Authenticated write permission is needed or has been tested. No write was attempted.

## Safety
GET-only. No service restart, file mutation, token export, or production source change.
