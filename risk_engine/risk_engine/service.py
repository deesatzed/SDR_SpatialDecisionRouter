"""Localhost HTTP sidecar (stdlib http.server; no extra deps at runtime besides pyagrum + pyyaml).
POST /assess, POST /voi, POST /sample, GET /health, GET /params."""
import json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .params import load_params, markdown_table, source_summary, ParamError
from .model import assess, RiskModel, EvidenceError

PARAMS = load_params(os.environ.get("RISK_PARAMS"))


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def log_message(self, fmt, *a):
        sys.stderr.write("[risk] " + fmt % a + "\n")

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True, "param_source": source_summary(PARAMS), "complaints": sorted(PARAMS["complaints"])})
        if self.path == "/params":
            return self._send(200, {"markdown": markdown_table(PARAMS)})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/assess":
                return self._send(200, assess(PARAMS, req))
            if self.path == "/voi":
                r = assess(PARAMS, req)
                return self._send(200, {k: r[k] for k in ["complaint", "engine", "param_source", "voi", "escalation", "best_action", "expected_loss"]})
            if self.path == "/sample":
                m = RiskModel(PARAMS, req.get("complaint"))
                return self._send(200, {"samples": m.sample(int(req.get("n", 10)), int(req.get("seed", 0)))})
            self._send(404, {"error": "not found"})
        except (EvidenceError, ParamError, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            self._send(400, {"error": str(e)})


def main():
    port = int(os.environ.get("RISK_PORT", "8765"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"risk engine on http://127.0.0.1:{port} (params: {source_summary(PARAMS)})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
