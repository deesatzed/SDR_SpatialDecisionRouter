"""Bridge tests: run against a fresh WERIAM state produced by WERIAM's own `develop`."""
import json
import threading
import urllib.request
import time
import uuid
from pathlib import Path

import pytest

from weriam_bridge import adapter as A
from weriam_bridge import server as S
from weriam_bridge import signing as SG


@pytest.fixture(scope="module")
def state(tmp_path_factory):
    sd = tmp_path_factory.mktemp("weriam") / "state"
    A.init_state(sd, 2)
    return sd


@pytest.fixture()
def fresh(state, tmp_path):
    import shutil
    sd = tmp_path / "state"
    shutil.copytree(state, sd)
    return sd


def test_pending_requests_become_cards(state):
    cards = A.principal_cards(state)
    kinds = {c["kind"] for c in cards}
    assert "retire_watcher" in kinds
    c = next(c for c in cards if c["kind"] == "retire_watcher")
    assert c["evidence"]["ready"] is True and c["agent_pick"] == "Defer"
    assert "consumed" in c["scope"] and "shadow" in c["reversibility"] and "containment" in c["containment"]


def test_shadow_cards_hide_outcome(state):
    cs = A.shadow_cards(state)
    assert cs and all(c["outcome_hidden"] for c in cs)
    blob = json.dumps(cs)
    assert "D_executed" not in blob and "guard_hits" not in blob   # no teacher outcome before the label
    assert all(c["alternatives"][0]["option"] == c["agent_pick"] for c in cs)


def test_approve_goes_through_weriam_and_is_single_use(fresh, tmp_path):
    rid = next(c["id"] for c in A.principal_cards(fresh) if c["kind"] == "retire_watcher")
    n0 = len(A.journal(fresh))
    rec = A.decide(fresh, rid, "approve", "W. Allen Satz (test)", data_dir=tmp_path)
    assert rec["weriam"]["status"] == "approved" and rec["verify"]["ok"]
    j = A.journal(fresh)
    assert len(j) == n0 + 1 and j.entries()[-1]["kind"] == "principal_decision"
    assert j.entries()[-1]["payload"]["granted_by"] == "W. Allen Satz (test)"
    assert rid not in {c["id"] for c in A.principal_cards(fresh)}
    with pytest.raises(ValueError):                       # WERIAM refuses a second decision
        A.decide(fresh, rid, "decline", "x")
    # agent consumes it on its next develop run -> watcher retired, approval consumed
    A.init_state(fresh, 1)
    st = {r["id"]: r["status"] for r in A.principal_requests(fresh)}
    assert st[rid] == "consumed"
    assert A.verify(fresh)["ok"]


def test_defer_writes_nothing_to_weriam(fresh, tmp_path):
    rid = A.principal_cards(fresh)[0]["id"]
    n0 = len(A.journal(fresh))
    A.decide(fresh, rid, "defer", "me", data_dir=tmp_path)
    assert len(A.journal(fresh)) == n0
    assert (tmp_path / "principal_log.jsonl").exists()


def test_tamper_detected(fresh):
    p = fresh / "journal.jsonl"
    lines = p.read_text().splitlines()
    e = json.loads(lines[3]); e["payload"]["tampered"] = True; lines[3] = json.dumps(e)
    p.write_text("\n".join(lines) + "\n")
    assert A.verify(fresh)["journal"]["ok"] is False


def test_label_and_export_join_outcome(fresh, tmp_path):
    lp = tmp_path / "labels.jsonl"
    c = A.shadow_cards(fresh)[0]
    n0 = len(A.journal(fresh))
    r = A.record_label(fresh, lp, c["id"], "Alt #2", "me", 1.5)
    assert r["human_pick"] == c["alternatives"][1]["option"] and r["agree"] is False
    assert {"option_menu", "agent_pick", "human_label", "cd_scores", "reliability"} <= set(r)
    assert len(A.journal(fresh)) == n0                       # labels never written into WERIAM
    assert c["id"] not in {x["id"] for x in A.shadow_cards(fresh, lp)}
    out = tmp_path / "x.jsonl"
    assert A.export_labels(fresh, lp, out) == 1
    row = json.loads(out.read_text())
    assert row["observed_outcome"] is not None and "D_executed" in row["observed_outcome"]
    with pytest.raises(ValueError):
        A.record_label(fresh, lp, c["id"], "approve everything", "me")


