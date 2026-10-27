"""Pattern-fixture minds, outcome eval, and the Overseer learning rollup. SYNTHETIC."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from learning_export import load_records, rollup  # noqa: E402
from outcome_eval import load_fixtures, score_decision, score_pack  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = ROOT / "SpatialDecisionRouter" / "Domains" / "HomeHealth" / "homehealth_patterns.json"


def test_pattern_fixtures_carry_the_seven_reads():
    pack = json.loads(PATTERNS.read_text())
    by_id = {c["vignette"]["case_id"]: c for c in pack["cases"]}
    assert list(by_id)[:5] == ["PX-COPD-01", "PX-REVISE-01", "PX-REFUSE-01", "PX-DNH-01", "PX-WAIT-01"]

    copd = by_id["PX-COPD-01"]["mind"]
    assert len(copd["differential"]) >= 2
    assert copd["act_under_uncertainty"] is False
    assert "positional" in copd["differential"][0]

    revise = by_id["PX-REVISE-01"]["mind"]
    assert revise["falsifies_prior"] is True
    assert revise["prior_decision"]
    assert revise["new_evidence"]
    assert len(revise["differential"]) >= 2

    refused = by_id["PX-REFUSE-01"]["mind"]
    assert refused["agent_refused"] is True
    assert "conflicting" in by_id["PX-REFUSE-01"]["vignette"]["artifact_flags"]

    dnh = by_id["PX-DNH-01"]["mind"]
    assert dnh["blocks_escalation"] is True
    assert dnh["goals_kind"] == "dnh"
    assert by_id["PX-DNH-01"]["vignette"]["layer1"]["route"] == "urgent_page"

    wait = by_id["PX-WAIT-01"]["mind"]
    assert wait["wait_for"]
    assert wait["wait_minutes"] == 360
    assert wait["flip_route"] == "nurse_task"
    assert wait["flip_if"]
    assert by_id["PX-COPD-01"]["mind"]["wait_minutes"] == 120
    assert by_id["PX-REVISE-01"]["mind"]["wait_minutes"] == 30
    assert by_id["PX-REFUSE-01"]["mind"]["wait_minutes"] == 10
    assert by_id["PX-DNH-01"]["mind"]["wait_minutes"] == 240


def test_outcome_eval_separates_agreement_from_downstream_utility():
    cases = load_fixtures()
    assert {c["case_id"] for c in cases} >= {"EV-INCOMPLETE-BEATS", "EV-DNH-FEVER", "EV-LATE", "EV-STROKE"}
    stresses = {tag for c in cases for tag in c["stress"]}
    assert {"incomplete", "conflicting", "misleading"} <= stresses

    held = score_decision(
        next(c for c in cases if c["case_id"] == "EV-INCOMPLETE-BEATS"),
        "silent_log",
        "same_shift",
    )
    assert held["agreement_with_consensus"] is False
    assert held["route_appropriate"] is True
    assert held["beats_consensus_on_outcome"] is True
    assert held["looks_like_error_if_agreement_only"] is True

    paged = score_decision(
        next(c for c in cases if c["case_id"] == "EV-INCOMPLETE-BEATS"),
        "urgent_page",
        "immediate",
    )
    assert paged["agreement_with_consensus"] is True
    assert paged["outcome_utility"] < held["outcome_utility"]

    late = score_decision(
        next(c for c in cases if c["case_id"] == "EV-LATE"),
        "nurse_task",
        "next_day",
    )
    assert late["route_appropriate"] is True
    assert late["escalation_timing_on_time"] is False
    on_time = score_decision(
        next(c for c in cases if c["case_id"] == "EV-LATE"),
        "nurse_task",
        "same_shift",
    )
    assert on_time["outcome_utility"] > late["outcome_utility"]

    summary = score_pack(cases, {
        "EV-INCOMPLETE-BEATS": {"route": "silent_log", "timing": "same_shift"},
        "EV-DNH-FEVER": {"route": "nurse_task", "timing": "same_shift"},
    })
    assert summary["n_looks_like_error_if_agreement_only"] >= 2
    assert summary["n_beats_consensus"] >= 2
    assert "agreement" in summary["framing"].lower() or "Consensus" in summary["framing"] or "consensus" in summary["framing"]


def test_learning_rollup_from_ledger_and_routing_context(tmp_path):
    ledger = [
        {
            "kind": "decision",
            "card_payload": {
                "case_id": "PX-REFUSE-01",
                "review_role": "overseer",
                "review_action": "human_after_refusal",
                "agent_refused": "1",
                "refusal_reason": "notes conflict",
                "uncertainty_differential": "true deterioration · device artifact",
                "uncertainty_confidence": "open",
                "act_under_uncertainty": "1",
                "goals_constraint": "Goals of care are not recorded.",
                "goals_blocks_escalation": "0",
                "goals_kind": "unstated",
                "route": "urgent_page",
            },
            "human_decision": {"answer": "silent_log", "gesture": "select", "decided_by": "human"},
        },
        {
            "kind": "decision",
            "card_payload": {
                "case_id": "PX-REVISE-01",
                "review_role": "overseer",
                "review_action": "revisit_prior",
                "revisit": "1",
                "prior_decision": "Log only for positional desats",
                "new_evidence": "Resting SpO2 86%",
                "uncertainty_differential": "infection · secretion",
                "goals_constraint": "Hospital is acceptable if rest does not recover.",
                "goals_kind": "hospital_if_needed",
            },
            "human_decision": {"answer": "nurse_task", "gesture": "select"},
        },
        {
            "kind": "decision",
            "card_payload": {
                "case_id": "PX-WAIT-01",
                "review_role": "nurse",
                "review_action": "voi_wait",
                "voi_observation": "temperature and resting SpO2 over 6 hours",
                "voi_flip_route": "nurse_task",
                "voi_flip_if": "temperature reaches 38.5 C",
                "voi_wait_minutes": "360",
                "voi_wait_deadline": "360",
                "uncertainty_differential": "viral illness · early pneumonia",
                "goals_constraint": "Hospital is acceptable if home treatment does not recover.",
                "goals_blocks_escalation": "0",
            },
            "human_decision": {"answer": "silent_log", "gesture": "pass"},
        },
        {
            "kind": "decision",
            "card_payload": {
                "case_id": "PX-DNH-01",
                "review_role": "bedside",
                "review_action": "request_nurse_visit",
                "goals_constraint": "Would refuse hospital and ambulance.",
                "goals_blocks_escalation": "1",
                "goals_kind": "dnh",
                "uncertainty_differential": "infection · dehydration",
                "act_under_uncertainty": "1",
            },
            "human_decision": {"answer": "nurse_task", "gesture": "select"},
        },
    ]
    path = tmp_path / "ledger.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in ledger) + "\n")
    artifact = rollup(load_records(path))
    assert artifact["schema"] == "sdr.homehealth.learning.v1"
    assert artifact["overseer"]["n"] == 2
    assert artifact["all_roles"]["n"] == 4
    assert artifact["all_roles"]["by_review_role"]["overseer"] == 2
    assert artifact["all_roles"]["by_review_action"]["voi_wait"] == 1
    assert artifact["all_roles"]["by_review_action"]["revisit_prior"] == 1
    assert artifact["all_roles"]["by_review_action"]["human_after_refusal"] == 1
    shared = artifact["shared_update"]
    assert len(shared["refusals"]) == 1
    assert len(shared["revisits"]) == 1
    assert shared["voi_waits"][0]["voi_flip_route"] == "nurse_task"
    assert shared["voi_waits"][0]["voi_wait_minutes"] == "360"
    assert shared["voi_waits"][0]["voi_wait_deadline"] == "360"
    assert "voi_wait_minutes" in artifact["tracked_keys"]
    assert "voi_recheck" in artifact["tracked_keys"]
    assert any(g["goals_blocks_escalation"] == "1" for g in shared["goals_constraints"])
    assert len(shared["uncertainty"]) == 4

    routing = tmp_path / "routing.jsonl"
    routing.write_text(json.dumps({
        "context": ledger[0]["card_payload"],
        "routedAnswer": "silent_log",
        "gesture": "select",
        "decidedBy": "human",
    }) + "\n")
    from_context = rollup(load_records(routing))
    assert from_context["overseer"]["n"] == 1
    assert from_context["shared_update"]["refusals"][0]["chosen_route"] == "silent_log"


def test_overdue_wait_recheck_lands_in_the_rollup():
    artifact = rollup([{
        "kind": "decision",
        "card_payload": {
            "case_id": "PX-WAIT-01",
            "review_role": "overseer",
            "review_action": "voi_recheck",
            "voi_observation": "temperature and resting SpO2 over 6 hours",
            "voi_flip_route": "nurse_task",
            "voi_flip_if": "temperature reaches 38.5 C or resting SpO2 leaves the band",
            "voi_wait_minutes": "360",
            "voi_wait_deadline": "360",
            "voi_wait_overdue": "1",
            "voi_recheck": "1",
            "wait_overdue_line": "OVERDUE. Waited for temperature and resting SpO2 over 6 hours. The observation did not arrive.",
        },
        "human_decision": {"answer": "silent_log", "gesture": "recheck", "decided_by": "system"},
    }])
    row = artifact["shared_update"]["voi_waits"][0]
    assert row["review_action"] == "voi_recheck"
    assert row["voi_wait_minutes"] == "360"
    assert row["voi_wait_deadline"] == "360"
    assert row["voi_wait_overdue"] == "1"
    assert row["voi_recheck"] == "1"
    assert artifact["all_roles"]["by_review_action"]["voi_recheck"] == 1
    assert row["chosen_route"] == "silent_log"
