# HG → HG2 phone-side read-only connector

This candidate provides a narrowly scoped GitHub reader, not a broad GitHub authority runtime.

- Allowed target: `OAI-GIANG/HG2`, ref `hg-genesis`.
- Allowed upstream resources: the commit object for that exact ref and `manifest.json` at the same ref.
- Reads the GitHub token only from PHONE-private `~/.config/hg/github_token`; it checks current UID, regular-file type, no-follow open, mode without group/world access and bounded size.
- Requires a separate `github_hg2_public_read` grant in the existing registry. The older broad `github_access` entry stays REVOKED and unchanged.
- Rejects wrong repo/ref before reading the token or making network requests.
- Fixed HTTPS host `api.github.com`; GET only; bounded response; no redirects; error responses do not echo GitHub bodies or credential data.
- No arbitrary URLs, paths, owners, branch names, writes, pushes, merges or deletes.
- Runtime integration must remain bound to `127.0.0.1`; no VPS route is added.
- Unit tests use only a fake transport; a separate live probe is required before claiming end-to-end success.

Do not reinstall the quarantined Python `.pth` bootstrap. The only supported integration path is explicit runtime source with backup, source hash, and rollback.
