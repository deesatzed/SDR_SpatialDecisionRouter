# Smart hard-trigger policy: relabel, new pairs, VS layers and banded chest pain (2026-10-17)

The policy is in `casegen/prompts_v2/SMART_TRIGGERS.md`. The relabel model was anthropic/claude-haiku-5.5 and the grader was google/gemini-4-argon with GRADER_LLM3_v1.2. All counts below come from files in this folder (`summary.json`).

## Relabel of the 34 library_v2 hard-trigger cases
| tier | n | rules |
|---|---|---|
| ABSOLUTE (stayed escalate_human, alternates []) | 5 | FOCAL_NEURO 3, SYNCOPE 1, CHEST_PAIN_ECG 1 |
| CONFIRM_FIRST (escalate_human after the confirm step or timeout) | 25 | FALL_ANTICOAG 8, GAP48_HIGHRISK 7, SPO2_LT88 6, CHEST_PAIN_VITALS 4 |
| SUPPRESSED | 4 | all `goals_of_care` (hospice/comfort-only): SPO2_LT88 2, FALL_ANTICOAG 1, FOCAL_NEURO 1 |

- CONFIRM_FIRST confirm steps: 15 `already_confirmed` (the confirmation is already in the case, e.g. a fingertip value, a caregiver who saw the fall, or a visit), 6 `caregiver_ping`, 4 `patient_call`.
- **Route changes: 4.** HK1-007, NV6-001, NV6-010 and GC2-001 went from escalate_human to nurse_task (same-shift hospice nurse). No other route changed.
- Alternates changed on 1 case: HK5-002 gained `wake_specialist`. The other CONFIRM_FIRST-pending cases were left with `[]`.
- Rule renames: HT_CHEST_PAIN_CHANGE became HT_CHEST_PAIN_VITALS (4) and HT_CHEST_PAIN_ECG (1).
- **Grader (v1.2, blind):** agreed on route, rule, tier and suppression reason for **34/34**. All 34 were kept with score 5. There were 0 critical misses, 0 tier disputes and no fix-list entries.
- Case facts were not changed. Each rationale gained a one-sentence "Smart-trigger review:" note. The old labels are kept in `prev_labels` and the old grade in `prev_grade`.

## New near-miss pairs: 4 batches, 38 cases, **28 accepted, 11 complete pairs**
| batch | prompt / grader | focus | accepted | complete pairs |
|---|---|---|---|---|
| ST1 | v2.2 / v1.2 | SpO2, COPD baseline, gap, dropped watch, chest-pain ECG | 4/10 | 0 |
| ST2 | v2.2 / v1.2 | syncope vs hospice, old deficit, charger log, pending fingertip, fall vs hospice | 9/10 | 4 |
| ST3 | **v2.3 / v1.3** | **VS layers**: learning period, HR 280 artifact vs HR 184 danger, beta-blocker reset, slow drift, too-fast SpO2 drop | **10/10** | **5** |
| ST4 | v2.3 rev b / v1.3 rev b | **banded chest pain** (4 pairs, 8 cases) | 5/8 | 2 |

