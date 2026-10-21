# SMART_TRIGGERS — hard-trigger policy v1.10 (v1 approved by the clinical owner on 2026-10-17; section 6, the three-layer VS rule, added from Wayne's design note the same day; section 7, the banded chest-pain rule, after Wayne rejected a flat 10-min chest-pain confirm; v1.3 records Wayne's decided crescendo rule; v1.4 adds the CGM pressure-low artifact rule (section 8); v1.5 (2026-10-18) applies Wayne's review-queue rulings: net-then-clamp band math, unanswered prompt when living alone = failed confirm, hospice narrowing, and three new answer fields (section 9); v1.6 (2026-10-18) adds distressing breathlessness treatable at home to the urgent hospice-comfort list (section 9e); v1.7 (2026-10-18) narrows the hospice low-glucose rule to symptomatic lows and adds clinician_override (sections 9f-9g); v1.8 (2026-10-18) formalises the learning-period rule (section 9h); v1.9 (2026-10-21) renames and defines the four routes (section 0) and records the open Layer 1 hardening list (section 10); v1.10 (2026-10-21) Layer 1 fixes from Wayne's review-queue rulings (section 11))

This replaces the v2.1 default, under which every hard trigger was urgent_page with empty alternates. It applies to GEN_LLM2_v2.2/v2.3, GRADER_LLM3_v1.2/v1.3, grade_merge.py and convert_casegen.py. All data are synthetic.

## 0. Routes (v1.9, Wayne 2026-10-21)
Four routes, lowest to highest. The id is what cases, rules and model outputs store; the label is what people see.

| id | label | definition |
|---|---|---|
| `silent_log` | silent | Log only; no human action needed. |
| `nurse_task` | nurse task | Nurse contact within about 24 h (under hospice/comfort goals: a same-shift hospice nurse contact). |
| `provider_task` | provider task | Review by the clinician responsible for that condition or medication on the **same business day**. Not a page. |
| `urgent_page` | urgent page | Page someone now: ABSOLUTE triggers, failed confirm checks (CONFIRM_FIRST confirmed or timed out), acute presentations; urgent hospice-comfort problems page the hospice nurse (`escalation_target: hospice_nurse`). |

**Backward compatibility.** v1.8 and earlier used `wake_specialist` (now `provider_task`) and `escalate_human` (now `urgent_page`). It is a straight rename: no ruling, label or tier changes. Every reader (Layer 1 adapter, scoring, dual Jev, Fly, casegen) maps the old ids to the new ones on read (`jev_baseline/routes.py`, `LEGACY_ALIAS`), so stored model outputs and scores still parse. New writes use the new ids only.

## 1. The four checks (run before any page)
A trigger rule can **fire** (its condition is met on the surface). Before paging a human, it must pass four checks:

1. **Reliable reading.** The reading comes from a reliable device with no motion or poor-contact flag. A fingertip check (`fingertip_oximeter`) or a nurse visit (`visit:` note) counts as confirmation.
2. **Change from the patient's own baseline.** A population cutoff alone is not enough. Example: a COPD patient whose usual SpO2 is 88-90% and who reads 87% at rest is not a change.
3. **No explanation.** For example, a data gap covered by a timed contact, a charger/dock log or a caregiver check-in inside the gap, or a fall event that was a dropped or removed watch.
4. **Within the goals of care.** Hospice or comfort-focused goals suppress **hospital-directed** escalation: the trigger goes to the hospice nurse (same shift), not to emergency escalation. **v1.5:** an urgent, treatable, goal-consistent comfort problem (symptomatic danger-level hypoglycaemia (v1.7: recurrence alone no longer qualifies); v1.6: distressing breathlessness treatable at home) is NOT suppressed: it pages the hospice nurse now (section 9c).

