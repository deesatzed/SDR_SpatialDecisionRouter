# Rule governance: settings, FOUNDATION profiles, patient overrides — design (NOT implemented)

Status: draft for Wayne, 2026-10-23. SYNTHETIC examples only. Supersedes the precedence section of `PATIENT_OVERRIDES_DESIGN.md`
(that doc remains the spec for per-patient overrides on non-foundation rules). Values quoted from `trigger_engine/trigger_params.json`
(v0.10.1-placeholder) are themselves **placeholders** until clinically signed off; anything new here is marked `<placeholder>`.

## 1. Vocabulary
- **FOUNDATION rule** (was ABSOLUTE): a rule whose threshold and route are fixed *for a setting*, not universally. Patients and
  per-patient overrides cannot change them. Only a setting change for the patient, or a team-approved profile version, can.
- **Non-foundation rule**: CONFIRM_FIRST, SUPPRESSED/ARTIFACT logic, model-routed findings. Adjustable per patient (shared decision-making).
- **Setting**: where and how care is delivered, with one foundation profile. Examples: `facility_x/independent_living`,
  `facility_x/assisted_living`, `facility_x/snf`, `hospice/home`, and a single-household install `household/tier_2`.
  A single home is still a setting, assigned to a **household tier** by ADL capability × illness severity / care intensity.
- **Safety floor**: a system-wide minimum that no profile or override can go below (proposed; see open questions).

## 2. Setting inheritance
```
base (system defaults = today's SMART_TRIGGERS)        ← maintained by the product team
 └─ home_community (default profile, section 5)
     ├─ household/tier_1 … tier_4                       ← single-household installs
     └─ facility_x (site contacts, on-call routing)
         ├─ facility_x/independent_living
         ├─ facility_x/assisted_living
         ├─ facility_x/snf
         └─ facility_x/hospice
```
A child profile lists only what it changes (`extends:` + deltas). Resolution = deep merge, child wins, every key keeps the
source profile+version it came from (shown in the audit and the diff view). A child cannot delete a rule; it may set
`enabled: false` only with a `rationale` and reviewer sign-off.

**Household tiers** (grid; names/cut-points are `<placeholder>` for Wayne):

| Tier | ADL capability | Illness severity / care intensity |
|---|---|---|
| 1 | independent | stable, low intensity |
| 2 | needs help with some ADLs | moderate, recent change or multimorbidity |
| 3 | dependent for most ADLs | high, recent discharge / HF / insulin+CKD |
| 4 | — | comfort-focused / hospice at home (or use `hospice/home`) |

**Patient assignment**: at enrolment the provider (or care manager) picks setting + tier from a short checklist (residence type,
ADL items, program, goals of care). Stored as `{patient_id, setting_id, tier, assigned_by, assigned_on, review_by}`.
A change of setting (e.g. move to AL, hospice election) is a new assignment, logged, and takes effect on the next evaluation;
the profile version in force is pinned per assignment. Missing/expired assignment → evaluate with `home_community` and raise a
nurse_task "confirm setting".

## 3. Profile file format (YAML, one file per setting, in git)
```yaml
profile_id: facility_x/assisted_living
extends: home_community@1.0.0          # pinned parent version
version: 1.1.0                          # semver; any threshold/route change = minor; rule add/remove = major
status: draft | in_review | approved | live | retired
owner: sysadmin:<id>
effective_from: YYYY-MM-DD
rereview_by: YYYY-MM-DD                  # scheduled re-review, interval <placeholder>
escalation_targets: {urgent_page: on_site_nurse, provider_task: facility_physician, nurse_task: unit_nurse}
foundation_rules:
  HT_VS_DANGER:
    spo2: {danger_low: 80, unit: "%"}    # value inherited unless changed; shown here only if changed
    route: urgent_page
    rationale: "..."
    evidence: ["source / guideline / team decision ref"]
  HT_FALL_ANTICOAG:
    confirmed_tier: FOUNDATION
    route: urgent_page
    rationale: "..."
non_foundation_defaults: { ... }         # starting values that patient overrides may adjust
changelog:
  - {version: 1.1.0, date: YYYY-MM-DD, by: <id>, summary: "...", reviewers: [<ids>]}
```
Validation (CI): schema check; every changed key has `rationale` + `evidence`; no unknown rule ids; no value crosses a safety floor;
`extends` resolves to an approved version; diff vs previous version rendered for review.

