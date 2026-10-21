"""holdout_v1 generation + grading (SYNTHETIC). Reuses library_v1/run_library.py (call/gen/grade/control) with the CURRENT prompts:
GEN_LLM2_v2.3 rev h (SMART_TRIGGERS v1.8), Haiku hard-slice overrides, GRADER_LLM3_v1.3 rev h. Batch IDs HO1..HO8 (case IDs HOn-NNN),
src_library holdout_v1. DO_NOT_REPEAT = the 270-case library. Spend guard: generation+grading stop at $2.70 (Jev budget kept back).
Never prints the key."""
import json, os, sys, threading, traceback
sys.path.insert(0, "../library_v1")
import run_library as rl
P = "../casegen/prompts_v2/"
GEN = open(P + "GEN_LLM2_v2.3.md").read(); HS = open(P + "GEN_LLM3_hardslice.md").read()
rl.GEN_SYS = GEN; rl.HARD_SYS = GEN.rstrip() + "\n\n---\n" + HS[HS.index("## Hard-slice overrides"):]
rl.GRADER_SYS = open(P + "GRADER_LLM3_v1.3.md").read()
rl.BUDGET = float(os.environ.get("GEN_CAP", "2.70"))
_chat = rl.chat; rl.chat = lambda *a, **k: _chat(*a, **{**k, "timeout": 900})
LIB = json.load(open("../library_v2/smart_triggers/library_v2_smart_accepted.json"))["cases"]
if os.path.exists("state.json"):
    S = json.load(open("state.json")); S["stopped"] = False; rl.STATE.update(S)
else:
    rl.STATE["dnr"] = [rl.short(c.get("decisive_feature"), (c.get("category") or ["?"])[0]) for c in LIB]
V = lambda t: rl.specs.mod(t) if hasattr(rl, "specs") else None
import specs as SP
COMMON = ("Every case fills baseline_status. difficulty: hard+adversarial >= 70%, easy <= 1. At least 30% of cases outside the module focus. "
          "Use the v2.3 answer fields (trigger_tier, confirm_step, confirm_timeout_min, suppression_reason, baseline_layer, escalation_target where they apply). "
          "Vary sex, age band, Fitzpatrick type (>= 30% V-VI) and devices.")
