"""Answer key with Wayne's 2026-10-21 review-queue rulings (SYNTHETIC). No API calls.
holdout_v1_accepted (60, unchanged) + the 34 review-queue cases with CLINICIAN_RULING as expected_route, minus DROP (HO8-006, HO7-013, HO8-001) = 91.
Full case records for queued cases come from gen/<batch>.batch.json (GEN_DIR, default the box pipeline folder). Route ids are v1.9."""
import csv, json, glob, os, sys
HO = os.path.dirname(os.path.abspath(__file__)); GEN = os.environ.get("GEN_DIR", "/workspace/jevfly_smoke/holdout_v1/gen")
sys.path.insert(0, os.path.join(HO, "..", "casegen")); from grade_merge import canon_case_routes
TIER_RULINGS = {"HO7-021": ("ABSOLUTE", None), "HO8-015": ("ABSOLUTE", None), "HO8-025": ("ABSOLUTE", None),
                "HO8-020": ("CONFIRM_FIRST", None), "HO8-019": ("SUPPRESSED", "explained")}   # Wayne 2026-10-21 tier rulings
FIX = {"HO7-021": {"living": "with spouse"}}
def main():
    acc = json.load(open(os.path.join(HO, "holdout_v1_accepted.json")))["cases"]
    q = {r["case_id"]: r for r in csv.DictReader(open(os.path.join(HO, "review_queue.csv")))}
    full = {}
    for f in sorted(glob.glob(os.path.join(GEN, "*.batch.json"))):
        for c in json.load(open(f))["cases"]:
            if c.get("case_id") in q: full.setdefault(c["case_id"], canon_case_routes(c))
    out = [dict(c, key_source="author_label_accepted") for c in acc]; dropped = []
    for cid, r in q.items():
        ru = r["CLINICIAN_RULING (route)"]
        if ru == "DROP": dropped.append(cid); continue
        c = dict(full[cid]); c.update(FIX.get(cid, {}))
        if cid == "HO8-015": c["caregiver_or_nurse_note"] = c["caregiver_or_nurse_note"].replace("that she is hard", "that he is hard")
        c.update(author_route=c.get("expected_route"), expected_route=ru, acceptable_alternates=[], key_source="clinician_ruling_2026-10-21", clinician_note=r["CLINICIAN_NOTE"])
        if cid in TIER_RULINGS:
            t, s = TIER_RULINGS[cid]; c.update(trigger_tier=t, suppression_reason=s, hard_trigger=True)
        out.append(c)
    json.dump({"cases": out, "provenance": {"base": "holdout_v1_accepted.json (60)", "rulings": "review_queue.csv CLINICIAN_RULING (Wayne 2026-10-21)",
               "dropped": sorted(dropped), "n": len(out)}}, open(os.path.join(HO, "holdout_v1_ruled_key.json"), "w"), indent=1)
    return out, dropped
if __name__ == "__main__":
    o, d = main(); print(len(o), "cases; dropped", sorted(d))
