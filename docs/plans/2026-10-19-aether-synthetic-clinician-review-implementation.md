# Aether Synthetic Clinician-Review Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local-only synthetic-case review layer that conservatively assesses whether clinician-ruling evidence supports the deterministic trigger-engine output.

**Architecture:** A new `homehealth/aether_review/` package validates a synthetic request, retrieves bounded local rulings, validates a typed outcome, and emits an immutable packet. It never writes trigger parameters, clinician rulings, or case-library labels.

**Tech Stack:** Python standard library, existing pytest suite, CSV/JSON, and `homehealth/jev_baseline/phi_guard.py`.

---

### Task 1: Review schemas and synthetic-input guard

**Files:** create `homehealth/aether_review/models.py`, `homehealth/aether_review/review.py`, `homehealth/aether_review/__init__.py`, and `homehealth/aether_review/test_review.py`.

1. Write failing tests for accepted synthetic input, unmarked input, PHI-like input, and unsupported outcomes.
2. Run `python -m pytest -q homehealth/aether_review/test_review.py` and observe failure.
3. Implement request, evidence, outcome, and packet schemas; require a synthetic marker, case ID, engine tier/reasons/rule version; validate with the existing PHI guard.
4. Re-run the focused suite and commit `feat(homehealth): add synthetic review schemas`.

### Task 2: Bounded current clinician-ruling retrieval

**Files:** create `homehealth/aether_review/rulings.py`, modify `review.py`, and create `test_rulings.py`.

1. Write failing tests for CSV loading, current matching references, malformed/policy-row rejection, five-reference cap, and evidence IDs.
2. Implement a read-only deterministic CSV loader/ranker using trigger, rule, and tier fields; persist bounded excerpts and IDs only.
3. Re-run focused tests and commit `feat(homehealth): retrieve bounded clinician rulings`.

### Task 3: Conservative outcomes and typed-decision contract

**Files:** create `decision_adapter.py`, modify `review.py`, and add focused tests.

1. Write failing tests for supported agreement, evidence conflict, named missing case input, empty/stale evidence, malformed typed output, and provider unavailability.
2. Implement deterministic-first routing: missing input → `needs_required_case_input`; conflict → `needs_clinician_review`; provenance/retrieval/typed failure → `system_review_unavailable`; validated support only → `agree_with_engine`.
3. Validate only the four outcomes and finite probabilities. Use test doubles only; no credentials or network calls.
4. Re-run focused tests and commit `feat(homehealth): add conservative review outcomes`.

### Task 4: Frozen synthetic evaluation

**Files:** create `evaluation.py`, held-out/challenge JSON fixtures, `test_evaluation.py`, and `homehealth/docs/AETHER_REVIEW_EVALUATION.md`.

1. Write failing tests that require provenance, separate held-out fixtures, and failure on any unsafe agreement challenge case.
2. Implement local evaluation metrics for outcome, missing-input, evidence-integrity, and unsafe-agreement checks.
3. Set zero unsafe agreements on challenge cases as the mandatory gate; report latency/cost separately.
4. Run `python -m pytest -q homehealth/trigger_engine homehealth/jev_baseline homehealth/aether_review` and commit `test(homehealth): freeze synthetic review evaluation`.

### Task 5: Operational limits

**Files:** modify `homehealth/README.md`, create `homehealth/docs/AETHER_REVIEW_OPERATIONS.md`, and extend review tests.

1. Document synthetic-only input, the four outcomes, no parameter/ruling mutation, and no live calls by default.
2. Require separate authorization for any future live model evaluation: allowed fields, request count, spend cap, and clinical-owner authority.
3. Run all suites, `git diff --check`, and commit `docs(homehealth): document synthetic review boundary`.
