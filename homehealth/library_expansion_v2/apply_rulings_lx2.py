"""Apply Wayne's 2026-10-24 rulings on the 12 library_expansion_v2 merge disputes + the two ticket policies (SYNTHETIC). Idempotent; re-run safe.
POLICY 1 (Wayne 2026-10-24): when a clinical route (nurse_task/provider_task/urgent_page) fires, NO device ticket; the evaluating clinician files one.
POLICY 2 (Wayne 2026-10-24): device ticket only for internal device failures (sensor fault, expiry, battery, firmware, clock, sync);
  external human causes (lying on a CGM sensor, compression) go to nursing with no ticket.
Library re-check (v1 + v2 accepted): device_maintenance tickets on a clinical route plainly fall under POLICY 1 and are relabelled (listed in
policy_relabels.json). Other ticket types on clinical routes, and human-cause tickets on silent_log, are LISTED for Wayne (policy_review_for_wayne.json), not changed."""
import csv, json, subprocess, collections, glob, os
NOTE = "Wayne ruling 2026-10-24"
CLIN = ("nurse_task", "provider_task", "urgent_page")
R = {"LX9-007": (None, "POLICY 1: keep clinical route, no ticket (evaluating clinician files one)"),
     "LX9-010": (None, "POLICY 1: keep clinical route, no ticket (evaluating clinician files one)"),
     "LX9-011": (None, "POLICY 1: keep clinical route, no ticket (evaluating clinician files one)"),
     "LX12-009": (None, "POLICY 1: keep clinical route, no ticket (evaluating clinician files one)"),
     "LX12-010": (None, "POLICY 1: keep clinical route, no ticket (evaluating clinician files one)"),
     "LX11-005": ("silent_log", "silent_log, no ticket (single CGM warm-up artifact disproved by fingerstick)"),
     "LX11-006": ("silent_log", "silent_log + device_maintenance ticket (expired CGM sensor drift; internal device fault)"),
     "LX9-006": ("silent_log", "silent_log + device_maintenance ticket (ring clock 5 h ahead; internal device fault)"),
     "LX10-002": ("silent_log", "silent_log + device_maintenance ticket (not a separate oximeter-reference type)"),
     "LX10-004": ("silent_log", "silent_log + device_maintenance ticket (not a separate oximeter-reference type)"),
     "LX12-001": ("silent_log", "silent_log + device_maintenance ticket (not a separate oximeter-reference type)"),
     "LX12-007": ("silent_log", "silent_log + device_maintenance ticket (not a separate oximeter-reference type)")}
TK = {"LX11-005": None}
G = {c["case_id"]: c for f in sorted(glob.glob("gen/LX*.batch.json")) for c in json.load(open(f))["cases"]}
def ruled(cid):
    route, why = R[cid]; route = route or G[cid]["expected_route"]
    tk = None if route in CLIN or cid in TK else "device_maintenance"
    return route, tk, why
rows = list(csv.reader(open("merge_disputes.csv"))); h = rows[0]; ir, inote = h.index("CLINICIAN_RULING (route + ticket)"), h.index("CLINICIAN_NOTE")
for r in rows[1:]:
    route, tk, why = ruled(r[0]); r[ir] = route + (f" + {tk}" if tk else " (no ticket)"); r[inote] = f"{NOTE}: {why}"
csv.writer(open("merge_disputes.csv", "w", newline="")).writerows(rows)
# rebuild from the merge-accepted set (finalize_lx2.py output is kept in merge/<b>/accepted.json; accepted.json here may already hold rulings)
A = json.load(open("library_expansion_v2_accepted.json")); A["cases"] = [c for c in A["cases"] if c["case_id"] not in R]
for cid in R:
    route, tk, why = ruled(cid); c = dict(G[cid]); c.pop("device_ticket", None)
    if c.get("expected_device_ticket") != tk: c["author_device_ticket_original"] = c.get("expected_device_ticket")
    if c["expected_route"] != route: c["author_route_original"] = c["expected_route"]; c["acceptable_alternates"] = []
    c["expected_route"] = route; c["expected_device_ticket"] = tk
    c["src"] = c["src_library"] = "library_expansion_v2"; c["grade"] = {"clinician_ruling": route + (f" + {tk}" if tk else ""), "note": f"{NOTE}: {why}"}
    A["cases"].append(c)
