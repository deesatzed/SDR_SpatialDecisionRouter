"""localhost bridge: WERIAM ⇄ SDR app (stdlib + cryptography).  python3 -m weriam_bridge.server  (or ./run_bridge.sh)

Every route except GET /health needs header  X-SDR-Token: <DATA/token>  (created 0600 at first start).
GET  /health                       -> {ok, state, weriam_root, hooks}
GET  /cards                        -> {principal:[...], live:{status,pending,results,...}, shadow_record, verify}
POST /approver/register            {name, pub}  (Ed25519 raw public key, base64; pinned on first use)
POST /principal/decide             {request_id, decision: approve|decline|defer, payload?, sig?, key_id?}
                                   approve/decline need a signed payload {request_id, decision, by, ts, nonce, request_hash}
POST /live/start                   {episodes, scenarios?, max_pauses, timeout, preset: weriam|theology_observed|baseline…}
POST /live/label                   {pause_id, label, by, latency}
GET  /verify                       -> WERIAM hash chains + signed side ledger audit
GET  /ledger/principal | POST /export | POST /develop {episodes}
"""
from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

from . import adapter as A
from . import signing as SG
from .live import Live

STATE = Path(os.environ.get("WERIAM_STATE", Path.home() / ".sdr" / "weriam_state"))
DATA = Path(os.environ.get("WERIAM_BRIDGE_DATA", Path.home() / ".sdr" / "weriam_bridge"))
LOCK = Lock()
_live: Live | None = None


def live() -> Live:
    global _live
    if _live is None or _live.state != STATE:
        _live = Live(STATE, DATA)
    return _live


def hooks_available() -> bool:
    import inspect
    from weriam.runner import run_episode
    return "pause_hook" in inspect.signature(run_episode).parameters


def _decide(body: dict) -> dict:
    dec = body["decision"].lower()
    rid = body["request_id"]
    if dec.startswith("defer"):
        return A.decide(STATE, rid, "defer", body.get("by", "principal (SDR app)"), body.get("reason", ""), DATA)
    ap = SG.Approvers(DATA)
    payload, sig, kid = body.get("payload"), body.get("sig"), body.get("key_id")
    if not (payload and sig and kid):
        raise PermissionError("approve/decline must be signed (payload, sig, key_id)")
    if payload.get("request_id") != rid or not payload.get("decision", "").lower().startswith(dec[:5]):
        raise PermissionError("signed payload does not match this request/decision")
    req = next((e for e in A.journal(STATE).entries("principal_request") if e["hash"][:16] == rid), None)
    if req is None:
        raise KeyError(f"no principal request {rid}")
    if payload.get("request_hash") != req["hash"]:
        raise PermissionError("signed payload is for a different request entry (hash mismatch)")
    k = ap.verify(payload, sig, kid)
    by = f"{k['name']} · ed25519:{kid}"

    def apply():
        rec = A.decide(STATE, rid, dec, by, body.get("reason", ""), DATA)
        ent = next(e for e in A.journal(STATE).entries("principal_decision") if e["payload"]["request_id"] == rid)
        side = ap.record(payload, sig, kid, ent)
        rec.update(signed=True, key_id=kid, side_ledger_seq=side["seq"], side_ledger_hash=side["hash"])
        return rec

    lv = live()
    if lv.thread and lv.thread.is_alive():
        # the running agent holds the journal in memory: apply after the run so the chain cannot fork
        lv.after_run.append(apply)
        return {"request_id": rid, "decision": dec, "queued": True, "by": by,
                "note": "live run in progress; applied via WERIAM CLI when the run ends"}
    return apply()


def route(method: str, path: str, body: dict) -> tuple[int, dict]:
    if method == "GET" and path == "/health":
        return 200, {"ok": True, "state": str(STATE), "weriam_root": str(A.WERIAM_ROOT), "engine": "weriam-bridge",
                     "hooks": hooks_available(), "token_required": True}
    if method == "GET" and path == "/cards":
        lv = live()
        running = bool(lv.thread and lv.thread.is_alive())
        try:
            pc = A.principal_cards(STATE)
        except (ValueError, KeyError):          # journal line mid-write by the running agent: retry next poll
            pc = None
        return 200, {"principal": pc, "live": lv.snapshot(),
                     "shadow_record": A.shadow_record(STATE), "verify": A.verify(STATE) if not running else {"ok": None, "msg": "live run"}}
    if method == "GET" and path == "/verify":
        v = A.verify(STATE)
        v["signed"] = SG.Approvers(DATA).audit(A.journal(STATE).entries())
        v["ok"] = v["ok"] and v["signed"]["ok"]
        return 200, v
    if method == "GET" and path == "/ledger/principal":
        return 200, {"requests": A.principal_requests(STATE)}
    if method == "POST" and path == "/approver/register":
        return 200, SG.Approvers(DATA).register(body["name"], body["pub"])
    if method == "POST" and path == "/principal/decide":
        with LOCK:
            return 200, _decide(body)
    if method == "POST" and path == "/live/start":
        if not hooks_available():
            raise ValueError("WERIAM checkout lacks pause_hook (needs branch sdr-principal-hooks)")
        return 200, live().start(body.get("episodes", 1), body.get("scenarios"), body.get("max_pauses", 12),
                                 body.get("timeout", 90), preset_name=body.get("preset", "weriam"))
    if method == "POST" and path == "/live/label":
        return 200, live().label(body["pause_id"], body["label"], body.get("by", "human"), body.get("latency"))
    if method == "POST" and path == "/export":
        n = A.export_labels(STATE, DATA / "labels.jsonl", DATA / "labels_export.jsonl")
        return 200, {"rows": n, "path": str(DATA / "labels_export.jsonl"), "results": str(live().results_path)}
    if method == "POST" and path == "/develop":
        lv = live()
        if lv.thread and lv.thread.is_alive():
            raise ValueError("live run in progress")
        with LOCK:
            return 200, {"last_line": A.init_state(STATE, int(body.get("episodes", 1))), "verify": A.verify(STATE)}
    return 404, {"error": f"no route {method} {path}"}


class H(BaseHTTPRequestHandler):
    def _go(self, method):
        try:
            p = self.path.split("?")[0]
            if p != "/health" and self.headers.get("X-SDR-Token") != SG.token(DATA):
                raise PermissionError("missing or wrong X-SDR-Token")
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            code, out = route(method, p, body)
        except PermissionError as e:
            code, out = 401, {"error": str(e)}
        except (KeyError, ValueError) as e:
            code, out = 400, {"error": str(e)}
        except Exception as e:  # pragma: no cover
            code, out = 500, {"error": repr(e)}
        data = json.dumps(out).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_GET(self): self._go("GET")
    def do_POST(self): self._go("POST")
    def log_message(self, *a): pass


def main():
    global STATE, DATA
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--state", default=str(STATE))
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--init", action="store_true", help="create the WERIAM state with `weriam develop` if missing")
    a = ap.parse_args()
    STATE, DATA = Path(a.state), Path(a.data)
    if a.init and not (STATE / "agent.json").exists():
        print("init:", A.init_state(STATE, 2))
    tok = SG.token(DATA)
    print(f"weriam-bridge on 127.0.0.1:{a.port} state={STATE} data={DATA} token={DATA / 'token'} hooks={hooks_available()}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
