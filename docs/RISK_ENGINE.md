# Bayesian risk sidecar (risk_engine/) — SYNTHETIC, PLACEHOLDER PARAMETERS

**Every number in `risk_engine/params.yaml` is `source: placeholder`.** None is clinically validated. The UI shows categorical labels (very unlikely <5% · unlikely 5–20% · possible 20–50% · likely >50%), the param source, and an engine badge (`BN · params: placeholder` vs `fallback`). Treat the digits as illustrative only.

## Run
```bash
risk_engine/run_sidecar.sh            # creates risk_engine/.venv on first run; serves 127.0.0.1:8765 (RISK_PORT to change)
cd risk_engine && .venv/bin/python -m pytest -q
```
The visionOS app calls `POST /assess` with a 0.8 s timeout. It does so for each new encounter and after every ask-next or re-rating. If the sidecar is unreachable or the complaint has no network, the app uses the Swift heuristics: the badge shows `fallback` and `-noSidecar` forces it. The app needs `NSAllowsLocalNetworking` (set in project.yml).

## Model
Each complaint has its own discrete BN, solved by exact inference (pyAgrum 3.2.1 LazyPropagation). Complaints:
- ED: `abdominal_pain`, `chest_pain`, `head_injury`, `infection_abx` (cough/fever and urinary symptoms).
- Outpatient AI-doc requests (v2): `uri_abx`, `med_refill`, `glp1_weight`, `hrt_menopause`, `testosterone`, `erectile_dysfunction`.

**Nodes**
- **Context roots:** `ctx_companion`, `ctx_interpreter`, `ctx_adolescent`, `ctx_low_literacy`, `ctx_elderly_alone`. Plan flags: `plan_qt_drug`, `plan_teratogen`.
- **Hidden truths (ED):** `pregnant`, `qt_med` (methadone and other QT-prolonging meds), `anticoag`, `substance` (none/alcohol/cocaine/opioid), `unsafe_home`, `minimized` (symptom severity understated).
- **Hidden truths (outpatient):**
  - URI: `pcn_allergy`, `airway_red_flag`
  - refill: `nonadherent`, `overdue_monitoring`, `controlled_misuse`, `new_interaction`, `masked_symptom`
  - GLP-1: `mtc_men2`, `pancreatitis_hx`, `gallbladder`, `eating_disorder`, `hypoglycemic_meds`, `inflated_bmi`
  - HRT: `hormone_cancer`, `vte_stroke_hx`, `smoker`, `unexplained_bleeding`, `migraine_aura`, `liver_disease`, `late_start`
  - testosterone: `fertility_desire`, `high_hct`, `untreated_osa`, `prostate_issue`, `cv_risk_high`, `not_confirmed_low`
  - PDE5: `nitrate_use`, `exertional_cp`, `alpha_blocker`, `recreational_drugs`
  - `pregnant` and `qt_med` are shared.
- **`<truth>__rep`** (neg/pos): parents are the truth plus the relevant context nodes.
  - If the truth is risky: P(neg) = noisy-OR(concealment, recall).
    - concealment = noisy-OR(conceal_base, conceal_context increments for active context)
    - recall = noisy-OR(recall_miss, recall_context increments)
  - If the truth is benign: P(pos) = false_positive.
- **`<truth>__hedge` / `<truth>__record`:** consistency signals (transcript hedging; pharmacy/PDMP/PMH record).
- **`<truth>__ask`:** the answer to a direct physician question (reveal / false_positive).
- **`dx_*`:** key diagnoses and plan-risk events, with explicit CPT rows in the file:
  - ectopic, pancreatitis, surgical_abdomen, teratogen_exposure, ipv_injury
  - acs, qt_event, ich, sepsis
- **`critical`:** deterministic OR of dx with severity ≥ `critical_severity`.
- **`critical_esc`:** the same, restricted to critical dx that a plan change (`modify`) cannot mitigate. It drives the escalation recommendation, so a disclosed nitrate leads to *decline*, not *escalate*.
- **Per-complaint `modify_cost`:** overrides `loss.modify_cost` (the cost of declining or conditioning an appropriate request). This is what makes asking worthwhile before declining.

## Outputs (`POST /assess`)
- **Per truth:**
  - `posterior` and `label`
  - `state` (one of 4), derived from the posterior vs the report:
    - no report → **Not said**
    - positive report or answer → **Reliable**
    - negative report with posterior < `doubt_posterior` → **Reliable**. For truths with a critical child dx, `doubt_posterior_critical` is used instead (stakes-aware).
    - otherwise, if the topic is sensitive and concealment ≥ recall in this context → **Said differently on purpose**; else **Said wrong**
  - `if_wrong`: the worst-case dx (max severity × high) with `current`, `low` = P(dx | evidence, truth benign) and `high` = max over risky states of P(dx | evidence, truth = state). Also `worst_miss`, `plan_change`, and labels.
- **Overall:**
  - `dx`, `p_critical`
  - `expected_loss` for sign_off / modify / escalate. Loss = Σ P(dx)·miss_cost[severity], times `residual_after_mitigation` if the action mitigates that dx, plus the action cost.
  - `best_action`
- **`voi[]`:** true VOI = EL(best action now) − E_answer[EL(best action | answer)]. Each entry also has `p_answer_pos` and `p_ruleout` = P(the answer drives P(critical) below `critical_escalate`).
- **`escalation.recommend`** = P(critical_esc) > `critical_escalate` AND max `p_ruleout` < `min_ruleout`. Also reported: `p_critical_needs_escalation`.

Other endpoints:
- `POST /voi`: the VOI, escalation and loss subset.
- `POST /sample` `{complaint, n, seed}`: seeded forward-sampled synthetic encounters (reproducible).
- `GET /health`, `GET /params` (the markdown table).

