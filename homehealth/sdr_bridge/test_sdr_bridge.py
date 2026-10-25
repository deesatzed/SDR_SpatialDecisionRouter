"""The headset pack matches Layer 1 v1.14.4 on copied library facts, and the bridge serves that recompute."""
import json
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decide import ENGINE_VERSION, PACK, PACK_PATH, build_pack, decision_for, live_cases  # noqa: E402
from server import H, handle  # noqa: E402


def test_pack_matches_library_and_engine():
    built = build_pack()
    on_disk = json.loads(PACK_PATH.read_text())
    assert on_disk == built
    assert built["engine_version"] == ENGINE_VERSION
    assert built["params_version"] == "0.14.4-placeholder"
    assert [c["case_id"] for c in built["cases"]] == [cid for _, cid in PACK]
    routes = {c["layer1"]["route"] for c in built["cases"]}
    assert routes == {"silent_log", "nurse_task", "provider_task", "urgent_page"}
    by_id = {c["case_id"]: c for c in built["cases"]}
    assert by_id["LX12-007"]["layer1"]["ticket"]["type"] == "device_maintenance"
    assert by_id["LX12-007"]["layer1"]["route"] == "silent_log"
    assert by_id["LX12-008"]["layer1"]["route"] == "urgent_page"
    assert by_id["LX12-008"]["layer1"]["ticket"] is None
    assert by_id["ST1-002"]["layer1"]["route"] == "silent_log"
    assert by_id["ST1-002"]["layer1"]["ticket"] is None
    assert by_id["NV6-001"]["layer1"]["route"] == "nurse_task"
    assert by_id["LX4-009"]["layer1"]["route"] == "provider_task"
    assert by_id["HK6-007"]["layer1"]["route"] == "urgent_page"
    for c in built["cases"]:
        assert "expected_route" not in c["facts"]
        assert "rationale" not in c["facts"]
        assert c["trend"]
        assert c["layer1"] == decision_for(c["facts"])
        # display text is the library narrative, not a rewritten vignette
        assert c["trend"] == (c["facts"].get("trend_last_7d") or "")
        assert c["note"] == (c["facts"].get("caregiver_or_nurse_note") or "")


def test_live_recompute_matches_snapshot():
    pack = build_pack()
    live = live_cases(pack)
    assert [c["case_id"] for c in live] == [c["case_id"] for c in pack["cases"]]
    for got, src in zip(live, pack["cases"]):
        assert got["layer1"] == src["layer1"]


def test_http_health_cases_and_decide():
    code, health = handle("GET", "/health", None)
    assert code == 200 and health["ok"] and health["cloud"] is False
    assert health["params_version"] == "0.14.4-placeholder"
    code, cases = handle("GET", "/cases", None)
    assert code == 200 and cases["source"] == "live"
    assert {c["layer1"]["route"] for c in cases["cases"]} == {
        "silent_log", "nurse_task", "provider_task", "urgent_page"
    }
    code, one = handle("POST", "/decide", {"case_id": "LX12-007"})
    assert code == 200 and one["layer1"]["ticket"]["type"] == "device_maintenance"
    code, missing = handle("POST", "/decide", {"case_id": "NO-SUCH"})
    assert code == 404
    code, bad = handle("POST", "/decide", {})
    assert code == 400


def test_http_server_smoke():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as resp:
            body = json.loads(resp.read().decode())
        assert body["ok"] is True
        assert body["engine_version"] == ENGINE_VERSION
    finally:
        srv.shutdown()
        thread.join(timeout=3)
