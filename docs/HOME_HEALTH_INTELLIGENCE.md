# Home-health HITM and medical intelligence

This note is about **Spatial HITM**. Source paths under `SpatialDecisionRouter/` are the app folder in this checkout. The GitHub repository may still be `SDR_SpatialDecisionRouter` until a later rename.

Liu et al., *Medical superintelligence: foundations and aspirations*, BMJ Digital Health & AI 2026;2:e000395. <https://bmjdigitalhealth.bmj.com/content/2/1/e000395>

The paper's six dimensions describe medical intelligence across the arc of care. This app's home-health seat is the **coordination layer**: a physician, a covering clinician, or a nurse decides a route while the case is still open. It is not a vignette solver, and a match to a library label is not the score that matters.

| Dimension | What this HITM does |
|---|---|
| Medical knowledge and its application | **Still open** on L0 is a retained differential built from facts already on the card. The list is not collapsed to one diagnosis label. |
| Diagnostic reasoning and triage | The same face shows when a route is required **before** that list closes, a **Wait for …** action whose observation would flip the route, and **Revise prior** when new evidence falsifies the last Pass or Log only. Every wait has a visible timer. If that window passes without the observation, the case comes back for a person. It is not dropped, paged, or auto-passed. |
| Therapeutic decision-making and action | The route is the action. Log only, a nurse task, a provider task, or a page can be chosen while the differential is still open. |
| Longitudinal context | **Why now** stays the triggering event. **This week** stays the pattern. A falsified prior sits beside the new evidence as Prior → new evidence → Revise. |
| Clinical coordination | When the proposing agent should not decide, the card **refuses** and will not auto-pass. Overseer, Bedside, or Nurse HITM chooses. Pass still goes to the on-call recipient. |
| Alignment with human values and agency | **Goals of care** sit on the pass. Do-not-hospitalize or comfort-focused goals constrain a page and are stored with the decision. |

The paper also describes collective learning: lessons from one seat become a shared update other seats can use later. The first slice is a local rollup of Overseer logs (other seats included in the same file). See `homehealth/sdr_bridge/learning_export.py`.

Outcome-linked scoring lives in `homehealth/sdr_bridge/outcome_eval.py`. It reports route appropriateness, escalation timing, and a synthetic downstream utility next to agreement with an expert-consensus fixture. A choice can beat that consensus on the outcome. An agreement-only score would call that beat an error. Fixtures include incomplete, conflicting, and misleading information.

Display logic for the card is `HomeHealthMind` in `SpatialDecisionRouter/Domains/HomeHealth/HomeHealthMind.swift`. `HomeHealthWaitClock` reads a duration from the wait text (PX-WAIT-01 “over 6 hours” is 6h, a spray wait “after 10 minutes” is 10m) or uses a visible default when the text has no number. The decision stores `voi_wait_minutes` and `voi_wait_deadline`. The engine checks that deadline on each tick. An expired wait is logged as `voi_recheck` with `voi_wait_overdue` and returned to Now. Pattern fixtures in `homehealth_patterns.json` supply the reads that library text does not (`PX-REVISE-01`, `PX-REFUSE-01`, `PX-DNH-01`, `PX-WAIT-01`, and the mind block on `PX-COPD-01`), including an explicit `wait_minutes` on each. Library cases derive the same read from the vignette text. Nothing here is PHI.
