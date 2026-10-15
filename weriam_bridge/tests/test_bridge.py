"""Bridge tests: run against a fresh WERIAM state produced by WERIAM's own `develop`."""
import json
import threading
import urllib.request
from pathlib import Path

import pytest

from weriam_bridge import adapter as A
from weriam_bridge import server as S


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


def test_http_roundtrip(fresh, tmp_path):
    S.STATE, S.DATA = fresh, tmp_path
    srv = S.ThreadingHTTPServer(("127.0.0.1", 0), S.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    get = lambda p: json.loads(urllib.request.urlopen(base + p).read())
    def post(p, b):
        rq = urllib.request.Request(base + p, json.dumps(b).encode(), {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(rq).read())
    assert get("/health")["ok"]
    cards = get("/cards")
    rid = cards["principal"][0]["id"]
    assert post("/principal/decide", {"request_id": rid, "decision": "decline", "by": "http"})["weriam"]["status"] == "declined"
    assert post("/shadow/label", {"id": cards["shadow"][0]["id"], "label": "Agree"})["agree"] is True
    assert get("/verify")["ok"]
    try:
        post("/principal/decide", {"request_id": "nope", "decision": "approve"})
        assert False
    except urllib.error.HTTPError as e:
        assert e.code == 400
    srv.shutdown()
