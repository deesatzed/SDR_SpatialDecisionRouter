"""Read-only loader for explicitly synthetic, preconfigured review cases."""

import json
from dataclasses import dataclass
from pathlib import Path

from homehealth.jev_baseline.phi_guard import phi_hits


@dataclass(frozen=True)
class QueueCase:
    case_id: str
    summary: str
    clinician_ruling_ref: str
    input: dict
    expected: dict


def load_queue(path: Path | str) -> list[QueueCase]:
    """Load a queue without changing it or the underlying case library."""
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, list):
        raise ValueError("review queue must be a JSON list")

    cases = [_parse_case(raw) for raw in payload]
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("review queue contains duplicate case IDs")
    return cases


def _parse_case(raw: object) -> QueueCase:
    if not isinstance(raw, dict) or raw.get("synthetic") is not True:
        raise ValueError("review queue accepts explicitly synthetic cases only")
    case_id = raw.get("case_id")
    summary = raw.get("summary")
    ruling_ref = raw.get("clinician_ruling_ref")
    trigger_input = raw.get("input")
    expected = raw.get("expected")
    if not all(isinstance(value, str) and value.strip() for value in (case_id, summary, ruling_ref)):
        raise ValueError("case ID, summary, and clinician ruling reference are required")
    if phi_hits(summary):
        raise ValueError("review queue summary contains PHI-like input")
    if not isinstance(trigger_input, dict) or trigger_input.get("synthetic") is not True:
        raise ValueError("queue case requires explicitly synthetic trigger input")
    if trigger_input.get("case_id") != case_id:
        raise ValueError("queue case ID must match trigger input case ID")
    if not isinstance(expected, dict) or not all(isinstance(expected.get(key), str) and expected[key] for key in ("tier", "rule")):
        raise ValueError("queue case requires expected tier and rule")
    return QueueCase(case_id, summary, ruling_ref, trigger_input, expected)