### Request schema (`/assess`, `/voi`)
```json
{"complaint": "abdominal_pain|chest_pain|head_injury|infection_abx|uri_abx|med_refill|glp1_weight|hrt_menopause|testosterone|erectile_dysfunction",
 "context": {"companion": bool, "interpreter": bool, "adolescent": bool, "low_literacy": bool, "elderly_alone": bool},
 "plan_flags": {"plan_qt_drug": bool, "plan_teratogen": bool},
 "reports": {"<truth>": null | "neg" | "pos" | "<risky state, e.g. yes / cocaine>"},   // a risky state fixes the truth (disclosed)
 "signals": {"<truth>": {"hedge": bool, "record": bool}},
 "answers": {"<truth>": "neg" | "pos"},
 "known": {"<truth>": "<state>"},
 "encounter_id": "optional"}
```
Unknown keys, unknown truths/context for the complaint, non-boolean flags, and bad report values return HTTP 400.

## Tests (pytest, 35)
- **Hand-computed reference values on a 1-truth network:** prior marginals; negative-report posterior with and without a companion (0.1·0.335/(0.1·0.335+0.9·0.99) etc.); if-wrong range; VOI by explicit arithmetic; posterior after an answer; escalation rule; known truth.
- **Invalid parameter rejection:** probability >1, literature without a citation, placeholder with a citation, unknown source, incomplete CPT, bad parent, negative cost.
- **Invalid request rejection:** 7 cases.
- **Reproducibility:** same seed gives the same samples; different seed differs; frequency matches the prior within 0.01 at n=20000; assess is deterministic.
- **Shipped file:** all entries are placeholder and all complaints run.
- **HTTP service:** 200 responses, plus 400 on bad input.
- **Outpatient presentations (qualitative):**
  - disclosed nitrate gives *likely* hard-stop dx and no sign-off
  - a hidden nitrate with a record mismatch is not Reliable; if-wrong is nitrate_hypotension; the answer gives a posterior > 0.9
  - URI with hidden methadone flags qt_event
  - testosterone with fertility desire leads to modify
  - a GLP-1 hedge raises the MTC posterior
  - escalation ignores risk that a plan change fixes
  - stakes-aware doubt threshold

## Parameter table for Wayne's review