## 2. Tiers
| tier | rules | action | route | acceptable_alternates |
|---|---|---|---|---|
| **ABSOLUTE** | `HT_SYNCOPE`, `HT_FOCAL_NEURO`, `HT_CHEST_PAIN_ECG` (chest pain/pressure **with an ECG change**) | escalate now; no confirm step | `urgent_page` | `[]` (must be empty) |
| **CONFIRM_FIRST** | `HT_SPO2_LT88`, `HT_GAP48_HIGHRISK`, `HT_FALL_ANTICOAG`; `HT_CHEST_PAIN_VITALS` is **banded** (section 7): ABSOLUTE, CONFIRM_FIRST with a band-scaled timeout, or LOG_ONLY | an automatic check with a timeout (fingertip recheck, caregiver ping or patient call); **escalate if confirmed OR no answer by the timeout** | `urgent_page` | may contain `nurse_task_with_recheck` and/or `provider_task`; never `silent_log` |
| **SUPPRESSED** | any rule that fired but failed check 1, 2, 3 or 4 | not paged. The suppression is **logged with a reason, never silently dropped, and sampled to the HITM (human-in-the-middle) review** | `silent_log`, `nurse_task` or `provider_task` (never `urgent_page`) | normal rules for non-trigger cases |

Notes:
- **Fall on an anticoagulant** escalates once confirmed (a patient or caregiver confirms the fall, or a visit) and once it is not a dropped watch. If the case data already shows a dropped or removed watch with the patient fine, the tier is SUPPRESSED (`explained`).
- If **confirmation is already in the case** (for example, a fingertip recheck at 85% or a caregiver who saw the fall), the tier is CONFIRM_FIRST with `confirm_step: "already_confirmed"`, `confirm_timeout_min: null` and `acceptable_alternates: []`.
- An ABSOLUTE sign seen **only on a flagged device** (e.g. a watch ECG with a poor-contact flag and no symptoms) does not count as ABSOLUTE. Treat it as CONFIRM_FIRST (patient call), or SUPPRESSED if the case already refutes it.
- **Goals of care** apply to every tier, including ABSOLUTE. With a hospice or comfort-only plan the tier is SUPPRESSED, the `suppression_reason` is `goals_of_care`, and the route is `nurse_task` (meaning a same-shift hospice nurse contact, not a 24-72 h task). It is never `silent_log`. **v1.5 exception:** an urgent, treatable, goal-consistent comfort problem keeps its tier, routes `urgent_page` with `escalation_target: "hospice_nurse"` (an urgent hospice-nurse page now), and is not suppressed (section 9c).
- **v1.5: an unanswered patient prompt when the patient lives alone is a failed confirm.** If a CONFIRM_FIRST patient-directed prompt (patient call or watch tap-to-confirm) gets no answer and the patient lives alone, escalate now: `confirm_step: "already_confirmed"`, timeout null, alternates `[]` (section 9b). A caregiver ping is not a patient prompt.
- **High-risk** (for `HT_GAP48_HIGHRISK`) has the same meaning as in v2.1: HF; discharge within 30 days; home O2; dementia living alone; insulin or sulfonylurea; anticoagulant with a fall history.

## 3. Case fields (all are answer fields; never put them in case text or router_input)
| field | type | rule |
|---|---|---|
| `hard_trigger` | bool | **true when any trigger rule FIRED**, including SUPPRESSED (changed from v2.1) |
| `hard_trigger_rule` | rule id or null | required when hard_trigger is true. `HT_CHEST_PAIN_CHANGE` is split into `HT_CHEST_PAIN_ECG` (ABSOLUTE) and `HT_CHEST_PAIN_VITALS` (CONFIRM_FIRST) |
| `trigger_tier` | `ABSOLUTE` \| `CONFIRM_FIRST` \| `SUPPRESSED` \| null | null if and only if hard_trigger is false |
| `confirm_step` | `fingertip_recheck` \| `caregiver_ping` \| `patient_call` \| `already_confirmed` \| null | required for CONFIRM_FIRST, null otherwise |
| `confirm_timeout_min` | integer \| null | required for CONFIRM_FIRST unless `already_confirmed`. Defaults: fingertip_recheck 15, patient_call 10, caregiver_ping 30 (a gap: 60). Range 5-120 |
| `suppression_reason` | `unreliable_reading` \| `at_patient_baseline` \| `explained` \| `goals_of_care` \| `below_band_threshold` \| null | required for SUPPRESSED, null otherwise |
| `escalation_target` (v1.5) | `hospice_nurse` or absent | urgent comfort problem in a hospice/comfort-only patient: ABSOLUTE or CONFIRM_FIRST, `urgent_page`, category includes `goals_of_care` |
| `route_basis` (v1.5) | `clinical_presentation` or absent | only on a SUPPRESSED trigger routed `urgent_page` by clinician ruling because the clinical picture (not the trigger) needs a human now (e.g. ST1-004) |
| `secondary_triggers` (v1.5) | list or absent | further rules that fired on the same case, each `{hard_trigger_rule, trigger_tier, confirm_step, confirm_timeout_min, suppression_reason, if_confirmed_route, evidence}`. The primary fields above describe the trigger that sets the route now. A pending secondary CONFIRM_FIRST (e.g. an HR `device_recheck`) escalates if confirmed or at timeout (`if_confirmed_route: urgent_page`) and makes the route at least nurse_task |

