# ai_doc_review — physician in the middle (SYNTHETIC)

The default domain, `Domains/AIDocReview/`. ED triage is kept: run it with `-domain ed_triage`, or use Next Domain on the board.

**Item.** One AI–patient encounter:
- a transcript snippet
- extracted fields: CC, vitals if available, PMH, meds, allergies, pregnancy, substance use, safety at home, adherence, symptoms, sexual history
- the AI's ESI, differential and plan
- reason chips
- ED census as context

**Links.**
- `esi`: AI Triage → ED Intake.
- `plan`: AI Plan → Orders, with options `sign off | modify plan | escalate`. When `escalate` fires, the ball goes to the Alert Team (`alertDest`).

**Physician actions.**
- Sign off: pass.
- Modify: use the ring.
- Escalate: the Escalate button.
- Ask next: the Ask next panel → Send.
- Re-rate: the Reliability panel → R/N/W/D.

## Hard escalation triggers
Triggers are STEMI, stroke, unstable vitals and new AMS. They are generic: set `review.escalationLink` and the domain's `hardTrigger(item:)`. When one fires:
- the proposal becomes `escalate`
- the alert fires at emission
- priority goes up by 100 and the item pre-empts the Now card
- a red banner is shown and reliability analysis is skipped
- the physician acknowledges

The log records `hardTrigger` and `triggerFiredAt`. Use `-forceTrigger` to make encounters 3, 10, 17… triggered.

## Reliability layer (generic types in `Core/ReliabilityKit.swift`)
Each field has a `FieldReliability`:
- the stated value
- a state: Reliable / Not said / Said wrong / Said differently on purpose
- a score from 0 to 1
- why (the context drivers)
- notAsked: the complaint-specific expected questions that were never asked
- ifWrong (a `RiskRange`)
- physicianState
- the hidden `trueValue` and `trueState`, which are logged and never rendered

The score depends on context:
- topic sensitivity
- companion present
- interpreter
- adolescent
- age 75 or over without a companion (recall)
- low health literacy
- inconsistencies, e.g. a methadone-clinic pharmacy record, AFib in the PMH but no anticoagulant stated, a refill gap, or transcript cues

**If wrong.** For a field with score below 0.75:
- `alternative`: the dangerous value
- `pAlt`
- risk range = pAlt × severity/5 × [0.6, 1.4]
- `worstMiss`
- `planChange`
- `ddxShift`

The differential widens with these, for example ectopic 0–18% or ACS 15→40%.

**VOI** = pAlt × plan-change × severity. The top 3 are offered. Sending one simulates the patient's answer from hidden truth: it is revealed with probability 0.9, or 0.7 for sensitive topics. The answer updates the encounter, then reliability, VOI and chips are re-scored.

If a severity-4 or higher miss with pAlt of 0.2 or more is not excluded, the chip "critical miss not excluded → recommend escalation" appears.

## Generator (parametric, `AIDocReviewDomain.make`)
Hidden truth per field is drawn from complaint- and age-dependent priors. The conversation is then simulated:
- **Asked or not:** expected fields are asked with p 0.7, others with p 0.25. A field that isn't asked is Not said.
- **Deliberate nondisclosure:** applies to sensitive risky truths. p = 0.3, +0.3 with a companion present, +0.1 with an interpreter, +0.25 for adolescents, +0.05 for low literacy. Minimized symptoms are 0.35, +0.15 if age is over 70. Result: Said differently.
- **Recall error:** p = 0.06, +0.18 for age 75+ alone, +0.12 for low literacy (meds/allergies), +0.08 with an interpreter. Result: Said wrong.

Some withheld or wrong fields leave a consistency clue.

**Ground truth.**
- True ESI and plan come from hidden truth.
- Plan is `escalate` for a dangerous diagnosis that was missed:
  - pregnant + abdominal pain
  - anticoagulant + head strike
  - minimized chest pain or headache
  - cocaine + chest pain
  - unsafe at home
- Plan is `modify plan` for a plan hazard:
  - methadone + azithromycin/fluoroquinolone/ondansetron
  - pregnancy + ciprofloxacin/ibuprofen
  - penicillin allergy + a β-lactam
  - non-adherence
  - cocaine + propranolol

## Logged per decision (`RoutingDecision`)
- `reliability[]`: estimate, physician state and hidden truth
- `reRatings[]`
- `asks[]`: question, VOI and answer
- `voiOffered[]`
- `hardTrigger`, `triggerFiredAt`
- `hiddenTruth`: per field, plus trueESI and truePlan
- the review-queue telemetry: `decidedBy`, reasons, sections and dwell

`tools/to_training.py` also writes:
- `reliability_flagging.jsonl`: per encounter, fields → 4-state labels. The label is hidden truth, overridden by the physician's re-rating, which is weighted ×2.
- `ask_next.jsonl`: the question the physician chose from the VOI candidates, plus escalate examples.

## Importer (xlsx → CSV for now): `EncounterImporter.swift`
Put `encounters.csv` in the app's Documents folder, or pass `-importCSV <path>`. It has one row per encounter. Native xlsx is a TODO: export the sheet as CSV (UTF-8). Imported rows are queued ahead of the synthetic ones and get IDs `X-<encounter_id>`.

| column | meaning |
|---|---|
| encounter_id | required |
| age, sex | |
| chief_complaint | one of: chest pain, abdominal pain, fall / head strike, cough + fever, urinary symptoms, headache, palpitations / anxiety, medication refill |
| channel, companion (`none`), interpreter (`yes`/`no`), language, health_literacy (`low`/`adequate`) | context |
| hr, sbp, spo2, temp | blank = not available |
| pmh | `;`-separated |
| ai_plan, transcript | |
| stated_<field> | field ∈ pregnancy, meds, substance, allergies, symptoms, safety, adherence, sexual; `—` = not said |
| true_<field> | optional adjudicated truth (blank → stated is treated as truth) |
| hard_trigger | optional text; non-empty = hard escalation |
