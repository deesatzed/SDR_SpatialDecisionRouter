"""Merge library_expansion_v1 (local-only dedupe also vs holdout_v3/v4; their text never enters any prompt). grader outputs, dedupe (text AND story level) vs the 270-case library AND every holdout_v1, holdout_v2 and holdout_v3 generated case, write accepted/review_queue/fix_list + SDR runner (SYNTHETIC)."""
import csv, glob, json, os, re, subprocess, collections
GM = "../casegen/prompts_v2/grade_merge.py"
LIB = json.load(open("../library_v2/smart_triggers/library_v2_smart_accepted.json"))["cases"]
LIB += [c for f in sorted(glob.glob("../holdout_v1/gen/*.batch.json")) + sorted(glob.glob("../holdout_v2/gen/*.batch.json")) + sorted(glob.glob("../holdout_v3/gen/*.batch.json")) + sorted(glob.glob("../holdout_v4/gen/*.batch.json")) for c in json.load(open(f))["cases"]]
groups = {}
for g in glob.glob("grade/*.grader.json"):
    n = os.path.basename(g)[:-len(".grader.json")]
    if n.startswith("CONTROL"): continue
    key = re.sub(r"-p\d$", "", n); groups.setdefault(key, []).append(g)
acc, rq, fx, merged_ids = [], [], [], []
for key, gs in sorted(groups.items()):
    args = ["python3", GM, "--smart", "--src", "library_expansion_v1", "--out", f"merge/{key}"]
    for b in key.split("+"): args += ["--batch", f"gen/{b}.batch.json"]
    for g in sorted(gs): args += ["--grader", g]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode: print("MERGE FAIL", key, r.stderr[-500:]); continue
    acc += json.load(open(f"merge/{key}/accepted.json"))["cases"]
    rq += list(csv.DictReader(open(f"merge/{key}/review_queue.csv"))); fx += list(csv.DictReader(open(f"merge/{key}/fix_list.csv")))
gen = [c for f in sorted(glob.glob("gen/LX*.batch.json")) for c in json.load(open(f))["cases"]]
# near-duplicate check vs the library (stricter than library_v2: any route/category)
STOP = {"the","a","and","of","with","in","on","no","to","for","after","from","at","is","but","plus","by","day","her","his","she","he"}
def toks(s): return set(re.findall(r"[a-z0-9]+", (s or "").lower())) - STOP
def jac(a, b): return len(a & b) / len(a | b) if a and b else 0.0
LT = [(c["case_id"], toks(c.get("decisive_feature")), toks((c.get("trend_last_7d") or "") + " " + (c.get("caregiver_or_nurse_note") or ""))) for c in LIB]
def nearest(c):
    d, t = toks(c.get("decisive_feature")), toks((c.get("trend_last_7d") or "") + " " + (c.get("caregiver_or_nurse_note") or ""))
    return max(((cid, round(jac(d, ld), 3), round(jac(t, lt), 3)) for cid, ld, lt in LT), key=lambda x: max(x[1], x[2]))
# story-level check (Wayne 2026-10-23: catch repeated narratives such as 'sack of potatoes', not only text overlap):
# shared RARE word 3-grams (document frequency <= 3 across all prior cases, no digits) between the case narrative and any prior case,
# (at least 2 content words each) plus a list of known repeated idioms. >= 3 shared rare 3-grams in the caregiver/nurse narrative with the same first category, or any known idiom, = story duplicate.
def words(c): return re.findall(r"[a-z']+", (c.get("caregiver_or_nurse_note") or "").lower())   # the narrative (who said what happened)
def grams(c): w = words(c); return {" ".join(w[i:i+3]) for i in range(len(w) - 2)}
PG = [(c["case_id"], (c.get("category") or ["?"])[0], grams(c)) for c in LIB]
DF = collections.Counter(g for _, _, gs in PG for g in gs)
IDIOMS = ["sack of potatoes", "eyes rolled back", "came to on the floor", "elephant sitting", "calling the kettle", "missing the button", "pulling down at one corner", "tightness up into the jaw", "knocked the watch on the sink", "indigestion-like ache"]
def story_match(c, pool):
    g = {x for x in grams(c) if DF.get(x, 0) <= 3 and sum(1 for t in x.split() if t not in STOP and len(t) > 3) >= 2}
    cat = (c.get("category") or ["?"])[0]; best = None
    for pid, pcat, pg, *pp in pool:
        if pp and pp[0] and pp[0] == c.get("pair_id"): continue   # designed near-miss pair partners share a story on purpose
        sh = g & pg
        if len(sh) >= 3 and pcat == cat and (best is None or len(sh) > best[1]): best = (pid, len(sh), sorted(sh)[:4])
    txt = " ".join(re.findall(r"[a-z'-]+", ((c.get("trend_last_7d") or "") + " " + (c.get("caregiver_or_nurse_note") or "")).lower())); hit = [i for i in IDIOMS if i in txt]
    return best, hit
