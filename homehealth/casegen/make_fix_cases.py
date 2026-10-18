"""Deterministic fix-list repairs + hand-derived pair partner (SYNTHETIC; no API). Wayne 2026-10-18 items 7-8.
Writes fix_cases.json: cases ST1-003 (banned word fixed), ST1-006 (recycled timed contact replaced, subtle_deterioration true),
ST1-011 (new benign partner of ST1-004 for pair ST1-P02), plus grade_context ST1-004 (banned word fixed) and ST1-005 (ST1-006's partner)."""
import json, copy
B = {c["case_id"]: c for c in json.load(open("raw/ST1.batch.json"))["cases"]}
L = {c["case_id"]: c for c in json.load(open("library_v2_smart_accepted.json"))["cases"]}
STRIP = {"grade", "clinician_ruling", "src", "src_model", "src_batch", "src_module", "src_prompt", "src_grader", "src_library", "pair_complete_in_accepted", "prev_labels", "prev_grade", "relabel", "pair_note"}
def base(c): return {k: copy.deepcopy(v) for k, v in c.items() if k not in STRIP}
def sub(c, field, old, new):
    assert old in c[field], (c["case_id"], field, old); c[field] = c[field].replace(old, new)
FIXES = {}
AF_OLD, AF_NEW = "no artifact flags", "no device quality flags"
# ---- ST1-003: banned word only (fix list: script 'banned words: artifact')
c = base(B["ST1-003"]); sub(c, "router_input", AF_OLD, AF_NEW)
c["pair_id"] = None
FIXES["ST1-003"] = ["router_input: 'no artifact flags' -> 'no device quality flags' (banned word)", "pair_id: ST1-P02 -> null (ST1-P02 re-formed as ST1-004 vs new ST1-011)"]
st3 = c
# ---- ST1-006: recycled timed contact (grader novelty fix) + subtle_deterioration true (as its partner ST1-005)
c = base(B["ST1-006"])
sub(c, "caregiver_or_nurse_note", "Spouse phoned at Day -1 13:15, patient answered and described lunch and a short walk.",
    "Spouse made a video call at Day -1 19:40; patient answered from his sister's sofa and said he had eaten supper and taken his evening tablets.")
sub(c, "router_input", "Timed phone check Day -1 13:15 inside the gap: patient answered, described lunch and a short walk.",
    "Timed video call Day -1 19:40 inside the gap: patient answered from his sister's sofa, said he had eaten supper and taken his evening tablets.")
sub(c, "rationale", "a spouse phone check at Day -1 13:15 inside the 50 h gap", "a spouse video call at Day -1 19:40 inside the 50 h gap")
sub(c, "decisive_feature", "A spouse's phone check at Day -1 13:15, placed inside the gap,", "A spouse's video call at Day -1 19:40, placed inside the gap,")
assert "13:15" not in json.dumps(c)
c["subtle_deterioration"] = True
FIXES["ST1-006"] = ["caregiver_or_nurse_note/router_input/rationale/decisive_feature: recycled 'Day -1 13:15 ... lunch and a short walk' contact -> 'Day -1 19:40 video call ... supper and evening tablets'",
                    "subtle_deterioration: false -> true (2.3 kg weight rise and HR 84 after an HF discharge; matches partner ST1-005)",
                    "category suggestion 'hf,missing_data' already equal (no change)"]
st6 = c
# ---- ST1-004 (library) banned-word fix, for grading context; applied to the library by apply_rulings.py
st4 = base(L["ST1-004"]); sub(st4, "router_input", AF_OLD, AF_NEW)
st4["decisive_feature"] = "Same 87% fingertip reading inside her own 86-88% range, but since this morning she is breathless walking to the kitchen and speaking in short sentences, with resting HR 96 bpm and RR 26/min."
# ---- ST1-011: hand-derived benign partner of ST1-004 (differs ONLY in the acute decompensation signs)
c = copy.deepcopy(st4); c["case_id"] = "ST1-011"; c["pair_id"] = "ST1-P02"
sub(c, "trend_last_7d", "Day 0 09:40 watch wrist SpO2 88%, resting HR 96 bpm, RR 26/min.", "Day 0 09:40 watch wrist SpO2 88%, resting HR 78 bpm, RR 18/min.")
sub(c, "router_input", "Day 0 09:40 watch wrist SpO2 88%, resting HR 96 bpm, RR 26/min.", "Day 0 09:40 watch wrist SpO2 88%, resting HR 78 bpm, RR 18/min.")
c["caregiver_or_nurse_note"] = "Daughter says she walked to the kitchen at her usual pace this morning and is talking in full sentences, breathing as she normally does; no fever reported."
sub(c, "router_input", "Daughter: breathless walking to kitchen and speaking in short sentences since this morning; no fever reported.",
    "Daughter: walked to kitchen at her usual pace this morning, talking in full sentences, breathing as normal; no fever reported.")
c.update(expected_route="silent_log", acceptable_alternates=["nurse_task"], hard_trigger=True, hard_trigger_rule="HT_SPO2_LT88", trigger_tier="SUPPRESSED",
         confirm_step=None, confirm_timeout_min=None, suppression_reason="at_patient_baseline", subtle_deterioration=False, difficulty="hard", category=["respiratory"])
c.pop("route_basis", None)
c["decisive_feature"] = "Same 87% fingertip reading inside her own 86-88% range, with resting HR 78 bpm, RR 18/min and her usual breathing and speech."
c["rationale"] = ("Check 1 (reliable reading) passes: fingertip repeats at 09:40 and 09:43 both read 87% with good waveforms. Check 2 (change from own baseline) fails: her own fingertip rest readings over 30 days sit at 86-88%, "
  "so the saturation rule is SUPPRESSED with at_patient_baseline. Nothing else has changed: resting HR 78 bpm sits in her 76-80 range, RR is 18/min, and her daughter reports her usual pace, full sentences and normal breathing, "
  "so there is no acute decompensation and the reading is logged (silent_log), with a routine nurse call as the acceptable alternate. "
  "Naive-model trap: a shallow model sees an SpO2 below 88% in a COPD GOLD 3 patient who lives alone and sends it to a human, when 87% is her own documented range and every other sign is at baseline.")
assert "artifact" not in c["router_input"]
FIXES["ST1-011"] = ["new: hand-derived from ST1-004 (no generation); differs only in Day 0 HR 96->78, RR 26->18 and the daughter's report (breathless/short sentences -> usual pace/full sentences)",
                    "labels: SUPPRESSED at_patient_baseline, silent_log, alternates [nurse_task]; pair ST1-P02 with ST1-004"]
st11 = c
json.dump({"note": "SYNTHETIC. Deterministic repairs, Wayne 2026-10-18 items 7-8; built by make_fix_cases.py", "fixes": FIXES,
           "cases": [st3, st6, st11], "grade_context": [st4, base(L["ST1-005"])]}, open("fix_cases.json", "w"), indent=1)
print("fix_cases.json:", [x["case_id"] for x in (st3, st6, st11)], "+ context ST1-004, ST1-005")
