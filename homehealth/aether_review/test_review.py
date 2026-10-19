import unittest

from homehealth.aether_review.models import ReviewOutcome, ReviewRequest
from homehealth.aether_review.review import build_review_packet


class ReviewSchemaTests(unittest.TestCase):
    def request(self, **changes):
        data = {
            "synthetic": True,
            "case_id": "SYN-001",
            "engine_tier": "CONFIRM_FIRST",
            "rule_version": "synthetic-v1",
            "engine_reasons": ["requires_recheck"],
            "case_text": "Day -1 sensor reading needs recheck.",
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


if __name__ == "__main__":
    unittest.main()