## 4. Governance workflow
1. **Draft** — sysadmin edits the YAML on a branch (or via a form that writes YAML).
2. **Team review** — named reviewers per setting (e.g. medical lead, nursing lead, pharmacist for med rules; roster is a question
   for Wayne). Review screen shows the merged profile, the diff vs live, and replay results (step 5). Each reviewer signs off or
   requests changes; quorum `<placeholder>` (proposed: all named clinical reviewers).
3. **Replay check** — run the candidate profile over the practice library + paired setting cases (never holdout text) and show
   route changes vs the live profile.
4. **Go-live** — on approval, status `live`, tagged version, `effective_from`; patients pick it up unless pinned.
5. **Scheduled re-review** by `rereview_by`; also triggered by a SMART_TRIGGERS release, an incident, or a reviewer request.
   Overdue → stays live but a nurse/admin task is raised and the dashboard shows "overdue".
6. **Rollback** — re-pin the previous approved version (no edit needed); logged.
Change log, diff view and sign-offs are retained for every version; nothing is edited in place after approval.

## 5. Layer 1 evaluation order
1. **Resolve profile**: patient → setting/tier assignment → merged foundation profile (pinned version).
2. **Evaluate rules** with that profile's thresholds/routes (FOUNDATION and non-foundation), plus artifact/repeat logic as today.
3. **Apply patient overrides** — only to non-foundation rules (`PATIENT_OVERRIDES_DESIGN.md`: threshold, variance range, route
   change, suppression with `min_route`, carve-backs, expiry). An override naming a foundation rule is rejected at entry.
4. **Apply safety floors** (proposed, system-wide, last word):
   - insulin or sulfonylurea user with CKD + danger-level low → hard HITM flag, route ≥ nurse_task (current v1.10.1 rule);
   - a fired FOUNDATION rule can never end at `silent_log` (no-silent floor).
5. **Models** (Jev dual, `cautious_max_hitm`) get the profile id/version, the patient's active overrides and the Layer 1 result as a
   structured block; they may route up; Layer 1 clamps anything below the floor/override minimum. Fly flags only.
6. **Audit** every evaluation: profile@version, assignment, overrides applied/rejected, floors applied, final route, HITM.

## 6. Default profile `home_community` (from SMART_TRIGGERS v1.10.1 ABSOLUTE rules)
Values are the current `trigger_params.json` values (file version `0.10.1-placeholder`, so all are placeholders pending sign-off).

| Rule id | Fires when (current logic) | Current values | Route |
|---|---|---|---|
| HT_VS_DANGER | reliable reading beyond danger limit (implausible → ARTIFACT) | HR <35 / >180; SpO2 <80; RR <6 / >35; SBP <80 / >200; glucose <54 / >400 mg/dL; temp <35.0 / >40.0 °C | urgent_page |
| HT_VS_DANGER (glucose sub-cases) | fingerstick-confirmed or symptomatic danger low | as above + CGM pressure-low rule (`cgm_pressure_low`, placeholders) | urgent_page |
| HT_SYNCOPE | syncope wording (synonym list), not near-faint | — | urgent_page |
| HT_FOCAL_NEURO | new focal deficit (not documented baseline) | — | urgent_page |
| HT_CHEST_PAIN_ECG | reliable ECG change with chest pain | — | urgent_page |
| HT_CHEST_PAIN_VITALS | chest pain, band A | band cut-points in `chest_pain` (all placeholders) | urgent_page |
| HT_FALL_ANTICOAG | confirmed (witnessed/reported) fall on anticoagulant | `confirmed_tier` | urgent_page |
| learning outside-population default | beyond population defaults during learning, if configured ABSOLUTE | `learning.outside_population_default_tier` (CONFIRM_FIRST or ABSOLUTE) | urgent_page if ABSOLUTE |

