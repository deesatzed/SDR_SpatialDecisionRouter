"""Validated schemas for local synthetic clinician-review packets."""

from dataclasses import dataclass, field
from enum import StrEnum


class ReviewOutcome(StrEnum):
    AGREE_WITH_ENGINE = "agree_with_engine"
    NEEDS_CLINICIAN_REVIEW = "needs_clinician_review"
    NEEDS_REQUIRED_CASE_INPUT = "needs_required_case_input"
    SYSTEM_REVIEW_UNAVAILABLE = "system_review_unavailable"


@dataclass(frozen=True)
class ReviewRequest:
    synthetic: bool
    case_id: str
    engine_tier: str
    rule_version: str
    engine_reasons: list[str]
    case_text: str
    required_case_inputs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.synthetic:
            raise ValueError("review requests must be explicitly synthetic")
        if not self.case_id or not self.engine_tier or not self.rule_version or not self.engine_reasons:
            raise ValueError("case ID, engine tier, rule version, and reasons are required")
        from homehealth.jev_baseline.phi_guard import phi_hits
        if phi_hits(self.case_text):
            raise ValueError("review request contains PHI-like input")


@dataclass(frozen=True)
class ReviewPacket:
    case_id: str
    engine_tier: str
    rule_version: str
    outcome: ReviewOutcome
    rationale: str
    evidence_ids: list[str] = field(default_factory=list)
