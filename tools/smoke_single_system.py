#!/usr/bin/env python3
"""Authenticated, no-provider-call acceptance smoke for an isolated HG2 staging API."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class Probe:
    def __init__(self, base_url: str, read_token: str, write_token: str, timeout: int = 4):
        self.base_url = base_url.rstrip("/")
        self.read_token = read_token
        self.write_token = write_token
        self.timeout = timeout
        self.checks = {}

    def call(self, path, method="GET", token=None, payload=None):
        raw = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.base_url + path, data=raw, method=method)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        if raw is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                content = response.read()
                return response.status, response.headers, content
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def json_call(self, path, method="GET", token=None, payload=None):
        status, headers, raw = self.call(path, method, token, payload)
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = {}
        return status, headers, body

    def require(self, name: str, condition: bool, detail: object = None):
        self.checks[name] = {"ok": bool(condition), "detail": detail}
        if not condition:
            raise RuntimeError("staging acceptance failed: " + name)


def run(args):
    read_token = os.environ.get("HG_API_READ_TOKEN", "")
    write_token = os.environ.get("HG_API_WRITE_TOKEN", "")
    if not read_token or not write_token or read_token == write_token:
        raise RuntimeError("distinct read/write API credentials must be set in process environment")
    if args.base_url not in ("http://127.0.0.1:8788", "http://localhost:8788",
                             "http://[::1]:8788"):
        raise RuntimeError("smoke is restricted to the isolated loopback staging endpoint")
    probe = Probe(args.base_url, read_token, write_token)
    status, headers, html = probe.call("/")
    ui_text = html.decode("utf-8", "replace")
    probe.require("ui_http", status == 200 and "Bộ nhớ hợp nhất" in ui_text,
                  {"http_status": status, "expected_title_present": "Bộ nhớ hợp nhất" in ui_text})
    probe.require("ui_security_headers", "no-store" in headers.get("Cache-Control", "").lower()
                  and "connect-src 'self'" in headers.get("Content-Security-Policy", ""), {
                      "cache_control": headers.get("Cache-Control", ""),
                      "csp_present": bool(headers.get("Content-Security-Policy")),
                  })

    status, _, health = probe.json_call("/api/health")
    build = health.get("build", {})
    provenance = health.get("provenance", {})
    probe.require("health_and_integrity", status == 200 and health.get("ok") is True
                  and (health.get("integrity") or {}).get("ok") is True, {
                      "http_status": status, "integrity": (health.get("integrity") or {}).get("ok")})
    probe.require("source_to_process_identity", provenance.get("ok") is True
                  and provenance.get("startup_manifest_sha256") == provenance.get("current_manifest_sha256")
                  and build.get("git_commit") == args.expected_commit
                  and build.get("source_manifest_sha256") == args.expected_source_manifest
                  and str(build.get("process_pid")) == args.expected_pid, {
                      "commit_matches": build.get("git_commit") == args.expected_commit,
                      "source_manifest_sha256": build.get("source_manifest_sha256"),
                      "process_pid_matches": str(build.get("process_pid")) == args.expected_pid,
                  })
    model_state = health.get("model_gateway", {})
    probe.require("model_gateway_no_network", model_state.get("status") == "NOT_CONFIGURED"
                  and model_state.get("network_called") is False, model_state)
    probe.require("durable_outbox_fail_closed_status",
                  (health.get("durable") or {}).get("status") == "NOT_CONFIGURED",
                  {"status": (health.get("durable") or {}).get("status")})

    status, _, listed = probe.json_call("/api/memory", token=read_token)
    initial_count = int(args.expected_memory_count)
    probe.require("imported_memory_projection", status == 200 and listed.get("count") == initial_count,
                  {"http_status": status, "expected_count": initial_count, "observed_count": listed.get("count")})
    status, _, wrong_read = probe.json_call("/api/memory", token=write_token)
    probe.require("read_write_credential_separation", status == 401,
                  {"write_token_cannot_read": status == 401, "response_code": (wrong_read.get("error") or {}).get("code")})
    denied_record = {"id": "hg2-smoke-denied-" + uuid.uuid4().hex, "type": "fact",
                     "title": "denied", "content": "must not be written", "scope_id": "global"}
    status, _, wrong_write = probe.json_call("/api/memory", method="POST", token=read_token,
                                              payload={"record": denied_record, "idempotency_key": "deny-" + uuid.uuid4().hex})
    probe.require("read_token_cannot_write", status == 401,
                  {"http_status": status, "response_code": (wrong_write.get("error") or {}).get("code")})

    status, _, library = probe.json_call("/api/library", token=read_token)
    assets = library.get("assets", [])
    library_ok = status == 200 and library.get("count") == int(args.expected_library_count)
    library_ok = library_ok and int(library.get("quarantined_count", -1)) == int(args.expected_library_quarantine)
    library_ok = library_ok and all(x.get("integrity") == "VERIFIED" and len(x.get("sha256", "")) == 64 for x in assets)
    probe.require("library_metadata_and_blob_hashes", library_ok, {
        "http_status": status, "count": library.get("count"),
        "quarantined_count": library.get("quarantined_count"),
        "hashes_verified": all(x.get("integrity") == "VERIFIED" for x in assets),
    })

    status, _, durable_status = probe.json_call("/api/durable/status", token=read_token)
    probe.require("durable_status_authenticated", status == 200
                  and (durable_status.get("durable") or {}).get("status") == "NOT_CONFIGURED",
                  {"http_status": status, "status": (durable_status.get("durable") or {}).get("status")})
    status, _, durable_sync = probe.json_call("/api/durable/sync", method="POST", token=write_token, payload={})
    probe.require("durable_sync_not_configured_fail_closed", status == 503
                  and (durable_sync.get("error") or {}).get("code") == "DURABLE_NOT_CONFIGURED",
                  {"http_status": status, "code": (durable_sync.get("error") or {}).get("code")})

    status, _, ask = probe.json_call("/api/ask", method="POST", token=read_token,
                                     payload={"query": "HG2 staging smoke; do not call a model"})
    probe.require("no_real_model_call", status == 503
                  and (ask.get("error") or {}).get("code") == "MODEL_NOT_CONFIGURED",
                  {"http_status": status, "code": (ask.get("error") or {}).get("code")})

    smoke_id = "hg2-staging-smoke-" + uuid.uuid4().hex
    idempotency = "hg2-staging-create-" + uuid.uuid4().hex
    record = {"id": smoke_id, "type": "fact", "title": "Temporary staging acceptance",
              "content": "A non-production record used to verify create/read/delete and tombstone semantics.",
              "scope_id": "global", "source": "staging-acceptance"}
    status, _, created = probe.json_call("/api/memory", method="POST", token=write_token,
                                         payload={"record": record, "idempotency_key": idempotency})
    probe.require("memory_create", status == 201 and (created.get("memory") or {}).get("version") == 1,
                  {"http_status": status})
    status, _, after_create = probe.json_call("/api/memory", token=read_token)
    probe.require("memory_read_after_create", status == 200 and after_create.get("count") == initial_count + 1
                  and any(r.get("id") == smoke_id for r in after_create.get("memory", [])), {
                      "http_status": status, "count": after_create.get("count")})
    status, _, deleted = probe.json_call("/api/memory/" + smoke_id, method="DELETE", token=write_token,
                                         payload={"expected_version": 1, "idempotency_key": "hg2-staging-delete-" + uuid.uuid4().hex})
    probe.require("memory_delete_tombstone", status == 200 and (deleted.get("memory") or {}).get("status") == "tombstoned",
                  {"http_status": status, "status": (deleted.get("memory") or {}).get("status")})
    status, _, after_delete = probe.json_call("/api/memory", token=read_token)
    probe.require("memory_projection_restored", status == 200 and after_delete.get("count") == initial_count
                  and all(r.get("id") != smoke_id for r in after_delete.get("memory", [])), {
                      "http_status": status, "count": after_delete.get("count")})

    evidence = {
        "schema": "HG2_SINGLE_SYSTEM_STAGING_ACCEPTANCE_V1",
        "status": "PASS",
        "base_url": args.base_url,
        "expected_commit": args.expected_commit,
        "expected_source_manifest_sha256": args.expected_source_manifest,
        "process_pid": args.expected_pid,
        "initial_active_memory_count": initial_count,
        "library_assets_expected": int(args.expected_library_count),
        "library_quarantine_count": int(args.expected_library_quarantine),
        "model_provider_called": False,
        "durable_replication_enabled": False,
        "checks": probe.checks,
        "finished_at_unix": int(time.time()),
    }
    raw = json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(raw, encoding="utf-8")
    print(json.dumps({"status": evidence["status"], "checks_passed": sum(x["ok"] for x in probe.checks.values()),
                      "checks_total": len(probe.checks), "evidence_output": args.output}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8788")
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-source-manifest", required=True)
    parser.add_argument("--expected-pid", required=True)
    parser.add_argument("--expected-memory-count", default="31")
    parser.add_argument("--expected-library-count", default="4")
    parser.add_argument("--expected-library-quarantine", default="13")
    parser.add_argument("--output")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
