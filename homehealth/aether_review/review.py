"""Local packet creation; outcome derivation is added in the next task."""

from .models import ReviewOutcome, ReviewPacket, ReviewRequest


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