# POLICY relabels / review lists across v1 + v2
V1 = "../library_expansion_v1/library_expansion_v1_accepted.json"; A1 = json.load(open(V1))
relabel, review = [], []
HUMAN = {"LX10-001": "loose replacement strap (fit)", "LX10-011": "too-large cuff on a thin arm", "LX11-002": "bag on the scale platform", "LX11-003": "scale moved onto a rug", "LX2-006": "single cuff reading corrected by a seated repeat (technique?)"}
for lib, AA in (("library_expansion_v1", A1), ("library_expansion_v2", A)):
    for c in AA["cases"]:
        t = c.get("expected_device_ticket"); cid = c["case_id"]
        if cid == "LX11-007" and t:
            c["author_device_ticket_original"] = t; c["expected_device_ticket"] = None; c["policy_relabel"] = f"{NOTE}: POLICY 2 (CGM compression = external human cause -> nursing, no ticket)"
            relabel.append({"case_id": cid, "library": lib, "route": c["expected_route"], "old_ticket": t, "new_ticket": None, "policy": "POLICY 2 (explicit ruling)"}); continue
        if t == "supply_reference_oximeter_and_baseline" and c["expected_route"] == "silent_log":
            c["author_device_ticket_original"] = t; c["expected_device_ticket"] = "device_maintenance"; c["policy_relabel"] = f"{NOTE}: oximeter disagreement on silent_log = device_maintenance ticket (LX10-002/004, LX12-001/007 ruling)"
            relabel.append({"case_id": cid, "library": lib, "route": c["expected_route"], "old_ticket": t, "new_ticket": "device_maintenance", "policy": "ticket-type ruling"}); continue
        if t == "device_maintenance" and c["expected_route"] in CLIN:
            c["author_device_ticket_original"] = t; c["expected_device_ticket"] = None; c["policy_relabel"] = f"{NOTE}: POLICY 1 (clinical route, no device ticket; clinician files one)"
            relabel.append({"case_id": cid, "library": lib, "route": c["expected_route"], "old_ticket": t, "new_ticket": None, "policy": "POLICY 1"})
        elif t and c["expected_route"] in CLIN:
            review.append({"case_id": cid, "library": lib, "route": c["expected_route"], "ticket": t, "question": "POLICY 1: non-maintenance ticket type on a clinical route (is this a clinical order rather than a device ticket?) - left unchanged"})
        elif t and cid in HUMAN:
            review.append({"case_id": cid, "library": lib, "route": c["expected_route"], "ticket": t, "question": f"POLICY 2: cause looks external/human ({HUMAN[cid]}); keep ticket or drop? - left unchanged"})
for AA in (A, A1): AA["cases"].sort(key=lambda c: c["case_id"])
A["provenance"]["clinician_rulings"] = f"{NOTE}: 12 merge_disputes.csv cases added; POLICY 1/2 relabels in policy_relabels.json"
A1["provenance"]["policy_relabels"] = f"{NOTE}: POLICY 1 relabels (clinical route -> no device ticket) listed in ../library_expansion_v2/policy_relabels.json"
json.dump(A, open("library_expansion_v2_accepted.json", "w"), indent=1); json.dump(A1, open(V1, "w"), indent=1)
json.dump(relabel, open("policy_relabels.json", "w"), indent=1); json.dump(review, open("policy_review_for_wayne.json", "w"), indent=1)
print(subprocess.run(["python3", "../casegen/convert_casegen.py", "--source=LIB=library_expansion_v2_accepted.json:library_expansion_v2:v2.3", "--out-prefix=library_expansion_v2_"], capture_output=True, text=True).stdout[-300:])
print(subprocess.run(["python3", "../casegen/convert_casegen.py", "--source=LIB=library_expansion_v1_accepted.json:library_expansion_v1:v2.3", "--out-prefix=library_expansion_v1_"], capture_output=True, text=True, cwd="../library_expansion_v1").stdout[-300:])
S = json.load(open("library_counts.json")); k = A["cases"]
S.update({"accepted_final": len(k), "clinician_added_from_disputes": len(R), "clinician_excluded": [], "review_queue_disputed_open": 0,
  "policy_relabels": [r["case_id"] for r in relabel], "policy_review_for_wayne": [r["case_id"] for r in review],
  "routes": dict(collections.Counter(c["expected_route"] for c in k)), "tickets": dict(collections.Counter(c.get("expected_device_ticket") or "none" for c in k)),
  "tiers": dict(collections.Counter(c.get("trigger_tier") for c in k if c.get("trigger_tier"))),
  "by_batch_accepted": dict(sorted(collections.Counter(c["case_id"].split("-")[0] for c in k).items())),
  "categories": dict(collections.Counter(x for c in k for x in (c.get("category") or [])).most_common()), "difficulty": dict(collections.Counter(c.get("difficulty") for c in k))})
json.dump(S, open("library_counts.json", "w"), indent=1)
print(len(k), S["routes"], S["tickets"], "v1:", len(A1["cases"])); print("relabel", relabel); print("review", review)
