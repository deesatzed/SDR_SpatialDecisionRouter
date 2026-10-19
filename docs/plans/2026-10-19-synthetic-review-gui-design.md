# Synthetic Clinician-Review GUI Design

## Purpose

Provide a local reviewer interface for converting selected synthetic home-health cases into frozen structured trigger inputs. Reviewers confirm a preconfigured conversion, edit only a needed field, route an ambiguity to clinician review, or exclude a case from the structured corpus.

## Stack and data flow

The interface uses Flask, Jinja templates, and SQLite. It binds to `127.0.0.1` only. Existing synthetic cases, clinician rulings, and trigger parameters are read-only sources. SQLite stores proposed conversions, reviewer actions, and append-only audit events. The deterministic trigger engine recalculates locally after a draft edit.

## Focused review screen

The screen shows a queue count, concise source summary, existing clinician ruling, pre-filled structured input, expected engine result, and five checks: synthetic source, accurate trigger reading, accurate confirmation, matching deterministic result, and correct clinician-ruling link.

Actions are `agree with all 5`, `edit one field`, `needs clinician review`, and `exclude`. Approving requires all five checks and a matching recomputed engine result. An edit is visible as a draft and requires recomputation before approval.

## Safety

Only explicitly synthetic cases are accepted. PHI-like content, malformed payloads, missing ruling references, invalid fields, engine failures, and storage failures block approval. The app has no live-model, network, trigger-parameter mutation, clinician-ruling mutation, or escalation-execution path.

Every action appends case ID, reviewer display name, action, changed fields, prior/current engine result, and timestamp to the review-state audit trail. A source-case, source-ruling, or trigger-parameter write is prohibited.

## Acceptance checks

Tests cover queue filtering/counts, prefilled rendering, all-five approval requirement, draft recomputation, clinician-review/exclusion actions, audit immutability, PHI/synthetic guards, and source immutability. The GUI evaluates synthetic review workflow behavior only and does not establish clinical validity.
