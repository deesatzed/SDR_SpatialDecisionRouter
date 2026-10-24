"""Apply Wayne's 2026-10-24 rulings on the 5 LX1 merge disputes (SYNTHETIC). Idempotent."""
import csv, json, subprocess, collections
NOTE = "Wayne ruling 2026-10-24"
R = {"LX1-002": ("DROP", None, "drop from library (expected drug effect after empagliflozin start; baseline reset, not drift)"),
     "LX1-003": ("silent_log", "device_maintenance", "silent_log + device ticket (keep)"),
     "LX1-004": ("silent_log", "device_maintenance", "silent_log + device ticket (keep; overrides author provider_task)"),
     "LX1-007": ("provider_task", None, "provider_task (keep)"),
     "LX1-011": ("urgent_page", None, "urgent_page (keep; HT_VS_DANGER ABSOLUTE)")}
rows = list(csv.reader(open("merge_disputes.csv"))); h = rows[0]; ir, inote = h.index("CLINICIAN_RULING (route)"), h.index("CLINICIAN_NOTE")
for r in rows[1:]:
    route, tk, why = R[r[0]]; r[ir] = route + (" + device_ticket" if tk else ""); r[inote] = f"{NOTE}: {why}"
csv.writer(open("merge_disputes.csv", "w", newline="")).writerows(rows)
G = {c["case_id"]: c for c in json.load(open("gen/LX1.batch.json"))["cases"]}
A = json.load(open("library_expansion_v1_accepted.json")); A["cases"] = [c for c in A["cases"] if not c["case_id"].startswith("LX1-")]
for cid, (route, tk, why) in R.items():
    if route == "DROP": continue
    c = dict(G[cid]); c.pop("device_ticket", None)
    if c["expected_route"] != route: c["author_route_original"] = c["expected_route"]; c["acceptable_alternates"] = []
    c["expected_route"] = route; c["expected_device_ticket"] = tk
    c["src"] = c["src_library"] = "library_expansion_v1"; c["grade"] = {"clinician_ruling": route, "note": f"{NOTE}: {why}", "batch_id": ["LX1+LX2"]}
    A["cases"].append(c)
A["cases"].sort(key=lambda c: c["case_id"])
A["provenance"]["clinician_rulings"] = f"{NOTE}: LX1-003/004/007/011 added from merge_disputes.csv; LX1-002 excluded (see excluded_by_ruling.json)"
json.dump(A, open("library_expansion_v1_accepted.json", "w"), indent=1)
json.dump([{"case_id": "LX1-002", "ruling": "DROP", "note": f"{NOTE}: {R['LX1-002'][2]}"}], open("excluded_by_ruling.json", "w"), indent=1)
print(subprocess.run(["python3", "../casegen/convert_casegen.py", "--source=LIB=library_expansion_v1_accepted.json:library_expansion_v1:v2.3", "--out-prefix=library_expansion_v1_"], capture_output=True, text=True).stdout)
S = json.load(open("library_counts.json")); k = A["cases"]
S.update({"accepted_final": len(k), "clinician_added_from_disputes": 4, "clinician_excluded": ["LX1-002"], "review_queue_disputed_open": 0,
  "routes": dict(collections.Counter(c["expected_route"] for c in k)), "tiers": dict(collections.Counter(c.get("trigger_tier") for c in k if c.get("trigger_tier"))),
  "by_batch_accepted": dict(sorted(collections.Counter(c["case_id"].split("-")[0] for c in k).items())),
  "complete_pairs": sum(1 for v in collections.Counter(c.get("pair_id") for c in k if c.get("pair_id")).values() if v == 2),
  "categories": dict(collections.Counter(x for c in k for x in (c.get("category") or [])).most_common()), "difficulty": dict(collections.Counter(c.get("difficulty") for c in k))})
json.dump(S, open("library_counts.json", "w"), indent=1); print(len(k), S["routes"])
