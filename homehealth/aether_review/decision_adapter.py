"""Validate typed review decisions without invoking a provider."""

import math

from .models import ReviewOutcome


def validate_typed_decision(value: object) -> tuple[ReviewOutcome, float]:
    if not isinstance(value, dict):
        raise ValueError("typed decision is required")
    try:
        outcome = ReviewOutcome(value["outcome"])
        probability = float(value["probability"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("typed decision has invalid fields") from error
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("typed decision probability must be finite and in range")
    return outcome, probability
