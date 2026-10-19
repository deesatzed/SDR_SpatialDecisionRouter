import unittest
from pathlib import Path

from homehealth.aether_review.models import ReviewOutcome
from homehealth.aether_review.review import derive_outcome
from homehealth.aether_review.rulings import ClinicianReference
from homehealth.aether_review.trigger_adapter import review_request_from_trigger_input


PARAMS = Path(__file__).resolve().parents[1] / "trigger_engine" / "trigger_params.json"


class TriggerAdapterTests(unittest.TestCase):
    def test_structured_synthetic_danger_reading_preserves_engine_result(self):
        request = review_request_from_trigger_input({
            "synthetic": True,
            "case_id": "SYN-END-001",
            "reading": {"vital": "hr", "value": 185, "ts": 3600, "activity_state": "rest"},
        }, PARAMS)
        self.assertEqual(request.engine_tier, "ABSOLUTE")
        self.assertIn("hard_limit_danger", request.engine_reasons)
        outcome, _ = derive_outcome(request, [ClinicianReference("SYN-END-001", "escalate_human", "supports", "clinician_ruling:SYN-END-001")], {"outcome": "agree_with_engine", "probability": 0.9})
        self.assertEqual(outcome, ReviewOutcome.AGREE_WITH_ENGINE)

    def test_confirm_first_requires_the_engine_named_recheck(self):
        request = review_request_from_trigger_input({
            "synthetic": True,
            "case_id": "SYN-END-002",
            "reading": {"vital": "hr", "value": 112, "ts": 3600, "activity_state": "rest"},
        }, PARAMS)
        self.assertEqual(request.engine_tier, "CONFIRM_FIRST")
        outcome, rationale = derive_outcome(request, [], None)
        self.assertEqual(outcome, ReviewOutcome.NEEDS_REQUIRED_CASE_INPUT)
        self.assertIn("patient_call", rationale)

    def test_rejects_unmarked_input(self):
        with self.assertRaises(ValueError):
            review_request_from_trigger_input({"case_id": "bad", "reading": {}}, PARAMS)
