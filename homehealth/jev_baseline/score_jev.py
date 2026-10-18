"""Score the Jev baseline (SYNTHETIC). Section 5 of PLAN.md. Inputs: runner JSON (labels), accepted library JSON (subtle, categories),
Outcomes CSV (severity_if_wrong), results/parsed/*.jsonl. Outputs: results/summary.json, results/per_case.csv.
Scored on the base variant; robustness uses the other three. Two systems: 'jev' (model alone) and 'l1_jev' (Layer 1 label tier
ABSOLUTE forces escalate_human, else the model's pick)."""
import csv, json, os, glob, collections
_HERE = os.path.dirname(os.path.abspath(__file__))
_BOX = "/workspace/jevfly_smoke/library_v2/smart_triggers"
def find_input(env, name):
    """env var, else the SDR repo layout (homehealth/library next to homehealth/jev_baseline), else the box pipeline folder."""
    for p in (os.environ.get(env), os.path.join(_HERE, "..", "library", name), os.path.join(_BOX, name)):
        if p and os.path.exists(p): return p
    raise SystemExit(f"{name} not found: set {env} (the runner JSON is written by casegen/convert_casegen.py via build_outputs.py)")
ROUTES = ["silent_log", "nurse_task", "wake_specialist", "escalate_human"]; RANK = {r: i for i, r in enumerate(ROUTES)}
ALIAS = {"nurse_task_with_recheck": "nurse_task"}
SEV_W = {"critical": 3, "major": 2, "minor": 1}
ESC = "escalate_human"
def norm(r): return ALIAS.get(r, r)
def ok_set(case): return {norm(case["expected"])} | {norm(a) for a in case.get("acceptable") or []}
def correct(pick, case): return pick is not None and norm(pick) in ok_set(case)
def critical_miss(pick, case):
    """escalation needed (expected escalate_human) and the pick is lower and not an acceptable alternate"""
    return pick is not None and norm(case["expected"]) == ESC and not correct(pick, case)
def under_triage(pick, case): return pick is not None and not correct(pick, case) and RANK[norm(pick)] < RANK[norm(case["expected"])]
def over_escalation(pick, case): return pick is not None and norm(pick) == ESC and ESC not in ok_set(case)
def l1_pick(pick, case): return ESC if case.get("trigger_tier") == "ABSOLUTE" else pick
def tier_implies_escalate(case): return case.get("trigger_tier") in ("ABSOLUTE", "CONFIRM_FIRST")
def brier_bin(p, y): return (p - y) ** 2
def brier_multi(probs, expected):
    return sum((float(probs.get(r, 0) or 0) - (1.0 if r == norm(expected) else 0.0)) ** 2 for r in ROUTES)
def rate(n, d): return round(n / d, 4) if d else None

def score_system(cases, picks, sev, extra):
    """picks: case_id -> route or None. Returns metrics dict."""
    n = len(cases); got = [c for c in cases if picks.get(c["id"]) is not None]
    esc_cases = [c for c in cases if norm(c["expected"]) == ESC]; non_esc = [c for c in got if norm(c["expected"]) != ESC]
    cm = [c["id"] for c in got if critical_miss(picks[c["id"]], c)]
    cm_w = sum(SEV_W.get(sev.get(i, "minor"), 1) for i in cm)
    over = [c["id"] for c in got if over_escalation(picks[c["id"]], c)]
    pages = sum(norm(picks[c["id"]]) == ESC for c in got)
    def brk(key):
        d = collections.defaultdict(lambda: [0, 0, 0, 0])   # n, correct, critical, over
        for c in got:
            for k in key(c):
                x = d[k]; p = picks[c["id"]]; x[0] += 1; x[1] += correct(p, c); x[2] += critical_miss(p, c); x[3] += over_escalation(p, c)
        return {k: {"n": v[0], "accuracy": rate(v[1], v[0]), "critical_misses": v[2], "over_escalations": v[3]} for k, v in sorted(d.items(), key=lambda kv: str(kv[0]))}
    pairs = collections.defaultdict(list)
    for c in cases:
        if c.get("pair_id"): pairs[c["pair_id"]].append(c)
    full = {p: m for p, m in pairs.items() if len(m) == 2}
    pair_ok = sum(all(correct(picks.get(c["id"]), c) for c in m) for m in full.values())
    hard = [c for c in got if c.get("trigger_tier")]
    agree = [(c["id"], (norm(picks[c["id"]]) == ESC) == tier_implies_escalate(c)) for c in hard]
    return {"n_cases": n, "n_with_pick": len(got), "no_pick": [c["id"] for c in cases if picks.get(c["id"]) is None],
            "accuracy": rate(sum(correct(picks[c["id"]], c) for c in got), len(got)),
            "accuracy_exact": rate(sum(norm(picks[c["id"]]) == norm(c["expected"]) for c in got), len(got)),
            "critical_misses": len(cm), "critical_miss_ids": cm, "critical_miss_weighted": cm_w,
            "critical_miss_by_severity": dict(collections.Counter(sev.get(i, "minor") for i in cm)),
            "escalate_needed_n": len(esc_cases), "escalation_sensitivity": rate(sum(correct(picks.get(c["id"]), c) for c in esc_cases if picks.get(c["id"])), sum(1 for c in esc_cases if picks.get(c["id"]))),
            "under_triage": sum(under_triage(picks[c["id"]], c) for c in got),
            "over_escalations": len(over), "over_escalation_ids": over, "over_escalation_rate": rate(len(over), len(non_esc)),
            "pages_per_100": rate(100 * pages, len(got)), "false_pages_per_100": rate(100 * len(over), len(got)),
            "by_category": brk(lambda c: extra[c["id"]]["categories"]), "by_difficulty": brk(lambda c: [c["difficulty"]]),
            "by_tier": brk(lambda c: [c.get("trigger_tier") or "no_trigger"]), "by_subtle": brk(lambda c: ["subtle" if extra[c["id"]]["subtle"] else "not_subtle"]),
            "by_hard_trigger": brk(lambda c: ["hard_trigger" if c.get("hard_trigger") else "no_trigger"]),
            "pairs_complete": len(full), "pairs_both_correct": pair_ok, "pair_consistency": rate(pair_ok, len(full)),
            "engine_tier_agreement": rate(sum(a for _, a in agree), len(agree)), "engine_tier_disagree_ids": [i for i, a in agree if not a]}

