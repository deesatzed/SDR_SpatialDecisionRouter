import unittest

from homehealth.aether_review.models import ReviewOutcome, ReviewRequest
from homehealth.aether_review.review import build_review_packet, derive_outcome
from homehealth.aether_review.rulings import ClinicianReference


class ReviewSchemaTests(unittest.TestCase):
    def request(self, **changes):
        data = {
            "synthetic": True,
            "case_id": "SYN-001",
            "engine_tier": "CONFIRM_FIRST",
            "rule_version": "synthetic-v1",
            "engine_reasons": ["requires_recheck"],
            "case_text": "Day -1 sensor reading needs recheck.",
            "required_case_inputs": [],
        }
        data.update(changes)
        return ReviewRequest(**data)

    def test_accepts_explicitly_synthetic_review_request(self):
        packet = build_review_packet(self.request(), ReviewOutcome.SYSTEM_REVIEW_UNAVAILABLE, "no evidence")
        self.assertEqual(packet.case_id, "SYN-001")
        self.assertEqual(packet.outcome, ReviewOutcome.SYSTEM_REVIEW_UNAVAILABLE)

    def test_rejects_unmarked_input(self):
        with self.assertRaises(ValueError):
            self.request(synthetic=False)

    def test_rejects_phi_like_input(self):
        with self.assertRaises(ValueError):
            self.request(case_text="patient: Alice called from 555-123-4567")

    def test_rejects_unsupported_outcome(self):
        with self.assertRaises(ValueError):
            ReviewOutcome("auto_escalate")

    def test_missing_required_case_input_defers_to_named_check(self):
        outcome, rationale = derive_outcome(self.request(required_case_inputs=["fingerstick"]), [], None)
        self.assertEqual(outcome, ReviewOutcome.NEEDS_REQUIRED_CASE_INPUT)
        self.assertIn("fingerstick", rationale)

    def test_missing_evidence_or_invalid_typed_result_never_agrees(self):
        outcome, _ = derive_outcome(self.request(), [], {"outcome": "agree_with_engine", "probability": 0.99})
        self.assertEqual(outcome, ReviewOutcome.SYSTEM_REVIEW_UNAVAILABLE)
        reference = ClinicianReference("SYN-001", "nurse_task", "supported", "clinician_ruling:SYN-001")
        outcome, _ = derive_outcome(self.request(), [reference], {"outcome": "agree_with_engine", "probability": float("nan")})
        self.assertEqual(outcome, ReviewOutcome.SYSTEM_REVIEW_UNAVAILABLE)

    def test_valid_conflict_and_agreement_typed_results_are_explicit(self):
        reference = ClinicianReference("SYN-001", "nurse_task", "supported", "clinician_ruling:SYN-001")
        outcome, _ = derive_outcome(self.request(), [reference], {"outcome": "needs_clinician_review", "probability": 0.8})
        self.assertEqual(outcome, ReviewOutcome.NEEDS_CLINICIAN_REVIEW)
        outcome, _ = derive_outcome(self.request(), [reference], {"outcome": "agree_with_engine", "probability": 0.8})
        self.assertEqual(outcome, ReviewOutcome.AGREE_WITH_ENGINE)


if __name__ == "__main__":
    unittest.main()
