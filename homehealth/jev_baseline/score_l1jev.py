"""Score Layer 1 (deterministic adapter) + Jev against the earlier baseline (SYNTHETIC). Wayne 2026-10-18.
Systems (base variant): baseline Jev alone (results/), baseline label-tier L1 + Jev (ABSOLUTE label tier forces escalate),
new Jev alone (results_v18/, v1.8 prompt), new Layer 1 (derived from case facts by layer1_adapter) + Jev, and the derived Layer 1
with the baseline Jev picks (isolates the Layer 1 effect from the prompt change). Also reports Layer 1 vs label tier agreement."""
import csv, json, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import score_jev as S, layer1_adapter as L
def load_picks(d, model):
    f = os.path.join(d, "parsed", S_slug(model) + ".jsonl"); last = {}
    if not os.path.exists(f): return None, []
    for l in open(f):
        if l.strip(): r = S.RT.canon_row(json.loads(l)); last[(r["case"], r["variant"])] = r
    rows = list(last.values())
    return {r["case"]: r.get("pick") for r in rows if r["variant"] == "base"}, rows
def S_slug(m):
    import re; return re.sub(r"[^A-Za-z0-9._-]+", "_", m)
def label_l1(case):
    t = case.get("trigger_tier")
    return t, case.get("suppression_reason")
def agreement(cases, A, l1):
    hard = [c for c in cases if c.get("trigger_tier")]; non = [c for c in cases if not c.get("trigger_tier")]
    eq = lambda c: l1[c["id"]]["tier"] == c["trigger_tier"]
    eq_reason = lambda c: eq(c) and (c["trigger_tier"] != "SUPPRESSED" or l1[c["id"]].get("reason") == c.get("suppression_reason"))
    eq_rule = lambda c: l1[c["id"]].get("rule") == c.get("hard_trigger_rule")
    by = collections.defaultdict(lambda: [0, 0, 0])
    for c in hard:
        k = f'{c.get("hard_trigger_rule")} {c["trigger_tier"]}' + (f' {c.get("suppression_reason")}' if c["trigger_tier"] == "SUPPRESSED" else "")
        by[k][0] += 1; by[k][1] += eq(c); by[k][2] += eq_reason(c)
    conf = collections.Counter((c["trigger_tier"], l1[c["id"]]["tier"] or "none") for c in hard)
    return {"hard_trigger_cases": len(hard), "tier_match": sum(eq(c) for c in hard), "tier_and_suppression_reason_match": sum(eq_reason(c) for c in hard),
            "rule_match": sum(eq_rule(c) for c in hard),
            "paging_tier_match": sum((c["trigger_tier"] in ("ABSOLUTE", "CONFIRM_FIRST")) == (l1[c["id"]]["tier"] in ("ABSOLUTE", "CONFIRM_FIRST")) for c in hard),
            "mismatches": [{"id": c["id"], "label": [c["trigger_tier"], c.get("suppression_reason"), c.get("hard_trigger_rule")], "layer1": [l1[c["id"]]["tier"], l1[c["id"]].get("reason"), l1[c["id"]].get("rule")]} for c in hard if not eq_reason(c) or not eq_rule(c)],
            "confusion_label_vs_layer1": {f"{a}->{b}": n for (a, b), n in sorted(conf.items())},
            "by_rule": {k: {"n": v[0], "tier_match": v[1], "tier_reason_match": v[2]} for k, v in sorted(by.items())},
            "non_trigger_cases": len(non), "false_triggers": [{"id": c["id"], "layer1": [l1[c["id"]]["tier"], l1[c["id"]].get("reason"), l1[c["id"]].get("rule")], "expected": c["expected"]} for c in non if l1[c["id"]]["tier"]],
            "false_paging_triggers": sum(l1[c["id"]]["tier"] in ("ABSOLUTE", "CONFIRM_FIRST") for c in non)}
def subset_acc(cases, picks, ids):
    sub = [c for c in cases if c["id"] in ids and picks.get(c["id"])]
    return {"n": len(sub), "correct": sum(S.correct(picks[c["id"]], c) for c in sub), "accuracy": S.rate(sum(S.correct(picks[c["id"]], c) for c in sub), len(sub)),
            "wrong_ids": [c["id"] for c in sub if not S.correct(picks[c["id"]], c)]}