HK = [
 ("HO1", "hard-trigger tiers", 11, "FOCUS=hard-trigger tiers under SMART_TRIGGERS v1.8. Routes exactly: silent_log 2, nurse_task 2, wake_specialist 2, escalate_human 5. "
  ">=2 ABSOLUTE (different rules), >=2 CONFIRM_FIRST (one pending with a confirm_step and timeout, one already_confirmed), >=2 SUPPRESSED with different suppression_reason (unreliable_reading, explained or at_patient_baseline), >=1 ARTIFACT (HT_VS_IMPLAUSIBLE, silent_log). tally.minimums: absolute 2, confirm_first 2, suppressed 2, artifact 1."),
 ("HO2", "goals of care + learning period", 11, "FOCUS=hospice/goals-of-care and the learning period. Routes exactly: silent_log 2, nurse_task 4, wake_specialist 2, escalate_human 3. "
  ">=3 hospice/comfort-only patients: >=1 SUPPRESSED goals_of_care (nurse_task, hospice nurse same shift), >=1 urgent symptomatic comfort problem (escalate_human, escalation_target hospice_nurse). "
  ">=3 learning-period cases (baseline_status phase learning): a reading beyond the population default band or SpO2 < 88% with no learned or clinician-set baseline is CONFIRM_FIRST; include one clinician-set baseline exception. >=1 condition-change reset (relearning after a medication change). tally.minimums: goals_of_care 3, learning_period 3, reset 1."),
 ("HO3", "CGM / glucose", 10, "FOCUS=CGM and glucose. Routes exactly: silent_log 3, nurse_task 2, wake_specialist 2, escalate_human 3. "
  ">=3 CGM pressure-low (compression) artifacts with the SMART_TRIGGERS section 8 features, >=1 true symptomatic hypoglycaemia on insulin or a sulfonylurea, >=1 sensor warm-up or calibration artefact, >=1 sustained hyperglycaemia that needs a nurse. 1 near-miss pair (artifact vs real low). tally.minimums: cgm_artifact 3, true_hypo 1, pairs 1."),
 ("HO4", "near-miss pairs", 10, "FOCUS=adversarial near-miss pairs. Exactly 4 near-miss pairs (8 cases, adjacent IDs, exactly ONE decisive fact differs, different routes) + 2 unpaired. Pairs: (a) 47 h vs 49 h data gap in a high-risk patient, (b) SpO2 reliable on-skin repeat vs poor-contact flag with a normal fingertip recheck, "
  "(c) chest discomfort band pair under the banded chest-pain rule, (d) a fall on an anticoagulant confirmed vs explained. Routes exactly: silent_log 3, nurse_task 2, wake_specialist 2, escalate_human 3. tally.minimums: pairs 4."),
 ("HO5", "subtle deterioration", 11, "FOCUS=subtle deterioration and hidden hypoxemia, mechanisms NOT in DO_NOT_REPEAT. Routes exactly: silent_log 2, nurse_task 2, wake_specialist 4, escalate_human 3. "
  ">=5 subtle_deterioration=true with >=2 weak corroborating signals each, >=2 hidden-hypoxemia (Fitzpatrick V-VI, wearable 91-94%, no fingertip oximeter), >=1 drift-guard case (slow 2-week creep, drift_not_absorbed), >=2 look-alike noise cases (silent_log). tally.minimums: subtle 5, hidden_hypoxemia 2, drift 1, lookalike_noise 2."),
 ("HO6", "missing data + social", 10, "FOCUS=missing-data boundaries plus dementia/proxy, caregiver strain, renal and electrolyte problems. Routes exactly: silent_log 2, nurse_task 3, wake_specialist 2, escalate_human 3. "
  ">=3 data-gap cases (>=1 HT_GAP48_HIGHRISK unexplained, >=1 low-risk long gap, >=1 progressive wear-time decline), >=2 dementia/proxy or caregiver-strain cases, >=2 renal or electrolyte cases. tally.minimums: data_gap 3, social 2, renal_electrolyte 2."),
]
TOPUP = [
 ("HO9", "mixed top-up", 11, "FOCUS=mixed spread mirroring the library: medication change, respiratory, cardiac/arrhythmia, infection, recovery that should stay silent, and one hard trigger. Mechanisms NOT in DO_NOT_REPEAT. Routes exactly: silent_log 3, nurse_task 3, wake_specialist 2, escalate_human 3. >=1 hard trigger, >=2 recovery/should-stay-silent, >=2 medication-change cases, 1 near-miss pair. tally.minimums: hard_trigger 1, recovery 2, med_change 2, pairs 1."),
 ("HO10", "hard mix top-up", 11, "FOCUS=hard mix: 2 near-miss pairs (learning-period CONFIRM_FIRST vs learned own baseline; CGM compression low vs real symptomatic low), plus a hospice comfort case, a data-gap case, an ARTIFACT hard-limit case, a subtle deterioration and a hidden hypoxemia. Routes exactly: silent_log 3, nurse_task 3, wake_specialist 2, escalate_human 3. tally.minimums: pairs 2, goals_of_care 1, data_gap 1, artifact 1."),
]
if os.environ.get("TOPUP"): HK = HK + TOPUP
NV = [("HO7", "M6", SP.mod("M6")), ("HO8", "M4", SP.mod("M4"))]
HK_REQ = {"routes": "per sub-batch MODULE 'Routes exactly'", "hard_plus_adversarial_min_pct": 70, "minimums": "per sub-batch tally.minimums"}
NV_REQ = {"routes": "per module text (base: 8/6/5/6 for N=25)", "hard_plus_adversarial_min_pct": 40, "minimums": "per GEN v2.3 defaults scaled to N, or module"}
GROUPS = [("HO1", "HO2"), ("HO3", "HO4"), ("HO5", "HO6")] + ([("HO9", "HO10")] if os.environ.get("TOPUP") else [])
def done(b): return os.path.exists(f"grade/{b}.grader.json") or any(os.path.exists(f"grade/{g}.grader.json") or os.path.exists(f"grade/{g}-p1.grader.json") for g in ["+".join(x) for x in GROUPS] if b in g.split("+"))
def stream_hk():
    S = {b: (b, m, n, t) for b, m, n, t in HK}
    for grp in GROUPS:
        ok = []
        for b in grp:
            if rl.STATE["stopped"]: break
            try:
                _, m, n, t = S[b]
                if os.path.exists(f"gen/{b}.batch.json") or rl.gen_batch(b, rl.HAIKU, rl.HARD_SYS, n, t + "\n" + COMMON, True, 120000, m): ok.append(b)
            except Exception as e: rl.log(f"HK {b} EXC {e!r}"); traceback.print_exc()
        g = "+".join(ok)
        if ok and not rl.STATE["stopped"] and not (os.path.exists(f"grade/{g}.grader.json") or os.path.exists(f"grade/{g}-p1.grader.json")):
            try: rl.grade(g, ok, HK_REQ)
            except Exception as e: rl.log(f"HK grade {g} EXC {e!r}")
def stream_nv():
    for b, m, t in NV:
        if rl.STATE["stopped"]: break
        try:
            if not os.path.exists(f"gen/{b}.batch.json"): rl.gen_batch(b, rl.NEMO, rl.GEN_SYS, 25, t + "\n" + COMMON, False, 160000, m)
            if os.path.exists(f"gen/{b}.batch.json") and not (os.path.exists(f"grade/{b}.grader.json") or os.path.exists(f"grade/{b}-p1.grader.json")): rl.grade(b, [b], NV_REQ)
        except Exception as e: rl.log(f"NV {b} EXC {e!r}"); traceback.print_exc()
if __name__ == "__main__":
    rl.log(f"HOLDOUT START cap ${rl.BUDGET:.2f} spend ${rl.STATE['spend']:.3f}")
    if not os.path.exists("grade/CONTROL-start.grader.json"):
        try: rl.grade_control("CONTROL-start")
        except Exception as e: rl.log(f"control start EXC {e!r}")
    ts = [threading.Thread(target=stream_hk)] + ([] if os.environ.get("TOPUP") else [threading.Thread(target=stream_nv)]); [t.start() for t in ts]; [t.join() for t in ts]
    if not rl.STATE["stopped"] and not os.path.exists("grade/CONTROL-end2.grader.json" if os.environ.get("TOPUP") else "grade/CONTROL-end.grader.json") and (os.environ.get("TOPUP") or os.environ.get("CONTROL_END")):
        try: rl.grade_control("CONTROL-end2" if os.environ.get("TOPUP") else "CONTROL-end")
        except Exception as e: rl.log(f"control end EXC {e!r}")
    rl.log(f"HOLDOUT END spend=${rl.STATE['spend']:.3f} stopped={rl.STATE['stopped']}")
