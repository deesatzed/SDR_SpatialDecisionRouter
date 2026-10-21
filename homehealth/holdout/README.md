# holdout_v1: fresh out-of-sample synthetic set (SYNTHETIC)

This set is scored on the stack frozen at 81820c9; see `results/REPORT.md` for the results.

| Files | What they are |
|---|---|
| `holdout_v1_accepted.json` | the 60 accepted, undisputed cases; src_library `holdout_v1`, IDs `HOn-NNN` |
| `holdout_v1_runner.json`, `_Cases_Medical.csv`, `_Outcomes.csv` | SDR import of those cases (runner IDs `LIB-HOn-NNN`) |
| `review_queue.csv` | the 34 grader-disputed cases for Wayne: one row each, background first, blank CLINICIAN_RULING / CLINICIAN_NOTE |
| `fix_list.csv` | the 41 cases flagged for a fix; excluded from scoring |
| `dedupe_removed.json` | cases removed as near-duplicates of the library (none) |
| `holdout_counts.json` | case counts |
| `run_holdout.py` + `specs.py` | generation and grading; reuses `library_v1/run_library.py` from the jevfly_smoke pipeline |
| `finalize_holdout.py` | merge, dedupe, review queue and SDR conversion |
| `score_holdout.py` | scoring with the frozen `jev_baseline` / `fly_layer` code |
| `results/fly_readouts.json` | Fly readouts from `run_fly.py` on the Mac |

Raw model responses and Jev checkpoints are not committed.

## 2026-10-21: v1.9 route ids and clinician rulings

- Labels use the v1.9 ids (`provider_task`, `urgent_page`); stored Jev picks in `jev/parsed/` keep the v1.8 ids and are mapped on read. Scores unchanged.
- `review_queue.csv` carries Wayne's CLINICIAN_RULING / CLINICIAN_NOTE for all 34 queued cases (mapped to v1.9 ids; DROP: HO8-006, HO7-013, HO8-001). Case fixes applied in the queue: HO7-021 living -> with spouse; HO8-015 note pronoun she -> he. Rulings are recorded only; the accepted set and scores are not yet changed.
- HO8-025 is on the Layer 1 hardening list (hospice suppression applied to a symptomatic danger-level low; should be ABSOLUTE, urgent hospice-nurse page).
