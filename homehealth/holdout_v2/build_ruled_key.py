"""holdout_v2 answer key with Wayne's 2026-10-22 review-queue rulings (SYNTHETIC). No API calls.
holdout_v2_accepted (65; 9 of them re-ruled in the queue) + the 16 queued merge disputes with CLINICIAN_RULING as expected_route = 81.
Full records for disputed cases come from gen/<batch>.batch.json. Route ids are v1.9+."""
import csv, json, glob, os, sys
HO = os.path.dirname(os.path.abspath(__file__)); GEN = os.environ.get("GEN_DIR", os.path.join(HO, "gen"))
sys.path.insert(0, os.path.join(HO, "..", "casegen")); from grade_merge import canon_case_routes
TIER_RULINGS = {"HV3-010": ("ABSOLUTE", None), "HV5-007": ("CONFIRM_FIRST", None),
                "HV2-002": ("SUPPRESSED", "goals_of_care"), "HV6-001": ("SUPPRESSED", "goals_of_care")}   # Wayne 2026-10-22
FIX = {"HV9-006": {"living": "with spouse and adult child"}}   # note quotes an adult child; living said spouse only
def fix_condition_change(c):   # HV4-007: last condition change was starting oxycodone, not an oxygen change
    bs = dict(c.get("baseline_status") or {}); bs["last_condition_change"] = "medication_change"; c["baseline_status"] = bs
def main():
    acc = json.load(open(os.path.join(HO, "holdout_v2_accepted.json")))["cases"]
    q = {r["case_id"]: r for r in csv.DictReader(open(os.path.join(HO, "review_queue.csv")))}
    full = {}
    for f in sorted(glob.glob(os.path.join(GEN, "*.batch.json"))):
        for c in json.load(open(f))["cases"]:
            if c.get("case_id") in q: full.setdefault(c["case_id"], canon_case_routes(c))
    def apply(c, r, src):
        c = dict(c); c.update(FIX.get(c["case_id"], {}))
        if c["case_id"] == "HV4-007": fix_condition_change(c)
        c.update(author_route=c.get("expected_route"), expected_route=r["CLINICIAN_ROUTE"], acceptable_alternates=[], key_source=src, clinician_note=r["CLINICIAN_NOTE"])
        if c["case_id"] in TIER_RULINGS:
            t, s = TIER_RULINGS[c["case_id"]]; c.update(trigger_tier=t, suppression_reason=s, hard_trigger=True)
        return c
    for r in q.values(): r["CLINICIAN_ROUTE"] = r["CLINICIAN_RULING (route)"].strip()
    assert all(r["CLINICIAN_ROUTE"] in ("silent_log", "nurse_task", "provider_task", "urgent_page") for r in q.values())
    out = []; acc_ids = set()
    for c in acc:
        acc_ids.add(c["case_id"])
        if c["case_id"] in q: out.append(apply(c, q[c["case_id"]], "clinician_ruling_accepted_2026-10-22"))
        else: out.append(dict(c, **FIX.get(c["case_id"], {}), key_source="author_label_accepted"))
    for cid, r in q.items():
        if cid not in acc_ids: out.append(apply(full[cid], r, "clinician_ruling_2026-10-22"))
    json.dump({"cases": out, "provenance": {"base": "holdout_v2_accepted.json (65)", "rulings": "review_queue.csv CLINICIAN_RULING (Wayne 2026-10-22)",
               "data_fixes": {"HV9-006": "living -> with spouse and adult child", "HV4-007": "last_condition_change -> medication_change"}, "n": len(out)}},
              open(os.path.join(HO, "holdout_v2_ruled_key.json"), "w"), indent=1)
    return out
if __name__ == "__main__":
    o = main(); print(len(o), "cases")
