"""Score Fly (Layer 3) alone and the full stack Layer 1 + Jev (stored v1.8 d1-ultra picks, no new calls) + Fly (SYNTHETIC).

Fly's input flags come from fly_flags.derive_flags (facts + Layer 1 only). Labels are used only here, for scoring and for
tuning thresholds on the TRAIN split. Held-out split: whole source batches (pairs never straddle batches), chosen by
sha256(batch) order until >= 30% of cases. Combination rules never lower a route; Fly can only raise or flag.
"""
from __future__ import annotations
import csv, hashlib, json, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
JEV = os.environ.get("JEV_BASELINE_DIR", os.path.join(HERE, "..", "jev_baseline")); sys.path.insert(0, JEV)
import score_jev as S, layer1_adapter as L  # noqa: E402

ROUTES = S.ROUTES; RK = S.RANK; ESC = S.ESC
HOLDOUT_FRAC = 0.30

def split_batches(batch_of):
    """batch_of: case_id -> batch. Returns set of held-out batches (deterministic, label-free)."""
    n = collections.Counter(batch_of.values()); total = sum(n.values()); held, k = set(), 0
    for b in sorted(n, key=lambda b: hashlib.sha256(b.encode()).hexdigest()):
        if k >= HOLDOUT_FRAC * total: break
        held.add(b); k += n[b]
    return held

def fly_band(peak, cuts):
    """Fly alone as a router: cuts = (t_nurse, t_wake, t_escalate), ascending."""
    return ROUTES[sum(peak > t for t in cuts)]

def combine(rule, base_route, owner, fly_high):
    """Returns (route, hitm_flag). base_route/owner from layer1_adapter.route. Never lowers a route."""
    jev_owned = owner in ("jev", "jev_capped")
    if rule == "l1_jev": return base_route, False
    if rule == "flag_only":   # HITM sees a disagreement; route unchanged
        return base_route, (fly_high and RK[base_route] <= RK["nurse_task"] and jev_owned) or (not fly_high and base_route == ESC and owner == "jev")
    if rule == "confirm_first":   # Fly high on a Jev-owned non-escalate -> confirm-first step (offline: paged, like L1 CONFIRM_FIRST)
        if fly_high and jev_owned and base_route != ESC: return ESC, True
        return base_route, False
    if rule == "bump_wake":    # Fly high on Jev-owned silent/nurse -> wake_specialist
        if fly_high and jev_owned and RK[base_route] < RK["wake_specialist"]: return "wake_specialist", True
        return base_route, False
    raise ValueError(rule)
RULES = ("l1_jev", "flag_only", "confirm_first", "bump_wake")

def load(readouts_path):
    cases = json.load(open(S.find_input("RUNNER_JSON", "library_v2_smart_runner.json")))
    A = {c["case_id"]: c for c in json.load(open(S.find_input("ACCEPTED_JSON", "library_v2_smart_accepted.json")))["cases"]}
    sev = {r["case_id"]: r["severity_if_wrong"] for r in csv.DictReader(open(S.find_input("OUTCOMES_CSV", "library_v2_smart_Outcomes.csv")))}
    extra = {c["id"]: {"categories": A[c["id"][4:]].get("category") or [c["kind"]], "subtle": bool(A[c["id"][4:]].get("subtle_deterioration"))} for c in cases}
    R = json.load(open(readouts_path))
    return cases, A, sev, extra, R

def load_picks(path):
    last = {}
    for l in open(path):
        if l.strip(): r = json.loads(l); last[(r["case"], r["variant"])] = r
    return {k[0]: v.get("pick") for k, v in last.items() if k[1] == "base"}

def metrics(cases, picks, sev, extra, supp, hospice):
    m = S.score_system(cases, picks, sev, extra)
    for k in ("by_category", "by_difficulty", "by_subtle", "by_hard_trigger", "by_tier", "engine_tier_agreement", "engine_tier_disagree_ids"): m.pop(k, None)
    def sub(ids):
        s = [c for c in cases if c["id"] in ids and picks.get(c["id"])]
        ok = sum(S.correct(picks[c["id"]], c) for c in s)
        return {"n": len(s), "correct": ok, "accuracy": S.rate(ok, len(s)), "wrong_ids": [c["id"] for c in s if not S.correct(picks[c["id"]], c)]}
    m["suppressed_cases"] = sub(supp); m["hospice_cases"] = sub(hospice)
    return m

def objective(m):   # lexicographic: weighted critical misses, then false pages, then accuracy
    return (m["critical_miss_weighted"], m["false_pages_per_100"] or 0, -(m["accuracy"] or 0))

