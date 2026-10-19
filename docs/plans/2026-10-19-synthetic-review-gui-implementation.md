# Synthetic Clinician-Review GUI Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver a local-only reviewer GUI for preconfigured synthetic structured-case conversions.

**Architecture:** Flask routes read immutable synthetic sources and use SQLite only for local review state/audit records. The existing adapter recomputes trigger results from draft inputs; no source data is modified.

**Tech Stack:** Flask, Jinja templates, SQLite, pytest, existing `homehealth.aether_review` and trigger engine.

---

### Task 1: Local review-state store

Create `homehealth/review_gui/store.py` and `test_store.py`. Write red tests for queue records, immutable audit records, and source-read-only boundaries. Implement SQLite schema and repository methods. Run focused tests and commit.

### Task 2: Preconfigured synthetic queue loader

Create `homehealth/review_gui/queue.py` and fixture JSON. Write red tests for synthetic markers, ruling references, queue filters, and counts. Implement read-only loader with PHI guard. Run focused tests and commit.

### Task 3: Flask focused review screen

Create `homehealth/review_gui/app.py`, templates, static CSS, and route tests. Write red tests for localhost-only configuration, rendering, and all-five agreement gating. Implement local routes and templates. Run focused tests and commit.

### Task 4: Draft edit and deterministic recomputation

Extend the queue/store/app and tests. Write red tests that a draft edit recomputes through `trigger_adapter`, displays before/after output, and cannot approve without confirmation. Implement and commit.

### Task 5: Disposition and audit actions

Add clinician-review/exclusion routes and tests. Require display name and append-only audit event. Verify source files remain byte-identical. Commit.

### Task 6: Documentation and verification

Document localhost-only operation and run instructions in `homehealth/docs`. Run `python -m pytest -q homehealth/trigger_engine homehealth/jev_baseline homehealth/aether_review homehealth/review_gui`, inspect `git diff --check`, and commit.
