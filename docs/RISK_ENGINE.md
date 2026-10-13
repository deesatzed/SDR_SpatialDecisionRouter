# Bayesian risk sidecar (risk_engine/) — SYNTHETIC, PLACEHOLDER PARAMETERS

**Every number in `risk_engine/params.yaml` is `source: placeholder`.** None is clinically validated. The UI shows categorical labels (very unlikely <5% · unlikely 5–20% · possible 20–50% · likely >50%), the param source, and an engine badge (`BN · params: placeholder` vs `fallback`). Treat the digits as illustrative only.

## Run
```bash
risk_engine/run_sidecar.sh            # creates risk_engine/.venv on first run; serves 127.0.0.1:8765 (RISK_PORT to change)
cd risk_engine && .venv/bin/python -m pytest -q
```
The visionOS app calls `POST /assess` with a 0.8 s timeout. It does so for each new encounter and after every ask-next or re-rating. If the sidecar is unreachable or the complaint has no network, the app uses the Swift heuristics: the badge shows `fallback` and `-noSidecar` forces it. The app needs `NSAllowsLocalNetworking` (set in project.yml).

## Model
Each complaint has its own discrete BN, solved by exact inference (pyAgrum 3.2.1 LazyPropagation). Complaints: `abdominal_pain`, `chest_pain`, `head_injury`, and `infection_abx` (cough/fever and urinary symptoms).

**Nodes**
- **Context roots:** `ctx_companion`, `ctx_interpreter`, `ctx_adolescent`, `ctx_low_literacy`, `ctx_elderly_alone`. Plan flags: `plan_qt_drug`, `plan_teratogen`.
- **Hidden truths:** `pregnant`, `qt_med` (methadone and other QT-prolonging meds), `anticoag`, `substance` (none/alcohol/cocaine/opioid), `unsafe_home`, `minimized` (symptom severity understated).
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

## Outputs (`POST /assess`)
- **Per truth:**
  - `posterior` and `label`
  - `state` (one of 4), derived from the posterior vs the report:
    - no report → **Not said**
    - positive report or answer → **Reliable**
    - negative report with posterior < `doubt_posterior` → **Reliable**
    - otherwise, if the topic is sensitive and concealment ≥ recall in this context → **Said differently on purpose**; else **Said wrong**
  - `if_wrong`: the worst-case dx (max severity × high) with `current`, `low` = P(dx | evidence, truth benign) and `high` = max over risky states of P(dx | evidence, truth = state). Also `worst_miss`, `plan_change`, and labels.
- **Overall:**
  - `dx`, `p_critical`
  - `expected_loss` for sign_off / modify / escalate. Loss = Σ P(dx)·miss_cost[severity], times `residual_after_mitigation` if the action mitigates that dx, plus the action cost.
  - `best_action`
- **`voi[]`:** true VOI = EL(best action now) − E_answer[EL(best action | answer)]. Each entry also has `p_answer_pos` and `p_ruleout` = P(the answer drives P(critical) below `critical_escalate`).
- **`escalation.recommend`** = P(critical) > `critical_escalate` AND max `p_ruleout` < `min_ruleout`.

Other endpoints:
- `POST /voi`: the VOI, escalation and loss subset.
- `POST /sample` `{complaint, n, seed}`: seeded forward-sampled synthetic encounters (reproducible).
- `GET /health`, `GET /params` (the markdown table).

### Request schema (`/assess`, `/voi`)
```json
{"complaint": "abdominal_pain|chest_pain|head_injury|infection_abx",
 "context": {"companion": bool, "interpreter": bool, "adolescent": bool, "low_literacy": bool, "elderly_alone": bool},
 "plan_flags": {"plan_qt_drug": bool, "plan_teratogen": bool},
 "reports": {"<truth>": null | "neg" | "pos" | "<risky state, e.g. cocaine>"},
 "signals": {"<truth>": {"hedge": bool, "record": bool}},
 "answers": {"<truth>": "neg" | "pos"},
 "known": {"<truth>": "<state>"},
 "encounter_id": "optional"}
```
Unknown keys, unknown truths/context for the complaint, non-boolean flags, and bad report values return HTTP 400.

## Tests (pytest, 27)
- **Hand-computed reference values on a 1-truth network:** prior marginals; negative-report posterior with and without a companion (0.1·0.335/(0.1·0.335+0.9·0.99) etc.); if-wrong range; VOI by explicit arithmetic; posterior after an answer; escalation rule; known truth.
- **Invalid parameter rejection:** probability >1, literature without a citation, placeholder with a citation, unknown source, incomplete CPT, bad parent, negative cost.
- **Invalid request rejection:** 7 cases.
- **Reproducibility:** same seed gives the same samples; different seed differs; frequency matches the prior within 0.01 at n=20000; assess is deterministic.
- **Shipped file:** all entries are placeholder and all complaints run.
- **HTTP service:** 200 responses, plus 400 on bad input.

## Parameter table for Wayne's review
To change a value, edit `risk_engine/params.yaml` and set `source: expert_estimate`. For `source: literature`, fill `citation` with a real reference. The validator rejects a citation on non-literature entries and a literature entry without one.

| parameter | value | source | citation | note |
|---|---|---|---|---|
| `thresholds.doubt_posterior` | 0.15 | placeholder |  | posterior P(risky) at/above which a negative report is not Reliable |
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
| `loss.miss_cost_by_severity.1` | 1 | placeholder |  |  |
| `loss.miss_cost_by_severity.2` | 5 | placeholder |  |  |
| `loss.miss_cost_by_severity.3` | 20 | placeholder |  |  |
| `loss.miss_cost_by_severity.4` | 60 | placeholder |  |  |
| `loss.miss_cost_by_severity.5` | 100 | placeholder |  |  |
| `loss.modify_cost` | 1.0 | placeholder |  |  |
| `loss.escalate_cost` | 6.0 | placeholder |  |  |
| `loss.residual_after_mitigation` | 0.1 | placeholder |  | fraction of miss cost remaining when an action mitigates the dx |