def main(readouts=os.path.join(HERE, "results", "fly_readouts.json"), picks_path=None, out_dir=os.path.join(HERE, "results")):
    picks_path = picks_path or os.environ.get("JEV_PICKS") or os.path.join(JEV, "results_v18", "parsed", "liquid_d1-ultra.jsonl")
    cases, A, sev, extra, R = load(readouts)
    jev = load_picks(picks_path)
    l1 = {c["id"]: L.evaluate_case(A[c["id"][4:]]) for c in cases}
    base = {c["id"]: L.route(l1[c["id"]], jev.get(c["id"])) for c in cases}
    supp = {c["id"] for c in cases if c.get("trigger_tier") == "SUPPRESSED"}
    hospice = {c["id"] for c in cases if c.get("escalation_target") == "hospice_nurse" or c.get("suppression_reason") == "goals_of_care"}
    batch = {c["id"]: A[c["id"][4:]].get("src_batch") or c["id"][4:].split("-")[0] for c in cases}
    held_b = split_batches(batch)
    split = {"train": [c for c in cases if batch[c["id"]] not in held_b], "heldout": [c for c in cases if batch[c["id"]] in held_b], "all": cases}
    leaks = [str(x) for x in R["leaks"]]
    peak = {lk: {cid: max(R["cases"][cid[4:]]["readouts"][lk]) for cid in (c["id"] for c in cases)} for lk in leaks}
    M = lambda part, picks: metrics(split[part], picks, sev, extra, supp, hospice)
    out = {"label_pages_per_100": S.rate(100 * sum(S.norm(c["expected"]) == ESC for c in cases), len(cases)),
           "split": {"heldout_batches": sorted(held_b), **{k: len(v) for k, v in split.items()}},
           "jev_picks": os.path.basename(picks_path), "new_paid_calls": 0}
    # --- Fly alone, a priori threshold (frozen smoke threshold 0.2 at leak 0.8): check -> escalate_human, else silent_log
    fixed = {c["id"]: (ESC if peak["0.8"][c["id"]] > 0.2 else "silent_log") for c in cases}
    out["fly_alone_binary_frozen_t0.2_leak0.8"] = {p: M(p, fixed) for p in split}
    # --- Fly alone, banded router: tune (leak, cuts) on TRAIN
    best = None
    for lk in leaks:
        vals = sorted(set(peak[lk].values())); mids = [0.0] + [(a + b) / 2 for a, b in zip(vals, vals[1:])]
        for i in range(len(mids)):
            for j in range(i, len(mids)):
                for k in range(j, len(mids)):
                    cuts = (mids[i], mids[j], mids[k]); pk = {c["id"]: fly_band(peak[lk][c["id"]], cuts) for c in split["train"]}
                    m = S.score_system(split["train"], pk, sev, extra); key = (m["critical_miss_weighted"], -(m["accuracy"] or 0), m["false_pages_per_100"])
                    if best is None or key < best[0]: best = (key, lk, cuts)
    _, lk, cuts = best; band = {c["id"]: fly_band(peak[lk][c["id"]], cuts) for c in cases}
    out["fly_alone_banded_tuned"] = {"leak": float(lk), "cuts": [round(x, 4) for x in cuts], **{p: M(p, band) for p in split}}
    # --- full stack: L1 + Jev (+ Fly rule); tune Fly threshold per rule on TRAIN
    stack, tuned, flags_all = {}, {}, {}
    for rule in RULES:
        bestr = None
        for lk in leaks:
            for t in sorted(set(peak[lk].values())) + [-1.0]:
                rp = {c["id"]: combine(rule, *base[c["id"]], peak[lk][c["id"]] > t)[0] for c in split["train"]}
                m = S.score_system(split["train"], rp, sev, extra)
                nflag = sum(combine(rule, *base[c["id"]], peak[lk][c["id"]] > t)[1] for c in split["train"])
                if rule == "flag_only":   # routes unchanged: tune for flags that land on stack errors (Youden on train)
                    err = [c for c in split["train"] if not S.correct(base[c["id"]][0], c)]; okc = [c for c in split["train"] if S.correct(base[c["id"]][0], c)]
                    fl = lambda cs: sum(combine(rule, *base[c["id"]], peak[lk][c["id"]] > t)[1] for c in cs)
                    key = (-(fl(err) / max(len(err), 1) - fl(okc) / max(len(okc), 1)), nflag)
                else: key = objective(m) + (nflag,)
                if bestr is None or key < bestr[0]: bestr = (key, lk, t)
                if rule == "l1_jev": break
            if rule == "l1_jev": break
        _, lk, t = bestr; tuned[rule] = {"leak": float(lk), "threshold": t}
        res = {c["id"]: combine(rule, *base[c["id"]], peak[lk][c["id"]] > t) for c in cases}
        picks = {k: v[0] for k, v in res.items()}; fl = {k for k, v in res.items() if v[1]}; flags_all[rule] = (picks, fl, lk, t)
        stack[rule] = {"tuned_on_train": tuned[rule]}
        for p in split:
            ids = {c["id"] for c in split[p]}; m = M(p, picks); f = fl & ids
            m["hitm_flags"] = len(f); m["hitm_flags_per_100"] = S.rate(100 * len(f), len(ids))
            m["hitm_flags_on_base_errors"] = sum(not S.correct(base[i][0], c) for c in split[p] for i in [c["id"]] if i in f)
            stack[rule][p] = m
    out["stack"] = stack
    # --- the same rules at the a-priori frozen smoke threshold (0.2, leak 0.8): no tuning at all
    fz = {}
    for rule in RULES[1:]:
        res = {c["id"]: combine(rule, *base[c["id"]], peak["0.8"][c["id"]] > 0.2) for c in cases}
        picks = {k: v[0] for k, v in res.items()}; fl = {k for k, v in res.items() if v[1]}; fz[rule] = {}
        for p in split:
            ids = {c["id"] for c in split[p]}; m = M(p, picks); f = fl & ids
            m["hitm_flags"] = len(f); m["hitm_flags_per_100"] = S.rate(100 * len(f), len(ids))
            m["hitm_flags_on_base_errors"] = sum(1 for c in split[p] if c["id"] in f and not S.correct(base[c["id"]][0], c))
            fz[rule][p] = m
    out["stack_frozen_t0.2_leak0.8"] = fz
    # --- disagreement (what the HITM would see), Fly at the frozen a-priori threshold 0.2 / leak 0.8 and at the flag_only tuned threshold
    def disagree(lk, t):
        rows = []
        for c in cases:
            r, ow = base[c["id"]]; hi = peak[lk][c["id"]] > t
            if hi != (r == ESC): rows.append((c["id"], r, ow, hi, S.correct(r, c)))
        return {"leak": float(lk), "threshold": t, "n": len(rows), "per_100": S.rate(100 * len(rows), len(cases)),
                "fly_high_stack_not_escalate": sum(1 for x in rows if x[3]), "fly_low_stack_escalate": sum(1 for x in rows if not x[3]),
                "stack_wrong_among_disagreements": sum(1 for x in rows if not x[4]),
                "stack_wrong_total": sum(not S.correct(base[c["id"]][0], c) for c in cases),
                "by_owner": dict(collections.Counter(x[2] for x in rows))}
    out["disagreement_frozen_t0.2_leak0.8"] = disagree("0.8", 0.2)
    out["disagreement_flag_only_tuned"] = disagree(str(tuned["flag_only"]["leak"]), tuned["flag_only"]["threshold"])
    os.makedirs(out_dir, exist_ok=True)
    json.dump(out, open(os.path.join(out_dir, "summary.json"), "w"), indent=1)
    with open(os.path.join(out_dir, "per_case.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case_id", "split", "expected", "acceptable", "severity_if_wrong", "l1_tier", "l1_reason", "jev_pick", "l1_jev_route", "owner",
                    "fly_latent_days", "fly_why_day0", "fly_peak_leak0.8", "fly_alone_banded"] + [f"{r}_route" for r in RULES[1:]] + [f"{r}_hitm_flag" for r in RULES[1:]])
        for c in cases:
            i = c["id"]; d = R["cases"][i[4:]]
            w.writerow([i, "heldout" if batch[i] in held_b else "train", c["expected"], ";".join(c.get("acceptable") or []), sev.get(i),
                        l1[i].get("tier") or "", l1[i].get("reason") or "", jev.get(i), base[i][0], base[i][1],
                        sum(x["latent"] for x in d["days"]), "|".join(d["days"][-1]["why"]), round(peak["0.8"][i], 4), band[i]]
                       + [flags_all[r][0][i] for r in RULES[1:]] + [int(i in flags_all[r][1]) for r in RULES[1:]])
    return out