- ST3 (all kept, score 5; the grader's blind tier and baseline layer matched every label):
  - P01: COPD SpO2 87% on day 4 of learning → CONFIRM_FIRST, vs the same reading on day 46 with a learned 86-90% baseline → SUPPRESSED at_patient_baseline.
  - P02: HR 280 with motion → ARTIFACT, vs HR 184 at rest → ABSOLUTE (HT_VS_DANGER).
  - P03: HR 58-61 after a metoprolol start → baseline_reset / silent_log, vs the same drop with no med change → wake_specialist.
  - P04: a 16-day monotonic rest-HR rise → drift_not_absorbed / wake_specialist, vs a fluctuating HR with no trend → silent_log.
  - P05: SpO2 97→79% in 4 s → ARTIFACT, vs 96→85% over 25 min → CONFIRM_FIRST.
- ST1/ST2 review queue (5):
  - **ST1-010: CRITICAL_MISS + reject.** It was labelled SUPPRESSED (unreliable ECG), but the case has chest pressure, diaphoresis, HR 102 on bisoprolol and BP 156/94 in a stent patient.
  - **ST1-004: CRITICAL_MISS** under the conservative rule. The grader agreed with at_patient_baseline but its blind route was escalate_human.
  - ST1-002 and ST1-008: route disagreements (the grader chose silent_log where the labels say nurse_task).
  - ST2-009: tier dispute. CONFIRM_FIRST is agreed, but the grader suggests patient_call instead of caregiver_ping because the patient lives alone.
- ST1/ST2 fix list (2): ST1-003 contains the banned word "artifact" in case text; ST1-006 has a category change and is a near-duplicate of a v1 case.
- Every case carries `pair_complete_in_accepted`.

## Three-layer VS rule (Wayne's design note)
- Engine: `casegen/trigger_engine/trigger_eval.py` (a `Baseline` object plus state, serializable). Parameters are in `trigger_params.json` (**all PLACEHOLDER**; changed only via `apply_param_change(approved_by=<human>)`, which validates nesting and logs to change_log). Tests: `test_trigger_eval.py` (15) and `test_grade_merge_layers.py` (7). **22/22 pass.** The tests cover:
  - artifact HR 280 (rechecks, no page, never learned)
  - a flatline with motion, and a too-fast SpO2 drop
  - a danger value that is ABSOLUTE even with a high learned baseline, and is redirected to the hospice nurse under comfort-only goals
  - a learning-period patient: HR 112 and COPD SpO2 87% both CONFIRM_FIRST, with no at-baseline suppression until learning ends; a clinician-set baseline is the exception
  - a beta-blocker start: before the reset, HR 60 is a deviation; after it, HR 60 is NORMAL while relearning; the new median lands at about 60, and the old 78 becomes a deviation
  - a slow drift of +0.6 bpm/day: flagged on day 29 (τ 0.91, +8.2 bpm); learning frozen, 1008 samples excluded, the baseline median stays below 71.5, the route goes to wake_specialist, and clearing needs a human. With the guard disabled, the same drift is absorbed (median above 72.5, no alert).
  - a drift explained by a beta-blocker stop, which is not flagged
  - BOUND_CLAMP logging, and parameter changes that need a named human approver
  - a state round-trip
- Changes to the prompts, policy doc and scripts:
  - SMART_TRIGGERS.md is now v1.1, with a new section 6.
  - GEN_LLM2_v2.3.md and GRADER_LLM3_v1.3.md are new; v2.2 and v1.2 are kept. They add the ARTIFACT tier, HT_VS_IMPLAUSIBLE, HT_VS_DANGER, the `baseline_status` fact and the `baseline_layer` answer.
  - grade_merge.py validates the new fields and adds a DRIFT_MISS queue reason. Re-running it on ST1/ST2 and the relabel gives unchanged results.
  - The converter carries baseline_layer and marks a drift as severity major.

## Banded chest-pain rule (replaces the flat CONFIRM_FIRST / 10 min that Wayne rejected)
- Engine: `evaluate_chest_pain()` in `trigger_eval.py`. Params: `trigger_params.json` → `chest_pain` (**placeholders**, apart from the decided crescendo rule). Policy: SMART_TRIGGERS.md section 7 (v1.3). Prompts: GEN v2.3 rev b and GRADER v1.3 rev b; the pre-chest-pain v2.3/v1.3, SMART_TRIGGERS v1.1 and grade_merge are in `prompts_snapshot/pre_chest_pain/`. The policy text and v2.3/v1.3 also add an explicit order-of-operations line after ST4-002 (see below).
- Tests: `test_chest_pain.py` has 19 tests. **The full suite is now 41/41 passing** (15 engine, 7 grade_merge layers, 19 chest pain, including 2 crescendo tests).
- `grade_merge.py`:
  - HT_CHEST_PAIN_VITALS is banded: ABSOLUTE is allowed.
  - New suppression_reason `below_band_threshold`; it must not go to silent_log.
  - `chest_pain_eval` must be consistent with the tier.
  - New confirm step `device_recheck+patient_call`.
  - `chest_pain_eval` is excluded from the banned-word scan.
- Library cases: inputs were hand-extracted with quotes (`chest_inputs.json`). Engine output is in `chest_pain_eval.json/.csv`. The update is applied by `apply_chest_pain.py`, which `build_outputs.py` runs after every rebuild.

| case | old | new | band (raw → final) | modifiers |
|---|---|---|---|---|
| HK5-002 | CONFIRM_FIRST patient_call 10 | CONFIRM_FIRST patient_call 30 | B → C | post-exertion (0 min) hr_high -1 ; post-exertion timeout x2.0 |
| AC1-003 | CONFIRM_FIRST already_confirmed | ABSOLUTE | B → A | post-exertion (0 min) hr_high -1 ; rate-control med hr_high +1 ; red flags ['crescendo_pattern'] +1 ; now unpaired (see below) |
| AC1-005 | CONFIRM_FIRST already_confirmed | ABSOLUTE | B → A | multi-vital (>=2 at band B or worse) +1 ; red flags ['diaphoresis', 'pallor'] +2 |
| AC2-001 | CONFIRM_FIRST already_confirmed | ABSOLUTE | B → A | red flags ['diaphoresis', 'pallor'] +2 |
| AC2-003 | ABSOLUTE (ECG) | ABSOLUTE | A → A | reliable ECG change |
| ST1-009 | ABSOLUTE (ECG) | ABSOLUTE | A → A | reliable ECG change |
| HK5-001 | non-trigger wake_specialist | engine: LOG_ONLY — **labels not changed** | D → D | — |
| AC1-002 | non-trigger wake_specialist (alt escalate_human) | **CONFIRM_FIRST already_confirmed**, escalate_human, alternates [] (crescendo rule) | D → C | red flags ['crescendo_pattern'] +1 |
| AC2-005 | non-trigger wake_specialist | **CONFIRM_FIRST patient_call 15**, escalate_human, alternates [wake_specialist] (crescendo rule) | D → C | red flags ['crescendo_pattern'] +1 (no post-exertion ×2: vitals normal) |
| AC1-012 (new) | — | **SUPPRESSED below_band_threshold**, nurse_task, alternates [wake_specialist] | D → D | — (stable frequency) |

- **Label changes (4 cases, all still escalate_human):**
  - HK5-002: timeout 10 → 30 min (post-exertion band C ×2).
  - AC1-003, AC1-005, AC2-001: CONFIRM_FIRST already_confirmed → ABSOLUTE.
  - The ECG cases AC2-003 and ST1-009 are unchanged.
  - No route changes. Library severities are unchanged (both tiers export as critical).
- **Blind v1.3 regrade of the 4 changed cases (`raw/CPRL.grader.json`): 4/4 agree on tier, band and route, all kept with score 5.** Caveat: the case JSON shown to the grader includes the `chest_pain_eval` record.
- **Crescendo rule, decided by Wayne (2026-10-17 16:49 EDT):** a crescendo angina pattern with normal vitals → CONFIRM_FIRST. This is now a decided rule in SMART_TRIGGERS v1.3 section 7 and in GEN v2.3 rev c / GRADER v1.3 rev c.
  - Engine changes:
    - Added `chest_pain.crescendo_rule` (min band C) through `apply_param_change(approved_by="Wayne")`, so it is logged in change_log. Params are now 0.3-placeholder.
    - A crescendo case can no longer drop to log-only through discordance.
    - With normal vitals, the post-exertion ×2 timeout no longer applies.
  - The two CP_RULE_DISPUTE items are resolved and removed from review_queue.csv.
  - Relabels: **AC1-002** and **AC2-005** were added to relabeled_cases (36 rows now).
  - **Pair AC1-P01 is now AC1-002 (crescendo) vs the new AC1-012 (stable).**
    - AC1-012 is a hand-derived copy of AC1-002. Only the episode frequency and the phone-check wording change ("unchanged for a year, 2-3 a week on hills, still walking"), plus the derived DF and rationale. It is in manual_cases.json.
    - AC1-003 (crescendo plus HR 116, ABSOLUTE) is now unpaired. Its labels are unchanged, and the "(paired case stays at 66 bpm)" wording was removed from its DF.
  - New tests: crescendo with normal vitals → CONFIRM_FIRST C, patient_call 15 (also with discordance, and already_confirmed); a stable frequency with normal vitals → LOG_ONLY, no page. **41/41 passing.**
  - **Blind regrade (argon v1.3 rev c, `raw/CPRL2.grader.json`):** AC1-002, AC1-012 and AC2-005 are all keep / score 5. The grader matched rule, tier, band and route on all 3. Cost $0.050.
- **ST4 pairs (Haiku v2.3 rev b → Gemini v1.3 rev b):**
  - Accepted: ST4-003/004 (HR 104 post-exertion → log-only, vs at rest → CONFIRM_FIRST 15) and ST4-005/006 (SBP 85 → ABSOLUTE, vs SBP 112 → log-only). These are 2 complete pairs. ST4-008 (clean repeat HR 82 → log-only) was also accepted.
  - ST4-001 (fix): asleep HR 50 on bisoprolol → log-only, nurse_task. The grader agreed with the label; the only fix is category → acs.
  - ST4-007 (fix): poor-contact HR 135 → device_recheck+patient_call 5. Tier and route agree, but the generator's `chest_pain_eval.band` says A when a flagged vital is unbanded.
  - ST4-002 (TIER_DISPUTE, review): the grader computed band C (it offset the context −2 against the red flags +2). The engine computes B, 5 min, because context is applied per vital first and red flags after. The tier and route agree; only the timeout differs (5 vs 15). I added the order-of-operations line to the policy and prompts.

## Re-check of the non-trigger cases (Wayne approved, 2026-10-17 19:29 EDT; updated 19:55 with the CGM rule)
- **Scope:** all 200 non-trigger cases in the pre-recheck `library_v2_smart_accepted.json`. Snapshot: `pre_recheck/` (library JSON, CSVs, runner, DIFF_SUMMARY, summary, review/fix queues, relabeled_cases, new_pairs).
- **1. Deterministic screen** (`recheck/det.py` → `det_results.json`, trigger_eval params **0.4-placeholder**):
  - Readings are regex-extracted from the trend, notes **and data-quality flags**. Only Day -1 and Day 0 count.
  - CGM context (pressure cues, symptoms, fingerstick pairing by day and episode time window) is now taken from the whole case text, not just one sentence.
  - Layers scored: hard limits, the CGM pressure-low rule, SpO2 < 88 (rule only), gap ≥ 48 h (candidate only) and banded chest pain. Fall, syncope and focal neuro are not deterministically scorable.
  - 195/200 cases were scorable and 12 had a finding:
    - glucose → SUPPRESSED unreliable_reading on 3 (GC1-010, GL1-001, GL1-002: CGM low not confirmed by fingerstick, pinned sensor)
    - ABSOLUTE on 2 (NV2-015 symptomatic; GL1-005 confirmed by fingerstick)
    - SUPPRESSED goals_of_care on 1 (GC2-003)
    - HK5-001 → LOG_ONLY band D
    - 5 gap candidates
  - 5 more cases (NV8-005, CG1-007, DM2-009, GL1-003, GL1-004) had danger glucose only on older, resolved days.
- **2. Proposals** (anthropic/claude-haiku-5.5, 4 calls, independent of the screen, `recheck/proposals.json`): 11/200 have a trigger present; {'SUPPRESSED/below_band_threshold': 1, 'CONFIRM_FIRST/None': 2, 'SUPPRESSED/explained': 2, 'ABSOLUTE/None': 2, 'SUPPRESSED/unreliable_reading': 3, 'SUPPRESSED/goals_of_care': 1}.
- **3. Blind grade** (google/gemini-4-argon, GRADER v1.3 rev c, compact, `recheck/grades.json`): 11/11 graded.
- **Applied, where evaluator, model and grader all agree and there is no route change: 4.**
  - HK8-003: HT_GAP48_HIGHRISK SUPPRESSED `explained`.
  - GC1-010, GL1-001, GL1-002: HT_VS_DANGER SUPPRESSED `unreliable_reading`.
  - Routes and alternates are unchanged. Library routes stay 76/51/69/65. Hard-trigger cases: 61 → 65. The previous values are in `prev_labels`, and provenance in `recheck`.
- **Review queue: 7 rows** (`pass=recheck`, prefix `RECHECK_`):
  - Route changes proposed: HK7-009, GC2-003
  - Critical miss from the model: HK7-009. The grader disagrees: it reads this as an explained near-fall.
  - Evaluator/model disagreements: **none** (were 3)
  - Drift misses: none
  - The other rows agree on rule and tier but need a non-additive fix (e.g. alternates → [] for ABSOLUTE/already_confirmed, or a rationale that still says "no hard trigger").

| case | current route | proposed | grader (blind) | queue reasons |
|---|---|---|---|---|
| HK5-001 | wake_specialist | HT_CHEST_PAIN_VITALS SUPPRESSED below_band_threshold | HT_CHEST_PAIN_VITALS SUPPRESSED below_band_threshold → nurse_task | GRADER_DISAGREE |
| HK6-001 | escalate_human | HT_FALL_ANTICOAG CONFIRM_FIRST  | HT_FALL_ANTICOAG CONFIRM_FIRST  → escalate_human | SCRIPT_CHECK|GRADER_DISAGREE |
| HK6-002 | wake_specialist | HT_FALL_ANTICOAG SUPPRESSED explained | HT_FALL_ANTICOAG SUPPRESSED unreliable_reading → wake_specialist | GRADER_DISAGREE |
| HK7-009 | nurse_task | HT_FALL_ANTICOAG CONFIRM_FIRST  | HT_FALL_ANTICOAG SUPPRESSED explained → nurse_task | ROUTE_CHANGE|CRITICAL_MISS|SCRIPT_CHECK|GRADER_DISAGREE |
| NV2-015 | escalate_human | HT_VS_DANGER ABSOLUTE  | HT_VS_DANGER ABSOLUTE  → escalate_human | SCRIPT_CHECK|GRADER_DISAGREE |
| GC2-003 | escalate_human | HT_VS_DANGER SUPPRESSED goals_of_care | HT_VS_DANGER SUPPRESSED goals_of_care → wake_specialist | ROUTE_CHANGE|SCRIPT_CHECK|GRADER_DISAGREE |
| GL1-005 | escalate_human | HT_VS_DANGER ABSOLUTE  | HT_VS_DANGER ABSOLUTE  → escalate_human | SCRIPT_CHECK|GRADER_DISAGREE |

- **CGM pressure-low rule** (SMART_TRIGGERS v1.4 section 8; `cgm_pressure_low` added via apply_param_change approved_by Wayne). Tests: `test_cgm_pressure.py` (9). **The full suite is 50/50 passing.**
  - The 3 evaluator-only critical misses (GC1-010, GL1-001, GL1-002) are **resolved**. The evaluator now gives SUPPRESSED unreliable_reading, matching Haiku and the grader, so the 3 review rows were removed and the agreed metadata applied.
  - The cause was a cross-sentence extraction gap: the "pinned sensor" cue was in another sentence or in the data-quality flags.
- Soft notes, not queued: the gap ≥ 48 h candidates HK8-006, HK8-010, NV3-024 and NV7-006 were not adopted by the model.
- Cost: proposals $0.058 and grade $0.066, **$0.124 in total**. The CGM rule step made no API calls. The smart-pass total is **$1.096**.

## Per-trigger actionable-escalation rate (`merge_relabel/trigger_stats.csv`, label-based)
FALL_ANTICOAG 0.89 (8/9), SPO2_LT88 0.75 (6/8), FOCAL_NEURO 0.75 (3/4); GAP48, CHEST_PAIN_VITALS, CHEST_PAIN_ECG and SYNCOPE are 1.0. No rule is flagged NOISY (the flag needs n ≥ 3 and a rate < 0.5). In the pair batch every rule is 0.5 by design (`merge_pairs/trigger_stats.csv`). These are label rates on synthetic data; the production rate needs real confirmations.

## Cost
**Banded chest-pain step: $0.181** over 3 calls: ST4 generation $0.024, ST4 grading $0.098 and CPRL regrade $0.059. The step stop was $0.50. Crescendo regrade (CPRL2): $0.050, one call. **The smart pass total is now $0.972.**

Earlier: **$0.742** in total over 10 calls, none retried: relabel $0.022 (Haiku ×2), relabel grading $0.278 (Gemini ×2), ST1/ST2 generation $0.068, ST1/ST2 grading $0.234, ST3 generation $0.032 and ST3 grading $0.110. This is under the ~$1 target; the $2 stop was not reached.

## Caveats
- The 34/34 grader agreement is real, but the blind pass reads router_input, so the case facts strongly determine the tier. This agreement does not prove that the grader catches mislabels on its own. ST1-010 shows that it does catch a real suppressed trigger.
- Done (see the re-check section): the 200 non-trigger cases were re-checked; 4 label additions were applied and 7 items are queued for review.
- All VS-layer numbers in trigger_params.json are placeholders, chosen by me, that the clinical owner must set. The drift guard excludes samples from the window start onward once it fires, which is conservative and also drops some pre-drift days.
- Policy choices that need the clinical owner's confirmation:
  - Superseded: the flat chest-pain CONFIRM_FIRST 10 min was rejected by Wayne and replaced by the banded rule. All band cut-offs, modifiers, timeouts and the 'rate-control med makes tachycardia +1' choice are placeholders for Wayne.
  - (confirmed by Wayne) A goals_of_care suppression maps to `nurse_task`, with the meaning "same-shift hospice nurse".
  - Goals of care can also suppress ABSOLUTE rules.