| parameter | value | source | citation | note |
|---|---|---|---|---|
| `thresholds.doubt_posterior` | 0.15 | placeholder |  | posterior P(risky) at/above which a negative report is not Reliable |
| `thresholds.doubt_posterior_critical` | 0.05 | placeholder |  | lower doubt threshold for truths that can cause a critical miss (stakes-aware reliability) |
| `thresholds.critical_severity` | 4 | placeholder |  | dx severity >= this counts as critical miss (integer 1-5) |
| `thresholds.critical_escalate` | 0.05 | placeholder |  | P(critical miss under sign-off) above which escalation is considered |
| `thresholds.min_ruleout` | 0.5 | placeholder |  | a question 'reduces it enough' if P(answer drives P(critical) below critical_escalate) >= this |
| `context_priors.companion` | 0.3 | placeholder |  |  |
| `context_priors.interpreter` | 0.15 | placeholder |  |  |
| `context_priors.adolescent` | 0.08 | placeholder |  |  |
| `context_priors.low_literacy` | 0.2 | placeholder |  |  |
| `context_priors.elderly_alone` | 0.1 | placeholder |  |  |
| `context_priors.plan_qt_drug` | 0.4 | placeholder |  |  |
| `context_priors.plan_teratogen` | 0.3 | placeholder |  |  |
| `truths.pregnant.prior.abdominal_pain` | 0.08 | placeholder |  | F 14-50 only |
| `truths.pregnant.prior.infection_abx` | 0.05 | placeholder |  | F 14-50 only |
| `truths.pregnant.prior.uri_abx` | 0.05 | placeholder |  |  |
| `truths.pregnant.prior.glp1_weight` | 0.04 | placeholder |  |  |
| `truths.pregnant.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.pregnant.report.recall_miss` | 0.05 | placeholder |  |  |
| `truths.pregnant.report.conceal_base` | 0.2 | placeholder |  |  |
| `truths.pregnant.report.conceal_context.companion` | 0.3 | placeholder |  |  |
| `truths.pregnant.report.conceal_context.adolescent` | 0.35 | placeholder |  |  |
| `truths.pregnant.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.pregnant.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.pregnant.signals.hedge.p_if_true` | 0.3 | placeholder |  |  |
| `truths.pregnant.signals.hedge.p_if_false` | 0.03 | placeholder |  |  |
| `truths.pregnant.ask.reveal` | 0.75 | placeholder |  |  |
| `truths.pregnant.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.qt_med.prior.infection_abx` | 0.04 | placeholder |  |  |
| `truths.qt_med.prior.chest_pain` | 0.03 | placeholder |  |  |
| `truths.qt_med.prior.uri_abx` | 0.04 | placeholder |  |  |
| `truths.qt_med.prior.erectile_dysfunction` | 0.02 | placeholder |  |  |
| `truths.qt_med.report.false_positive` | 0.005 | placeholder |  |  |
| `truths.qt_med.report.recall_miss` | 0.1 | placeholder |  |  |
| `truths.qt_med.report.conceal_base` | 0.3 | placeholder |  |  |
| `truths.qt_med.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.qt_med.report.recall_context.elderly_alone` | 0.2 | placeholder |  |  |
| `truths.qt_med.report.recall_context.low_literacy` | 0.15 | placeholder |  |  |
| `truths.qt_med.report.recall_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.qt_med.signals.record.p_if_true` | 0.5 | placeholder |  | pharmacy/PDMP record |
| `truths.qt_med.signals.record.p_if_false` | 0.01 | placeholder |  |  |
| `truths.qt_med.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.qt_med.ask.false_positive` | 0.005 | placeholder |  |  |
| `truths.anticoag.prior.head_injury` | 0.15 | placeholder |  |  |
| `truths.anticoag.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.anticoag.report.recall_miss` | 0.1 | placeholder |  |  |
| `truths.anticoag.report.conceal_base` | 0.0 | placeholder |  |  |
| `truths.anticoag.report.recall_context.elderly_alone` | 0.25 | placeholder |  |  |
| `truths.anticoag.report.recall_context.low_literacy` | 0.15 | placeholder |  |  |
| `truths.anticoag.report.recall_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.anticoag.signals.record.p_if_true` | 0.6 | placeholder |  | AFib/VTE in PMH or pharmacy record |
| `truths.anticoag.signals.record.p_if_false` | 0.05 | placeholder |  |  |
| `truths.anticoag.ask.reveal` | 0.9 | placeholder |  |  |
| `truths.anticoag.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.substance.prior.abdominal_pain.alcohol` | 0.08 | placeholder |  |  |
| `truths.substance.prior.abdominal_pain.cocaine` | 0.01 | placeholder |  |  |
| `truths.substance.prior.abdominal_pain.opioid` | 0.02 | placeholder |  |  |
| `truths.substance.prior.chest_pain.alcohol` | 0.05 | placeholder |  |  |
| `truths.substance.prior.chest_pain.cocaine` | 0.04 | placeholder |  |  |
| `truths.substance.prior.chest_pain.opioid` | 0.02 | placeholder |  |  |
| `truths.substance.prior.head_injury.alcohol` | 0.12 | placeholder |  |  |
| `truths.substance.prior.head_injury.cocaine` | 0.01 | placeholder |  |  |
| `truths.substance.prior.head_injury.opioid` | 0.02 | placeholder |  |  |
| `truths.substance.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.substance.report.recall_miss` | 0.02 | placeholder |  |  |
| `truths.substance.report.conceal_base` | 0.35 | placeholder |  |  |
| `truths.substance.report.conceal_context.companion` | 0.3 | placeholder |  |  |
| `truths.substance.report.conceal_context.adolescent` | 0.3 | placeholder |  |  |
| `truths.substance.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.substance.signals.hedge.p_if_true` | 0.3 | placeholder |  |  |
| `truths.substance.signals.hedge.p_if_false` | 0.05 | placeholder |  |  |
| `truths.substance.ask.reveal` | 0.65 | placeholder |  |  |
| `truths.substance.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.unsafe_home.prior.head_injury` | 0.04 | placeholder |  |  |
| `truths.unsafe_home.prior.abdominal_pain` | 0.02 | placeholder |  |  |
| `truths.unsafe_home.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.unsafe_home.report.recall_miss` | 0.0 | placeholder |  |  |
| `truths.unsafe_home.report.conceal_base` | 0.4 | placeholder |  |  |
| `truths.unsafe_home.report.conceal_context.companion` | 0.5 | placeholder |  |  |
| `truths.unsafe_home.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.unsafe_home.signals.hedge.p_if_true` | 0.4 | placeholder |  | partner answers for patient / hesitation |
| `truths.unsafe_home.signals.hedge.p_if_false` | 0.05 | placeholder |  |  |
| `truths.unsafe_home.ask.reveal` | 0.6 | placeholder |  |  |
| `truths.unsafe_home.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.minimized.prior.chest_pain` | 0.15 | placeholder |  |  |
| `truths.minimized.prior.abdominal_pain` | 0.12 | placeholder |  |  |
| `truths.minimized.prior.head_injury` | 0.08 | placeholder |  |  |
| `truths.minimized.prior.infection_abx` | 0.08 | placeholder |  |  |
| `truths.minimized.report.false_positive` | 0.05 | placeholder |  |  |
| `truths.minimized.report.recall_miss` | 0.05 | placeholder |  |  |
| `truths.minimized.report.conceal_base` | 0.35 | placeholder |  |  |
| `truths.minimized.report.conceal_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.minimized.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.minimized.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.minimized.signals.hedge.p_if_true` | 0.35 | placeholder |  | 'probably nothing', stops walking |
| `truths.minimized.signals.hedge.p_if_false` | 0.08 | placeholder |  |  |
| `truths.minimized.ask.reveal` | 0.7 | placeholder |  |  |
| `truths.minimized.ask.false_positive` | 0.05 | placeholder |  |  |
| `truths.pcn_allergy.prior.uri_abx` | 0.1 | placeholder |  |  |
| `truths.pcn_allergy.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.pcn_allergy.report.recall_miss` | 0.15 | placeholder |  |  |
| `truths.pcn_allergy.report.conceal_base` | 0.02 | placeholder |  |  |
| `truths.pcn_allergy.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.pcn_allergy.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.pcn_allergy.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.pcn_allergy.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.pcn_allergy.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.pcn_allergy.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.pcn_allergy.signals.record.p_if_true` | 0.5 | placeholder |  |  |
| `truths.pcn_allergy.signals.record.p_if_false` | 0.01 | placeholder |  |  |
| `truths.airway_red_flag.prior.uri_abx` | 0.02 | placeholder |  |  |
| `truths.airway_red_flag.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.airway_red_flag.report.recall_miss` | 0.15 | placeholder |  |  |
| `truths.airway_red_flag.report.conceal_base` | 0.1 | placeholder |  |  |
| `truths.airway_red_flag.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.airway_red_flag.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.airway_red_flag.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.airway_red_flag.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.airway_red_flag.ask.reveal` | 0.9 | placeholder |  |  |
| `truths.airway_red_flag.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.airway_red_flag.signals.hedge.p_if_true` | 0.3 | placeholder |  |  |
| `truths.airway_red_flag.signals.hedge.p_if_false` | 0.03 | placeholder |  |  |
| `truths.nonadherent.prior.med_refill` | 0.3 | placeholder |  |  |
| `truths.nonadherent.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.nonadherent.report.recall_miss` | 0.08 | placeholder |  |  |
| `truths.nonadherent.report.conceal_base` | 0.35 | placeholder |  |  |
| `truths.nonadherent.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.nonadherent.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.nonadherent.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.nonadherent.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.nonadherent.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.nonadherent.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.nonadherent.signals.record.p_if_true` | 0.5 | placeholder |  |  |
| `truths.nonadherent.signals.record.p_if_false` | 0.01 | placeholder |  |  |
| `truths.overdue_monitoring.prior.med_refill` | 0.3 | placeholder |  |  |
| `truths.overdue_monitoring.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.overdue_monitoring.report.recall_miss` | 0.3 | placeholder |  |  |
| `truths.overdue_monitoring.report.conceal_base` | 0.05 | placeholder |  |  |
| `truths.overdue_monitoring.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.overdue_monitoring.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.overdue_monitoring.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.overdue_monitoring.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.overdue_monitoring.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.overdue_monitoring.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.overdue_monitoring.signals.record.p_if_true` | 0.5 | placeholder |  |  |
| `truths.overdue_monitoring.signals.record.p_if_false` | 0.01 | placeholder |  |  |
| `truths.controlled_misuse.prior.med_refill` | 0.06 | placeholder |  |  |
| `truths.controlled_misuse.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.controlled_misuse.report.recall_miss` | 0.08 | placeholder |  |  |
| `truths.controlled_misuse.report.conceal_base` | 0.5 | placeholder |  |  |
| `truths.controlled_misuse.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.controlled_misuse.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.controlled_misuse.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.controlled_misuse.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.controlled_misuse.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.controlled_misuse.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.controlled_misuse.signals.record.p_if_true` | 0.5 | placeholder |  |  |
| `truths.controlled_misuse.signals.record.p_if_false` | 0.01 | placeholder |  |  |
| `truths.new_interaction.prior.med_refill` | 0.12 | placeholder |  |  |
| `truths.new_interaction.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.new_interaction.report.recall_miss` | 0.25 | placeholder |  |  |
| `truths.new_interaction.report.conceal_base` | 0.05 | placeholder |  |  |
| `truths.new_interaction.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.new_interaction.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.new_interaction.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.new_interaction.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.new_interaction.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.new_interaction.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.masked_symptom.prior.med_refill` | 0.1 | placeholder |  |  |
| `truths.masked_symptom.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.masked_symptom.report.recall_miss` | 0.08 | placeholder |  |  |
| `truths.masked_symptom.report.conceal_base` | 0.3 | placeholder |  |  |
| `truths.masked_symptom.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.masked_symptom.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.masked_symptom.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.masked_symptom.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.masked_symptom.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.masked_symptom.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.masked_symptom.signals.hedge.p_if_true` | 0.3 | placeholder |  |  |
| `truths.masked_symptom.signals.hedge.p_if_false` | 0.03 | placeholder |  |  |
| `truths.mtc_men2.prior.glp1_weight` | 0.02 | placeholder |  |  |
| `truths.mtc_men2.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.mtc_men2.report.recall_miss` | 0.35 | placeholder |  |  |
| `truths.mtc_men2.report.conceal_base` | 0.05 | placeholder |  |  |
| `truths.mtc_men2.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.mtc_men2.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.mtc_men2.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.mtc_men2.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.mtc_men2.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.mtc_men2.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.mtc_men2.signals.hedge.p_if_true` | 0.4 | placeholder |  |  |
| `truths.mtc_men2.signals.hedge.p_if_false` | 0.02 | placeholder |  |  |
| `truths.pancreatitis_hx.prior.glp1_weight` | 0.02 | placeholder |  |  |
| `truths.pancreatitis_hx.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.pancreatitis_hx.report.recall_miss` | 0.15 | placeholder |  |  |
| `truths.pancreatitis_hx.report.conceal_base` | 0.05 | placeholder |  |  |
| `truths.pancreatitis_hx.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.pancreatitis_hx.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.pancreatitis_hx.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.pancreatitis_hx.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.pancreatitis_hx.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.pancreatitis_hx.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.pancreatitis_hx.signals.record.p_if_true` | 0.5 | placeholder |  |  |
| `truths.pancreatitis_hx.signals.record.p_if_false` | 0.01 | placeholder |  |  |
| `truths.gallbladder.prior.glp1_weight` | 0.08 | placeholder |  |  |
| `truths.gallbladder.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.gallbladder.report.recall_miss` | 0.2 | placeholder |  |  |
| `truths.gallbladder.report.conceal_base` | 0.03 | placeholder |  |  |
| `truths.gallbladder.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.gallbladder.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.gallbladder.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.gallbladder.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.gallbladder.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.gallbladder.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.eating_disorder.prior.glp1_weight` | 0.06 | placeholder |  |  |
| `truths.eating_disorder.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.eating_disorder.report.recall_miss` | 0.08 | placeholder |  |  |
| `truths.eating_disorder.report.conceal_base` | 0.5 | placeholder |  |  |
| `truths.eating_disorder.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.eating_disorder.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.eating_disorder.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.eating_disorder.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.eating_disorder.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.eating_disorder.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.eating_disorder.signals.hedge.p_if_true` | 0.3 | placeholder |  |  |
| `truths.eating_disorder.signals.hedge.p_if_false` | 0.03 | placeholder |  |  |
| `truths.hypoglycemic_meds.prior.glp1_weight` | 0.1 | placeholder |  |  |
| `truths.hypoglycemic_meds.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.hypoglycemic_meds.report.recall_miss` | 0.15 | placeholder |  |  |
| `truths.hypoglycemic_meds.report.conceal_base` | 0.02 | placeholder |  |  |
| `truths.hypoglycemic_meds.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.hypoglycemic_meds.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.hypoglycemic_meds.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.hypoglycemic_meds.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.hypoglycemic_meds.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.hypoglycemic_meds.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.hypoglycemic_meds.signals.record.p_if_true` | 0.5 | placeholder |  |  |
| `truths.hypoglycemic_meds.signals.record.p_if_false` | 0.01 | placeholder |  |  |
| `truths.inflated_bmi.prior.glp1_weight` | 0.1 | placeholder |  |  |
| `truths.inflated_bmi.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.inflated_bmi.report.recall_miss` | 0.08 | placeholder |  |  |
| `truths.inflated_bmi.report.conceal_base` | 0.4 | placeholder |  |  |
| `truths.inflated_bmi.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.inflated_bmi.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.inflated_bmi.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.inflated_bmi.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.inflated_bmi.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.inflated_bmi.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.inflated_bmi.signals.hedge.p_if_true` | 0.3 | placeholder |  |  |
| `truths.inflated_bmi.signals.hedge.p_if_false` | 0.03 | placeholder |  |  |
| `truths.hormone_cancer.prior.hrt_menopause` | 0.03 | placeholder |  |  |
| `truths.hormone_cancer.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.hormone_cancer.report.recall_miss` | 0.05 | placeholder |  |  |
| `truths.hormone_cancer.report.conceal_base` | 0.05 | placeholder |  |  |
| `truths.hormone_cancer.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.hormone_cancer.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.hormone_cancer.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.hormone_cancer.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.hormone_cancer.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.hormone_cancer.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.hormone_cancer.signals.record.p_if_true` | 0.5 | placeholder |  |  |
| `truths.hormone_cancer.signals.record.p_if_false` | 0.01 | placeholder |  |  |
| `truths.vte_stroke_hx.prior.hrt_menopause` | 0.04 | placeholder |  |  |
| `truths.vte_stroke_hx.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.vte_stroke_hx.report.recall_miss` | 0.15 | placeholder |  |  |
| `truths.vte_stroke_hx.report.conceal_base` | 0.05 | placeholder |  |  |
| `truths.vte_stroke_hx.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.vte_stroke_hx.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.vte_stroke_hx.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.vte_stroke_hx.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.vte_stroke_hx.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.vte_stroke_hx.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.vte_stroke_hx.signals.record.p_if_true` | 0.5 | placeholder |  |  |
| `truths.vte_stroke_hx.signals.record.p_if_false` | 0.01 | placeholder |  |  |
| `truths.smoker.prior.hrt_menopause` | 0.15 | placeholder |  |  |
| `truths.smoker.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.smoker.report.recall_miss` | 0.08 | placeholder |  |  |
| `truths.smoker.report.conceal_base` | 0.3 | placeholder |  |  |
| `truths.smoker.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.smoker.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.smoker.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.smoker.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.smoker.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.smoker.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.smoker.signals.hedge.p_if_true` | 0.3 | placeholder |  |  |
| `truths.smoker.signals.hedge.p_if_false` | 0.03 | placeholder |  |  |
| `truths.unexplained_bleeding.prior.hrt_menopause` | 0.06 | placeholder |  |  |
| `truths.unexplained_bleeding.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.unexplained_bleeding.report.recall_miss` | 0.08 | placeholder |  |  |
| `truths.unexplained_bleeding.report.conceal_base` | 0.3 | placeholder |  |  |
| `truths.unexplained_bleeding.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.unexplained_bleeding.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.unexplained_bleeding.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.unexplained_bleeding.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.unexplained_bleeding.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.unexplained_bleeding.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.unexplained_bleeding.signals.hedge.p_if_true` | 0.3 | placeholder |  |  |
| `truths.unexplained_bleeding.signals.hedge.p_if_false` | 0.03 | placeholder |  |  |
| `truths.migraine_aura.prior.hrt_menopause` | 0.06 | placeholder |  |  |
| `truths.migraine_aura.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.migraine_aura.report.recall_miss` | 0.3 | placeholder |  |  |
| `truths.migraine_aura.report.conceal_base` | 0.02 | placeholder |  |  |
| `truths.migraine_aura.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.migraine_aura.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.migraine_aura.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.migraine_aura.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.migraine_aura.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.migraine_aura.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.liver_disease.prior.hrt_menopause` | 0.02 | placeholder |  |  |
| `truths.liver_disease.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.liver_disease.report.recall_miss` | 0.15 | placeholder |  |  |
| `truths.liver_disease.report.conceal_base` | 0.05 | placeholder |  |  |
| `truths.liver_disease.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.liver_disease.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.liver_disease.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.liver_disease.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.liver_disease.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.liver_disease.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.liver_disease.signals.record.p_if_true` | 0.5 | placeholder |  |  |
| `truths.liver_disease.signals.record.p_if_false` | 0.01 | placeholder |  |  |
| `truths.late_start.prior.hrt_menopause` | 0.15 | placeholder |  |  |
| `truths.late_start.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.late_start.report.recall_miss` | 0.2 | placeholder |  |  |
| `truths.late_start.report.conceal_base` | 0.02 | placeholder |  |  |
| `truths.late_start.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.late_start.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.late_start.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.late_start.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.late_start.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.late_start.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.fertility_desire.prior.testosterone` | 0.25 | placeholder |  |  |
| `truths.fertility_desire.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.fertility_desire.report.recall_miss` | 0.05 | placeholder |  |  |
| `truths.fertility_desire.report.conceal_base` | 0.05 | placeholder |  |  |
| `truths.fertility_desire.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.fertility_desire.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.fertility_desire.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.fertility_desire.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.fertility_desire.ask.reveal` | 0.95 | placeholder |  |  |
| `truths.fertility_desire.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.high_hct.prior.testosterone` | 0.08 | placeholder |  |  |
| `truths.high_hct.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.high_hct.report.recall_miss` | 0.3 | placeholder |  |  |
| `truths.high_hct.report.conceal_base` | 0.02 | placeholder |  |  |
| `truths.high_hct.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.high_hct.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.high_hct.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.high_hct.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.high_hct.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.high_hct.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.high_hct.signals.record.p_if_true` | 0.5 | placeholder |  |  |
| `truths.high_hct.signals.record.p_if_false` | 0.01 | placeholder |  |  |
| `truths.untreated_osa.prior.testosterone` | 0.2 | placeholder |  |  |
| `truths.untreated_osa.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.untreated_osa.report.recall_miss` | 0.3 | placeholder |  |  |
| `truths.untreated_osa.report.conceal_base` | 0.05 | placeholder |  |  |
| `truths.untreated_osa.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.untreated_osa.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.untreated_osa.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.untreated_osa.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.untreated_osa.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.untreated_osa.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.untreated_osa.signals.hedge.p_if_true` | 0.3 | placeholder |  |  |
| `truths.untreated_osa.signals.hedge.p_if_false` | 0.03 | placeholder |  |  |
| `truths.prostate_issue.prior.testosterone` | 0.08 | placeholder |  |  |
| `truths.prostate_issue.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.prostate_issue.report.recall_miss` | 0.2 | placeholder |  |  |
| `truths.prostate_issue.report.conceal_base` | 0.1 | placeholder |  |  |
| `truths.prostate_issue.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.prostate_issue.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.prostate_issue.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.prostate_issue.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.prostate_issue.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.prostate_issue.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.prostate_issue.signals.record.p_if_true` | 0.5 | placeholder |  |  |
| `truths.prostate_issue.signals.record.p_if_false` | 0.01 | placeholder |  |  |
| `truths.cv_risk_high.prior.testosterone` | 0.1 | placeholder |  |  |
| `truths.cv_risk_high.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.cv_risk_high.report.recall_miss` | 0.1 | placeholder |  |  |
| `truths.cv_risk_high.report.conceal_base` | 0.15 | placeholder |  |  |
| `truths.cv_risk_high.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.cv_risk_high.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.cv_risk_high.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.cv_risk_high.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.cv_risk_high.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.cv_risk_high.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.cv_risk_high.signals.hedge.p_if_true` | 0.3 | placeholder |  |  |
| `truths.cv_risk_high.signals.hedge.p_if_false` | 0.03 | placeholder |  |  |
| `truths.not_confirmed_low.prior.testosterone` | 0.4 | placeholder |  |  |
| `truths.not_confirmed_low.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.not_confirmed_low.report.recall_miss` | 0.08 | placeholder |  |  |
| `truths.not_confirmed_low.report.conceal_base` | 0.35 | placeholder |  |  |
| `truths.not_confirmed_low.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.not_confirmed_low.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.not_confirmed_low.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.not_confirmed_low.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.not_confirmed_low.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.not_confirmed_low.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.not_confirmed_low.signals.hedge.p_if_true` | 0.3 | placeholder |  |  |
| `truths.not_confirmed_low.signals.hedge.p_if_false` | 0.03 | placeholder |  |  |
| `truths.nitrate_use.prior.erectile_dysfunction` | 0.04 | placeholder |  |  |
| `truths.nitrate_use.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.nitrate_use.report.recall_miss` | 0.1 | placeholder |  |  |
| `truths.nitrate_use.report.conceal_base` | 0.4 | placeholder |  |  |
| `truths.nitrate_use.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.nitrate_use.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.nitrate_use.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.nitrate_use.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.nitrate_use.ask.reveal` | 0.9 | placeholder |  |  |
| `truths.nitrate_use.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.nitrate_use.signals.record.p_if_true` | 0.5 | placeholder |  |  |
| `truths.nitrate_use.signals.record.p_if_false` | 0.1 | placeholder |  | record can be stale (old/stopped prescription) |
| `truths.exertional_cp.prior.erectile_dysfunction` | 0.06 | placeholder |  |  |
| `truths.exertional_cp.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.exertional_cp.report.recall_miss` | 0.08 | placeholder |  |  |
| `truths.exertional_cp.report.conceal_base` | 0.3 | placeholder |  |  |
| `truths.exertional_cp.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.exertional_cp.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.exertional_cp.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.exertional_cp.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.exertional_cp.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.exertional_cp.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.exertional_cp.signals.hedge.p_if_true` | 0.3 | placeholder |  |  |
| `truths.exertional_cp.signals.hedge.p_if_false` | 0.03 | placeholder |  |  |
| `truths.alpha_blocker.prior.erectile_dysfunction` | 0.1 | placeholder |  |  |
| `truths.alpha_blocker.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.alpha_blocker.report.recall_miss` | 0.2 | placeholder |  |  |
| `truths.alpha_blocker.report.conceal_base` | 0.02 | placeholder |  |  |
| `truths.alpha_blocker.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.alpha_blocker.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.alpha_blocker.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.alpha_blocker.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.alpha_blocker.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.alpha_blocker.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.alpha_blocker.signals.record.p_if_true` | 0.5 | placeholder |  |  |
| `truths.alpha_blocker.signals.record.p_if_false` | 0.01 | placeholder |  |  |
| `truths.recreational_drugs.prior.erectile_dysfunction` | 0.08 | placeholder |  |  |
| `truths.recreational_drugs.report.false_positive` | 0.01 | placeholder |  |  |
| `truths.recreational_drugs.report.recall_miss` | 0.08 | placeholder |  |  |
| `truths.recreational_drugs.report.conceal_base` | 0.5 | placeholder |  |  |
| `truths.recreational_drugs.report.conceal_context.companion` | 0.2 | placeholder |  |  |
| `truths.recreational_drugs.report.conceal_context.interpreter` | 0.1 | placeholder |  |  |
| `truths.recreational_drugs.report.recall_context.low_literacy` | 0.1 | placeholder |  |  |
| `truths.recreational_drugs.report.recall_context.elderly_alone` | 0.15 | placeholder |  |  |
| `truths.recreational_drugs.ask.reveal` | 0.8 | placeholder |  |  |
| `truths.recreational_drugs.ask.false_positive` | 0.01 | placeholder |  |  |
| `truths.recreational_drugs.signals.hedge.p_if_true` | 0.3 | placeholder |  |  |
| `truths.recreational_drugs.signals.hedge.p_if_false` | 0.03 | placeholder |  |  |
| `complaints.abdominal_pain.dx.ectopic.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.abdominal_pain.dx.ectopic.cpt[1].p` | 0.03 | placeholder |  |  |
| `complaints.abdominal_pain.dx.pancreatitis.cpt[0].p` | 0.01 | placeholder |  |  |
| `complaints.abdominal_pain.dx.pancreatitis.cpt[1].p` | 0.08 | placeholder |  |  |
| `complaints.abdominal_pain.dx.pancreatitis.cpt[2].p` | 0.02 | placeholder |  |  |
| `complaints.abdominal_pain.dx.pancreatitis.cpt[3].p` | 0.02 | placeholder |  |  |
| `complaints.abdominal_pain.dx.surgical_abdomen.cpt[0].p` | 0.03 | placeholder |  |  |
| `complaints.abdominal_pain.dx.surgical_abdomen.cpt[1].p` | 0.15 | placeholder |  |  |
| `complaints.abdominal_pain.dx.teratogen_exposure.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.abdominal_pain.dx.teratogen_exposure.cpt[1].p` | 0.0 | placeholder |  |  |
| `complaints.abdominal_pain.dx.teratogen_exposure.cpt[2].p` | 0.0 | placeholder |  |  |
| `complaints.abdominal_pain.dx.teratogen_exposure.cpt[3].p` | 0.9 | placeholder |  |  |
| `complaints.abdominal_pain.dx.ipv_injury.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.abdominal_pain.dx.ipv_injury.cpt[1].p` | 0.5 | placeholder |  |  |
| `complaints.chest_pain.dx.acs.cpt[0].p` | 0.04 | placeholder |  |  |
| `complaints.chest_pain.dx.acs.cpt[1].p` | 0.04 | placeholder |  |  |
| `complaints.chest_pain.dx.acs.cpt[2].p` | 0.1 | placeholder |  |  |
| `complaints.chest_pain.dx.acs.cpt[3].p` | 0.04 | placeholder |  |  |
| `complaints.chest_pain.dx.acs.cpt[4].p` | 0.15 | placeholder |  |  |
| `complaints.chest_pain.dx.acs.cpt[5].p` | 0.15 | placeholder |  |  |
| `complaints.chest_pain.dx.acs.cpt[6].p` | 0.25 | placeholder |  |  |
| `complaints.chest_pain.dx.acs.cpt[7].p` | 0.15 | placeholder |  |  |
| `complaints.chest_pain.dx.qt_event.cpt[0].p` | 0.001 | placeholder |  |  |
| `complaints.chest_pain.dx.qt_event.cpt[1].p` | 0.001 | placeholder |  |  |
| `complaints.chest_pain.dx.qt_event.cpt[2].p` | 0.001 | placeholder |  |  |
| `complaints.chest_pain.dx.qt_event.cpt[3].p` | 0.03 | placeholder |  |  |
| `complaints.head_injury.dx.ich.cpt[0].p` | 0.01 | placeholder |  |  |
| `complaints.head_injury.dx.ich.cpt[1].p` | 0.03 | placeholder |  |  |
| `complaints.head_injury.dx.ich.cpt[2].p` | 0.02 | placeholder |  |  |
| `complaints.head_injury.dx.ich.cpt[3].p` | 0.02 | placeholder |  |  |
| `complaints.head_injury.dx.ich.cpt[4].p` | 0.05 | placeholder |  |  |
| `complaints.head_injury.dx.ich.cpt[5].p` | 0.08 | placeholder |  |  |
| `complaints.head_injury.dx.ich.cpt[6].p` | 0.06 | placeholder |  |  |
| `complaints.head_injury.dx.ich.cpt[7].p` | 0.06 | placeholder |  |  |
| `complaints.head_injury.dx.ipv_injury.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.head_injury.dx.ipv_injury.cpt[1].p` | 0.6 | placeholder |  |  |
| `complaints.infection_abx.dx.qt_event.cpt[0].p` | 0.001 | placeholder |  |  |
| `complaints.infection_abx.dx.qt_event.cpt[1].p` | 0.001 | placeholder |  |  |
| `complaints.infection_abx.dx.qt_event.cpt[2].p` | 0.001 | placeholder |  |  |
| `complaints.infection_abx.dx.qt_event.cpt[3].p` | 0.03 | placeholder |  |  |
| `complaints.infection_abx.dx.teratogen_exposure.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.infection_abx.dx.teratogen_exposure.cpt[1].p` | 0.0 | placeholder |  |  |
| `complaints.infection_abx.dx.teratogen_exposure.cpt[2].p` | 0.0 | placeholder |  |  |
| `complaints.infection_abx.dx.teratogen_exposure.cpt[3].p` | 0.9 | placeholder |  |  |
| `complaints.infection_abx.dx.sepsis.cpt[0].p` | 0.01 | placeholder |  |  |
| `complaints.infection_abx.dx.sepsis.cpt[1].p` | 0.08 | placeholder |  |  |
| `complaints.uri_abx.dx.qt_event.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.uri_abx.dx.qt_event.cpt[1].p` | 0.002 | placeholder |  |  |
| `complaints.uri_abx.dx.qt_event.cpt[2].p` | 0.003 | placeholder |  |  |
| `complaints.uri_abx.dx.qt_event.cpt[3].p` | 0.08 | placeholder |  |  |
| `complaints.uri_abx.dx.teratogen_exposure.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.uri_abx.dx.teratogen_exposure.cpt[1].p` | 0.0 | placeholder |  |  |
| `complaints.uri_abx.dx.teratogen_exposure.cpt[2].p` | 0.0 | placeholder |  |  |
| `complaints.uri_abx.dx.teratogen_exposure.cpt[3].p` | 0.6 | placeholder |  |  |
| `complaints.uri_abx.dx.anaphylaxis.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.uri_abx.dx.anaphylaxis.cpt[1].p` | 0.05 | placeholder |  |  |
| `complaints.uri_abx.dx.deep_neck_infection.cpt[0].p` | 0.002 | placeholder |  |  |
| `complaints.uri_abx.dx.deep_neck_infection.cpt[1].p` | 0.5 | placeholder |  |  |
| `complaints.uri_abx.modify_cost` | 2.0 | placeholder |  | cost of declining / conditioning / delaying an appropriate request (overrides loss.modify_cost) |
| `complaints.med_refill.dx.unmonitored_toxicity.cpt[0].p` | 0.005 | placeholder |  |  |
| `complaints.med_refill.dx.unmonitored_toxicity.cpt[1].p` | 0.1 | placeholder |  |  |
| `complaints.med_refill.dx.decompensation.cpt[0].p` | 0.01 | placeholder |  |  |
| `complaints.med_refill.dx.decompensation.cpt[1].p` | 0.15 | placeholder |  |  |
| `complaints.med_refill.dx.overdose_diversion.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.med_refill.dx.overdose_diversion.cpt[1].p` | 0.2 | placeholder |  |  |
| `complaints.med_refill.dx.interaction_harm.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.med_refill.dx.interaction_harm.cpt[1].p` | 0.2 | placeholder |  |  |
| `complaints.med_refill.dx.missed_new_dx.cpt[0].p` | 0.002 | placeholder |  |  |
| `complaints.med_refill.dx.missed_new_dx.cpt[1].p` | 0.25 | placeholder |  |  |
| `complaints.med_refill.modify_cost` | 4.0 | placeholder |  | cost of declining / conditioning / delaying an appropriate request (overrides loss.modify_cost) |
| `complaints.glp1_weight.dx.mtc_contraindication.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.glp1_weight.dx.mtc_contraindication.cpt[1].p` | 0.9 | placeholder |  |  |
| `complaints.glp1_weight.dx.recurrent_pancreatitis.cpt[0].p` | 0.002 | placeholder |  |  |
| `complaints.glp1_weight.dx.recurrent_pancreatitis.cpt[1].p` | 0.1 | placeholder |  |  |
| `complaints.glp1_weight.dx.cholecystitis.cpt[0].p` | 0.005 | placeholder |  |  |
| `complaints.glp1_weight.dx.cholecystitis.cpt[1].p` | 0.06 | placeholder |  |  |
| `complaints.glp1_weight.dx.fetal_exposure.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.glp1_weight.dx.fetal_exposure.cpt[1].p` | 0.9 | placeholder |  |  |
| `complaints.glp1_weight.dx.ed_relapse.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.glp1_weight.dx.ed_relapse.cpt[1].p` | 0.4 | placeholder |  |  |
| `complaints.glp1_weight.dx.hypoglycemia.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.glp1_weight.dx.hypoglycemia.cpt[1].p` | 0.15 | placeholder |  |  |
| `complaints.glp1_weight.dx.inappropriate_rx.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.glp1_weight.dx.inappropriate_rx.cpt[1].p` | 0.8 | placeholder |  |  |
| `complaints.glp1_weight.modify_cost` | 6.0 | placeholder |  | cost of declining / conditioning / delaying an appropriate request (overrides loss.modify_cost) |
| `complaints.hrt_menopause.dx.cancer_progression.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.hrt_menopause.dx.cancer_progression.cpt[1].p` | 0.5 | placeholder |  |  |
| `complaints.hrt_menopause.dx.vte_stroke.cpt[0].p` | 0.002 | placeholder |  |  |
| `complaints.hrt_menopause.dx.vte_stroke.cpt[1].p` | 0.006 | placeholder |  |  |
| `complaints.hrt_menopause.dx.vte_stroke.cpt[2].p` | 0.08 | placeholder |  |  |
| `complaints.hrt_menopause.dx.vte_stroke.cpt[3].p` | 0.15 | placeholder |  |  |
| `complaints.hrt_menopause.dx.missed_endometrial_ca.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.hrt_menopause.dx.missed_endometrial_ca.cpt[1].p` | 0.1 | placeholder |  |  |
| `complaints.hrt_menopause.dx.aura_stroke.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.hrt_menopause.dx.aura_stroke.cpt[1].p` | 0.02 | placeholder |  |  |
| `complaints.hrt_menopause.dx.hepatotoxicity.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.hrt_menopause.dx.hepatotoxicity.cpt[1].p` | 0.2 | placeholder |  |  |
| `complaints.hrt_menopause.dx.late_start_cv.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.hrt_menopause.dx.late_start_cv.cpt[1].p` | 0.05 | placeholder |  |  |
| `complaints.hrt_menopause.modify_cost` | 6.0 | placeholder |  | cost of declining / conditioning / delaying an appropriate request (overrides loss.modify_cost) |
| `complaints.testosterone.dx.infertility.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.testosterone.dx.infertility.cpt[1].p` | 0.9 | placeholder |  |  |
| `complaints.testosterone.dx.polycythemia_thrombosis.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.testosterone.dx.polycythemia_thrombosis.cpt[1].p` | 0.15 | placeholder |  |  |
| `complaints.testosterone.dx.osa_worsening.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.testosterone.dx.osa_worsening.cpt[1].p` | 0.2 | placeholder |  |  |
| `complaints.testosterone.dx.prostate_progression.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.testosterone.dx.prostate_progression.cpt[1].p` | 0.08 | placeholder |  |  |
| `complaints.testosterone.dx.cv_event.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.testosterone.dx.cv_event.cpt[1].p` | 0.08 | placeholder |  |  |
| `complaints.testosterone.dx.inappropriate_rx.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.testosterone.dx.inappropriate_rx.cpt[1].p` | 0.9 | placeholder |  |  |
| `complaints.testosterone.modify_cost` | 6.0 | placeholder |  | cost of declining / conditioning / delaying an appropriate request (overrides loss.modify_cost) |
| `complaints.erectile_dysfunction.dx.nitrate_hypotension.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.erectile_dysfunction.dx.nitrate_hypotension.cpt[1].p` | 0.6 | placeholder |  |  |
| `complaints.erectile_dysfunction.dx.missed_cad.cpt[0].p` | 0.005 | placeholder |  |  |
| `complaints.erectile_dysfunction.dx.missed_cad.cpt[1].p` | 0.3 | placeholder |  |  |
| `complaints.erectile_dysfunction.dx.orthostatic_syncope.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.erectile_dysfunction.dx.orthostatic_syncope.cpt[1].p` | 0.1 | placeholder |  |  |
| `complaints.erectile_dysfunction.dx.stimulant_event.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.erectile_dysfunction.dx.stimulant_event.cpt[1].p` | 0.05 | placeholder |  |  |
| `complaints.erectile_dysfunction.dx.qt_event.cpt[0].p` | 0.0 | placeholder |  |  |
| `complaints.erectile_dysfunction.dx.qt_event.cpt[1].p` | 0.05 | placeholder |  |  |
| `complaints.erectile_dysfunction.modify_cost` | 4.0 | placeholder |  | cost of declining / conditioning / delaying an appropriate request (overrides loss.modify_cost) |
| `loss.miss_cost_by_severity.1` | 1 | placeholder |  |  |
| `loss.miss_cost_by_severity.2` | 5 | placeholder |  |  |
| `loss.miss_cost_by_severity.3` | 20 | placeholder |  |  |
| `loss.miss_cost_by_severity.4` | 60 | placeholder |  |  |
| `loss.miss_cost_by_severity.5` | 100 | placeholder |  |  |
| `loss.modify_cost` | 1.0 | placeholder |  |  |
| `loss.escalate_cost` | 6.0 | placeholder |  |  |
| `loss.residual_after_mitigation` | 0.1 | placeholder |  | fraction of miss cost remaining when an action mitigates the dx |