def robustness(cases, rows):
    by = {(r["case"], r["variant"]): r for r in rows}
    rev = [(by[(c["id"], "base")]["pick"], by[(c["id"], "reversed")]["pick"]) for c in cases if by.get((c["id"], "base"), {}).get("pick") and by.get((c["id"], "reversed"), {}).get("pick")]
    kd = [by[(c["id"], "key_deleted")] for c in cases if by.get((c["id"], "key_deleted"), {}).get("pick")]
    kd_chg = sum(by[(r["case"], "base")].get("pick") != r["pick"] for r in kd if by.get((r["case"], "base")))
    ma = [by[(c["id"], "missing_all")] for c in cases if by.get((c["id"], "missing_all"), {}).get("pick")]
    return {"reversed_same_pick": rate(sum(a == b for a, b in rev), len(rev)), "reversed_n": len(rev),
            "key_deleted_pick_changed": rate(kd_chg, len(kd)), "key_deleted_escalate_or_veto": rate(sum(r["pick"] == ESC or (r.get("veto") or 0) >= 0.5 for r in kd), len(kd)),
            "missing_all_escalate": rate(sum(r["pick"] == ESC for r in ma), len(ma)), "missing_all_escalate_or_veto": rate(sum(r["pick"] == ESC or (r.get("veto") or 0) >= 0.5 for r in ma), len(ma)), "missing_all_n": len(ma)}

def calibration(cases, base):
    b, m, n = 0.0, 0.0, 0
    for c in cases:
        r = base.get(c["id"])
        if not r or not r.get("probs"): continue
        p = float(r["probs"].get(ESC, 0) or 0); y = 1.0 if norm(c["expected"]) == ESC else 0.0
        b += brier_bin(p, y); m += brier_multi(r["probs"], c["expected"]); n += 1
    return {"brier_escalate": round(b / n, 4) if n else None, "brier_multiclass": round(m / n, 4) if n else None, "n": n}

