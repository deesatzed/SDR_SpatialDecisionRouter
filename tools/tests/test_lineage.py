import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import unified_export as ux  # noqa: E402
import lineage as lg  # noqa: E402
GOLD = os.path.join(HERE, "fixtures", "swift_ledger.jsonl")


def test_lineage_matches_ledger_contents():
    recs = ux.load_jsonl(GOLD)
    L = lg.build("symbiosis:personal_finance", recs)
    kinds = {"dial_change", "spot_check", "policy_proposal", "policy_evaluation", "principal_decision", "promotion", "rollback"}
    want = [r["id"] for r in recs if r["domain"] == "symbiosis:personal_finance" and r["kind"] in kinds]
    got = [e["id"] for e in L["events"] if e["kind"] != "critical_miss"]
    assert got == want and L["chain_ok"]
    assert L["champion_generation"] == 1 and L["counts"]["decisions"] == sum(r["kind"] == "decision" and r["domain"] == "symbiosis:personal_finance" for r in recs)
    md = lg.markdown(L)
    for e in L["events"]:
        assert e["hash"][:10] in md          # every event, by its signed hash
    assert "✓ verified" in md and "PROMOTED → champion gen 1" in md


def test_tamper_shows_in_status():
    recs = ux.load_jsonl(GOLD)
    recs[2] = dict(recs[2], timestamp="1999-01-01T00:00:00Z")
    st = lg.line_status(recs)
    assert st[:2] == ["verified", "verified"] and st[2] == "chain break here" and st[3].startswith("after chain break")
    assert "✗ broken" in lg.markdown(lg.build("symbiosis:personal_finance", recs))


def test_exporter_writes_lineage(tmp_path):
    assert ux.main([GOLD, "-o", str(tmp_path), "--replay-name", "t"]) == 0
    md = open(tmp_path / "lineage" / "symbiosis_personal_finance.md").read()
    assert md.startswith("# Lineage · symbiosis:personal_finance")
    assert json.load(open(tmp_path / "summary.json"))["outputs"]["lineage_events"]["symbiosis:personal_finance"] >= 2