## 4. Route and alternate mapping (validated by grade_merge.py)
- ABSOLUTE → expected `urgent_page`, alternates `[]`, confirm/suppression fields null.
- CONFIRM_FIRST → expected `urgent_page`, alternates ⊆ {`nurse_task_with_recheck`, `provider_task`}, `confirm_step` set; timeout set unless `already_confirmed`, in which case alternates are `[]`.
- SUPPRESSED → expected ∈ {`silent_log`, `nurse_task`, `provider_task`}, `suppression_reason` set. `goals_of_care` → `nurse_task` (or `provider_task`), never `silent_log`. v1.5: `urgent_page` only with `route_basis: "clinical_presentation"`.
- `escalation_target: hospice_nurse` → expected `urgent_page`, tier ABSOLUTE or CONFIRM_FIRST, `goals_of_care` in category.
- `secondary_triggers` → each entry is validated like a trigger; a CONFIRM_FIRST entry needs a confirm step (CONFIRM_FIRST steps or `device_recheck`), a 5-120 min timeout unless already confirmed, `if_confirmed_route: urgent_page`, and the case may not be `silent_log`.
- `nurse_task_with_recheck` is an alternate token only, never an expected_route. A grader or router answering `nurse_task` on a CONFIRM_FIRST case whose alternates include `nurse_task_with_recheck` counts as an acceptable alternate, **provided** the recheck and timeout are part of that answer. In script scoring, the recheck is taken as implied by the confirm_step label.

## 5. Scoring
- **Critical miss (label QA):** a case labelled SUPPRESSED where the blind grader judges the trigger real (blind route `urgent_page`, or blind tier ABSOLUTE/CONFIRM_FIRST). This goes to the review queue as `CRITICAL_MISS` with top priority and is never auto-accepted.
- **Critical miss (router eval):** on an ABSOLUTE or CONFIRM_FIRST case, the router answers `silent_log`, or suppresses the trigger. In the SDR export these cases carry `severity_if_wrong: critical`.
- **Over-escalation:** on a SUPPRESSED case the router answers `urgent_page`. This is counted per rule as a false page, not a critical miss.
- **Per-trigger actionable-escalation rate** = (cases where the rule fired and the tier is ABSOLUTE or CONFIRM_FIRST) / (cases where the rule fired). grade_merge writes it to `trigger_stats.csv`. A rule with n ≥ 3 and a rate < 0.5 is flagged **NOISY** for threshold review. In production the same rate is computed from real confirmations: a page is "actionable" when the human acts on it.
- **HITM sampling:** every SUPPRESSED trigger is logged with its reason. A sample goes to human review (suggested: 100% of `goals_of_care` and `at_patient_baseline`, 20% of `unreliable_reading` and `explained`). A sampled suppression that the human judges real is a critical miss.

## 6. Vital-sign layers: hard limits, a learning period and ongoing adaptation (v1.1)
Design note from Wayne: some VS values are clearly very abnormal or clearly artifact. The learning period for VS and activity is specific to each patient and their current condition, so it changes over time.
The reference implementation is `casegen/trigger_engine/trigger_eval.py`, with parameters in `trigger_params.json` and tests in `test_trigger_eval.py`. **Every number is a PLACEHOLDER.** Only a named human changes the parameters, through `apply_param_change(approved_by=...)`, which validates nesting and appends to `change_log`. The engine never writes them.

