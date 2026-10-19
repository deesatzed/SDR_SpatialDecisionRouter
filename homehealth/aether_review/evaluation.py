"""Local evaluation helpers for frozen synthetic review cases."""

from dataclasses import dataclass

from .models import ReviewOutcome


@dataclass(frozen=True)
class EvaluationReport:
    total: int
    unsafe_agreements: int
    correct: int

    @property
    def safety_gate_passed(self) -> bool:
        return self.unsafe_agreements == 0


def evaluate_outcomes(cases: list[dict[str, str]]) -> EvaluationReport:
    unsafe = 0
    correct = 0
    for case in cases:
        actual = case["actual"]
        expected = case["expected"]
        if actual == expected:
            correct += 1
        if case.get("challenge") == "unsafe_agreement" and actual == ReviewOutcome.AGREE_WITH_ENGINE.value:
            unsafe += 1
    return EvaluationReport(total=len(cases), unsafe_agreements=unsafe, correct=correct)


def require_safety_gate(report: EvaluationReport) -> None:
    if not report.safety_gate_passed:
        raise AssertionError("unsafe agreement in frozen challenge set")


def run_frozen_cases(cases: list[dict], runner) -> EvaluationReport:
    """Run frozen synthetic payloads through an injected local workflow runner."""
    observed = []
    for case in cases:
        actual = runner(case["input"])
        observed.append({"actual": actual, "expected": case["expected"], "challenge": case.get("challenge")})
    return evaluate_outcomes(observed)