def main(results_dir=os.path.join(_HERE, "results"), runner=None, accepted=None, outcomes=None):
    runner = runner or find_input("RUNNER_JSON", "library_v2_smart_runner.json")
    accepted = accepted or find_input("ACCEPTED_JSON", "library_v2_smart_accepted.json")
    outcomes = outcomes or find_input("OUTCOMES_CSV", "library_v2_smart_Outcomes.csv")
    cases = json.load(open(runner)); A = {c["case_id"]: c for c in json.load(open(accepted))["cases"]}
    sev = {r["case_id"]: r["severity_if_wrong"] for r in csv.DictReader(open(outcomes))}
    extra = {c["id"]: {"categories": A[c["id"][4:]].get("category") or [c["kind"]], "subtle": bool(A[c["id"][4:]].get("subtle_deterioration"))} for c in cases}
    hospice = [c["id"] for c in cases if c.get("escalation_target") == "hospice_nurse" or c.get("suppression_reason") == "goals_of_care"]
    overrides = [c["id"] for c in cases if c.get("clinician_override")]
    S = {"models": {}, "hospice_case_ids": hospice, "clinician_override_ids": overrides}; per = []
    for f in sorted(glob.glob(os.path.join(results_dir, "parsed", "*.jsonl"))):
        rows = [json.loads(l) for l in open(f) if l.strip()]
        if not rows: continue
        m = rows[0]["model"]; last = {}
        for r in rows: last[(r["case"], r["variant"])] = r   # latest row wins (resume)
        rows = list(last.values()); base = {r["case"]: r for r in rows if r["variant"] == "base"}
        picks = {c["id"]: (base.get(c["id"]) or {}).get("pick") for c in cases}
        l1 = {c["id"]: l1_pick(picks[c["id"]], c) for c in cases}
        jev = score_system(cases, picks, sev, extra); l1s = score_system(cases, l1, sev, extra)
        errs = collections.Counter(r.get("error") for r in rows if not r.get("pick"))
        S["models"][m] = {"jev": jev, "l1_jev": l1s, "robustness": robustness(cases, rows), "calibration": calibration(cases, base),
            "calls": len(rows), "calls_without_pick": sum(1 for r in rows if not r.get("pick")), "errors": dict(errs),
            "retried_calls": sum(1 for r in rows if (r.get("attempts") or 1) > 1),
            "cost_usd": round(sum(r.get("cost") or 0 for r in rows), 6), "input_tokens": sum(r.get("input_tokens") or 0 for r in rows),
            "median_latency_s": sorted(r["latency_s"] for r in rows)[len(rows) // 2],
            "hospice": {i: {"expected": next(c["expected"] for c in cases if c["id"] == i), "pick": picks.get(i)} for i in hospice},
            "clinician_override": {i: {"pick": picks.get(i), "label_tier": "CONFIRM_FIRST", "engine_tier": "ABSOLUTE",
                                       "correct": correct(picks.get(i), next(c for c in cases if c["id"] == i)),
                                       "l1_forced_if_engine_tier_used": True, "l1_forced_with_label_tier": False} for i in overrides}}
        by = {(r["case"], r["variant"]): r for r in rows}
        for c in cases:
            p = picks[c["id"]]; b = base.get(c["id"]) or {}
            per.append({"model": m, "case_id": c["id"], "expected": c["expected"], "acceptable": ";".join(c.get("acceptable") or []), "severity_if_wrong": sev.get(c["id"]),
                "category": ";".join(extra[c["id"]]["categories"]), "difficulty": c["difficulty"], "trigger_tier": c.get("trigger_tier") or "", "hard_trigger_rule": c.get("hard_trigger_rule") or "",
                "subtle": extra[c["id"]]["subtle"], "pair_id": c.get("pair_id") or "", "hospice": c["id"] in hospice, "clinician_override": c["id"] in overrides,
                "pick": p, "p_escalate": (b.get("probs") or {}).get(ESC), "veto": b.get("veto"), "correct": correct(p, c), "critical_miss": critical_miss(p, c),
                "under_triage": under_triage(p, c), "over_escalation": over_escalation(p, c),
                "pick_reversed": (by.get((c["id"], "reversed")) or {}).get("pick"), "pick_key_deleted": (by.get((c["id"], "key_deleted")) or {}).get("pick"),
                "pick_missing_all": (by.get((c["id"], "missing_all")) or {}).get("pick"),
                "l1_jev_pick": l1[c["id"]], "l1_jev_correct": correct(l1[c["id"]], c), "l1_jev_critical_miss": critical_miss(l1[c["id"]], c), "error": b.get("error")})
    S["total_cost_usd"] = round(sum(v["cost_usd"] for v in S["models"].values()), 6)
    rank = sorted(S["models"], key=lambda m: (S["models"][m]["jev"]["critical_miss_weighted"], S["models"][m]["jev"]["over_escalations"], -(S["models"][m]["jev"]["accuracy"] or 0)))
    S["ranking_jev"] = rank; S["ranking_rule"] = "fewest severity-weighted critical misses, then fewest over-escalations, then accuracy"
    json.dump(S, open(os.path.join(results_dir, "summary.json"), "w"), indent=1)
    with open(os.path.join(results_dir, "per_case.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(per[0])); w.writeheader(); w.writerows(per)
    return S
if __name__ == "__main__":
    S = main()
    for m in S["ranking_jev"]:
        j = S["models"][m]["jev"]; l = S["models"][m]["l1_jev"]
        print(m, "acc", j["accuracy"], "crit", j["critical_misses"], "pages/100", j["pages_per_100"], "| L1+Jev crit", l["critical_misses"], "cost", S["models"][m]["cost_usd"])
