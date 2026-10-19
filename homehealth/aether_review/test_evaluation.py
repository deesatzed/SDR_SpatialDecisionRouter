import unittest
import json
from pathlib import Path

from homehealth.aether_review.evaluation import evaluate_outcomes, require_safety_gate, run_frozen_cases
from homehealth.aether_review.models import ReviewOutcome
from homehealth.aether_review.review import derive_outcome
from homehealth.aether_review.trigger_adapter import review_request_from_trigger_input


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

    def test_frozen_challenge_runs_through_trigger_adapter(self):
        fixture = Path(__file__).parent / "fixtures" / "challenge_review_cases.json"
        cases = json.loads(fixture.read_text())
        params = Path(__file__).resolve().parents[1] / "trigger_engine" / "trigger_params.json"
        def runner(payload):
            request = review_request_from_trigger_input(payload, params)
            return derive_outcome(request, [], None)[0].value
        report = run_frozen_cases(cases, runner)
        self.assertEqual(report.correct, 1)
        require_safety_gate(report)
