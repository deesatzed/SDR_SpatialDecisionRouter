"""library_expansion_v1 generation (adapted from holdout_v4; DO_NOT_REPEAT = library_v2 + holdout_v1/v2 only) + grading (SYNTHETIC). SAME pipeline as holdout_v3 (library_v1/run_library.py gen/grade, GEN_LLM2_v2.3 + hard-slice,
GRADER_LLM3_v1.3, generators haiku-5.5 + deepseek-v4-pro, grader gemini-4-argon) with the v1.11.2 addendum (ADDENDUM_v1112.md, appended after
ADDENDUM_v1103.md), a NEW seed (specs_lx1.SEED, sent as the OpenRouter 'seed' parameter) and new author prompts (specs_lx1).
DO_NOT_REPEAT = library_v2 (270) + holdout_v1 + holdout_v2 (holdout_v3/v4 NEVER in prompts). Spend guard GEN_CAP (default $2.70 of the $3.00 cap;
Jev kept back). An HTTP 402 stops the run. Never prints the key."""
import json, os, sys, threading, traceback
sys.path.insert(0, "../library_v1")
import run_library as rl
import specs_lx1 as SP
P = "../casegen/prompts_v2/"; ADD = open("ADDENDUM_v1103.md").read() + open("ADDENDUM_v1112.md").read()
GEN = open(P + "GEN_LLM2_v2.3.md").read(); HS = open(P + "GEN_LLM3_hardslice.md").read().replace("escalate_human", "urgent_page").replace("wake_specialist", "provider_task")
rl.HARD_SYS = GEN.rstrip() + "\n\n---\n" + HS[HS.index("## Hard-slice overrides"):] + ADD
rl.GRADER_SYS = open(P + "GRADER_LLM3_v1.3.md").read() + ADD
rl.BUDGET = float(os.environ.get("GEN_CAP", "2.70"))
_chat = rl.chat
def chat(*a, **k):
    ex = dict(k.get("extra") or {}); ex["seed"] = SP.SEED
    r = _chat(*a, **{**k, "extra": ex, "timeout": 900})
    if r.get("error") and "402" in str(r["error"]):
        rl.STATE["stopped"] = True; rl.log("HTTP 402: stopping (OpenRouter key limit)")
    return r
rl.chat = chat
MODELS = {"haiku": "anthropic/claude-haiku-5.5", "deepseek": "deepseek/deepseek-v4-pro"}
LIB = json.load(open("../library_v2/smart_triggers/library_v2_smart_accepted.json"))["cases"]
HO = [c for d in ("../holdout_v1/gen/", "../holdout_v2/gen/") for f in (d + x for x in sorted(os.listdir(d)) if x.endswith(".batch.json")) for c in json.load(open(f))["cases"]]
if os.path.exists("state.json"):
    S = json.load(open("state.json")); S["stopped"] = False; rl.STATE.update(S)
else:
    rl.STATE["dnr"] = [rl.short(c.get("decisive_feature"), (c.get("category") or ["?"])[0]) for c in LIB + HO]
COMMON = ("Every case fills baseline_status and expected_device_ticket (null unless a device disagreement). difficulty: hard+adversarial >= 70%, easy <= 1. At most 15% of cases outside the module focus. "
          "Use the v2.3 answer fields (trigger_tier, confirm_step, confirm_timeout_min, suppression_reason, baseline_layer, escalation_target where they apply). "
          "Vary sex, age band, Fitzpatrick type (>= 30% V-VI) and devices. " + SP.ROUTE_IDS + "\n" + SP.WORDING + "\n" + SP.SETTINGS)
REQ = {"routes": "per sub-batch MODULE 'Routes exactly'", "hard_plus_adversarial_min_pct": 70, "minimums": "per sub-batch tally.minimums", "route_ids": "silent_log, nurse_task, provider_task, urgent_page"}
def graded(g): return os.path.exists(f"grade/{g}.grader.json") or os.path.exists(f"grade/{g}-p1.grader.json")
def run_group(grp):
    S = {x[0]: x for x in SP.HK}; ok = []
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
    rl.log(f"LIBRARY_EXPANSION_V1 START cap ${rl.BUDGET:.2f} spend ${rl.STATE['spend']:.3f} seed {SP.SEED}")
    GR = SP.TOPUP if "--topup" in sys.argv else SP.GROUPS
    if "--seq" in sys.argv:   # 2026-10-23: 4 parallel streams stalled to read timeouts; run groups one at a time
        for g in GR: run_group(g)
    else:
        ts = [threading.Thread(target=run_group, args=(g,)) for g in GR]; [t.start() for t in ts]; [t.join() for t in ts]
    rl.log(f"LIBRARY_EXPANSION_V1 END spend=${rl.STATE['spend']:.3f} stopped={rl.STATE['stopped']}")
