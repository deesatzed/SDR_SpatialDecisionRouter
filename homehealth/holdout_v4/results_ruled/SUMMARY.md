# holdout_v4 re-scored against Wayne's ruled key (SYNTHETIC)

- Key: `holdout_v4_ruled_key.json` (build_ruled_key.py), 76 cases = 67 accepted + 9 merge disputes. CLINICIAN_RULING from review_queue.csv (commit ded1a40) on all 34 queued cases, author label elsewhere.
- Label changes vs author: HX2-003, HX2-004, HX5-005, HX5-007, HX7-003. HX5-005 ruling is silent_log + device ticket with no type named, so any Layer 1 ticket counts.
- Layer 1 v1.11.2 (params 0.11.2-placeholder), Jev prompt v1.10. Stored picks for the 67 accepted cases (jev/parsed); the 9 merge disputes had no picks, so they were run once (jev_disputes/, 3 models, $0.0012, run after the key was built, picks only).
- Not comparable 1:1 with results/SUMMARY.md (67 cases, author labels): the merge disputes are now scored.

| System | Accuracy (decided/n) | Critical misses | False pages /100 | HITM /100 | Errors |
|---|---|---|---|---|---|
| L1 + dual(d1-ultra, pplx) [default] | 75.0% (76/76) | 1 HX7-011 | 9.21 (HX2-003, HX2-004, HX4-004, HX6-001, HX6-003, HX7-003, HX7-005) | 11.84 | 19 |
| L1 + dual(d1-ultra, drex-max) [challenger] | 75.0% (76/76) | 1 HX7-011 | 9.21 (HX2-003, HX2-004, HX4-004, HX6-001, HX6-003, HX7-003, HX7-005) | 7.89 | 19 |
| L1 + d1-ultra | 76.3% (76/76) | 1 HX7-011 | 9.21 (HX2-003, HX2-004, HX4-004, HX6-001, HX6-003, HX7-003, HX7-005) | 2.63 | 18 |
| L1 + pplx | 76.3% (76/76) | 1 HX7-011 | 7.89 (HX2-004, HX4-004, HX6-001, HX6-003, HX7-003, HX7-005) | 2.63 | 18 |
| L1 + drex-max | 75.0% (76/76) | 1 HX7-011 | 7.89 (HX2-003, HX2-004, HX4-004, HX6-001, HX6-003, HX7-003) | 2.63 | 19 |
| Layer 1 alone | 74.3% (35/76) | 1 HX7-011 | 5.26 (HX4-004, HX6-001, HX6-003, HX7-003) | 56.58 | 9 |

Device tickets (Layer 1): 0/9 expected hit, 0 with any ticket; missed HX1-009, HX2-011, HX4-003, HX4-010, HX5-002, HX5-003, HX5-004, HX5-005, HX5-011; unexpected -.

Default-stack errors: HX2-001 nurse_task->silent_log (L1 None/no_trigger); HX2-003 provider_task->urgent_page (L1 None/no_trigger); HX2-004 provider_task->urgent_page (L1 None/no_trigger); HX2-007 nurse_task->silent_log (L1 None/no_trigger); HX3-004 nurse_task->provider_task (L1 SUPPRESSED/recent_ckd_low_dose_review); HX3-008 nurse_task->provider_task (L1 SUPPRESSED/recent_ckd_low_dose_review); HX4-004 provider_task->urgent_page (L1 CONFIRM_FIRST/below_88_change_from_own_baseline); HX4-005 provider_task->silent_log (L1 None/no_trigger); HX4-011 nurse_task->silent_log (L1 None/no_trigger); HX5-001 silent_log->nurse_task (L1 SUPPRESSED/below_band_threshold); HX5-005 silent_log->provider_task (L1 None/no_trigger); HX6-001 nurse_task->urgent_page (L1 CONFIRM_FIRST/fall_on_anticoagulant); HX6-003 nurse_task->urgent_page (L1 CONFIRM_FIRST/fall_on_anticoagulant); HX6-005 nurse_task->provider_task (L1 SUPPRESSED/explained); HX7-003 provider_task->urgent_page (L1 CONFIRM_FIRST/outside_population_default_learning); HX7-011 urgent_page->nurse_task (L1 SUPPRESSED/goals_of_care); HX7-005 nurse_task->urgent_page (L1 None/no_trigger); HX8-003 nurse_task->provider_task (L1 None/no_trigger); HX8-005 nurse_task->provider_task (L1 None/no_trigger)

Notes
- HX7-011 (hospice, distressing breathlessness, ruled urgent_page to the hospice nurse) is a critical miss in every system: Layer 1's goals_of_care suppression caps it at nurse_task and cautious_max_hitm caps SUPPRESSED decisions below urgent_page.
- No device ticket fired on any of the 9 device cases.
