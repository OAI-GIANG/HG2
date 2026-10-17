"""Fail-closed HG2 durable outbox adapter.

The canonical event log is the local authority. Delivery is an at-least-once
replication attempt; only an authenticated, contract-matching receipt counts as
acknowledgement. The legacy HG_DURABLE backend is deliberately not assumed
compatible with the HG2 memory schema.
"""
from __future__ import annotations
import hashlib, json, os, urllib.error, urllib.request
from urllib.parse import urlsplit
from .history import canonical

CONTRACT = "HG2_DURABLE_BATCH_V1"
MEMORY_EVENTS = {"memory.mutated", "memory.tombstoned"}


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a bearer token to a redirect target.
        return None


def _urlopen_without_redirect(req, timeout=4):
    return urllib.request.build_opener(_NoRedirectHandler).open(req, timeout=timeout)


class DurableError(Exception):
    code = "DURABLE_ERROR"
class DurableNotConfigured(DurableError):
    code = "DURABLE_NOT_CONFIGURED"
class DurableContractMismatch(DurableError):
    code = "DURABLE_CONTRACT_MISMATCH"
class DurableDeliveryError(DurableError):
    code = "DURABLE_DELIVERY_FAILED"

class DurableOutbox:
    def __init__(self, store, *, base_url=None, token=None, timeout=4, opener=None):
        self.store=store
        self.base_url=(base_url if base_url is not None else os.environ.get("HG_DURABLE_URL", "")).strip().rstrip("/")
        self.token=token if token is not None else os.environ.get("HG_DURABLE_TOKEN", "")
        self.timeout=max(1,min(30,int(timeout)))
        self.opener=opener or _urlopen_without_redirect

    def status(self):
        events=self.store.replay()
        acked=set()
        for e in events:
            if e.get("event_type")=="durable.batch.acknowledged":
                p=e.get("payload",{})
                acked.update(p.get("event_batch_ids", []))
        pending=[]
        for e in events:
            if e.get("event_type") not in MEMORY_EVENTS: continue
            bid=hashlib.sha256(canonical({"event_id":e["event_id"],"record_hash":e["record_hash"]}).encode()).hexdigest()
            if bid not in acked: pending.append({"batch_id":bid,"event":e})
        return {"configured":bool(self.base_url and self.token),"contract":CONTRACT,
                "pending_count":len(pending),"acknowledged_count":len(acked),
                "local_authority":"PHONE_EVENT_LOG","remote_is_authority":False,
                "status":"READY" if self.base_url and self.token else "NOT_CONFIGURED"}

    def deliver_once(self, limit=25):
        if not self.base_url or not self.token: raise DurableNotConfigured("durable URL/token not configured")
        parts = urlsplit(self.base_url)
        if (not parts.hostname or parts.username or parts.password or parts.query or parts.fragment
                or parts.path not in ("", "/")):
            raise DurableDeliveryError("durable URL must be an absolute origin without embedded credentials, path, query, or fragment")
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname.lower() in local_hosts):
            raise DurableDeliveryError("durable endpoint requires HTTPS outside loopback staging")
        if not isinstance(limit,int) or not 1<=limit<=100: raise DurableDeliveryError("limit must be 1..100")
        # Contract negotiation is mandatory; legacy /backend/memory/persist is not this protocol.
        req=urllib.request.Request(self.base_url+"/backend/hg2/capabilities",method="GET")
        req.add_header("Authorization","Bearer "+self.token); req.add_header("Accept","application/json")
        try:
            with self.opener(req,timeout=self.timeout) as response:
                caps=json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401,403): raise DurableDeliveryError("durable credential rejected or insufficiently scoped") from None
            if exc.code==404: raise DurableContractMismatch("backend does not expose HG2 durable contract") from None
            raise DurableDeliveryError("durable capability request failed with HTTP %d"%exc.code) from None
        except (urllib.error.URLError,TimeoutError,OSError,json.JSONDecodeError,UnicodeDecodeError) as exc:
            raise DurableDeliveryError("durable capability request failed: "+type(exc).__name__) from None
        if caps.get("contract")!=CONTRACT or caps.get("memory_schema")!="HG_MEMORY_V1" or caps.get("supports_tombstones") is not True or caps.get("supports_scopes") is not True or caps.get("required_scope")!="MEMORY_PERSIST":
            raise DurableContractMismatch("backend capabilities do not satisfy HG2 memory contract")
        st=self.status(); acked=set()
        for event in self.store.replay():
            if event.get("event_type")=="durable.batch.acknowledged": acked.update(event.get("payload",{}).get("event_batch_ids", []))
        batch=[]
        for e in self.store.replay():
            if e.get("event_type") not in MEMORY_EVENTS: continue
            bid=hashlib.sha256(canonical({"event_id":e["event_id"],"record_hash":e["record_hash"]}).encode()).hexdigest()
            if bid not in acked: batch.append({"batch_id":bid,"event":e})
            if len(batch)>=limit: break
        if not batch: return {"status":"EMPTY","delivered":0,"pending_count":st["pending_count"]}
        body={"contract":CONTRACT,"batch_id":hashlib.sha256(canonical([x["batch_id"] for x in batch]).encode()).hexdigest(),"events":batch}
        raw=canonical(body).encode(); post=urllib.request.Request(self.base_url+"/backend/hg2/memory/batch",data=raw,method="POST")
        post.add_header("Authorization","Bearer "+self.token); post.add_header("Content-Type","application/json")
        post.add_header("Idempotency-Key",body["batch_id"])
        try:
            with self.opener(post,timeout=self.timeout) as response: receipt=json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,OSError,json.JSONDecodeError,UnicodeDecodeError) as exc:
            raise DurableDeliveryError("durable batch delivery failed: "+type(exc).__name__) from None
        if receipt.get("ok") is not True or receipt.get("contract")!=CONTRACT or receipt.get("batch_id")!=body["batch_id"] or receipt.get("accepted_count")!=len(batch):
            raise DurableDeliveryError("durable receipt failed strict validation")
        # The acknowledgement is an append-only event; the next retry is idempotent.
        self.store.emit("durable.batch.acknowledged",{"batch_id":body["batch_id"],"event_batch_ids":[x["batch_id"] for x in batch],"accepted_count":len(batch),"receipt_sha256":hashlib.sha256(canonical(receipt).encode()).hexdigest()},event_id="durable-ack:"+body["batch_id"])
        return {"status":"ACKNOWLEDGED","delivered":len(batch),"batch_id":body["batch_id"]}
