"""Least-privilege HG -> HG2 public-read adapter. Python standard library only."""
from __future__ import annotations

import json
import os
import stat
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OWNER = "OAI-GIANG"
REPO = "HG2"
FULL_REPO = f"{OWNER}/{REPO}"
REF = "hg-genesis"
API_BASE = "https://api.github.com"
CAPABILITY_ID = "github_hg2_public_read"
DEFAULT_TOKEN_PATH = Path.home() / ".config" / "hg" / "github_token"
DEFAULT_REGISTRY_PATH = Path.home() / ".config" / "hg" / "capabilities" / "registry.json"
MAX_RESPONSE_BYTES = 1_000_000
MAX_TOKEN_BYTES = 4096
USER_AGENT = "HG2-Phone-ReadOnly-Connector/1.0"


class ConnectorError(Exception):
    """Safe-to-report error; contains no upstream body, URL with auth or secret."""

    def __init__(self, code: str, status: int):
        super().__init__(code)
        self.code = code
        self.status = status


def _read_private_token(path=DEFAULT_TOKEN_PATH) -> str:
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise ConnectorError("CREDENTIAL_FILE_INVALID", 503)
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise ConnectorError("CREDENTIAL_PERMISSIONS_INVALID", 503)
            raw = os.read(fd, MAX_TOKEN_BYTES + 1)
        finally:
            os.close(fd)
    except ConnectorError:
        raise
    except OSError:
        raise ConnectorError("CREDENTIAL_UNAVAILABLE", 503) from None

    if len(raw) > MAX_TOKEN_BYTES:
        raise ConnectorError("CREDENTIAL_SIZE_INVALID", 503)
    try:
        token = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise ConnectorError("CREDENTIAL_FORMAT_INVALID", 503) from None
    if not token or "\n" in token or "\r" in token:
        raise ConnectorError("CREDENTIAL_FORMAT_INVALID", 503)
    return token


def _read_grant(path=DEFAULT_REGISTRY_PATH) -> dict:
    try:
        info = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ConnectorError("CAPABILITY_REGISTRY_INVALID", 503)
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise ConnectorError("CAPABILITY_REGISTRY_PERMISSIONS_INVALID", 503)
        with open(path, "r", encoding="utf-8") as stream:
            if os.fstat(stream.fileno()).st_size > 65_536:
                raise ConnectorError("CAPABILITY_REGISTRY_TOO_LARGE", 503)
            registry = json.load(stream)
    except ConnectorError:
        raise
    except (OSError, ValueError):
        raise ConnectorError("CAPABILITY_REGISTRY_UNAVAILABLE", 503) from None

    capabilities = registry.get("capabilities") if isinstance(registry, dict) else None
    grant = capabilities.get(CAPABILITY_ID) if isinstance(capabilities, dict) else None
    if not isinstance(grant, dict):
        raise ConnectorError("CAPABILITY_NOT_AUTHORIZED", 403)
    if (
        grant.get("id") != CAPABILITY_ID
        or grant.get("owner_authorization") != "GRANTED"
        or grant.get("install_state") != "AUTHORIZED"
        or grant.get("runtime_state") != "READY"
        or grant.get("revocation_state") != "ACTIVE"
        or grant.get("target") != {"repository": FULL_REPO, "ref": REF}
        or set(grant.get("actions", [])) != {"commit.read", "manifest.read"}
        or set(grant.get("requested_permissions", [])) != {"metadata:read", "contents:read"}
        or grant.get("write_enabled") is not False
    ):
        raise ConnectorError("CAPABILITY_NOT_AUTHORIZED", 403)
    return grant


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _get_json(url: str, token: str, *, opener=None, timeout=8.0) -> tuple[int, dict]:
    # URLs are assembled from constants only. Ref/path input is never forwarded from callers.
    req = urllib.request.Request(
        url, method="GET",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
            "Cache-Control": "no-store",
        },
    )
    if opener is None:
        opener = urllib.request.build_opener(_NoRedirect()).open
    try:
        response = opener(req, timeout=timeout)
        try:
            status = int(response.status)
            body = response.read(MAX_RESPONSE_BYTES + 1)
        finally:
            close = getattr(response, "close", None)
            if close:
                close()
    except urllib.error.HTTPError as exc:
        try:
            exc.close()
        except Exception:
            pass
        if exc.code == 401:
            raise ConnectorError("GITHUB_CREDENTIAL_REJECTED", 502) from None
        if exc.code == 403:
            raise ConnectorError("GITHUB_ACCESS_DENIED", 502) from None
        raise ConnectorError("GITHUB_UPSTREAM_ERROR", 502) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ConnectorError("GITHUB_UPSTREAM_UNAVAILABLE", 502) from None
    except ConnectorError:
        raise
    except Exception:
        raise ConnectorError("GITHUB_RESPONSE_INVALID", 502) from None

    if not 200 <= status < 300:
        raise ConnectorError("GITHUB_UPSTREAM_ERROR", 502)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ConnectorError("GITHUB_RESPONSE_TOO_LARGE", 502)
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ConnectorError("GITHUB_RESPONSE_INVALID", 502) from None
    if not isinstance(payload, dict):
        raise ConnectorError("GITHUB_RESPONSE_INVALID", 502)
    return status, payload


def read_hg2_ref(repository: str, ref: str, *, token_path=DEFAULT_TOKEN_PATH,
                 registry_path=DEFAULT_REGISTRY_PATH, opener=None, timeout=8.0) -> dict:
    """Only read the approved commit and manifest. Wrong target is denied before disk/network access."""
    if repository != FULL_REPO:
        raise ConnectorError("REPOSITORY_SCOPE_MISMATCH", 403)
    if ref != REF:
        raise ConnectorError("REF_SCOPE_MISMATCH", 403)

    _read_grant(registry_path)
    token = _read_private_token(token_path)
    commit_url = f"{API_BASE}/repos/{OWNER}/{REPO}/commits/{REF}"
    manifest_url = (
        f"{API_BASE}/repos/{OWNER}/{REPO}/contents/manifest.json?"
        f"ref={urllib.parse.quote(REF, safe='')}"
    )
    commit_status, commit = _get_json(commit_url, token, opener=opener, timeout=timeout)
    manifest_status, manifest = _get_json(manifest_url, token, opener=opener, timeout=timeout)

    sha = commit.get("sha")
    tree_sha = ((commit.get("commit") or {}).get("tree") or {}).get("sha")
    blob_sha = manifest.get("sha")
    if (
        not isinstance(sha, str) or len(sha) not in (40, 64)
        or not isinstance(tree_sha, str) or len(tree_sha) not in (40, 64)
        or manifest.get("path") != "manifest.json"
        or not isinstance(blob_sha, str) or len(blob_sha) not in (40, 64)
    ):
        raise ConnectorError("GITHUB_RESPONSE_SCHEMA_INVALID", 502)

    return {
        "ok": True,
        "source": "github-api",
        "authenticated": True,
        "repository": FULL_REPO,
        "ref": REF,
        "commit_sha": sha,
        "commit_url": commit.get("html_url"),
        "tree_sha": tree_sha,
        "manifest_path": "manifest.json",
        "manifest_blob_sha": blob_sha,
        "http_status": {"commit": commit_status, "manifest": manifest_status},
    }