def main(model="liquid/d1-ultra", base_dir=os.path.join(HERE, "results"), new_dir=os.path.join(HERE, "results_v18")):
    cases = json.load(open(S.find_input("RUNNER_JSON", "library_v2_smart_runner.json")))
    A = {c["case_id"]: c for c in json.load(open(S.find_input("ACCEPTED_JSON", "library_v2_smart_accepted.json")))["cases"]}
    sev = {r["case_id"]: r["severity_if_wrong"] for r in csv.DictReader(open(S.find_input("OUTCOMES_CSV", "library_v2_smart_Outcomes.csv")))}
    extra = {c["id"]: {"categories": A[c["id"][4:]].get("category") or [c["kind"]], "subtle": bool(A[c["id"][4:]].get("subtle_deterioration"))} for c in cases}
    l1 = {c["id"]: L.evaluate_case(A[c["id"][4:]]) for c in cases}
    hospice = {c["id"] for c in cases if c.get("escalation_target") == "hospice_nurse" or c.get("suppression_reason") == "goals_of_care"}
    supp = {c["id"] for c in cases if c.get("trigger_tier") == "SUPPRESSED"}
    b_picks, _ = load_picks(base_dir, model); n_picks, n_rows = load_picks(new_dir, model)
    systems = {}
    def add(name, picks):
        if picks is None: return
        m = S.score_system(cases, picks, sev, extra)
        m["suppressed_cases"] = subset_acc(cases, picks, supp); m["hospice_cases"] = subset_acc(cases, picks, hospice)
        for k in ("by_category", "by_difficulty", "by_subtle", "by_hard_trigger"): m.pop(k, None)
        systems[name] = {"picks": picks, "m": m}
    add("baseline_jev", b_picks)
    if b_picks: add("baseline_labelL1_jev", {c["id"]: S.l1_pick(b_picks.get(c["id"]), c) for c in cases})
    if b_picks: add("baseline_jev_derivedL1_router", {c["id"]: L.route(l1[c["id"]], b_picks.get(c["id"]))[0] for c in cases})
    add("v18_jev", n_picks)
    owner = {}
    if n_picks:
        r = {c["id"]: L.route(l1[c["id"]], n_picks.get(c["id"])) for c in cases}; owner = {k: v[1] for k, v in r.items()}
        add("v18_derivedL1_jev", {k: v[0] for k, v in r.items()})
    label_pages = S.rate(100 * sum(S.norm(c["expected"]) == S.ESC for c in cases), len(cases))
    out = {"model": model, "label_pages_per_100": label_pages, "systems": {k: v["m"] for k, v in systems.items()},
           "layer1_agreement": agreement(cases, A, l1), "router_owner_counts": dict(collections.Counter(owner.values())),
           "v18_cost_usd": round(sum(r.get("cost") or 0 for r in n_rows), 6), "v18_calls": len(n_rows), "v18_calls_without_pick": sum(1 for r in n_rows if not r.get("pick"))}
    if n_rows:
        out["v18_robustness"] = S.robustness(cases, n_rows)
        out["v18_calibration"] = S.calibration(cases, {r["case"]: r for r in n_rows if r["variant"] == "base"})
    os.makedirs(new_dir, exist_ok=True)
    json.dump(out, open(os.path.join(new_dir, "summary_l1.json"), "w"), indent=1)
    with open(os.path.join(new_dir, "per_case_l1.csv"), "w", newline="") as fh:
        w = csv.writer(fh); names = list(systems)
        w.writerow(["case_id", "expected", "acceptable", "severity_if_wrong", "label_tier", "label_reason", "label_rule", "l1_tier", "l1_reason", "l1_rule", "l1_acute", "router_owner"] + [f"{n}_pick" for n in names] + [f"{n}_correct" for n in names])
        for c in cases:
            d = l1[c["id"]]
            w.writerow([c["id"], c["expected"], ";".join(c.get("acceptable") or []), sev.get(c["id"]), c.get("trigger_tier") or "", c.get("suppression_reason") or "", c.get("hard_trigger_rule") or "",
                        d["tier"] or "", d.get("reason") or "", d.get("rule") or "", d.get("acute_presentation"), owner.get(c["id"], "")] +
                       [systems[n]["picks"].get(c["id"]) for n in names] + [S.correct(systems[n]["picks"].get(c["id"]), c) for n in names])
    return out
if __name__ == "__main__":
    o = main()
    print("label pages/100", o["label_pages_per_100"])
    for k, m in o["systems"].items():
        print(f'{k:32s} acc {m["accuracy"]} crit {m["critical_misses"]} {m["critical_miss_ids"]} pages {m["pages_per_100"]} false {m["false_pages_per_100"]} supp {m["suppressed_cases"]["accuracy"]} hospice {m["hospice_cases"]["accuracy"]} pairs {m["pairs_both_correct"]}/{m["pairs_complete"]}')
    a = o["layer1_agreement"]; print("L1 tier", a["tier_match"], "reason", a["tier_and_suppression_reason_match"], "rule", a["rule_match"], "/", a["hard_trigger_cases"], "false", len(a["false_triggers"]), "false paging", a["false_paging_triggers"], "cost", o["v18_cost_usd"], o["v18_calls"])
