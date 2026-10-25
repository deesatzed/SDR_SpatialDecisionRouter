#!/usr/bin/env python3
"""Localhost Layer 1 bridge for the Spatial Decision Router home-health review pack.

Does not call OpenRouter or any other cloud model. Binds 127.0.0.1 unless
HOMEHEALTH_BIND is set. Default port 8767 (risk sidecar is 8765, WERIAM is 8766).

  homehealth/sdr_bridge/run_bridge.sh
  GET  /health
  GET  /cases          recompute Layer 1 for the bundled synthetic pack
  POST /decide         {"case_id": "LX12-007"} or {"facts": { ...library fact fields... }}
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decide import ENGINE, ENGINE_VERSION, live_cases, load_pack, decision_for  # noqa: E402


def handle(method: str, path: str, body: dict | None) -> tuple[int, dict]:
    path = path.split("?", 1)[0]
    try:
        pack = load_pack()
    except (OSError, json.JSONDecodeError) as e:
        return 500, {"ok": False, "error": f"vignette pack unreadable: {e}"}
    params = pack.get("params_version")
    if method == "GET" and path == "/health":
        return 200, {
            "ok": True,
            "engine": ENGINE,
            "engine_version": ENGINE_VERSION,
            "params_version": params,
            "cases": len(pack.get("cases") or []),
            "cloud": False,
        }
    if method == "GET" and path == "/cases":
        return 200, {
            "ok": True,
            "engine": ENGINE,
            "engine_version": ENGINE_VERSION,
            "params_version": params,
            "source": "live",
            "cases": live_cases(pack),
        }
    if method == "POST" and path == "/decide":
        body = body or {}
        if body.get("case_id"):
            cid = body["case_id"]
            found = next((c for c in pack["cases"] if c["case_id"] == cid), None)
            if found is None:
                return 404, {"ok": False, "error": f"unknown case_id {cid}"}
            facts = found["facts"]
            case_id = cid
        elif isinstance(body.get("facts"), dict):
            facts = body["facts"]
            case_id = body.get("case_id")
        else:
            return 400, {"ok": False, "error": "send case_id or facts"}
        return 200, {
            "ok": True,
            "engine": ENGINE,
            "engine_version": ENGINE_VERSION,
            "params_version": params,
            "case_id": case_id,
            "layer1": decision_for(facts),
        }
    return 404, {"ok": False, "error": "not found"}


class H(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict) -> None:
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, fmt, *args):
        sys.stderr.write("[homehealth-l1] " + (fmt % args) + "\n")

    def do_GET(self):
        code, obj = handle("GET", self.path, None)
        self._send(code, obj)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n) if n else b"{}"
            body = json.loads(raw or b"{}")
            if not isinstance(body, dict):
                return self._send(400, {"ok": False, "error": "JSON object required"})
            code, obj = handle("POST", self.path, body)
            self._send(code, obj)
        except json.JSONDecodeError:
            self._send(400, {"ok": False, "error": "invalid JSON"})


def main() -> None:
    host = os.environ.get("HOMEHEALTH_BIND", "127.0.0.1")
    port = int(os.environ.get("HOMEHEALTH_PORT", "8767"))
    srv = ThreadingHTTPServer((host, port), H)
    print(f"homehealth Layer 1 on http://{host}:{port} ({ENGINE} {ENGINE_VERSION}, no cloud)", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
