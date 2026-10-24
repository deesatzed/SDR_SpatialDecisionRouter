"""Wayne 2026-10-24 open-item rulings (SYNTHETIC): drop stale ticket labels. Routes unchanged. Edits keys by case ID only (holdout text not read)."""
import json, os
H = os.path.dirname(os.path.abspath(__file__)); NOTE = "Wayne 2026-10-24 open-item ruling"
WHY = {"HX5-002": "motion artifact", "HX5-011": "ECG strip already recorded and cleared as sinus", "LX2-010": "nurse route covers it (POLICY 1)", "LX8-010": "nurse route covers it (POLICY 1)"}
def edit(f, ids, prov_key):
    k = json.load(open(f)); log = []
    for c in k["cases"]:
        if c["case_id"] in ids:
            old = c.pop("expected_device_ticket", None); c.pop("any_device_ticket_ok", None)
            c["ticket_relabel"] = {"from": old, "to": None, "by": NOTE, "why": WHY[c["case_id"]]}; log.append((c["case_id"], c["expected_route"], old))
    assert len(log) == len(ids), (f, log)
    if prov_key:
        k["provenance"].setdefault("ticket_relabels_2026-10-24", {}).update({i: None for i, _, _ in log})
        if "tickets" in k["provenance"]:
            for i, _, _ in log: k["provenance"]["tickets"].pop(i, None)
    json.dump(k, open(f, "w"), indent=1); return log
out = {"holdout_v4": edit(f"{H}/holdout_v4/holdout_v4_ruled_key.json", ["HX5-002", "HX5-011"], True),
       "library_v1": edit(f"{H}/library_expansion_v1/library_expansion_v1_accepted.json", ["LX2-010", "LX8-010"], False)}
print(json.dumps(out, indent=1))
