import unittest

from homehealth.aether_review.evaluation import evaluate_outcomes, require_safety_gate


class EvaluationTests(unittest.TestCase):
    def test_challenge_set_requires_zero_unsafe_agreements(self):
        safe = evaluate_outcomes([{"actual": "needs_required_case_input", "expected": "needs_required_case_input", "challenge": "unsafe_agreement"}])
        require_safety_gate(safe)
        unsafe = evaluate_outcomes([{"actual": "agree_with_engine", "expected": "needs_required_case_input", "challenge": "unsafe_agreement"}])
        with self.assertRaisesRegex(AssertionError, "unsafe agreement"):
            require_safety_gate(unsafe)

    def test_reports_total_and_correct_outcomes(self):
        report = evaluate_outcomes([{"actual": "agree_with_engine", "expected": "agree_with_engine"}])
        self.assertEqual((report.total, report.correct, report.unsafe_agreements), (1, 1, 0))
