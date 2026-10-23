"""holdout_v3 answer key with Wayne's 2026-10-23 review-queue rulings (SYNTHETIC). No API calls.
holdout_v3_accepted (63; 20 of them in the queue) + the 17 queued merge disputes with CLINICIAN_RULING as expected_route = 80.
CLINICIAN_RULING is used where present, the merged label otherwise. Full records for disputed cases come from gen/<batch>.batch.json.
Conditional ruling HW6-011 (provider_task if at baseline, urgent_page if currently more confused) is keyed as provider_task (the case text
does not say the patient is currently more confused than baseline) and marked conditional. Route ids are v1.9+."""
import csv, json, glob, os, sys
HO = os.path.dirname(os.path.abspath(__file__)); GEN = os.environ.get("GEN_DIR", os.path.join(HO, "gen"))
sys.path.insert(0, os.path.join(HO, "..", "casegen")); from grade_merge import canon_case_routes
TICKETS = {"HW7-007": "device_maintenance", "HW2-008": "device_maintenance", "HW2-009": "supply_reference_oximeter_and_baseline", "HW8-011": "ecg_strip_request"}   # Wayne 2026-10-23
CONDITIONAL = {"HW6-011": "provider_task if currently at baseline; urgent_page if currently more confused than baseline"}
def main():
    acc = json.load(open(os.path.join(HO, "holdout_v3_accepted.json")))["cases"]
    q = {r["case_id"]: r for r in csv.DictReader(open(os.path.join(HO, "review_queue.csv")))}
    for r in q.values(): r["CLINICIAN_ROUTE"] = r["CLINICIAN_RULING (route)"].strip()
    assert all(r["CLINICIAN_ROUTE"] in ("silent_log", "nurse_task", "provider_task", "urgent_page") for r in q.values())
    full = {}
    for f in sorted(glob.glob(os.path.join(GEN, "*.batch.json"))):
        for c in json.load(open(f))["cases"]:
            if c.get("case_id") in q: full.setdefault(c["case_id"], canon_case_routes(c))
    def apply(c, r, src):
        c = dict(c); c.update(author_route=c.get("expected_route"), expected_route=r["CLINICIAN_ROUTE"], acceptable_alternates=[], key_source=src, clinician_note=r["CLINICIAN_NOTE"])
        if c["case_id"] in TICKETS: c["expected_device_ticket"] = TICKETS[c["case_id"]]
        if c["case_id"] in CONDITIONAL: c["conditional_ruling"] = CONDITIONAL[c["case_id"]]
        return c
    out = []; acc_ids = set()
    for c in acc:
        acc_ids.add(c["case_id"])
        out.append(apply(c, q[c["case_id"]], "clinician_ruling_accepted_2026-10-23") if c["case_id"] in q else dict(c, key_source="author_label_accepted"))
    for cid, r in q.items():
        if cid not in acc_ids: out.append(apply(full[cid], r, "clinician_ruling_2026-10-23"))
    json.dump({"cases": out, "provenance": {"base": "holdout_v3_accepted.json (63)", "rulings": "review_queue.csv CLINICIAN_RULING (Wayne 2026-10-23)",
               "tickets": TICKETS, "conditional": CONDITIONAL, "n": len(out)}}, open(os.path.join(HO, "holdout_v3_ruled_key.json"), "w"), indent=1)
    return out
if __name__ == "__main__":
    o = main(); print(len(o), "cases", sum(1 for c in o if c["key_source"] != "author_label_accepted"), "ruled")