def _server(fresh, tmp_path):
    S.STATE, S.DATA, S._live = fresh, tmp_path, None
    srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    tok = SG.token(tmp_path)
    def call(p, b=None, token=tok):
        rq = urllib.request.Request(base + p, json.dumps(b).encode() if b is not None else None,
                                    {"Content-Type": "application/json", "X-SDR-Token": token or ""})
        try:
            return 200, json.loads(urllib.request.urlopen(rq).read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    return srv, call


def _signed(k, kid, card, decision, by="W. Allen Satz"):
    payload = {"request_id": card["id"], "decision": decision, "by": by, "ts": time.time(),
               "nonce": uuid.uuid4().hex, "request_hash": card["request_hash"]}
    return {"request_id": card["id"], "decision": decision, "payload": payload, "sig": SG.sign(k, payload), "key_id": kid}


def test_http_token_and_signed_approval(fresh, tmp_path):
    srv, call = _server(fresh, tmp_path)
    assert call("/health", token=None)[1]["hooks"] is True
    assert call("/cards", token="wrong")[0] == 401
    cards = call("/cards")[1]
    card = next(c for c in cards["principal"] if c["kind"] == "retire_watcher")
    # unsigned approve refused
    assert call("/principal/decide", {"request_id": card["id"], "decision": "approve"})[0] == 401
    k, pub = SG.dev_keypair()
    kid = call("/approver/register", {"name": "W. Allen Satz", "pub": pub})[1]["key_id"]
    # a second key for the same name is refused (pinned)
    assert call("/approver/register", {"name": "W. Allen Satz", "pub": SG.dev_keypair()[1]})[0] == 401
    body = _signed(k, kid, card, "approve")
    bad = dict(body, sig=SG.sign(SG.dev_keypair()[0], body["payload"]))
    assert call("/principal/decide", bad)[0] == 401
    code, rec = call("/principal/decide", body)
    assert code == 200 and rec["signed"] and rec["weriam"]["status"] == "approved"
    assert "ed25519:" + kid in rec["weriam"]["granted_by"]
    assert call("/principal/decide", body)[0] == 401          # nonce replay refused
    v = call("/verify")[1]
    assert v["ok"] and v["signed"]["signed"] == 1 and not v["signed"]["bad"]
    srv.shutdown()


def test_live_pause_label_changes_run_and_grades(fresh, tmp_path):
    srv, call = _server(fresh, tmp_path)
    assert call("/live/start", {"episodes": 1, "scenarios": ["water_gap"], "max_pauses": 3, "timeout": 20})[0] == 200
    seen = []
    for i in range(3):
        for _ in range(200):
            snap = call("/cards")[1]["live"]
            if snap["pending"] or snap["status"] != "running":
                break
            time.sleep(0.05)
        if not snap["pending"]:
            break
        card = snap["pending"]
        assert "D_executed" not in json.dumps(card)                # outcome hidden while paused
        assert card["reliability_beta"]["n"] >= 0 and card["alternatives"][0]["option"] == card["agent_pick"]
        lab = "WAIT / ask" if i == 0 else "Agree"
        assert call("/live/label", {"pause_id": card["pause_id"], "label": lab, "by": "t"})[0] == 200
        seen.append((card["pause_id"], lab, card["action"]))
    S._live.wait_done(60)
    res = {r["pause_id"]: r for r in call("/cards")[1]["live"]["results"]}
    assert seen and all(pid in res for pid, _, _ in seen)
    pid, lab, act = seen[0]
    if act != "wait":
        assert res[pid]["applied"] == "wait" and "principal_pause:WAIT / ask" in res[pid]["guard_hits"]
    assert all(r["hit"] in (True, False) for r in res.values())
    assert call("/verify")[1]["journal"]["ok"]
    srv.shutdown()


def test_live_timeout_defaults_to_wait(fresh, tmp_path):
    srv, call = _server(fresh, tmp_path)
    call("/live/start", {"episodes": 1, "scenarios": ["water_gap"], "max_pauses": 1, "timeout": 0.2})
    S._live.wait_done(60)
    r = call("/cards")[1]["live"]["results"]
    assert r and r[0]["label"].startswith("timeout") and r[0]["applied"] in ("wait", r[0]["nominated"])
    if r[0]["nominated"] != "wait":
        assert r[0]["applied"] == "wait"
    srv.shutdown()


def test_approval_during_live_is_queued_then_applied(fresh, tmp_path):
    srv, call = _server(fresh, tmp_path)
    card = next(c for c in call("/cards")[1]["principal"] if c["kind"] == "retire_watcher")
    k, pub = SG.dev_keypair()
    kid = call("/approver/register", {"name": "W. Allen Satz", "pub": pub})[1]["key_id"]
    call("/live/start", {"episodes": 1, "scenarios": ["water_gap"], "max_pauses": 1, "timeout": 3})
    code, rec = call("/principal/decide", _signed(k, kid, card, "approve"))
    assert code == 200 and rec["queued"]
    S._live.wait_done(60)
    st = {r["id"]: r["status"] for r in A.principal_requests(fresh)}
    assert st[card["id"]] in ("approved", "consumed")
    assert call("/verify")[1]["ok"]
    srv.shutdown()


def test_beta_and_grade():
    from weriam_bridge.live import beta_summary, grade
    b = beta_summary(8, 2)
    assert b["n"] == 10 and b["lo"] < b["mean"] < b["hi"]
    assert grade("Agree", 3.0)["critical"] and grade("WAIT / ask", 3.0)["hit"] and not grade("Alt #2", 0.0)["hit"]