if __name__ == "__main__":
    o = main(); print(json.dumps({k: o[k] for k in ("split", "disagreement_frozen_t0.2_leak0.8", "disagreement_flag_only_tuned")}, indent=1))
    for name, blk in [("fly_binary_frozen", o["fly_alone_binary_frozen_t0.2_leak0.8"]), ("fly_banded", o["fly_alone_banded_tuned"])] + [(r, o["stack"][r]) for r in RULES]:
        for p in ("all", "train", "heldout"):
            m = blk[p]; print(f'{name:18s} {p:8s} acc={m["accuracy"]} crit={m["critical_misses"]} {m["critical_miss_ids"]} pages={m["pages_per_100"]} fp={m["false_pages_per_100"]} supp={m["suppressed_cases"]["accuracy"]} hosp={m["hospice_cases"]["correct"]}/{m["hospice_cases"]["n"]} pairs={m["pairs_both_correct"]}/{m["pairs_complete"]} flags={m.get("hitm_flags")}')
    for r, blk in o["stack_frozen_t0.2_leak0.8"].items():
        for p in ("all", "heldout"):
            m = blk[p]; print(f'FROZEN {r:14s} {p:8s} acc={m["accuracy"]} crit={m["critical_misses"]} pages={m["pages_per_100"]} fp={m["false_pages_per_100"]} {m["over_escalation_ids"]} flags={m["hitm_flags"]} on_err={m["hitm_flags_on_base_errors"]} pairs={m["pairs_both_correct"]}')
    for r in RULES[1:]:
        for p in ("all", "heldout"): print("TUNED", r, p, "flags", o["stack"][r][p]["hitm_flags"], "on_err", o["stack"][r][p]["hitm_flags_on_base_errors"])
    print({k: (o[k] if k != "stack" else {r: o["stack"][r]["tuned_on_train"] for r in RULES}) for k in ("stack",)}, o["fly_alone_banded_tuned"]["cuts"], o["fly_alone_banded_tuned"]["leak"])
