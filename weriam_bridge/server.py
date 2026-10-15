"""localhost bridge: WERIAM ⇄ SDR app (stdlib only).  python3 -m weriam_bridge.server  (or ./run_bridge.sh)

GET  /health                     -> {ok, state, weriam_root}
GET  /cards                      -> {principal:[...], shadow:[...], shadow_record, verify}
POST /principal/decide           {request_id, decision: approve|decline|defer, by, reason}
POST /shadow/label               {id, label, by, latency, note}
GET  /verify                     -> hash-chain verification of journal + evidence
GET  /ledger/principal           -> all principal requests with status (WERIAM's own view)
POST /export                     -> writes labels_export.jsonl (labels + later-observed outcome)
POST /develop {episodes}         -> run WERIAM develop (agent may consume an approval → retire watcher)
"""
from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

from . import adapter as A

STATE = Path(os.environ.get("WERIAM_STATE", Path.home() / ".sdr" / "weriam_state"))
DATA = Path(os.environ.get("WERIAM_BRIDGE_DATA", Path.home() / ".sdr" / "weriam_bridge"))
LOCK = Lock()


def labels_path() -> Path:
    return DATA / "labels.jsonl"


def route(method: str, path: str, body: dict) -> tuple[int, dict]:
    if method == "GET" and path == "/health":
        return 200, {"ok": True, "state": str(STATE), "weriam_root": str(A.WERIAM_ROOT), "engine": "weriam-bridge"}
    if method == "GET" and path == "/cards":
        return 200, {"principal": A.principal_cards(STATE), "shadow": A.shadow_cards(STATE, labels_path()),
                     "shadow_record": A.shadow_record(STATE), "verify": A.verify(STATE)}
    if method == "GET" and path == "/verify":
        return 200, A.verify(STATE)
    if method == "GET" and path == "/ledger/principal":
        return 200, {"requests": A.principal_requests(STATE)}
    if method == "POST" and path == "/principal/decide":
        with LOCK:
            return 200, A.decide(STATE, body["request_id"], body["decision"], body.get("by", "principal (SDR app)"),
                                 body.get("reason", ""), DATA)
    if method == "POST" and path == "/shadow/label":
        with LOCK:
            return 200, A.record_label(STATE, labels_path(), body["id"], body["label"], body.get("by", "human"),
                                       body.get("latency"), body.get("note", ""))
    if method == "POST" and path == "/export":
        n = A.export_labels(STATE, labels_path(), DATA / "labels_export.jsonl")
        return 200, {"rows": n, "path": str(DATA / "labels_export.jsonl")}
    if method == "POST" and path == "/develop":
        with LOCK:
            return 200, {"last_line": A.init_state(STATE, int(body.get("episodes", 1))), "verify": A.verify(STATE)}
    return 404, {"error": f"no route {method} {path}"}


class H(BaseHTTPRequestHandler):
    def _go(self, method):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            code, out = route(method, self.path.split("?")[0], body)
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
    print(f"weriam-bridge on 127.0.0.1:{a.port} state={STATE} data={DATA}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