Not foundation in v1.10.1 (stay per-patient adjustable): HT_SPO2_LT88, HT_BRADY_RATE_DRUG, HT_GAP48_HIGHRISK, CONFIRM_FIRST chest
bands, artifact/repeat clearing, documented-low-baseline suppression. Queued v1.10.2 fall fixes would modify HT_FALL_ANTICOAG
(foundation) and therefore need profile review once implemented.
Today's `goals_of_care` comfort-only logic (`apply_goals_of_care`) moves out of the global engine into the hospice profile.

## 7. Hospice cases: setting profile vs patient override
`hospice/home` (extends home_community; values `<placeholder>`): escalation_targets.urgent_page = hospice_nurse (never 911/ED);
FOUNDATION rules whose action is hospital-directed (HT_FOCAL_NEURO, HT_CHEST_PAIN_*, HT_SYNCOPE, HT_FALL_ANTICOAG) route
nurse_task (same-shift hospice nurse) with trigger logged; treatable-at-home danger (glucose danger low) stays urgent_page to hospice nurse.

| Case | Handled by | Result |
|---|---|---|
| HO8-025 hospice, insulin, danger low | profile: HT_VS_DANGER glucose → urgent_page hospice_nurse; floor (insulin+CKD if present) | urgent_page (hospice nurse) |
| HV6-002 hospice, low 45 treated by spouse | profile: same as HO8-025 | urgent_page (hospice nurse) |
| HV2-002 hospice, apixaban, new stroke signs | profile: HT_FOCAL_NEURO → nurse_task, logged (no patient override needed) | nurse_task |
| HV6-001 hospice COPD, confirmed SpO2 86% | profile does not cover (86 is above the danger limit 80; HT_SPO2_LT88 is non-foundation) → **patient override**: variance range at documented baseline `<placeholder>` + goals-of-care suppression, min_route nurse_task | nurse_task |
| HV10-002 hospice, digoxin, HR ~41, grey/drowsy | no foundation rule fires (HR 41 > danger 35); HT_BRADY_RATE_DRUG is non-foundation → **patient override** route_change → nurse_task, carve-back e.g. unresponsive | nurse_task |

Pattern: the setting decides *who is called and whether hospital-directed escalation applies*; the patient plan tunes
non-foundation thresholds to that person's documented baseline and wishes.

## 8. Test plan (design-level; practice cases only)
- Profile merge/inheritance unit tests (child wins, provenance kept, pinned versions, no deletion without sign-off).
- Validation tests: override on a foundation rule rejected; profile crossing a floor rejected; missing rationale/evidence rejected.
- Equivalence: `home_community` profile + no overrides must reproduce v1.10.1 scores on library_v2 and holdout_v1/v2 ruled keys.
- Paired practice cases across settings (IL vs AL vs hospice vs household tiers) — same event, intended route differences only.
- Replay report as the review artifact in step 3 of the workflow.

## 9. Open questions for Wayne
1. Are the two system-wide floors right (insulin/sulfonylurea + CKD danger low → hard HITM ≥ nurse_task; no-silent for a fired
   FOUNDATION rule)? Any others (e.g. "urgent_page can never become silent")? Can a hospice profile override them?
2. Which current ABSOLUTE rules should be FOUNDATION in every setting, and should any non-foundation rule (HT_SPO2_LT88,
   HT_BRADY_RATE_DRUG) be promotable to foundation per setting?
3. Household tiers: how many, which ADL items and severity criteria define them; who assigns and how often re-assessed?
4. Reviewer roster and quorum per setting; can one person be both author and reviewer at a small install?
5. Re-review interval for profiles and for patient assignments; what happens when overdue (stay live vs fall back)?
6. Hospice profile: should HT_SYNCOPE and HT_FALL_ANTICOAG be nurse_task or urgent hospice-nurse page? (HV3-010/HV5-002 rulings
   were full-care.)
7. Evidence field: what counts (guideline citation, team decision record, local policy)? Required for every change?
8. Who owns the base profile across installs, and may a site pin an older base indefinitely?
9. Patient-override questions carried from PATIENT_OVERRIDES_DESIGN.md: who may attest, review_by limits, family/patient
   disagreement, family visibility.