**Layer 1: HARD LIMITS (fixed, never learned)**
- *Implausible* → tier **ARTIFACT** (rule `HT_VS_IMPLAUSIBLE`). The system rechecks automatically (`device_recheck`, or `fingertip_recheck` for SpO2) and does not page. The event is logged, and the value is never learned. Implausible means any of:
  - outside the implausible range (placeholders: HR < 20 or > 250; SpO2 < 50; RR < 3 or > 70; SBP < 50 or > 300; glucose < 20 or > 600)
  - a rate of change too fast to be physiologic (SpO2 > 2 points/s, HR > 30 bpm/s)
  - an HR flatline of 60 s or more while the accelerometer shows motion
- *Danger* → **ABSOLUTE** (rule `HT_VS_DANGER`) regardless of baseline. Placeholders: HR ≤ 35 or ≥ 180; SpO2 ≤ 80; RR ≤ 6 or ≥ 35; SBP ≤ 80 or ≥ 200; glucose ≤ 54 or ≥ 400; temperature ≤ 35.0 or ≥ 40.0 °C. The reading must still be reliable: a quality-flagged danger value is SUPPRESSED `unreliable_reading` with an automatic recheck. Goals of care still apply, so a comfort-only plan goes to the hospice nurse.

**Layer 2: per-patient LEARNING PERIOD**
- An onboarding window of 10 days (placeholder; range 7-14) learns baselines per vital × activity state (sleep / rest / active) × time of day (night / morning / afternoon / evening). A stratum is used once it has 20 or more samples; otherwise it falls back to activity only, then to the population defaults.
- During learning the engine uses the conservative population default bands, and **confirm-first is widened**: any reading outside the band → CONFIRM_FIRST, and `at_patient_baseline` suppression is not allowed. The one exception is a clinician-set baseline documented in the record (e.g. a pulmonologist's note giving usual SpO2 86-90%).

**Layer 3: ONGOING ADAPTATION**
- **Rolling baseline:** a weighted median and MAD over a rolling 28-day window. |z| ≥ 3 → CONFIRM_FIRST (`baseline_deviation`); 2 ≤ |z| < 3 → WATCH (logged, no page).
- **Condition change:** a new diagnosis, a rate-control medication started or stopped (e.g. a beta-blocker), a diuretic, glucose or oxygen change, a hospitalization, or hospice enrollment. It partially resets the affected vitals (old samples keep weight 0.1) and re-enters a **shortened learning period** of 4 days. While relearning, a value inside the population band is NORMAL even if it is far from the old baseline (e.g. HR 60 after starting metoprolol, from a baseline of 78). A value outside the band still confirms first. Validated constraint: relearn_days > retain_weight × window, so the new data outweigh the old.
- **Drift guard:** a slow monotonic drift toward abnormal must NOT be absorbed as the new normal. The guard looks at daily rest medians over 21 days. It fires when Kendall τ ≥ 0.6 in the abnormal direction and the total change is at least the minimum (HR +8, SpO2 −3, RR +3, SBP ±15, glucose +30, temperature +0.5). When it fires:
  - the case is flagged **SUBTLE_DETERIORATION_TREND** and routed for review (`provider_task`, or higher if a trigger applies)
  - learning of that vital is frozen
  - samples from the window start onward are excluded from the baseline
  - only a named human can clear the flag

  A drift that starts within 14 days of a matching condition change is logged as `DRIFT_EXPLAINED` and not flagged.
- **Bounds and logging:** learned medians are clamped inside `learn_bounds`, which nest inside the hard limits; each clamp is logged `BOUND_CLAMP`. Every reset, drift flag, freeze, clamp, clearance and non-normal decision is appended to the baseline log.

**Case fields (GEN v2.3 / GRADER v1.3)**
- Fact (allowed in router_input): `baseline_status` = `{"phase": "learning|established|relearning", "monitoring_day": int, "learning_days_total": int, "last_condition_change": {"type": "...", "day": int} | null}`.
- Answer: `baseline_layer` ∈ null | `hard_limit_artifact` | `hard_limit_danger` | `learning_period` | `baseline_reset` | `drift_not_absorbed`. v1.5: `hard_limit_*` labels do not require `baseline_status` (hard limits are phase-independent); the other layers do.
- New tier **ARTIFACT**: rule `HT_VS_IMPLAUSIBLE`, route `silent_log` (or `provider_task` for repeated artifacts needing a device check), confirm_step `device_recheck` or `fingertip_recheck` with a timeout, suppression_reason null. `HT_VS_DANGER` is ABSOLUTE.
- `learning_period` cases are never SUPPRESSED `at_patient_baseline` unless a clinician-set baseline is documented. `drift_not_absorbed` cases have `subtle_deterioration: true` and are never `silent_log`. `baseline_reset` cases have a non-null `baseline_status.last_condition_change`.
- Scoring: a missed drift (routed `silent_log`) or a learned-away drift counts as a subtle-deterioration miss. An ARTIFACT that pages is a false page.

## 7. Chest pain with a vital-sign change: banded, context-modified (v1.2)
A flat CONFIRM_FIRST with a 10-minute timeout was rejected. `HT_CHEST_PAIN_VITALS` is evaluated with `evaluate_chest_pain()` in `trigger_engine/trigger_eval.py`, using `trigger_params.json` → `chest_pain`. **All values are placeholders.**

**Order:**
1. Hard limits: an implausible or poor-contact vital → recheck. A reliable danger value (HT_VS_DANGER) → ABSOLUTE.
2. A reliable ECG change → ABSOLUTE (HT_CHEST_PAIN_ECG).
3. Each reliable vital gets a band.
4. Side-specific context modifiers.
5. Symptom modifiers.
6. Safety floors.
7. Output.

| vital (chest pain present) | band A → ABSOLUTE | band B → CONFIRM_FIRST 5 min | band C → CONFIRM_FIRST 15 min |
|---|---|---|---|
| hr | ≥130 / ≤40 | ≥110 / ≤47 | ≥100 / ≤54 |
| sbp | ≥180 / ≤90 | ≥170 / ≤99 | ≥160 / ≤104 |
| spo2 | ≤88 | ≤91 | ≤93 |
| rr | ≥30 / ≤8 | ≥25 | ≥21 |
| none of the above | | | band D → LOG_ONLY (nurse_task) |

**Modifiers** (−1 = one band less severe, +1 = more severe):
| modifier | effect |
|---|---|
| sleep | HR-low −1, RR-low −1 |
| post-exertion (≤ 20 min) | HR/RR/SBP-high −1, **timeout ×2** |
| rate-control med (beta-blocker, non-DHP CCB, digoxin) | HR-low −1, **HR-high +1** (tachycardia despite rate control) |
| pacemaker | HR at the programmed lower rate (±2) is not banded; HR below the lower rate +1 |
| known brady (documented usual range) | HR-low −1 |
| known tachy (e.g. rate-controlled AF, within max +10) | HR-high −1 |
| device reliability | a quality-flagged or implausible vital is not banded → CONFIRM_FIRST `device_recheck+patient_call`, 5 min, unless the reliable inputs already give band A |
| red flags (diaphoresis, radiation, dyspnoea, syncope/presyncope, persistent ≥ 15 min, crescendo pattern, pallor) | +1 each, max +2 |
| ≥ 2 vitals at band B or worse | +1 |
| symptom–vital concordance | concordant +1; discordant −1 (only lowers B/C, never A) |

- **Order of operations (v1.5, DECIDED RULE, Wayne 2026-10-17, ST4-002): net all modifiers first, then clamp.** Band each vital and add that vital's context shifts (sleep, exertion, rate-control, pacemaker, known range) WITHOUT clamping. Take the worst net of the banded vitals (unbanded vitals do not contribute; none banded → band D), add multi-vital, red flags and concordance, and only then clamp once to D..A and apply the safety floors and the crescendo floor. Example: HR 50 asleep on a beta-blocker is raw C; sleep −1, rate control −1, two red flags +2 → net 0 → **band C, 15 min** (sequential clamping at D gave B, 5 min, which is replaced). A quality-flagged vital is unbanded (record band null/D) and gives `device_recheck+patient_call`, 5 min.
- **DECIDED RULE (Wayne, 2026-10-17): crescendo angina with normal vitals → CONFIRM_FIRST.** This is not an open question. A crescendo pattern (chest-pain episodes becoming more frequent, or new-onset exertional episodes over recent days) is `HT_CHEST_PAIN_VITALS` → `trigger_tier: CONFIRM_FIRST`, route urgent_page, even when every vital is in band D. The band is at least C (a crescendo floor that discordance or context cannot lower).
  - Confirm step: `already_confirmed` if the worsening is already confirmed in the case (patient or caregiver report, phone check). Otherwise `patient_call`, 15 min. The post-exertion ×2 does not apply when the vitals are normal.
  - A **stable** pattern (usual frequency, unchanged) with normal vitals stays band D: SUPPRESSED `below_band_threshold`, nurse_task. **No trigger escalation.**
  - Red flags and abnormal vitals still raise the band above C as usual.
**Safety:**
- Context lowers a raw band by at most 2 bands.
- Raw band A is never lowered below B; it is never log-only.
- Hard danger limits and a reliable ECG change are always ABSOLUTE.
- Goals of care still apply (hospice → hospice nurse; confirmed by Wayne).
- Timeouts are clamped to 5-60 min.
- A confirmation already in the case → CONFIRM_FIRST `already_confirmed` (escalate now).

**Labels (GEN v2.3, GRADER v1.3):**
- band A → ABSOLUTE.
- B/C → CONFIRM_FIRST with `confirm_timeout_min` = the band timeout × modifiers.
- D → SUPPRESSED with `suppression_reason: "below_band_threshold"`; route nurse_task or higher, never silent_log, and never urgent_page on the trigger alone.
- The answer field `chest_pain_eval` = `{"band", "raw_band", "modifiers", "tier", "timeout_min"}` records the computation.

## 8. CGM pressure-low ("compression low") artifact rule (v1.4, placeholders)
This applies to a **CGM** glucose reading at or below the glucose danger limit (`hard_limits.glucose.danger_low`, placeholder 54 mg/dL). Engine: `_cgm_pressure_low()` in `trigger_eval.py`. Params: `trigger_params.json` → `cgm_pressure_low`. It is evaluated before the other hard-limit checks. Steps, in order:
1. **A fingerstick within 60 min reads ≤ the danger limit → ABSOLUTE** (HT_VS_DANGER, confirmed).
2. **Hypoglycaemia symptoms** (sweaty/clammy, shaky, confused, drowsy/hard to rouse, seizure, unresponsive) **→ ABSOLUTE**, even when pressure is suspected.
3. **A fingerstick within 60 min reads above the danger limit → SUPPRESSED `unreliable_reading`.** The CGM low is not confirmed and the recheck is already done; route silent_log, or the case's clinical route for a mild low. A fingerstick that is ≥ max(15 mg/dL, 20%) above the CGM is also recorded as the `discordant_fingerstick` sign.
4. **Pressure signs with no fingerstick → ARTIFACT** (HT_VS_IMPLAUSIBLE) with `fingerstick_recheck`, 15 min, no page. Signs:
   - a pinned, pressed or compressed sensor documented **anywhere in the case** (trend, notes or data-quality flags; this is not limited to the sentence with the reading)
   - an overnight low while sleeping on the sensor side
   - a rapid drop and rebound
5. Otherwise the danger value stands → ABSOLUTE.

Goals of care still apply (comfort-only → hospice nurse). Fingerstick readings themselves are never treated as pressure artifacts.

## 9. v1.5 rulings (Wayne, review queue of 13 cases, 2026-10-17/18)
Engine: `trigger_eval.py`; params `trigger_params.json` 0.5-placeholder (change_log entries approved by Wayne); tests `test_rulings_v15.py`. The per-case rulings are in `clinician_rulings.csv` and each ruled case carries `clinician_ruling` with the changes and an engine re-derivation.

**a. Band math: net, then clamp** (`chest_pain.band_math.method = net_then_clamp`). See section 7. ST4-002 → band C, CONFIRM_FIRST `patient_call` 15 min. Re-running the engine on every other chest-pain input in the library changed no band or tier.

**b. Unanswered prompt + lives alone = failed confirm** (`confirm_first.unanswered_prompt`). `resolve_confirm(decision, "no_answer", params, {"lives_alone": True})` on a `patient_call` or `watch_prompt` step → page now, `confirm_step: already_confirmed`. Not living alone → wait for the timeout as before. A caregiver ping is excluded. ST2-009 → CONFIRM_FIRST `already_confirmed`, alternates `[]`.

**c. Hospice narrowing** (`goals_of_care`). Goals-of-care suppression applies to hospital-directed escalation only. An urgent, treatable, goal-consistent comfort problem keeps its tier and pages the hospice nurse now (`urgent_page`, `escalation_target: hospice_nurse`, notify `hospice_nurse_urgent_page`), not same-shift. Placeholder condition list: a danger-level low glucose that is symptomatic (artifact and unreliable lows do not count). v1.7 removed 'or recurrent within 6 h' (section 9f). A caller may also declare `comfort_treatable`. Everything else (a fall, a focal deficit, syncope, anything needing hospital treatment) stays SUPPRESSED `goals_of_care` → same-shift hospice nurse unless Wayne adds it to the list. v1.6 adds breathlessness (section 9e). GC2-003 → HT_VS_DANGER ABSOLUTE, hospice nurse now.

**d. CGM ordering confirmed.** Symptoms are checked before a fingerstick that reads above the danger limit: CGM 50 + fingerstick 58 + confusion → ABSOLUTE `hard_limit_danger_symptomatic` (NV2-015); the same data without symptoms → SUPPRESSED `unreliable_reading`.

**Fields:** `escalation_target`, `route_basis`, `secondary_triggers` (section 3). HK7-009 is the first `secondary_triggers` case: the fall is SUPPRESSED `explained` (nurse_task), plus HT_VS_BASELINE CONFIRM_FIRST `device_recheck` 10 min for possible AF with a rapid rate (HR 112 vs baseline 72), escalating if the rate stays high.

**e. v1.6 (Wayne 2026-10-18): distressing breathlessness treatable at home** is on the urgent hospice-comfort list (`goals_of_care.urgent_comfort.conditions.breathlessness_distressing_home_treatable`, params 0.6-placeholder). It applies to a respiratory trigger (SpO2 or RR; `breathlessness_vitals`) with context `breathlessness: {"distressing": true, "home_treatable": true}`: keep the tier, route `urgent_page` with `escalation_target: hospice_nurse` (urgent page now). Breathlessness that needs hospital treatment, or that is not distressing, and every non-respiratory trigger (including chest pain) stay SUPPRESSED `goals_of_care` → same-shift hospice nurse. Tests: `test_breathlessness_v16.py`. Relabelled: HK1-007, NV6-010 (rulings added to `clinician_rulings.csv`).

**f. v1.7 (Wayne 2026-10-18, check 4): hospice lows — symptoms only.** Only a SYMPTOMATIC danger-level low pages the hospice nurse urgently (`urgent_page`, `escalation_target: hospice_nurse`). A recurrence within 6 h WITHOUT symptoms goes back to SUPPRESSED `goals_of_care` with a same-shift hospice nurse contact (notify `hospice_nurse_same_shift`). Params 0.7-placeholder: `goals_of_care.urgent_comfort.conditions.hypoglycemia_recurrent = false` (the engine check is kept behind the flag; `recurrent_window_h` 6 is kept). Tests: `test_rulings_v15.py::test_v17_recurrent_low_without_symptoms_is_suppressed_same_shift`. Library impact: none — GC2-003 rests on its symptomatic 03:40 low (`goals_basis hypoglycemia_symptomatic`) and keeps urgent_page / hospice nurse; no other library case used the recurrence basis.

**g. v1.7: clinician override of the engine tier** (`clinician_override`, answer field). When the clinical owner rules a label tier that differs from the engine, the engine is not changed; the label carries `clinician_override {engine_tier, engine_band (chest pain), label_tier, approved_by, date, reason}`. grade_merge accepts the tier mismatch only when `engine_tier` equals the engine-implied tier and `label_tier` equals `trigger_tier`, with a named human approver; convert_casegen surfaces it (runner field `clinician_override`, note `CLINICIAN_OVERRIDE engine X -> label Y`) and summary.json lists it. Scoring: the route is unchanged, so routing is scored as usual; tier scoring uses the label tier and reports the engine tier beside it. First use: ST1-010 (engine band A / ABSOLUTE → label CONFIRM_FIRST, `patient_call`, 5 min = band-B timeout, the shortest CONFIRM_FIRST chest-pain timeout; no post-exertion factor because symptoms are ongoing; route urgent_page).

**h. v1.8 (Wayne 2026-10-18): learning-period rule formalised.** During the onboarding/learning period (`baseline_status.phase` learning or relearning, no learned own baseline), a reading beyond the population default band, or an SpO2 below the population threshold, is CONFIRM_FIRST with `route urgent_page` (paged on confirmation or timeout). It is **never silent** and never SUPPRESSED `at_patient_baseline`, unless a clinician has set the baseline. Danger limits stay ABSOLUTE in every phase. Params 0.8-placeholder: `learning.outside_population_default_tier = "CONFIRM_FIRST"`; `validate_params` rejects any non-paging value. Tests: `trigger_engine/test_learning_v18.py`. Library labels are unchanged: ST3-001, the case that prompted the rule, was already labelled CONFIRM_FIRST `fingertip_recheck`. For the Jev prompt (v1.8), the `baseline_status` fact is shown as a one-line monitoring status, and the policy summary states the learning-period and crescendo rules.

## 10. Layer 1 hardening list (v1.9, open)
- Wording recognition gaps from holdout_v1 (e.g. "loss of tone" for syncope in HO7-017, where Layer 1 finds no trigger and only the models page; HO1-006, HO1-011, HO8-009).
- (Removed 2026-10-21: an HO8-025 hospice-suppression note. Re-checked on the full case record, Layer 1 already tiers HO8-025 ABSOLUTE `HT_VS_DANGER` with an urgent page.)

## 11. v1.10 Layer 1 fixes (Wayne 2026-10-21; params `layer1_v110`, params version 0.10-placeholder)
Driven by Wayne's holdout_v1 review-queue rulings; developed on hand-written practice cases (`jev_baseline/test_layer1_v110.py`) and library (dev) cases, not on holdout text.
1. **Artifact cleared by a clean repeat.** An abnormal SpO2 followed within 15 min by a clean reading (≥ 92%, no flag; other finger/hand, second device or repeat), or a CGM low with a fingerstick in the normal range (≥ 70 mg/dL) within 60 min, with no symptoms → SUPPRESSED `cleared_by_repeat`, route `silent_log` (Layer 1 owns it). An engine ARTIFACT (implausible value, non-physiologic rate) stays ARTIFACT. A confirming low fingerstick is not a clean repeat.
   **Exception:** an insulin user with CKD and a danger-level low (CGM or meter ≤ danger limit) is always sent to HITM review (`hitm_required`, a hard flag regardless of the models), route at least `nurse_task`.
2. **Suppressed fallback derived per rule** (`suppressed_default_route`): no blanket `provider_task`. explained / unreliable_reading / at_patient_baseline / below_band → `nurse_task`; ARTIFACT and cleared_by_repeat → `silent_log`. Models stay capped at `provider_task` unless acute; `route_floor` sets minimums.
3. **Falls on an anticoagulant.** Confirmed fall (witnessed or reported) → ABSOLUTE, `urgent_page`. An unwitnessed possible fall (impact signal, watch found on the floor) cleared by a caregiver check → SUPPRESSED `explained_caregiver_check`, `nurse_task` (nurse confirms with the patient there was no fall). A watch on the floor is not a confirmed fall.
4. **Known low-baseline SpO2** (COPD etc.): a documented usual/baseline SpO2 in pmh/notes counts as the patient's own baseline; a reading at that baseline is SUPPRESSED `at_patient_baseline`, route floor `nurse_task`, not a CONFIRM_FIRST page. A drop below the own baseline still confirms.
5. **Wording.** Synonym lists (`layer1_v110.wording`) extend syncope (loss of tone, collapsed, slumped, unresponsive briefly, passed out…), focal neuro (face drooping, arm drift, trouble speaking, jumbled words…) and chest pain (crushing, pressure on the chest, band around the chest…). New rule `HT_BRADY_RATE_DRUG`: resting HR < 45 on a rate-slowing drug (amiodarone, digoxin, beta-blocker, non-DHP CCB, ivabradine…) **with symptoms** → CONFIRM_FIRST `patient_call`; asymptomatic → no Layer 1 decision (a new rule never caps a route).
6. **Gap contact.** Scale weigh-ins, syncs and uploads are not contact for `HT_GAP48_HIGHRISK`; only person-to-person contact inside the gap explains it.
Label note: library/holdout labels written before v1.10 tier confirmed anticoagulant falls CONFIRM_FIRST; Layer 1 now says ABSOLUTE (same route, `urgent_page`), which lowers tier agreement without changing routing.

