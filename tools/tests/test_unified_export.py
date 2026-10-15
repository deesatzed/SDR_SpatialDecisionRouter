"""M0 exporter tests. swift_ledger.jsonl is written by the Swift unit test testWriteGoldenFixture (real CryptoKit
Ed25519 + Swift JSONEncoder), so these tests prove the Python verifier matches the app byte-for-byte."""
import json, os, sys
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.dirname(HERE))
import unified_export as ux  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
GOLD = os.path.join(FIX, "swift_ledger.jsonl")


def test_swift_ledger_verifies():
    ok, probs = ux.verify(ux.load_jsonl(GOLD))
    assert ok, probs


def test_tamper_detected():
    recs = ux.load_jsonl(GOLD)
    recs[0]["human_decision"]["answer"] = "TAMPERED"
    ok, probs = ux.verify(recs)
    assert not ok and any("hash mismatch" in p for p in probs)
    recs = ux.load_jsonl(GOLD)[1:]
    assert not ux.verify(recs)[0]


def test_three_outputs_and_rules(tmp_path):
    rc = ux.main([GOLD, "-o", str(tmp_path), "--replay-name", "t", "--legacy", os.path.join(FIX, "legacy_routing.jsonl"), "--strict"])
    assert rc == 0
    s = json.load(open(tmp_path / "summary.json"))
    assert s["chain_ok"] and s["by_provenance"] == {"signed_ledger": 2, "legacy_unsigned": 1}
    sft = [json.loads(l) for l in open(tmp_path / "finetune" / "sft.jsonl")]
    pref = [json.loads(l) for l in open(tmp_path / "finetune" / "preference.jsonl")]
    rl = [json.loads(l) for l in open(tmp_path / "rl" / "rewards.jsonl")]
    assert len(sft) == 3 and len(rl) == 3 and len(pref) == 2
    dc = [json.loads(l) for l in open(tmp_path / "dials" / "dial_changes.jsonl")]
    assert len(dc) == 1 and dc[0]["dial_after"]["autonomy_horizon"] == dc[0]["dial_before"]["autonomy_horizon"] + 5 and dc[0]["evidence_refs"]
    sc = [json.loads(l) for l in open(tmp_path / "sharpness" / "spot_checks.jsonl")]
    # spot-check on decision `a` (proposal A); its later outcome line (A) is folded in: human called B → missed
    assert len(sc) == 1 and sc[0]["human_call"] == "B" and sc[0]["outcome"] == "A" and sc[0]["human_correct"] is False and sc[0]["agent_correct"] is True
    assert s["outputs"]["spot_checks"] == 1
    pr = [json.loads(l) for l in open(tmp_path / "promotion" / "promotion_records.jsonl")]
    assert len(pr) == 1 and pr[0]["kind"] == "promotion" and pr[0]["promo"]["rules_after"][0]["answer"] == "Hold — gather info"
    # split rating is auxiliary, never part of reward
    for r in rl:
        assert r["reward"] in (1.0, -1.0, None)
    assert any(r["aux_split_rating"] == "about_right" for r in rl)
    # outcome folded from amendment line
    ed = [r for r in rl if r["domain"] == "ed_triage" and r["provenance"] == "signed_ledger"][0]
    assert ed["reward"] == 1.0 and ed["reward_source"] == "test"
    # frozen + blinded replay
    rdir = tmp_path / "replay" / "t"
    cases = [json.loads(l) for l in open(rdir / "cases.jsonl")]
    assert cases and all("human_answer" not in c and "outcome" not in c for c in cases)
    assert ux.verify_replay(str(rdir))
    with open(rdir / "answers.jsonl", "a") as f:
        f.write("{}\n")
    assert not ux.verify_replay(str(rdir)), "edited replay pack must fail its manifest"


def test_null_outcome_gives_null_reward():
    r = {"human_decision": {"answer": "A"}, "outcome": None}
    assert ux.reward(r) is None


def test_legacy_mapping():
    d = ux.from_legacy(ux.load_jsonl(os.path.join(FIX, "legacy_routing.jsonl"))[0])
    assert d["human_decision"]["label"] == "modify" and d["outcome"]["value"] == "2" and d["provenance"] == "legacy_unsigned"
