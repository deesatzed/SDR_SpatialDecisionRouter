# Fly layer (Layer 3) results, SYNTHETIC library v2 (270 cases)

These results use no new paid calls. Jev is the stored v1.8 `liquid/d1-ultra` base-variant pick set. Fly ran locally (GoalJevFly `FlyPolicy`, EPG top-12 receipt).
Label pages/100 = 30.7. Held-out split: batches AC1, DM2, HK1, HK6, HK9, NV1, NV5, RN1, ST2 and ST3 (92 cases). Train: 178 cases.

## Headline (all 270, in-sample)

| System | Accuracy | Critical misses | Pages/100 | False pages/100 | Suppressed | Hospice | Pairs both correct | HITM flags |
|---|---|---|---|---|---|---|---|---|
| Fly alone (check -> escalate, frozen t=0.2, leak 0.8) | 51.9% | 5 | 72.2 | 34.1 | 1/24 | 3/7 | 3/39 | - |
| Layer 1 + Jev | 92.6% | 0 | 35.2 | 2.6 | 20/24 | 7/7 | 30/39 | 0 |
| + Fly flag_only (tuned: leak 0.5, t=0.841) | 92.6% | 0 | 35.2 | 2.6 | 20/24 | 7/7 | 30/39 | 32 (7 on stack errors) |
| + Fly confirm_first (tuned: leak 0.5, t=0.876) | 92.2% | 0 | 35.6 | 3.0 | 20/24 | 7/7 | 29/39 | 1 |
| + Fly bump_wake (tuned: leak 0.5, t=0.876) | 92.6% | 0 | 35.2 | 2.6 | 20/24 | 7/7 | 30/39 | 1 |
| + Fly confirm_first (frozen t=0.2, untuned) | 65.6% | 0 | 71.9 | 32.6 | 7/24 | 7/7 | 8/39 | 99 |
| + Fly bump_wake (frozen t=0.2, untuned) | 81.9% | 0 | 35.2 | 2.6 | 18/24 | 7/7 | 27/39 | 55 |

- Fly alone missed 5 critical cases: LIB-HK3-003, LIB-HK3-005, LIB-EL1-003, LIB-EL1-006 and LIB-EL1-008. None of the 5 had a derived deviation day, so the readout was 0.
- Fly alone was wrong on 4 hospice cases: LIB-NV6-001, LIB-GC2-001, LIB-ST2-002 and LIB-ST2-010. Fly has no goals-of-care input.
- The tuned banded Fly router (readout to 4 routes) collapsed to the binary rule on train. No band split beat it without adding critical misses, because the readout takes only a few discrete levels.

## Held-out (92 cases; thresholds tuned on train only)

| System | Accuracy | Critical misses | Pages/100 | False pages/100 | Pairs | HITM flags (on stack errors) |
|---|---|---|---|---|---|---|
| Fly alone (frozen t=0.2) | 52.2% | 0 | 80.4 | 40.2 | 2/19 | - |
| Layer 1 + Jev | 89.1% | 0 | 40.2 | 3.3 | 15/19 | 0 |
| + flag_only | 89.1% | 0 | 40.2 | 3.3 | 15/19 | 10 (2 of the 10 held-out stack errors) |
| + confirm_first | 88.0% | 0 | 41.3 | 4.3 | 14/19 | 1 (adds a false page: LIB-HK6-006) |
| + bump_wake | 89.1% | 0 | 40.2 | 3.3 | 15/19 | 1 |

## Disagreement (what the HITM would see)

- **flag_only rule, tuned:** 32/270 flagged (11.9/100); 10/92 held-out (10.9/100).
  - 7 of the 32 land on stack errors: LIB-AC1-009, LIB-GC1-008, LIB-GC2-004, LIB-GC2-007, LIB-GC2-008, LIB-RN1-002 and LIB-ST1-006. The stack makes 20 errors overall.
  - In-sample precision is 22%, against a 7.4% base error rate. On held-out it is 2/10, against 10/92 (10.9%).
- **Raw Fly vs stack disagreement (Fly check vs stack escalate/not), all owners:**
  - frozen t=0.2 / leak 0.8: 106/270 (39.3/100). In 103 of these Fly said check and the stack did not escalate; in 3 the reverse. 8 of the 106 are stack errors.
  - tuned t=0.841 / leak 0.5: 86/270 (31.9/100).

## Recommendation

Use **flag_only**: Fly is a second-opinion flag to the HITM and never changes a route.
- On this library, no raising rule improved any metric on train. The tuned raising rules converged to near no-ops. On held-out, confirm_first added a false page.
- At the a-priori threshold, the raising rules doubled pages or cost about 11 accuracy points.
- Keep Fly out of hospice and goals-of-care routing; Layer 1 owns those.

## Caveats

- All thresholds and leak values were swept, so any "all" number for a tuned rule is in-sample.
- The Layer 1 adapter itself was developed on this same library, so the stack numbers are also in-sample. The held-out batches were never used for Fly tuning, but they were seen during Layer 1 development.
- The day-flag cut-offs were fixed a priori. The 270-case label distribution was looked at only once, as a sanity check, and the cut-offs were not changed afterwards.
- The data is synthetic only.

## Review GUI queue (read only, not modified)

`homehealth/review_gui/queue.py` loads a JSON list of entries with these keys:
- `synthetic: true`
- `case_id`
- `summary` (PHI-guarded)
- `clinician_ruling_ref`
- `input` (`synthetic: true`, with a `case_id` that matches the entry's)
- `expected` (`tier` and `rule`)

It rebuilds a fixed `QueueCase`, so any extra keys are dropped. As written, a Fly/Jev disagreement could be carried only in the
`summary` string, with the case's trigger input and expected tier/rule. The flag's details (stack route, owner, Fly readout)
would need a schema change, such as an optional `disagreement` dict on QueueCase. `per_case.csv` (`flag_only_hitm_flag`) is the source for such entries.
