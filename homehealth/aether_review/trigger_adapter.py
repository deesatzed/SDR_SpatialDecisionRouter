"""Adapter from existing structured trigger-engine inputs to review requests."""

from pathlib import Path

from homehealth.trigger_engine import trigger_eval

from .models import ReviewRequest


def review_request_from_trigger_input(payload: dict, params_path: Path | str) -> ReviewRequest:
    if payload.get("synthetic") is not True:
        raise ValueError("trigger adapter accepts explicitly synthetic input only")
    case_id = payload.get("case_id")
    reading = payload.get("reading")
    if not isinstance(case_id, str) or not isinstance(reading, dict):
        raise ValueError("case_id and structured reading are required")
    params = trigger_eval.load_params(params_path)
    enrolled_ts = float(payload.get("enrolled_ts", 0.0))
    baseline = trigger_eval.Baseline(case_id, enrolled_ts, params)
    decision = trigger_eval.evaluate(reading, baseline, params, payload.get("context"))
    reasons = [str(decision.get("reason", ""))]
    if decision.get("rule"):
        reasons.append(str(decision["rule"]))
    required = []
    if decision.get("recheck"):
        required.append(str(decision["recheck"].get("step")))
    return ReviewRequest(
        synthetic=True,
        case_id=case_id,
        engine_tier=str(decision["tier"]),
        rule_version="trigger_params.json:placeholder",
        engine_reasons=reasons,
        case_text=f"synthetic structured trigger case {case_id}",
        required_case_inputs=required,
    )
