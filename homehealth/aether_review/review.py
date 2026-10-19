"""Local packet creation; outcome derivation is added in the next task."""

from .models import ReviewOutcome, ReviewPacket, ReviewRequest
from .decision_adapter import validate_typed_decision
from .rulings import ClinicianReference


def build_review_packet(request: ReviewRequest, outcome: ReviewOutcome, rationale: str) -> ReviewPacket:
    if not isinstance(outcome, ReviewOutcome):
        raise ValueError("outcome must be a supported review outcome")
    if not rationale:
        raise ValueError("review rationale is required")
    return ReviewPacket(
        case_id=request.case_id,
        engine_tier=request.engine_tier,
        rule_version=request.rule_version,
        outcome=outcome,
        rationale=rationale,
    )


def derive_outcome(request: ReviewRequest, references: list[ClinicianReference], typed_decision: object) -> tuple[ReviewOutcome, str]:
    if request.required_case_inputs:
        return ReviewOutcome.NEEDS_REQUIRED_CASE_INPUT, "required case input: " + ", ".join(request.required_case_inputs)
    if not references:
        return ReviewOutcome.SYSTEM_REVIEW_UNAVAILABLE, "no current clinician-ruling evidence"
    try:
        outcome, _ = validate_typed_decision(typed_decision)
    except ValueError as error:
        return ReviewOutcome.SYSTEM_REVIEW_UNAVAILABLE, str(error)
    if outcome == ReviewOutcome.NEEDS_REQUIRED_CASE_INPUT:
        return ReviewOutcome.SYSTEM_REVIEW_UNAVAILABLE, "typed decision cannot invent a missing case input"
    if outcome == ReviewOutcome.SYSTEM_REVIEW_UNAVAILABLE:
        return outcome, "typed review unavailable"
    if outcome == ReviewOutcome.NEEDS_CLINICIAN_REVIEW:
        return outcome, "typed review identified a substantive conflict or ambiguity"
    return ReviewOutcome.AGREE_WITH_ENGINE, "validated clinician-ruling evidence supports the engine result"
