"""Bring holdout keys + library human-cause cases in line with Wayne's 2026-10-24 device-ticket policies (SYNTHETIC). Routes unchanged."""
import json, os
H = os.path.dirname(os.path.abspath(__file__)); NOTE = "Wayne 2026-10-24 device-ticket policy relabel"
def edit(f, changes, prov_key):
    k = json.load(open(f)); log = []
    for c in k["cases"]:
        if c["case_id"] in changes:
            old = c.get("expected_device_ticket"); new = changes[c["case_id"]]
            if new is None: c.pop("expected_device_ticket", None)
            else: c["expected_device_ticket"] = new
            c.pop("any_device_ticket_ok", None) if new is None else None
            c["ticket_relabel"] = {"from": old, "to": new, "by": NOTE}; log.append((c["case_id"], c["expected_route"], old, new))
    assert len(log) == len(changes), (f, log)
    if prov_key: k["provenance"].setdefault("ticket_relabels_2026-10-24", {i: n for i, _, _, n in log})
    if prov_key and "tickets" in k["provenance"]:
        for i, _, _, n in log:
            if n is None: k["provenance"]["tickets"].pop(i, None)
            else: k["provenance"]["tickets"][i] = n
    json.dump(k, open(f, "w"), indent=1); return log
out = {}
out["holdout_v4"] = edit(f"{H}/holdout_v4/holdout_v4_ruled_key.json", {"HX4-010": None, "HX5-004": None}, True)
out["holdout_v3"] = edit(f"{H}/holdout_v3/holdout_v3_ruled_key.json", {"HW2-008": None, "HW2-009": "device_maintenance"}, True)
out["library_v1"] = edit(f"{H}/library_expansion_v1/library_expansion_v1_accepted.json", {"LX2-006": None}, False)
out["library_v2"] = edit(f"{H}/library_expansion_v2/library_expansion_v2_accepted.json", {"LX10-001": None, "LX10-011": None, "LX11-002": None, "LX11-003": None}, False)
print(json.dumps(out, indent=1))
