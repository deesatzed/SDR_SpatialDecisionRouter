# VARIANTS — user-message add-ons for GEN_LLM2_v2 / GEN_LLM3_hardslice

## Base user message (always send)
```
N=25
ID_START=G-101
DO_NOT_REPEAT=[ ...decisive_feature strings from all accepted cases so far... ]
Follow the system prompt. Output the {"cases":[...],"tally":{...}} object only.
```
Append AT MOST ONE module below.

**Rules for every module:**
- At least 30% of cases stay outside the focus. For N=25 that means ≤17 in focus and ≥8 outside.
- Cases outside the focus follow the default mix and minimums, scaled to their count.
- The route overrides apply to the whole batch.
- Wherever a module relaxes a default minimum, the tally still reports that minimum (`required` = the module's value).

**Routing:**
- **LLM3 hard slice:** modules 2, 3, 8, and the novel-artifact half of module 1. Use GEN_LLM3_hardslice.md.
- **LLM2 volume:** the rest of module 1, and modules 4, 5, 6, 7, 9 and 10.

---

## M1 — Noise / artifact (LLM2; novel-sensor variants → LLM3)
```
FOCUS=noise_artifact. 17 focus cases, category[0]="noise" unless a real change hides inside.
Routes (whole batch): silent_log 11, nurse_task 5, provider_task 4, urgent_page 5.
Use each at most once: device swap with a different HRV metric (SDNN→RMSSD), firmware update changing a baseline, altitude/travel SpO2 shift, essential tremor or knitting inflating steps, DST shift in sleep timing, watch left on the charger, shared watch (spouse or visiting grandchild wearing it), loose ring after weight loss, cold fingers/Raynaud, new tighter band raising skin temp, scale tare/low battery/rug, pet or child on the scale, CGM compression low, vaccine-day temperature bump, new mattress or bed partner on the bed sensor.
Include at least 3 traps where the artifact story is plausible but a real change sits underneath (provider_task or urgent_page).
artifact_flags stay neutral device states.
```

## M2 — SpO2 / skin-tone bias (→ LLM3)
```
FOCUS=spo2_bias. 15 focus cases, all tagged spo2_bias; ≥10 of them Fitzpatrick V-VI.
Routes: silent_log 6, nurse_task 5, provider_task 6, urgent_page 8.
At least 5 hidden-hypoxemia cases: wearable reads 91-94%, NO fingertip check, with corroborating clues (RR up, resting HR up, steps down, short-of-breath note, new O2 need). Use varied mechanisms (pneumonia, PE, HF, opioid hypoventilation, concentrator failure, COPD exacerbation).
At least 2 cases where a repeat reliable reading is <88% (HT_SPO2_LT88).
At least 3 lighter-skin or darker-skin motion/cold/poor-fit dips that are true noise (silent_log).
At least 1 near-miss pair: same 92% reading, one with corroborating clues and one without.
Never state "skin tone causes bias" in the case text; the bias must be inferable.
```

## M3 — Subtle deterioration (→ LLM3)
```
FOCUS=subtle_deterioration. 16 focus cases with subtle_deterioration=true.
Routes: silent_log 6, nurse_task 4, provider_task 7, urgent_page 8.
Menu, each at most twice: afebrile sepsis in the very old, hypothermic sepsis (skin-temp drop), euglycemic DKA on an SGLT2 inhibitor (near-normal CGM, Kussmaul-like breathing, nausea), SSRI/thiazide hyponatremia (confusion, unsteadiness), slow HF fluid gain (weight +1.5-3 kg over 5-7 d, night HR, falling HRV), early pneumonia, dehydration with orthostasis, early delirium shown by sleep and activity fragmentation, AKI on ACEi + diuretic + NSAID, slow GI bleed (rising HR, fatigue, DOAC).
Every case needs ≥2 weak corroborating signals; no single obvious number.
At least 4 look-alike noise cases (silent_log) with the same surface pattern but an innocent cause.
```

## M4 — Medication change (LLM2)
```
FOCUS=med_change. 16 focus cases, tag med_change, the change within 14 days, started_day exactly matching the change day.
Routes: silent_log 4, nurse_task 6, provider_task 8, urgent_page 7.
Menu, each at most twice: SGLT2 start (volume, euDKA, genital infection), SSRI start or dose up (hyponatremia, falls, insomnia), opioid start/up in OSA or COPD (night SpO2 and RR), anticholinergic in dementia (diphenhydramine, oxybutynin → delirium, retention), sulfonylurea start or renal decline (nocturnal lows on CGM), NSAID in HF or CKD (weight, BP), missed anticoagulant (copay, unfilled script, confusion over held vs resumed), beta-blocker duplication, donepezil bradycardia, diuretic over-response.
At least 3 cases where the expected drug effect is benign and the expected route is silent_log or nurse_task.
Doses must be current in meds; from_dose/to_dose filled for dose changes.
```

## M5 — Dementia / proxy report (LLM2)
```
FOCUS=dementia. 15 focus cases, tag dementia, the patient cannot reliably self-report; information comes from a proxy (spouse, adult child, aide, facility staff).
Routes: silent_log 5, nurse_task 7, provider_task 6, urgent_page 7.
Include: delirium vs baseline dementia fluctuation, sundowning vs infection, a proxy contradicting the patient, a patient denying a fall that the watch recorded, pain shown only as agitation or sleep change, wandering on bed/motion sensors, an anticholinergic added by another prescriber, and the proxy wearing the patient's device.
function_baseline is always filled. Note voice: varied, non-clinical.
```

## M6 — Caregiver strain / social (LLM2)
```
FOCUS=caregiver. 14 focus cases, tag caregiver with strain or capacity actually shown in the data or note.
Routes: silent_log 4, nurse_task 9, provider_task 5, urgent_page 7.
Include: an exhausted spouse missing doses, a caregiver hospitalised or travelling, a new paid aide unfamiliar with the devices, unaffordable or unfilled meds, food insecurity in a diabetic, a caregiver injury, a caregiver dementia (two patients), refused help, and a cluttered home after discharge without equipment.
At least 3 cases where the social problem is the ONLY finding (nurse_task); at least 2 where strain hides clinical deterioration.
No names, no exact ages for caregivers either.
```

## M7 — Goals of care / hospice (LLM2)
```
FOCUS=goals_of_care. 12 focus cases, tag goals_of_care, patient_goals or a POLST/hospice status filled.
Routes: silent_log 5, nurse_task 7, provider_task 6, urgent_page 7. goals_of_care cases are never silent_log.
Include: comfort-focused patient with a hard trigger (still urgent_page; the human honours goals), hospice dyspnoea at night, a family disagreeing with documented goals, a patient declining hospitalisation, slow functional decline needing a conversation (nurse_task), a POLST limiting intubation with a new fall on a DOAC, and terminal-phase sleep and activity changes.
Rationale explains how the goals shaped the route.
```

## M8 — Adversarial near-miss pairs (→ LLM3)
```
FOCUS=pairs. 8 pairs (16 cases), adjacent IDs, identical except EXACTLY ONE decisive fact, different routes; plus 9 unpaired cases on the default mix.
Routes (whole batch): silent_log 7, nurse_task 6, provider_task 6, urgent_page 6.
Decisive-fact menu, one per pair: on-wrist vs off-wrist fall signature, anticoagulant present vs stopped, gap 47 h vs 49 h in a high-risk patient, gap explained by a timed contact vs an unverified excuse, repeat SpO2 87% vs 89% on a reliable reading, darker vs lighter skin with the same 92% and clues, weight +2.1 kg in 4 days in HF vs a scale moved onto a rug, new vs old focal weakness, CGM low with vs without compression posture, chest discomfort with vs without HR/BP change.
Per pair, list the single difference in decisive_feature of both members. difficulty="adversarial" for both.
```

## M9 — Missing-data boundaries (LLM2; boundary pairs → LLM3)
```
FOCUS=missing_data. 12 focus cases, category includes missing_data; data_quality.longest_gap_h always filled.
Routes: silent_log 7, nurse_task 6, provider_task 5, urgent_page 7.
Spread: gaps of 20, 36, 47, 48, 52 and 72 h; high-risk vs low-risk; explained (timed visit, video call or caregiver contact inside the gap) vs unexplained (travel claim or charger story without contact); partial gaps (one device only); a device that syncs late (data arrives retroactively); wear time falling progressively as an early sign of illness.
Any ≥48 h unexplained gap in a high-risk patient = HT_GAP48_HIGHRISK, urgent_page.
```

## M10 — Recovery / should stay silent (LLM2)
```
FOCUS=recovery. 14 focus cases, category[0]="recovery" or "noise", mostly silent_log.
Routes: silent_log 13, nurse_task 5, provider_task 3, urgent_page 4.
Include: post-pneumonia steps rising, HR normalising after a diuretic adjustment, expected post-op HR/HRV recovery, a planned medication taper behaving as expected, CGM lows resolved after a dose cut, weight returning to dry weight, sleep recovering after a hospital stay, and an earlier alert already handled by a nurse (note shows closure).
At least 3 traps where the recovery stalls or reverses in one subtle signal (nurse_task or provider_task).
Naive-model trap usually = over-alerting on residual abnormal values.
```
