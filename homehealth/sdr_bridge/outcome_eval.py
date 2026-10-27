"""Outcome-linked eval for synthetic home-health routes.

Scores a chosen route against three things at once: whether it is in the
appropriate set, whether the escalation timing matches the fixture, and the
synthetic downstream outcome. Agreement with an expert-consensus route is
reported beside the outcome, because a route that beats consensus on the
outcome can look like an error if the only score is agreement.

SYNTHETIC. No PHI. Not a vignette exam score.
"""
from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "outcome_eval_cases.json"
ROUTES = ("silent_log", "nurse_task", "provider_task", "urgent_page")


def load_fixtures(path: Path | None = None) -> list[dict]:
    data = json.loads((path or FIXTURE).read_text())
    cases = data["cases"] if isinstance(data, dict) else data
    for case in cases:
        _check_case(case)
    return cases


def _check_case(case: dict) -> None:
    for key in ("case_id", "proposal", "consensus_route", "consensus_timing", "appropriate_routes", "outcome", "timing_penalty"):
        if key not in case:
            raise ValueError(f"{case.get('case_id')}: missing {key}")
    if case["consensus_route"] not in ROUTES:
        raise ValueError(f"{case['case_id']}: bad consensus route")
    by = case["outcome"].get("by_route") or {}
    missing = [r for r in ROUTES if r not in by]
    if missing:
        raise ValueError(f"{case['case_id']}: outcome.by_route missing {missing}")


def score_decision(case: dict, chosen_route: str, timing: str | None = None) -> dict:
    """One human or agent choice against one fixture."""
    if chosen_route not in ROUTES:
        raise ValueError(f"unknown route {chosen_route}")
    timing = timing or case["consensus_timing"]
    penalties = case["timing_penalty"]
    if timing not in penalties:
        raise ValueError(f"{case['case_id']}: unknown timing {timing}")
    by = case["outcome"]["by_route"][chosen_route]
    cons = case["outcome"]["by_route"][case["consensus_route"]]
    utility = round(float(by["utility"]) - float(penalties[timing]), 4)
    consensus_utility = round(
        float(cons["utility"]) - float(penalties[case["consensus_timing"]]), 4
    )
    agreement = chosen_route == case["consensus_route"] and timing == case["consensus_timing"]
    beats = utility > consensus_utility + 1e-9
    return {
        "case_id": case["case_id"],
        "synthetic": True,
        "stress": list(case.get("stress") or []),
        "chosen_route": chosen_route,
        "timing": timing,
        "consensus_route": case["consensus_route"],
        "consensus_timing": case["consensus_timing"],
        "agreement_with_consensus": agreement,
        "route_appropriate": chosen_route in case["appropriate_routes"],
        "escalation_timing_on_time": timing == case["consensus_timing"],
        "outcome_utility": utility,
        "consensus_utility": consensus_utility,
        "outcome_note": by.get("note") or "",
        "beats_consensus_on_outcome": beats,
        "looks_like_error_if_agreement_only": (not agreement) and beats,
    }


def score_pack(cases: list[dict], decisions: dict[str, dict] | None = None) -> dict:
    """Score each case. `decisions` maps case_id to {route, timing}.

    Missing decisions use the fixture proposal and the consensus timing, which
    is the 'agent as shipped' column, not the expert column.
    """
    decisions = decisions or {}
    rows = []
    for case in cases:
        choice = decisions.get(case["case_id"]) or {}
        route = choice.get("route") or case["proposal"]
        timing = choice.get("timing") or case["consensus_timing"]
        rows.append(score_decision(case, route, timing))
    n = len(rows) or 1
    return {
        "synthetic": True,
        "schema": "sdr.homehealth.outcome_eval.v1",
        "framing": (
            "Coordination-layer eval. Agreement with a consensus route is not the "
            "outcome. A higher utility with a different route is a beat, and an "
            "agreement-only score would call that beat an error."
        ),
        "n": len(rows),
        "route_appropriate_rate": round(sum(r["route_appropriate"] for r in rows) / n, 4),
        "agreement_rate": round(sum(r["agreement_with_consensus"] for r in rows) / n, 4),
        "timing_on_time_rate": round(sum(r["escalation_timing_on_time"] for r in rows) / n, 4),
        "mean_outcome_utility": round(sum(r["outcome_utility"] for r in rows) / n, 4),
        "mean_consensus_utility": round(sum(r["consensus_utility"] for r in rows) / n, 4),
        "n_beats_consensus": sum(r["beats_consensus_on_outcome"] for r in rows),
        "n_looks_like_error_if_agreement_only": sum(r["looks_like_error_if_agreement_only"] for r in rows),
        "rows": rows,
    }