dedupe, keep, seen = [], [], []
for c in acc:
    cid, jd, jt = nearest(c)
    sm, idi = story_match(c, PG + seen)
    if jd >= 0.5 or jt >= 0.6 or sm or idi:
        dedupe.append({"case_id": c["case_id"], "library_match": cid, "jaccard_decisive": jd, "jaccard_text": jt, "story_match": sm, "idioms": idi}); continue
    seen.append((c["case_id"], (c.get("category") or ["?"])[0], grams(c), c.get("pair_id")))
    c["src_library"] = "library_expansion_v1"; c["nearest_library"] = {"case_id": cid, "jaccard_decisive": jd, "jaccard_text": jt}; keep.append(c)
ids = [c["case_id"] for c in keep]; assert len(ids) == len(set(ids))
assert not set(ids) & {c["case_id"] for c in LIB}
# pairs: drop pair_id if its partner did not survive (keeps "complete pairs" honest)
pc = collections.Counter(c.get("pair_id") for c in keep if c.get("pair_id"))
for c in keep:
    if c.get("pair_id") and pc[c["pair_id"]] < 2: c["pair_partner_excluded"] = c["pair_id"]
json.dump({"cases": keep, "provenance": {"src_library": "library_expansion_v1", "synthetic": True, "prompts": "GEN_LLM2_v2.3 + hard-slice / GRADER_LLM3_v1.3 + ADDENDUM_v1103 + ADDENDUM_v1112 (SMART_TRIGGERS v1.11.2, params 0.11.2-placeholder, seed 20261024); generators haiku-5.5 + deepseek-v4-pro",
           "dedupe": "vs library_v2_smart (270) + holdout_v1/v2/v3/v4 (all generated) and earlier library_expansion_v1 accepted cases: decisive_feature Jaccard >= 0.5 or trend+note Jaccard >= 0.6, or story match (>= 3 shared rare 3-grams in the narrative note, same category) or a known repeated idiom"}}, open("library_expansion_v1_accepted.json", "w"), indent=1)
json.dump(dedupe, open("dedupe_removed.json", "w"), indent=1)
# review queue for Wayne: one case per row, background first
G = {c["case_id"]: c for c in gen}
cols = ["case_id", "age_band", "sex", "living", "patient_goals", "pmh", "meds", "recent_med_changes", "devices", "baseline_30d", "baseline_status", "trend_last_7d", "caregiver_or_nurse_note", "data_quality"]
with open("merge_disputes.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(cols + ["author_route", "author_alternates", "author_trigger_rule", "author_tier", "author_suppression_reason", "grader_route", "grader_tier", "grader_action", "queue_reasons", "grader_reasoning", "CLINICIAN_RULING (route)", "CLINICIAN_NOTE"])
    for r in rq:
        c = G.get(r["case_id"], {})
        w.writerow([json.dumps(c.get(k), ensure_ascii=False) if isinstance(c.get(k), (dict, list)) else (c.get(k) if c.get(k) is not None else "") for k in cols]
                   + [r.get("expected_route"), r.get("acceptable_alternates"), r.get("hard_trigger_rule_case"), r.get("trigger_tier_case"), r.get("suppression_reason"),
                      r.get("grader_route"), r.get("grader_trigger_tier"), r.get("grader_action"), r.get("queue_reasons"), r.get("grader_reasoning"), "", ""])
with open("fix_list.csv", "w", newline="") as fh:
    if fx:
        w = csv.DictWriter(fh, list(fx[0].keys())); w.writeheader(); w.writerows(fx)
print(subprocess.run(["python3", os.environ.get("CONVERT", "../casegen/convert_casegen.py"), "--source=LIB=library_expansion_v1_accepted.json:library_expansion_v1:v2.3", "--out-prefix=library_expansion_v1_"], capture_output=True, text=True).stdout)
S = {"generated": len(gen), "graded": sum(len(json.load(open(f"gen/{b}.batch.json"))["cases"]) for k in groups for b in k.split("+")), "accepted_by_merge": len(acc), "dedupe_removed": len(dedupe), "accepted_final": len(keep),
     "review_queue_disputed": len(rq), "fix_list_excluded": len(fx), "queue_reasons": dict(collections.Counter(x for r in rq for x in (r.get("queue_reasons") or "").split("|") if x)),
     "routes": dict(collections.Counter(c["expected_route"] for c in keep)), "tiers": dict(collections.Counter(c.get("trigger_tier") for c in keep if c.get("trigger_tier"))),
     "by_batch_accepted": dict(collections.Counter(c["case_id"].split("-")[0] for c in keep)), "by_batch_generated": dict(collections.Counter(c["case_id"].split("-")[0] for c in gen)),
     "complete_pairs": sum(1 for v in pc.values() if v == 2), "hospice_goals": sum(1 for c in keep if c.get("suppression_reason") == "goals_of_care" or c.get("escalation_target") == "hospice_nurse"),
     "learning_period": sum(1 for c in keep if (c.get("baseline_status") or {}).get("phase") == "learning"),
     "categories": dict(collections.Counter(x for c in keep for x in (c.get("category") or [])).most_common()), "difficulty": dict(collections.Counter(c.get("difficulty") for c in keep))}
json.dump(S, open("library_counts.json", "w"), indent=1); print(json.dumps(S, indent=1))
