"""holdout_v2 generation + grading (SYNTHETIC). Same pipeline as holdout_v1 (library_v1/run_library.py gen/grade) with the current prompts
(GEN_LLM2_v2.3 + hard-slice, GRADER_LLM3_v1.3, both with the v1.10.1 addendum ADDENDUM_v1101.md). Generators: anthropic/claude-haiku-5.5 and
deepseek/deepseek-v4-pro (two families; Nemotron dropped for low yield). Grader: google/gemini-4-argon (as v1). Batch ids HV1..HV8.
DO_NOT_REPEAT = library_v2 (270) + holdout_v1 (all 94 generated-and-merged cases). Checkpoints: state.json after every call, gen/ and grade/
files skip on restart (rerun the same command). Spend guard GEN_CAP (default $2.50 of the $3 total; Jev kept back). Never prints the key."""
import json, os, sys, threading, traceback
sys.path.insert(0, "../library_v1")
import run_library as rl
import specs_v2 as SP
P = "../casegen/prompts_v2/"; ADD = open("ADDENDUM_v1101.md").read()
GEN = open(P + "GEN_LLM2_v2.3.md").read(); HS = open(P + "GEN_LLM3_hardslice.md").read().replace("escalate_human", "urgent_page").replace("wake_specialist", "provider_task")
rl.HARD_SYS = GEN.rstrip() + "\n\n---\n" + HS[HS.index("## Hard-slice overrides"):] + ADD
rl.GRADER_SYS = open(P + "GRADER_LLM3_v1.3.md").read() + ADD
rl.BUDGET = float(os.environ.get("GEN_CAP", "2.50"))
_chat = rl.chat; rl.chat = lambda *a, **k: _chat(*a, **{**k, "timeout": 900})
MODELS = {"haiku": "anthropic/claude-haiku-5.5", "deepseek": "deepseek/deepseek-v4-pro"}
LIB = json.load(open("../library_v2/smart_triggers/library_v2_smart_accepted.json"))["cases"]
HO1 = [c for f in ("../holdout_v1/gen/" + x for x in sorted(os.listdir("../holdout_v1/gen")) if x.endswith(".batch.json")) for c in json.load(open(f))["cases"]]
if os.path.exists("state.json"):
    S = json.load(open("state.json")); S["stopped"] = False; rl.STATE.update(S)
else:
    rl.STATE["dnr"] = [rl.short(c.get("decisive_feature"), (c.get("category") or ["?"])[0]) for c in LIB + HO1]
COMMON = ("Every case fills baseline_status. difficulty: hard+adversarial >= 70%, easy <= 1. At least 30% of cases outside the module focus. "
          "Use the v2.3 answer fields (trigger_tier, confirm_step, confirm_timeout_min, suppression_reason, baseline_layer, escalation_target where they apply). "
          "Vary sex, age band, Fitzpatrick type (>= 30% V-VI) and devices. " + SP.ROUTE_IDS + "\n" + SP.WORDING)
REQ = {"routes": "per sub-batch MODULE 'Routes exactly'", "hard_plus_adversarial_min_pct": 70, "minimums": "per sub-batch tally.minimums", "route_ids": "silent_log, nurse_task, provider_task, urgent_page"}
def graded(g): return os.path.exists(f"grade/{g}.grader.json") or os.path.exists(f"grade/{g}-p1.grader.json")
def run_group(grp):
    S = {b: x for x in SP.HK for b in [x[0]]}; ok = []
    for b in grp:
        if rl.STATE["stopped"]: break
        _, gen, _, n, t = S[b]
        try:
            if os.path.exists(f"gen/{b}.batch.json") or rl.gen_batch(b, MODELS[gen], rl.HARD_SYS, n, t + "\n" + COMMON, True, 120000, gen): ok.append(b)
        except Exception as e: rl.log(f"GEN {b} EXC {e!r}"); traceback.print_exc()
    g = "+".join(ok)
    if ok and not rl.STATE["stopped"] and not graded(g):
        try: rl.grade(g, ok, REQ)
        except Exception as e: rl.log(f"GRADE {g} EXC {e!r}")
if __name__ == "__main__":
    rl.log(f"HOLDOUT_V2 START cap ${rl.BUDGET:.2f} spend ${rl.STATE['spend']:.3f}")
    ts = [threading.Thread(target=run_group, args=(g,)) for g in (SP.TOPUP if "--topup" in sys.argv else SP.GROUPS)]; [t.start() for t in ts]; [t.join() for t in ts]
    rl.log(f"HOLDOUT_V2 END spend=${rl.STATE['spend']:.3f} stopped={rl.STATE['stopped']}")