## 10. Layer 1 v1.11.0 changes (2026-10-23, trigger_params 0.11.0-placeholder; all numbers are PLACEHOLDERS pending clinical sign-off)

- **Drug-low hard floor (`HT_DRUG_LOW`, FOUNDATION).** A low glucose (<= `glucose_confirm_max` 54, placeholder) on a glucose-lowering drug (insulin / sulfonylurea / meglitinide) with symptoms (sweaty, clammy, confused, only responding to name ...) is a foundation rule: ABSOLUTE, urgent page, never suppressed by goals of care, CKD or a caregiver explanation. Foundation candidates win rank ties (`_rank` +0.5). In hospice the page goes to the hospice nurse (`escalation_target`), it is not dropped. Asymptomatic, recovered lows on CKD become a provider dose-review task (`ckd_low_dose_review`), not a nurse visit; a second danger low within `prior_low_days` (7, placeholder) becomes `repeated_lows_dose_review` (provider). A CKD low with documented sensor compression keeps the nurse floor (v1.10 behavior).
- **Device-ticket track.** Two devices that disagree on the same vital (SpO2 by > 2 points wrist vs finger, HR by > 10 bpm, rhythm disagreement; placeholders) produce a non-interruptive `device_ticket` (types: device_maintenance, supply_reference_oximeter_and_baseline, ecg_strip_request) routed to the device-maintenance process, and the clinical route is silent_log. **"Could change care" exception:** when the disagreement could change care (e.g. HR disagreement after a rate-drug change), the clinical route is floored at nurse_task (manual pulse) and the ticket is still filed.
- **Plain reasons.** Every Layer 1 decision carries `plain_reason`: one short sentence for the receiver (template table `PLAIN`, keyed rule:reason, then reason, then rule). `route_reason()` returns it whenever Layer 1 owns the route. On holdout_v3 40/40 Layer 1 decisions have a templated reason.
- **Conditional rulings.** A clinician ruling can be conditional ("provider_task unless X, then urgent"). The key stores the base route plus the condition in `clinician_note`; scoring uses the base route. Rules that would encode the condition (e.g. `serotonergic_confusion`, HW6-011's ruling) ship **disabled** (`enabled: false`) until confirmed on practice cases.
- **Other fixes:** BP cuff clean-repeat (repeat within 15 min with SBP 90-180 clears a single cuff reading; placeholders), witnessed-fall wording (watched/saw lose footing), head strike = confirmed fall, the impact-cap is bypassed for long inactivity (>= 30 min placeholder) or living alone with dementia.
- **Earlier keys that now conflict with the drug-low / dose-review direction:** holdout_v1 HO2-007, holdout_v2 HV3-004 and HV3-005 (labelled nurse_task, v1.11.0 routes provider_task dose review). Need re-ruling.

## 11. Layer 1 v1.11.1 (2026-10-23, params 0.11.1-placeholder; placeholders)

- **Explained CKD lows.** These rules cover a drug-related (insulin or sulfonylurea) danger-level CKD low with a normal recheck and no symptoms:
  - If sensor compression explains it (a witness account or an artifact flag), the route is `ckd_low_compression_explained`, nurse_task. The plain reason is "check sensor placement and confirm no symptoms". This replaces the v1.11.0 compromise.
  - If recent exertion explains it, the route is `ckd_low_exertion_explained`, nurse_task, for exercise-precaution teaching. A repeat danger low within 7 days goes to `repeated_lows_dose_review`, provider_task.
  - The provider dose review (`ckd_low_dose_review`) now applies only to unexplained lows, or to repeated lows that are unexplained or exertion-explained. Repeated lows explained by compression stay nurse_task; this is pending Wayne's confirmation (holdout_v1 HO3-004).
- **72 h glucose-low lookback (placeholder).** A recovered, asymptomatic drug-related CKD low from Day -3 to Day -2 gives `recent_ckd_low_dose_review`, provider_task.
- **Explained high-risk gap.** A gap can be explained by a contact whose "looked fine / well" detail sits in the next sentence. An explained gap is SUPPRESSED with a nurse_task floor and never pages.
