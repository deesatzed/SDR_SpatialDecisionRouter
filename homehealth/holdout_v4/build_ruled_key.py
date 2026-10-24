"""holdout_v4 answer key with Wayne's 2026-10-23 review-queue rulings (commit ded1a40) (SYNTHETIC). No API calls.
Pattern: holdout_v3/build_ruled_key.py. holdout_v4_accepted (67; 25 in the queue) + the 9 queued merge disputes = 76.
CLINICIAN_RULING is used where set, the author/merged label otherwise. Full records for disputed cases come from gen/<batch>.batch.json.
Ticket: HX5-005 ruled silent_log + device ticket; the frozen expected_device_ticket (supply_reference_oximeter_and_baseline) is kept, and
any device ticket is reported separately because the ruling did not name a ticket type. Also writes jev_disputes/disputes.json for the Jev run."""
import csv, json, glob, os, sys
HO = os.path.dirname(os.path.abspath(__file__)); GEN = os.path.join(HO, "gen")
sys.path.insert(0, os.path.join(HO, "..", "casegen")); from grade_merge import canon_case_routes
R = ("silent_log", "nurse_task", "provider_task", "urgent_page")
ANY_TICKET_OK = {"HX5-005": "ruling: silent_log + device ticket (type not named)"}
def main():
    acc = json.load(open(os.path.join(HO, "holdout_v4_accepted.json")))["cases"]
    q = {r["case_id"]: r for r in csv.DictReader(open(os.path.join(HO, "review_queue.csv")))}
    for r in q.values(): r["CR"] = r["CLINICIAN_RULING (route)"].strip()
    assert all(r["CR"] in R for r in q.values()), [k for k, r in q.items() if r["CR"] not in R]
    full = {}
    for f in sorted(glob.glob(os.path.join(GEN, "*.batch.json"))):
        if f.endswith(".orig.json"): continue
        for c in json.load(open(f))["cases"]:
            if c.get("case_id") in q: full.setdefault(c["case_id"], canon_case_routes(c))
    def apply(c, r, src):
        c = dict(c); c.update(author_route=c.get("expected_route"), expected_route=r["CR"], acceptable_alternates=[], key_source=src, clinician_note=r["CLINICIAN_NOTE"])
        if c["case_id"] in ANY_TICKET_OK: c["any_device_ticket_ok"] = True
        return c
    out, ids = [], set()
    for c in acc:
        ids.add(c["case_id"])
        out.append(apply(c, q[c["case_id"]], "clinician_ruling_accepted_2026-10-23") if c["case_id"] in q else dict(c, key_source="author_label_accepted"))
    disp = []
    for cid, r in q.items():
        if cid not in ids: d = apply(full[cid], r, "clinician_ruling_merge_dispute_2026-10-23"); out.append(d); disp.append(d)
    changed = [c["case_id"] for c in out if c.get("author_route") and c["author_route"] != c["expected_route"]]
    json.dump({"cases": out, "provenance": {"base": "holdout_v4_accepted.json (67)", "rulings": "review_queue.csv CLINICIAN_RULING (Wayne 2026-10-23, commit ded1a40)",
               "any_ticket_ok": ANY_TICKET_OK, "label_changes_vs_author": changed, "n": len(out)}}, open(os.path.join(HO, "holdout_v4_ruled_key.json"), "w"), indent=1)
    os.makedirs(os.path.join(HO, "jev_disputes"), exist_ok=True)
    json.dump({"cases": disp}, open(os.path.join(HO, "jev_disputes", "disputes.json"), "w"), indent=1)
    return out, changed, disp
if __name__ == "__main__":
    o, ch, d = main(); print(len(o), "cases", sum(1 for c in o if c["key_source"] != "author_label_accepted"), "ruled; disputes", len(d), "; label changes", ch)
